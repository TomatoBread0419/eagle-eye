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


def place_market_order(symbol: str, qty: int, side: str, dedupe: bool = True) -> Optional[dict]:
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
            return None

    client = get_alpaca_client()
    return client.place_order(
        symbol=symbol,
        qty=int(qty),
        side=side,
        type='market',
        time_in_force='day'
    )

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
