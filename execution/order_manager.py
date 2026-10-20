"""
execution/order_manager.py — 订单管理 (V7.1 Phase 3)

从 us_trader.py 提取，所有 Alpaca API 通信通过 AlpacaClient。
逻辑与原始完全相同，无任何计算、阈值或策略改动。
"""

from typing import Optional, Dict, Any, List
import json
from datetime import datetime, timezone, timedelta

from eagle_eye.core.config import cfg
from eagle_eye.core.logger import get_logger
from eagle_eye.broker.alpaca_client import get_alpaca_client

logger = get_logger('execution.order')


# ======================== 账户与持仓 ========================

def get_portfolio() -> tuple:
    """获取账户信息

    Returns:
        (acct_dict, equity, cash)
        失败时返回 ({}, 0, 0)
    """
    client = get_alpaca_client()
    acct = client.get_account()
    if not acct:
        return {}, 0, 0
    return acct, float(acct.get('equity', 0)), float(acct.get('cash', 0))


def get_holdings() -> list:
    """获取所有持仓

    Returns:
        [{
            'symbol': str, 'qty': float,
            'cost': float, 'avg': float,
            'current': float, 'market': float,
            'pnl': float, 'pnl_pct': float
        }, ...]
    """
    client = get_alpaca_client()
    pos = client.get_positions()
    if not pos:
        return []
    return [{
        'symbol': p['symbol'], 'qty': float(p['qty']),
        'cost': float(p['cost_basis']), 'avg': float(p['avg_entry_price']),
        'current': float(p['current_price']), 'market': float(p['market_value']),
        'pnl': float(p['unrealized_pl']), 'pnl_pct': float(p['unrealized_plpc']) * 100
    } for p in pos]


# ======================== 止损单管理 ========================

def get_open_stop_orders() -> dict:
    """获取所有已挂止损单

    Returns:
        {symbol: {id, stop_price, qty, submitted}, ...}
    """
    client = get_alpaca_client()
    orders = client.get_orders(status='open', limit=50)
    if not orders:
        return {}
    stops = {}
    for o in orders:
        if o.get('type') == 'stop' and o.get('side') == 'sell':
            stops[o['symbol']] = {
                'id': o['id'],
                'stop_price': float(o['stop_price']),
                'qty': float(o['qty']),
                'submitted': o.get('submitted_at', '')
            }
    return stops


def cancel_order(order_id: str) -> bool:
    """取消订单"""
    client = get_alpaca_client()
    return client.cancel_order(order_id)


def api_get(path: str) -> list:
    """获取订单列表（兼容旧代码 api_get 调用）"""
    client = get_alpaca_client()
    status = 'open'; limit = 100
    for part in path.replace('/orders?', '').split('&'):
        if '=' in part:
            k, v = part.split('=', 1)
            if k == 'status': status = v
            elif k == 'limit': limit = int(v)
    return client.get_orders(status=status, limit=limit)


def place_stop_order(symbol: str, qty: int, stop_price: float) -> Optional[dict]:
    """下止损单（GTC 卖单）

    Args:
        symbol: 标的符号
        qty: 数量
        stop_price: 止损价

    Returns:
        Alpaca 订单对象，失败返回 None
    """
    client = get_alpaca_client()
    # [execution_intent_type=stop_loss] 止损挂单入口 — Governor 不得阻断 (v1.1 §5.2)
    return client.place_order(
        symbol=symbol,
        qty=int(qty),
        side='sell',
        type='stop',
        time_in_force='gtc',
        stop_price=round(stop_price, 2)
    )


# ======================== 买单管理 ========================

def get_open_buy_orders() -> dict:
    """获取所有未成交的买入挂单（market/limit），避免重复下单

    Returns:
        {symbol: {'count': int, 'total_qty': int}, ...}
    """
    client = get_alpaca_client()
    orders = client.get_orders(status='open', limit=50)
    if not orders:
        return {}
    buys = {}
    for o in orders:
        if o.get('side') == 'buy' and o.get('status') in ('accepted', 'pending_new', 'new'):
            sym = o['symbol']
            if sym not in buys:
                buys[sym] = {'count': 0, 'total_qty': 0}
            buys[sym]['count'] += 1
            buys[sym]['total_qty'] += int(float(o['qty']))
    return buys


