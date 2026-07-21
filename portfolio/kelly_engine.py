"""
portfolio/kelly_engine.py — 凯利仓位计算器 (V7.1 Phase 5)

Kelly Engine is a CALCULATOR. It provides theoretical sizing values.
It does NOT manage the portfolio or make allocation decisions.

Formulas preserved exactly from us_kelly.py:
  f* = p - (1-p)/b        (Kelly criterion)
  f_half = f* / 2          (Half-Kelly for risk management)
  Constraints: 1% ≤ f_half ≤ 25%, 1% ≤ f_full ≤ 50%

Usage:
    from eagle_eye.portfolio.kelly_engine import calc_kelly, main
    result = calc_kelly(trades)
"""

import json
from datetime import datetime, timezone, timedelta
from collections import deque

from eagle_eye.core.config import cfg
from eagle_eye.core.logger import get_logger
from eagle_eye.core.http import http_get

logger = get_logger('portfolio.kelly')


def load_orders(api_key=None, api_secret=None, base_url=None, days=90):
    """从 Alpaca 拉取订单历史，支持分页

    Routes through eagle_eye.core.http layer (same Alpaca auth headers).
    Uses manual pagination because AlpacaClient.get_orders() lacks
    page_token / after parameter support.

    Args:
        api_key: Alpaca API key (defaults to cfg.alpaca_api_key)
        api_secret: Alpaca API secret (defaults to cfg.alpaca_secret_key)
        base_url: Alpaca base URL (defaults to cfg.alpaca_base_url)
        days: Lookback period (default 90)

    Returns:
        list of order dicts
    """
    if api_key is None:
        api_key = cfg.alpaca_api_key
    if api_secret is None:
        api_secret = cfg.alpaca_secret_key
    if base_url is None:
        base_url = cfg.alpaca_base_url

    headers = {
        'APCA-API-KEY-ID': api_key,
        'APCA-API-SECRET-KEY': api_secret,
    }

    all_orders = []
    page_token = None
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')

    for _ in range(5):  # 最多5页 = 2500条
        url = f'{base_url}/v2/orders?status=closed&limit=500&after={cutoff}&direction=desc'
        if page_token:
            url += f'&page_token={page_token}'

        code, body = http_get(url, headers=headers, timeout=30)
        if code != 200:
            logger.warning(f'订单获取失败: HTTP {code}')
            break

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            logger.warning('订单响应 JSON 解析失败')
            break

        orders = data if isinstance(data, list) else data.get('orders', data)
        if not orders:
            break
        all_orders.extend(orders)

        # 检查是否有下一页
        if isinstance(data, dict):
            page_token = data.get('next_page_token')
            if not page_token:
                break
        else:
            break

    logger.info(f'拉取 {len(all_orders)} 条已成交订单')
    return all_orders


def fifo_match(orders):
    """FIFO配对买卖: 按时间顺序匹配每笔买入和卖出"""
    buys = []
    sells = []
    for o in orders:
        if o.get('status') != 'filled' or not o.get('filled_at'):
            continue
        sym = o['symbol']
        qty = float(o.get('filled_qty', o.get('qty', 0)))
        price = float(o.get('filled_avg_price', 0))
        if qty <= 0 or price <= 0:
            continue
        entry = {
            'symbol': sym,
            'qty': qty,
            'price': price,
            'filled_at': o['filled_at'],
        }
        if o['side'] == 'buy':
            buys.append(entry)
        else:
            sells.append(entry)

    # 按时间排序
    buys.sort(key=lambda x: x['filled_at'])
    sells.sort(key=lambda x: x['filled_at'])

    trades = []
    buy_queue = {}  # {symbol: deque of buys}
    for sell in sells:
        sym = sell['symbol']
        if sym not in buy_queue:
            buy_queue[sym] = deque()

        # 入队所有在卖出之前的买入
        while buys and buys[0]['filled_at'] < sell['filled_at']:
            b = buys.pop(0)
            if b['symbol'] not in buy_queue:
                buy_queue[b['symbol']] = deque()
            buy_queue[b['symbol']].append(b)

        # FIFO匹配
        remaining_sell_qty = sell['qty']
        while remaining_sell_qty > 0 and buy_queue[sym]:
            buy = buy_queue[sym][0]
            match_qty = min(buy['qty'], remaining_sell_qty)

            # 按比例结算
            buy_cost = buy['price'] * match_qty
            sell_rev = sell['price'] * match_qty
            pnl = sell_rev - buy_cost
            pnl_pct = (sell['price'] / buy['price'] - 1) * 100

            trades.append({
                'symbol': sym,
                'qty': round(match_qty, 2),
                'buy_price': buy['price'],
                'sell_price': sell['price'],
                'pnl': round(pnl, 2),
                'pnl_pct': round(pnl_pct, 2),
                'buy_date': buy['filled_at'][:10],
                'sell_date': sell['filled_at'][:10],
            })

            if buy['qty'] > match_qty:
                buy['qty'] -= match_qty
            else:
                buy_queue[sym].popleft()

            remaining_sell_qty -= match_qty

    return trades


