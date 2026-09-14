"""
execution/stop_loss_manager.py — 止损管理（V7.1 Phase 3）

双层保底策略（v4.2 波动率分档）：
  第一层（硬件）— Alpaca 初始止损单（波动率分档 7-10%）
  第二层（软件）— 脚本跟踪最高价，跌破动态止损线自动卖出

波动率分档:
  <20% → 7% 止损 | 20-35% → 8% | 35-50% → 9% | >50% → 10%

提取自 ~/.hermes/scripts/us_trader.py 的以下函数：
  - update_trail_stops (lines 394-474)
  - stop_coverage_audit (extracted from stops_mode lines 1590-1614)
  - detect_ghost_stops (extracted from stops_mode lines 1622-1633)
  - update_stop_blacklist (lines 1496-1534)
"""

import json
import time
from datetime import datetime, timezone, timedelta

# ─── eagle_eye 内部导入 ───
from eagle_eye.core.logger import get_logger
from eagle_eye.core.config import cfg

# ─── order_manager 导入（所有 Alpaca API 调用必经此模块）───
from eagle_eye.execution.order_manager import (
    get_open_stop_orders,
    get_open_buy_orders,
    place_market_order,
    place_stop_order,
    cancel_order,
    api_get,
)

# ─── position_manager 导入（状态管理）───
from eagle_eye.execution.position_manager import (
    get_highest,
    set_highest,
    get_trail_stop,
    __get_volatility,
)

from eagle_eye.strategy.indicator_engine import get_volatility_stop_pct

logger = get_logger('stop_loss_manager')

# ─── 可注入回调 ───
# 用于替代买入记录（log_sell_for_replacement），
# 由 trade_executor.py 或其他模块通过 set_replacement_logger() 设置。
_replacement_logger = None


def set_replacement_logger(fn):
    """
    设置替代买入日志回调函数。

    fn 签名: fn(symbol, reason, qty, price) -> None
    其中 reason 为 'stop_loss' / 'trail_stop' / 'take_profit' / 'manual_sell'

    这个回调将在每次止损/止盈卖出后被调用，用于 P14/P15 替代买入配对。
    """
    global _replacement_logger
    _replacement_logger = fn


def _log_sell_for_replacement(symbol, reason, qty, price):
    """内部封装：调用注入的替代买入日志回调（如果已设置）"""
    if _replacement_logger:
        try:
            _replacement_logger(symbol, reason, qty, price)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════
# 1. update_trail_stops — 追踪止损管理（双层保底）
# ═══════════════════════════════════════════════════════════════════════

