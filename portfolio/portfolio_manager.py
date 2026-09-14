#!/usr/bin/env python3
"""
portfolio/portfolio_manager.py — 持仓分析器 (Phase 5)

输出 us_portfolio.json：持仓详情、板块分布、仓位缺口、风险标记
供 AI 决策层使用。

用法：
    python -m eagle_eye.portfolio.portfolio_manager [--target-util 0.50] [--mode normal]
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Optional

from eagle_eye.broker.alpaca_client import get_alpaca_client
from eagle_eye.core.config import cfg
from eagle_eye.strategy.indicator_engine import get_volatility_stop_pct
from eagle_eye.core.logger import get_logger

logger = get_logger('portfolio')

# ═══════════════════════════════════════════════════════════════
# 板块映射（与 screener 保持一致，87 只美股）
# ═══════════════════════════════════════════════════════════════
SECTOR_MAP = {
    'AAPL': 'tech', 'MSFT': 'tech', 'NVDA': 'tech', 'GOOGL': 'tech',
    'AMZN': 'tech', 'META': 'tech', 'AVGO': 'tech', 'TSLA': 'tech',
    'AMD': 'tech', 'INTC': 'tech', 'QCOM': 'tech', 'TXN': 'tech',
    'MU': 'tech', 'AMAT': 'tech', 'CRM': 'tech', 'ADBE': 'tech',
    'ORCL': 'tech', 'CSCO': 'tech', 'ACN': 'tech', 'IBM': 'tech', 'NFLX': 'tech',
    'ARM': 'ai', 'PLTR': 'ai', 'SNOW': 'ai', 'CRWD': 'ai',
    'NOW': 'ai', 'PANW': 'ai', 'UBER': 'ai', 'DASH': 'ai',
    'SQ': 'ai', 'SHOP': 'ai', 'ZS': 'ai', 'NET': 'ai', 'DDOG': 'ai',
    'WMT': 'consumer', 'HD': 'consumer', 'COST': 'consumer', 'MCD': 'consumer',
    'SBUX': 'consumer', 'NKE': 'consumer', 'DIS': 'consumer',
    'PG': 'consumer', 'PEP': 'consumer', 'KO': 'consumer',
    'JPM': 'finance', 'BAC': 'finance', 'WFC': 'finance', 'C': 'finance',
    'V': 'finance', 'MA': 'finance', 'GS': 'finance', 'MS': 'finance', 'BLK': 'finance',
    'LLY': 'pharma', 'UNH': 'pharma', 'MRK': 'pharma', 'ABBV': 'pharma',
    'PFE': 'pharma', 'TMO': 'pharma', 'DHR': 'pharma', 'ISRG': 'pharma',
    'CAT': 'industrial', 'BA': 'industrial', 'GE': 'industrial',
    'HON': 'industrial', 'UPS': 'industrial', 'LIN': 'industrial', 'NEE': 'industrial',
    'T': 'telecom', 'VZ': 'telecom',
    'XOM': 'energy', 'CVX': 'energy', 'COP': 'energy',
    'LMT': 'defense', 'RTX': 'defense', 'NOC': 'defense',
    'FCX': 'resources', 'NEM': 'resources',
}

# ═══════════════════════════════════════════════════════════════
# 板块推荐权重（按市场叙事模式）
# ═══════════════════════════════════════════════════════════════
SECTOR_RECOMMENDATIONS = {
    'aggressive': {
        'tech': 0.15, 'ai': 0.10, 'finance': 0.05,
        'industrial': 0.05, 'energy': 0.03,
    },
    'normal': {
        'tech': 0.10, 'ai': 0.05, 'finance': 0.05,
        'pharma': 0.05, 'consumer': 0.05, 'energy': 0.03,
    },
    'cautious': {
        'energy': 0.05, 'defense': 0.03, 'pharma': 0.05,
        'consumer': 0.05, 'finance': 0.05, 'telecom': 0.03,
    },
    'defensive': {
        'energy': 0.05, 'defense': 0.03, 'pharma': 0.05,
        'consumer': 0.05, 'telecom': 0.03,
    },
}

# 默认目标仓位利用率
DEFAULT_TARGET_UTIL = 0.50

# ─── 文件路径（通过 cfg.data_dir） ──────────────────
STATE_FILE_NAME = 'us_risk_state.json'
EVENTS_FILE_NAME = 'market_events_latest.json'
PORTFOLIO_FILE_NAME = 'us_portfolio.json'


def _load_json(path):
    """加载 JSON 文件，失败返回默认值"""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def analyze_portfolio(target_util: Optional[float] = None,
                      mode: str = 'normal') -> dict:
    """
    生成完整的持仓分析报告。

    Args:
        target_util: 目标仓位利用率 (0.0-1.0)，None=使用默认 0.50
        mode: 分析模式 (aggressive/normal/cautious/defensive)

    Returns:
        dict 包含 account, positions, sector_allocation, sector_gaps,
        risk_flags, orders 等完整分析结果
    """
    client = get_alpaca_client()

    # ─── 1. 获取账户 ─────────────────────────────
    acct_raw = client.get_account()
    if not acct_raw:
        return {'error': '无法连接 Alpaca API'}

    equity = float(acct_raw.get('equity', 0))
    cash = float(acct_raw.get('cash', 0))
    long_mv = float(acct_raw.get('long_market_value', 0))
    short_mv = abs(float(acct_raw.get('short_market_value', 0)))
    buying_power = float(acct_raw.get('buying_power', 0))
    status = acct_raw.get('status', '?')

    # ─── 2. 获取持仓 ─────────────────────────────
    positions_raw = client.get_positions()
    holdings = []
    for p in positions_raw:
        sym = p.get('symbol', '')
        qty = float(p.get('qty', 0))
        side = 'long' if qty > 0 else 'short'
        holdings.append({
            'symbol': sym,
            'sector': SECTOR_MAP.get(sym, 'other'),
            'qty': abs(qty),
            'side': side,
            'avg_entry': float(p.get('avg_entry_price', 0)),
            'current_price': float(p.get('current_price', 0)),
            'market_value': float(p.get('market_value', 0)),
            'unrealized_pl': float(p.get('unrealized_pl', 0)),
            'unrealized_plpc': float(p.get('unrealized_plpc', 0)),
            'cost_basis': float(p.get('cost_basis', 0)),
        })

    # ─── 3. 获取挂单 ─────────────────────────────
    orders_raw = client.get_orders(status='open', limit=50)
    orders = []
    for o in orders_raw:
        orders.append({
            'id': o.get('id', ''),
            'symbol': o.get('symbol', ''),
            'side': o.get('side', ''),
            'type': o.get('type', ''),
            'qty': o.get('qty', ''),
            'status': o.get('status', ''),
            'limit_price': o.get('limit_price'),
            'stop_price': o.get('stop_price'),
            'submitted_at': (o.get('submitted_at', '') or '')[:16],
        })

    # ─── 4. 加载风险状态 & 市场叙事 ───────────────
    data_dir = cfg.data_dir

    state = _load_json(data_dir / STATE_FILE_NAME)
    if state is None:
        state = {'peak_equity': 0, 'positions': {}}

    events = _load_json(data_dir / EVENTS_FILE_NAME)
    narrative = 'cautious'
    sentiment = ''
    if events:
        narrative = events.get('market_narrative', 'cautious')
        sentiment = events.get('overall_sentiment', '')

    # ─── 5. 仓位目标 ─────────────────────────────
    if target_util is None:
        target_util = DEFAULT_TARGET_UTIL

    # ─── 6. 仓位利用率 ───────────────────────────
    stock_value = long_mv + short_mv
    utilization = stock_value / equity if equity > 0 else 0
    gap_dollars = max(0, equity * target_util - stock_value)

    # ─── 7. 持仓详情 ─────────────────────────────
    positions = []
    for h in holdings:
        weight = abs(h['market_value']) / equity if equity > 0 else 0

        # 波动率分档止损（7-10%，默认 8%）
        stop_pct = get_volatility_stop_pct(None)  # 无波动率数据 → 默认 8%
        cost = h['avg_entry']
        stop_price = cost * (1 - stop_pct)
        dist_to_stop = (
            (h['current_price'] - stop_price) / h['current_price']
            if h['current_price'] > 0 else 0
        )
        # 距 TP1（+20%）
        tp1_price = cost * 1.20
        dist_to_tp1 = (
            (tp1_price - h['current_price']) / h['current_price']
            if h['current_price'] > 0 else 0
        )

        # 状态判定
        pos_status = 'normal'
        if dist_to_stop < 0.02:
            pos_status = 'approaching_stop'
        elif dist_to_stop < 0:
            pos_status = 'below_stop'
        if h['unrealized_plpc'] > 0.15:
            pos_status = 'near_tp1'
        if h['unrealized_plpc'] > 0.30:
            pos_status = 'near_tp2'

        positions.append({
            'symbol': h['symbol'],
            'sector': h['sector'],
            'side': h['side'],
            'qty': h['qty'],
            'avg_entry': round(h['avg_entry'], 2),
            'current_price': round(h['current_price'], 2),
            'market_value': round(h['market_value'], 2),
            'unrealized_pl': round(h['unrealized_pl'], 2),
            'unrealized_plpc': round(h['unrealized_plpc'], 4),
            'weight': round(weight, 4),
            'distance_to_stop': round(dist_to_stop, 4),
            'distance_to_tp1': round(dist_to_tp1, 4),
            'status': pos_status,
        })

    # ─── 8. 板块分布 ─────────────────────────────
    sector_allocation = {}
    for p in positions:
        s = p['sector']
        if s not in sector_allocation:
            sector_allocation[s] = {'count': 0, 'market_value': 0, 'weight': 0, 'pl': 0}
        sector_allocation[s]['count'] += 1
        sector_allocation[s]['market_value'] += p['market_value']
        sector_allocation[s]['weight'] += p['weight']
        sector_allocation[s]['pl'] += p['unrealized_pl']

    for s in sector_allocation:
        sector_allocation[s]['market_value'] = round(sector_allocation[s]['market_value'], 2)
        sector_allocation[s]['weight'] = round(sector_allocation[s]['weight'], 4)
        sector_allocation[s]['pl'] = round(sector_allocation[s]['pl'], 2)

    # ─── 9. 板块缺口分析 ─────────────────────────
    recommended = SECTOR_RECOMMENDATIONS.get(mode, SECTOR_RECOMMENDATIONS['normal'])
    sector_gaps = {}
    for sector, target_weight in recommended.items():
        current_weight = sector_allocation.get(sector, {}).get('weight', 0)
        if current_weight < target_weight:
            gap_amount = (target_weight - current_weight) * equity
            if gap_amount > 500:  # 只报告 >$500 的缺口
                sector_gaps[sector] = {
                    'current_weight': round(current_weight, 4),
                    'target_weight': round(target_weight, 4),
                    'gap_dollars': round(gap_amount, 2),
                }

    # ─── 10. 风险标记 ────────────────────────────
    risk_flags = []
    peak = state.get('peak_equity', equity)
    drawdown = (peak - equity) / peak if peak > 0 else 0
    if drawdown > 0.08:
        risk_flags.append(f'回撤 {drawdown*100:.1f}% 接近 12% 暂停线')
    if drawdown > 0.12:
        risk_flags.append(f'回撤 {drawdown*100:.1f}% 已超 12% 暂停买入')

    # 板块集中度
    for s, alloc in sector_allocation.items():
        if alloc['weight'] > 0.20:
            risk_flags.append(f'{s} 板块占比 {alloc["weight"]*100:.0f}% 过重（>20%）')

    # 个股风险
    for p in positions:
        if 0 < p['distance_to_stop'] < 0.03:
            risk_flags.append(f'{p["symbol"]} 距止损仅 {p["distance_to_stop"]*100:.1f}%')
        if p['unrealized_plpc'] < -0.05:
            risk_flags.append(f'{p["symbol"]} 浮亏 {p["unrealized_plpc"]*100:.1f}%')

    # ─── 11. 挂单统计 ────────────────────────────
    pending_buys = [o for o in orders if o['side'] == 'buy']
    pending_sells = [o for o in orders if o['side'] == 'sell']

    # ─── 12. 组装结果 ────────────────────────────
    tz_cst = timezone(timedelta(hours=8))
    result = {
        'timestamp': datetime.now(tz_cst).isoformat(),
        'account': {
            'equity': round(equity, 2),
            'cash': round(cash, 2),
            'long_mv': round(long_mv, 2),
            'short_mv': round(short_mv, 2),
            'buying_power': round(buying_power, 2),
            'utilization': round(utilization, 4),
            'target_util': target_util,
            'gap_dollars': round(gap_dollars, 2),
            'market_narrative': narrative,
            'sentiment': sentiment[:100] if sentiment else '',
            'drawdown': round(drawdown, 4),
            'peak_equity': round(peak, 2),
        },
        'positions': positions,
        'sector_allocation': sector_allocation,
        'sector_gaps': sector_gaps,
        'risk_flags': risk_flags,
        'orders': {
            'pending_buys': len(pending_buys),
            'pending_sells': len(pending_sells),
            'details': orders[:15],
        },
    }

    # ─── 13. 保存 ────────────────────────────────
    output_path = data_dir / PORTFOLIO_FILE_NAME
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        logger.info(f'持仓报告已保存: {output_path}')
    except OSError as e:
        logger.error(f'保存持仓报告失败: {e}')

    return result


def print_report(result: dict) -> None:
    """打印可读报告（纯格式化，无任何 API 依赖）"""
    if 'error' in result:
        print(f'\u274c {result["error"]}')
        return

    acct = result['account']
    print(f'=== 持仓分析 | {result["timestamp"][:16]} ===')
    print(f'Equity: ${acct["equity"]:,.2f} | Cash: ${acct["cash"]:,.2f}')
    print(f'仓位: {acct["utilization"]*100:.1f}% \u2192 目标 {acct["target_util"]*100:.0f}% | 缺口: ${acct["gap_dollars"]:,.0f}')
    print(f'叙事: {acct["market_narrative"]} | 回撤: {acct["drawdown"]*100:.1f}%')
    print()

    if result['positions']:
        print(f'持仓 ({len(result["positions"])} 只):')
        for p in result['positions']:
            arrow = '\U0001f7e2' if p['unrealized_pl'] >= 0 else '\U0001f534'
            flag = f' [{p["status"]}]' if p['status'] != 'normal' else ''
            print(f'  {arrow} {p["symbol"]:6s} [{p["sector"]:9s}] {p["qty"]:>3.0f}股 '
                  f'${p["current_price"]:<8.2f} pl={p["unrealized_plpc"]:+.1%} '
                  f'w={p["weight"]*100:.1f}%{flag}')

    if result['sector_allocation']:
        print(f'\n板块分布:')
        for s, alloc in sorted(result['sector_allocation'].items(),
                               key=lambda x: -x[1]['weight']):
            print(f'  {s:12s}: {alloc["count"]}只 {alloc["weight"]*100:.1f}% '
                  f'${alloc["market_value"]:,.0f} pl=${alloc["pl"]:+,.0f}')

    if result['sector_gaps']:
        print(f'\n板块缺口:')
        for s, gap in result['sector_gaps'].items():
            print(f'  \u274c {s:12s}: {gap["current_weight"]*100:.1f}% \u2192 '
                  f'{gap["target_weight"]*100:.0f}% (缺口 ${gap["gap_dollars"]:,.0f})')

    if result['risk_flags']:
        print(f'\n风险标记:')
        for flag in result['risk_flags']:
            print(f'  \u26a0\ufe0f {flag}')

    orders = result['orders']
    if orders['pending_buys'] or orders['pending_sells']:
        print(f'\n挂单: {orders["pending_buys"]}笔买入 + {orders["pending_sells"]}笔卖出')


# ═══════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='持仓分析器')
    parser.add_argument('--target-util', type=float, default=None,
                        help='目标仓位利用率 (0.0-1.0, 默认 0.50)')
    parser.add_argument('--mode',
                        choices=['aggressive', 'normal', 'cautious', 'defensive'],
                        default='normal', help='分析模式 (默认 normal)')
    args = parser.parse_args()

    result = analyze_portfolio(target_util=args.target_util, mode=args.mode)
    print_report(result)