def _shadow_hook(symbol, qty, side, intent_type, order_result):
    """Step 3: Shadow 治理记录 — 永不阻断真实订单, 永不 crash。

    mode='shadow': 调用 governor_bridge.check_governor 获得 Governor 决策,
    但只写入 audit JSONL, 不改变 actual_action (真实订单结果原样返回)。

    设计要点:
      - 无 intent_type (调用方未标注) → 直接返回, 零开销
      - lazy import (双路径) → bridge 缺失时订单不受影响
      - audit_path=os.devnull → 抑制 bridge 自动写, 由本函数写"合并记录"
        (governor_result + actual_action 单行)
      - 全 try/except → 任何异常都不影响下单路径
    """
    if not intent_type:
        return
    try:
        try:
            from eagle_eye.execution.governor_bridge import check_governor
        except ImportError:
            from governor_bridge import check_governor
        import os as _os
        audit_file = _os.environ.get("SHADOW_AUDIT_FILE") or \
            _os.path.join(_os.path.expanduser("~/stock_trader/audit"),
                          "governor_shadow_decisions.jsonl")
        _os.makedirs(_os.path.dirname(audit_file), exist_ok=True)
        audit_path = audit_file
        gov = check_governor(
            intent_type,
            candidates=[{"symbol": symbol}],
            side=side,
            audit_path=_os.devnull,  # 抑制 bridge 自动写, 由本函数写合并记录
        )
        rec = {
            "mode": "shadow",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "intent_type": intent_type,
            "symbol": symbol,
            "qty": int(qty),
            "side": side,
            "governor_result": {
                "permitted": gov.get("permitted"),
                "reason_code": gov.get("reason_code"),
                "regime": gov.get("regime"),
                "halt_flag": gov.get("halt_flag"),
                "data_freshness": gov.get("data_freshness", {}),
            },
            "actual_action": {
                "executed": bool(order_result and order_result.get("id")),
                "order_id": (order_result or {}).get("id"),
            },
        }
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _l3_gate(symbol, qty, side, intent_type, caller):
    """Governor L3 出口守卫钩子（下单前 BUY 检查）— 返回 True=拦截。

    委托 governor_gate.pre_order_check（三态 off|shadow|enforce，默认 off）。
    覆盖口径: 仅 side=='buy'；SELL/止损/止盈/退出零评估零日志。
    失败模式: 任何异常 fail-open 返回 False——守卫自身故障绝不阻断下单。
    """
    try:
        try:
            from eagle_eye.execution.governor_gate import pre_order_check
        except ImportError:
            from governor_gate import pre_order_check
        return bool(pre_order_check(symbol, qty, side,
                                    intent_type=intent_type,
                                    caller=caller).get('blocked'))
    except Exception:
        return False


def place_market_order(symbol: str, qty: int, side: str, dedupe: bool = True,
                       shadow_intent_type: Optional[str] = None) -> Optional[dict]:
    """下单，默认去重：同一symbol已有未成交买单时跳过

    Args:
        symbol: 标的符号
        qty: 数量
        side: 'buy' 或 'sell'
        dedupe: 是否去重（买入时检查已有未成交单）

    Returns:
        Alpaca 订单对象，失败或跳过返回 None
    """
    if side == 'buy' and dedupe:
        existing = get_open_buy_orders()
        if symbol in existing:
            logger.info(
                f'  ⏭ {symbol} 已有{existing[symbol]["count"]}笔买单'
                f'({existing[symbol]["total_qty"]}股)未成交，跳过'
            )
            _shadow_hook(symbol, qty, side, shadow_intent_type, None)
            return None

    if side == 'sell' and dedupe:
        # P2-20260802: 卖侧去重（纵深防御）。只检查非 stop 类型的未成交卖单，
        # 不拦止损单（止盈流程 cancel→sell→re-create stop 依赖 stop 单可共存）。
        client = get_alpaca_client()
        orders = client.get_orders(status='open', limit=100) or []
        for o in orders:
            if (o.get('symbol') == symbol
                    and o.get('side') == 'sell'
                    and o.get('type') != 'stop'
                    and o.get('status') in ('accepted', 'pending_new', 'new')):
                logger.info(f'  ⏭ {symbol} 已有未成交卖单，跳过（P2 防重复卖出）')
                _shadow_hook(symbol, qty, side, shadow_intent_type, None)
                return None
    # [L3 governor gate] BUY 开仓前守卫（三态默认 off；仅 side=buy 评估；异常 fail-open）
    if (side or '').lower() == 'buy' and _l3_gate(symbol, qty, side, shadow_intent_type, 'place_market_order'):
        return None
    client = get_alpaca_client()
    # [execution_intent_type=由调用方标注] 市价单唯一执行口 — 唯一 BUY/SELL 入口 (v1.1 §1.1)
    result = client.place_order(
        symbol=symbol,
        qty=int(qty),
        side=side,
        type='market',
        time_in_force='day'
    )
    _shadow_hook(symbol, qty, side, shadow_intent_type, result)
    return result