def update_trail_stops(holdings, state, existing_stops, vol_map=None, sold_this_cycle=None):
    """
    双层保底策略（v4.2 波动率分档）：
      第一层（硬件）— Alpaca 初始止损单（波动率分档 7-10%），永不动它
      第二层（软件）— 脚本跟踪最高价，跌破动态止损线自动卖出

    波动率分档:
      <20% → 7% 止损 | 20-35% → 8% | 35-50% → 9% | >50% → 10%

    参数:
        holdings: 持仓列表 [{symbol, qty, avg, current, ...}]
        state: 风控状态 dict
        existing_stops: 已挂止损单 {symbol: {id, stop_price, qty, submitted}}
        vol_map: {symbol: vol_20d} 可选，来自 analyze() 结果，复用已有数据避免重复 API 调用

    返回:
        list of messages (str)
    """
    if sold_this_cycle is None: sold_this_cycle = {}
    msgs = []
    sell_actions = []

    for h in holdings:
        sym = h['symbol']
        qty = h['qty'] - sold_this_cycle.get(sym, 0)
        if qty <= 0:
            continue
        cost = h['avg']
        current = h['current']

        # 优先从 vol_map 取波动率（analyze() 已算过），否则实时获取
        vol_20d = vol_map.get(sym) if vol_map else None
        if vol_20d is None:
            vol_20d = __get_volatility(sym)
        stop_pct = get_volatility_stop_pct(vol_20d)
        vol_tag = f'V{vol_20d:.0f}%' if vol_20d else 'V?'

        # 更新最高价
        old_highest = get_highest(sym, state)
        set_highest(sym, current, state, cost=cost)
        new_highest = max(current, old_highest)

        # 计算软件追踪止损价 = 最高价 * (1 - stop_pct)
        trail_stop = new_highest * (1 - stop_pct)
        init_stop = cost * (1 - stop_pct)
        soft_stop = max(trail_stop, init_stop)

        # 检查是否触发追踪止损
        if current <= soft_stop and current > init_stop:
            # 触发了！但没有跌破硬止损（硬止损还在），先取消止损单再手动卖出
            stop_order = existing_stops.get(sym)
            if stop_order:
                cancel_order(stop_order['id'])
                time.sleep(0.3)
            # [execution_intent_type=stop_loss] 追踪止损触发 — Governor 不得阻断
            order = place_market_order(sym, int(qty), 'sell')
            if order and order.get('id'):
                msgs.append(
                    f'  🔴 追踪止损触发！卖出 {sym} x{int(qty)} @ ${current:.2f}'
                    f'（{vol_tag} 止损{stop_pct*100:.0f}% 追踪线${soft_stop:.2f}，'
                    f'最高${new_highest:.2f}）'
                )
                sell_actions.append(sym)
                sold_this_cycle[sym] = sold_this_cycle.get(sym, 0) + int(qty)
                _log_sell_for_replacement(sym, 'trail_stop', int(qty), current)  # P14/P15
            else:
                msgs.append(f'  ⚠️ {sym} 追踪止损触发但卖出失败')

        elif current <= init_stop:
            # 跌破硬止损线，但Alpaca止损单应该已经处理了
            msgs.append(
                f'  ⚠️ {sym} 跌破硬止损线 ${init_stop:.2f}'
                f'（{vol_tag} 止损{stop_pct*100:.0f}%），等待Alpaca止损执行'
            )

        else:
            # 安全：报告当前止损位
            dist = (current - soft_stop) / current * 100
            stop_type = "硬止损" if soft_stop <= init_stop + 0.01 else "追踪"
            hard = existing_stops.get(sym)
            if hard:
                hard_str = f'硬${hard["stop_price"]:.2f}'
                msgs.append(
                    f'  🛡 {sym} {vol_tag} {stop_type}${soft_stop:.2f} '
                    f'距{hard_str} | 距现价{dist:.0f}% 最高${new_highest:.2f}'
                )
            else:
                # 新股没有硬止损 → 挂一个（波动率分档）
                # [execution_intent_type=stop_loss] 新股挂硬止损
                order = place_stop_order(sym, int(qty), init_stop)
                if order and order.get('id'):
                    msgs.append(
                        f'  🆕 {sym} 硬止损已挂 ${init_stop:.2f}'
                        f'（成本${cost:.2f} {vol_tag} {stop_pct*100:.0f}%）| 距现价{dist:.0f}%'
                    )
                else:
                    msgs.append(f'  ⚠️ {sym} 止损挂单失败（新股）')

    # 卖出后，取消对应的Alpaca止损单（避免冲突）
    for sym in sell_actions:
        oid = existing_stops.get(sym, {}).get('id', '')
        if oid:
            cancel_order(oid)
            time.sleep(0.3)

    return msgs


# ═══════════════════════════════════════════════════════════════════════
# 2. stop_coverage_audit — 止损覆盖审计
# ═══════════════════════════════════════════════════════════════════════

def stop_coverage_audit(holdings, vol_map=None):
    """
    v4.7: 止损覆盖审计 — 确保所有持仓都有止损保护

    检查所有持仓是否已有保护（挂有止损单 OR 有未成交卖单）。
    缺失保护 → 补挂止损单。

    参数:
        holdings: 当前持仓列表 [{symbol, qty, avg, ...}]
        vol_map: {symbol: vol_20d} 可选，复用已有波动率数据

    返回:
        list of audit messages (str)
    """
    from eagle_eye.execution.order_manager import get_holdings as _get_holdings

    audit_msgs = []

    # 再拉一次持仓（止盈可能改变了持仓）
    fresh_holdings = _get_holdings()
    fresh_orders = get_open_stop_orders()

    # 获取所有未成交卖单（非止损类型的卖单也算保护）
    all_open_orders = api_get('/orders?status=open&limit=100') or []
    open_sell_syms = {
        o['symbol'] for o in all_open_orders
        if o['side'] == 'sell' and o['type'] != 'stop'
    }
    protected = set(fresh_orders.keys()) | open_sell_syms

    for h in fresh_holdings:
        sym = h['symbol']
        if sym not in protected:
            qty = int(h['qty'])
            cost = h['avg']
            vol_20d = vol_map.get(sym) if vol_map else None
            if vol_20d is None:
                vol_20d = __get_volatility(sym)
            stop_pct = get_volatility_stop_pct(vol_20d)
            stop_price = round(cost * (1 - stop_pct), 2)
            # [execution_intent_type=stop_loss] 补挂止损
            order = place_stop_order(sym, qty, stop_price)
            if order and order.get('id'):
                vol_str = f'V{vol_20d:.0f}%' if vol_20d else 'V?'
                audit_msgs.append(
                    f'  🆕 补挂止损 {sym} x{qty} @ ${stop_price:.2f} '
                    f'({vol_str} {stop_pct*100:.0f}%)'
                )
            else:
                audit_msgs.append(f'  ⚠️ {sym} 止损补挂失败')

    return audit_msgs


