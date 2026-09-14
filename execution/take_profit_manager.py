"""
execution/take_profit_manager.py — 止盈执行管理（V7.1 Phase 3）

提取自 ~/.hermes/scripts/us_trader.py lines 477-516:
  - execute_take_profit(results, holdings, state)

止盈规则：
  RSI > 80 → 卖 50%（分批止盈）
  回撤（从20根K线最高点回落 >8%）→ 卖全部

卖完后如果还有剩余 → 重新挂止损单
"""

import time
import sys
import os

from eagle_eye.core.logger import get_logger

# ─── order_manager 导入（所有 Alpaca API 调用必经此模块）───
from eagle_eye.execution.order_manager import (
    get_open_stop_orders,
    place_market_order,
    place_stop_order,
    cancel_order,
)

# ─── position_manager 导入（状态管理）───
from eagle_eye.execution.position_manager import (
    get_trail_stop,
)

logger = get_logger('take_profit_manager')

# ─── 可注入回调 ───
# 用于替代买入记录（log_sell_for_replacement），
# 由 trade_executor.py 或其他模块通过 set_replacement_logger() 设置。
_replacement_logger = None


def set_replacement_logger(fn):
    """
    设置替代买入日志回调函数。

    fn 签名: fn(symbol, reason, qty, price) -> None
    其中 reason 为 'take_profit' / 'trail_stop' / 'stop_loss' / 'manual_sell'
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
# execute_take_profit — 止盈执行
# ═══════════════════════════════════════════════════════════════════════

def execute_take_profit(results, holdings, state, sold_this_cycle=None):
    """
    执行止盈卖出

    规则:
      RSI > 80 → 卖 50%（分批止盈，保留部分仓位继续上涨）
      回撤（从20根K线最高点回落 >8%）→ 卖全部

    执行流程:
      1. 获取已挂止损单（卖前必须先取消，否则 Alpaca 拒绝市价单）
      2. 卖出指定数量
      3. 卖完后如有剩余 → 重新挂止损单

    参数:
        results: analyze() 结果列表 [{symbol, price, sell_reason, vol_20d, ...}]
        holdings: 当前持仓列表 [{symbol, qty, avg, current, ...}]
        state: 风控状态 dict

    返回:
        list of messages (str)
    """
    if sold_this_cycle is None: sold_this_cycle = {}
    msgs = []
    existing_stops = get_open_stop_orders()

    for r in results:
        if not r['sell_reason']:
            continue
        sym = r['symbol']

        holding = next((h for h in holdings if h['symbol'] == sym), None)
        if not holding:
            continue

        qty = int(holding['qty']) - sold_this_cycle.get(sym, 0)
        if qty <= 0:
            continue

        # RSI>80: 卖50%；否则卖全部
        if '卖50%' in r['sell_reason']:
            sell_qty = max(1, qty // 2)
        else:
            sell_qty = qty

        # 先取消已有止损单（否则Alpaca因份额被冻结拒绝市价单）
        stop_order = existing_stops.get(sym)
        if stop_order:
            cancel_order(stop_order['id'])
            time.sleep(0.3)

        # [execution_intent_type=take_profit] 止盈卖出 — Governor 不得阻断
        order = place_market_order(sym, sell_qty, 'sell')
        if order and order.get('id'):
            msgs.append(
                f'  💰 止盈卖出 {sym} x{sell_qty} @ ${r["price"]} '
                f'| 原因: {r["sell_reason"]}'
            )
            sold_this_cycle[sym] = sold_this_cycle.get(sym, 0) + sell_qty
            _log_sell_for_replacement(sym, 'take_profit', sell_qty, r['price'])  # P14

            # 卖完后如果还有剩余，重新挂止损
            remaining = qty - sell_qty
            if remaining > 0:
                cost = holding['avg']
                # v4.6: 传入波动率，避免回退到默认 8%
                sym_vol = r.get('vol_20d')
                new_stop = get_trail_stop(sym, state, cost, vol_20d=sym_vol)
                # [execution_intent_type=take_profit] 止盈后重挂止损
                place_stop_order(sym, remaining, new_stop)
        else:
            msgs.append(f'  ❌ {sym} 止盈卖出失败')

    return msgs