# ════════════════════════════════════════════════════
# P14/P15: sell→buy 替代追踪
# ════════════════════════════════════════════════════

REPLACEMENT_FILE = f'{cfg.data_dir}/us_pending_replacements.json'

def _load_json(filepath):
    try:
        with open(filepath) as f:
            return json.load(f)
    except:
        return {}

def log_sell_for_replacement(symbol, reason, qty, price):
    """P14/P15: 记录卖出事件，供AI决策层检查替代买入需求。"""
    try:
        data = _load_json(REPLACEMENT_FILE)
    except:
        data = {'pending': []}
    existing = [p for p in data.get('pending', []) if p.get('symbol') == symbol]
    if existing:
        return
    data.setdefault('pending', []).append({
        'symbol': symbol, 'reason': reason, 'qty': qty, 'price': price,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'replace_by': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    })
    try:
        with open(REPLACEMENT_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except:
        pass

def check_pending_replacements():
    """P14/P15: 返回需要替代买入的标的列表。"""
    try:
        data = _load_json(REPLACEMENT_FILE)
    except:
        return []
    pending = data.get('pending', [])
    if not pending:
        return []
    now = datetime.now(timezone.utc)
    active = []
    for p in pending:
        try:
            replace_by = datetime.fromisoformat(p['replace_by'].replace('Z', '+00:00'))
            if now < replace_by:
                active.append(p)
        except:
            active.append(p)
    return active

def clear_pending_replacement(symbol):
    """P14/P15: 替代买入完成后清除记录。"""
    try:
        data = _load_json(REPLACEMENT_FILE)
        data['pending'] = [p for p in data.get('pending', []) if p['symbol'] != symbol]
        with open(REPLACEMENT_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except:
        pass


def place_limit_order(symbol: str, qty: int, side: str, limit_price: float,
                      dedupe: bool = True, client_order_id: str = None,
                      shadow_intent_type: Optional[str] = None) -> Optional[dict]:
    """下单（限价单）。Step 0-B 新增 — 唯一 limit 下单入口。

    目的: 封堵 trade_executor L305/L526 直连 alpaca_client 的 bypass (V8 Phase 3 Step 0-B)。
    纯新增函数, 不修改任何现有逻辑; 与 place_market_order 同模式 (薄封装 + dedupe)。

    Args:
        symbol: 标的符号
        qty: 数量
        side: 'buy' 或 'sell'
        limit_price: 限价
        dedupe: 买入时检查已有未成交单 (默认 True, 与 place_market_order 一致)
        client_order_id: 可选客户端订单号

    Returns:
        Alpaca 订单对象，失败或跳过返回 None
    """
    if side == 'buy' and dedupe:
        existing = get_open_buy_orders()
        if symbol in existing:
            logger.info(
                f'  ⏭ {symbol} 已有{existing[symbol]["count"]}笔买单'
                f'({existing[symbol]["total_qty"]}股)未成交，跳过'
            )
            _shadow_hook(symbol, qty, side, shadow_intent_type, None)
            return None
    if side == 'sell' and dedupe:
        # P2 卖侧去重对齐 (place_market_order L166-177): 只检查非 stop 类型, 不拦止损单
        client = get_alpaca_client()
        orders = client.get_orders(status='open', limit=100) or []
        for o in orders:
            if (o.get('symbol') == symbol
                    and o.get('side') == 'sell'
                    and o.get('type') != 'stop'
                    and o.get('status') in ('accepted', 'pending_new', 'new')):
                logger.info(f'  ⏭ {symbol} 已有未成交卖单，跳过（P2 防重复卖出）')
                _shadow_hook(symbol, qty, side, shadow_intent_type, None)
                return None
    kwargs = dict(
        symbol=symbol,
        qty=int(qty),
        side=side,
        type='limit',
        limit_price=float(limit_price),
        time_in_force='day',
    )
    if client_order_id:
        kwargs['client_order_id'] = client_order_id
    # [L3 governor gate] BUY 开仓前守卫（三态默认 off；仅 side=buy 评估；异常 fail-open）
    if (side or '').lower() == 'buy' and _l3_gate(symbol, qty, side, shadow_intent_type, 'place_limit_order'):
        return None
    client = get_alpaca_client()
    result = client.place_order(**kwargs)
    _shadow_hook(symbol, qty, side, shadow_intent_type, result)
    return result