# ═══════════════════════════════════════════════════════════════════════
# 3. detect_ghost_stops — 幽灵止损单诊断
# ═══════════════════════════════════════════════════════════════════════

def detect_ghost_stops(holdings):
    """
    v4.7: 幽灵止损单诊断 — 找出持仓中已不存在的标的的止损单

    死锁规则：只检测不清理。永远不要 cancel stop order。

    参数:
        holdings: 当前持仓列表 [{symbol, ...}]

    返回:
        (ghost_stops, messages) 元组
        - ghost_stops: 幽灵止损单列表 [{symbol, id, qty, ...}]
        - messages: 用户可读的报告消息列表
    """
    ghost_msgs = []

    all_orders_raw = api_get('/orders?status=open&limit=200') or []
    held_syms = {h['symbol'] for h in holdings}

    ghost_stops = [
        o for o in all_orders_raw
        if o.get('type') == 'stop'
        and o['side'] == 'sell'
        and o['symbol'] not in held_syms
    ]

    if ghost_stops:
        total_qty = sum(int(float(o.get('qty', 0))) for o in ghost_stops)
        ghost_stop_syms = set(o['symbol'] for o in ghost_stops)
        ghost_msgs.append(
            f'👻 幽灵止损单: {len(ghost_stops)}笔 '
            f'({total_qty}股，{len(ghost_stop_syms)}只标的)'
        )
        for sym in sorted(ghost_stop_syms):
            count = sum(1 for o in ghost_stops if o['symbol'] == sym)
            ghost_msgs.append(f'    {sym}: {count}笔')

    return ghost_stops, ghost_msgs


# ═══════════════════════════════════════════════════════════════════════
# 4. update_stop_blacklist — 止损黑名单更新
# ═══════════════════════════════════════════════════════════════════════

def update_stop_blacklist():
    """
    查询 Alpaca 最近7天内的止损成交记录，保存到黑名单文件

    使用 AlpacaClient.get_filled_stops() 直接获取已成交止损单，
    替代手动查询 /orders 并过滤的旧方案。

    黑名单文件: {cfg.data_dir}/us_recent_stops.json

    返回:
        blacklist list — 最近被止损卖出的标的符号列表
    """
    from eagle_eye.broker.alpaca_client import AlpacaClient

    blacklist_file = cfg.data_dir / 'us_recent_stops.json'

    try:
        client = AlpacaClient()
        stop_fills = client.get_filled_stops(days=7)

        if not stop_fills:
            # 写入空黑名单
            blacklist_data = {
                'updated': datetime.now(timezone.utc).isoformat(),
                'lookback_days': 7,
                'blacklist': [],
                'details': [],
            }
            with open(blacklist_file, 'w') as f:
                json.dump(blacklist_data, f, indent=2)
            return []

        # 构建黑名单详情
        details = []
        for o in stop_fills:
            sym = o.get('symbol', '?')
            details.append({
                'symbol': sym,
                'filled_at': o.get('filled_at', ''),
                'filled_price': o.get('filled_avg_price', o.get('limit_price', '?')),
            })

        blacklist = list(set(o['symbol'] for o in details))

        blacklist_data = {
            'updated': datetime.now(timezone.utc).isoformat(),
            'lookback_days': 7,
            'blacklist': blacklist,
            'details': details,
        }

        with open(blacklist_file, 'w') as f:
            json.dump(blacklist_data, f, indent=2)

        logger.info(f'止损黑名单已更新: {len(blacklist)} 只标的')
        return blacklist

    except Exception as e:
        logger.error(f'黑名单更新失败: {e}')
        return []