def calc_kelly(trades):
    """从交易记录计算凯利最优仓位"""
    if not trades:
        return None

    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] < 0]

    win_rate = len(wins) / len(trades) if trades else 0

    avg_win = sum(t['pnl_pct'] for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(t['pnl_pct'] for t in losses) / len(losses)) if losses else 0

    if avg_loss == 0:
        return None

    odds = avg_win / avg_loss  # 赔率 b
    # 凯利公式: f* = (b*p - q) / b = p - q/b
    kelly_full = win_rate - (1 - win_rate) / odds
    kelly_half = kelly_full / 2  # 半凯利

    # 约束: 1% ~ 25%
    kelly_half = max(0.01, min(0.25, kelly_half))
    kelly_full = max(0.01, min(0.50, kelly_full))

    # 按symbol分组统计
    symbol_stats = {}
    for t in trades:
        sym = t['symbol']
        if sym not in symbol_stats:
            symbol_stats[sym] = {'trades': 0, 'wins': 0, 'total_pnl': 0}
        symbol_stats[sym]['trades'] += 1
        symbol_stats[sym]['total_pnl'] += t['pnl']
        if t['pnl'] > 0:
            symbol_stats[sym]['wins'] += 1

    return {
        'total_trades': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': round(win_rate, 4),
        'avg_win_pct': round(avg_win, 2),
        'avg_loss_pct': round(avg_loss, 2),
        'odds_ratio': round(odds, 2),
        'kelly_full_pct': round(kelly_full * 100, 1),
        'kelly_half_pct': round(kelly_half * 100, 1),
        'recommendation': (
            '正期望，按半凯利执行' if kelly_half > 0.05 else
            '正期望但边缘，保守执行' if kelly_half > 0.02 else
            '无正期望或数据不足，暂停激进'
        ),
        'symbol_breakdown': {
            sym: {
                'trades': s['trades'],
                'win_rate': round(s['wins'] / s['trades'], 3) if s['trades'] > 0 else 0,
                'total_pnl': round(s['total_pnl'], 2),
            }
            for sym, s in sorted(symbol_stats.items(), key=lambda x: -x[1]['total_pnl'])[:15]
        },
    }


def main():
    """主流程: 拉取订单 → FIFO配对 → 凯利计算 → 输出

    Gets API keys from cfg.alpaca_api_key / cfg.alpaca_secret_key.
    Output saved to cfg.data_dir / 'trade_history.json'.
    Same console output format as us_kelly.py.
    """
    now = datetime.now(timezone(timedelta(hours=8)))

    print(f'🎲 凯利仓位计算 | {now.strftime("%Y-%m-%d %H:%M")}')

    # 1. 拉取订单
    print('  拉取90天订单历史...')
    orders = load_orders()
    filled = [o for o in orders if o.get('status') == 'filled']
    print(f'  获取 {len(orders)} 条订单，其中 {len(filled)} 条已成交')

    # 2. FIFO配对
    trades = fifo_match(filled)
    print(f'  FIFO配对 → {len(trades)} 笔完整交易')

    # 3. 凯利计算
    kelly_result = calc_kelly(trades)

    result = {
        'timestamp': now.isoformat(),
        'period_days': 90,
        'total_orders': len(orders),
        'filled_orders': len(filled),
        'matched_trades': len(trades),
        'kelly': kelly_result,
    }

    output_path = cfg.data_dir / 'trade_history.json'
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)

    # 可读输出
    if kelly_result:
        k = kelly_result
        print(f'\n{"="*45}')
        print(f'📊 交易统计 (90天)')
        print(f'  总交易: {k["total_trades"]} 笔')
        print(f'  胜: {k["wins"]} | 负: {k["losses"]} | 胜率: {k["win_rate"]*100:.1f}%')
        print(f'  平均盈利: +{k["avg_win_pct"]}% | 平均亏损: -{k["avg_loss_pct"]}%')
        print(f'  赔率: {k["odds_ratio"]}')
        print(f'  凯利全仓: {k["kelly_full_pct"]}% | 半凯利: {k["kelly_half_pct"]}%')
        print(f'  建议: {k["recommendation"]}')
        if k.get('symbol_breakdown'):
            print(f'\n  个股盈亏 TOP5:')
            for sym, s in list(k['symbol_breakdown'].items())[:5]:
                sign = '+' if s['total_pnl'] > 0 else ''
                print(f'    {sym:6s}: {s["trades"]}笔 胜率{s["win_rate"]*100:.0f}% PnL ${sign}{s["total_pnl"]:,.0f}')
    else:
        print('  ⚠️ 数据不足，无法计算凯利')

    print(f'\n✅ 已保存: {output_path}')


# Alias for clarity when importing
kelly_main = main


if __name__ == '__main__':
    main()
