#!/usr/bin/env python3
"""
strategy/market_breadth.py — 市场广度健康度扫描 (V7.1 Phase 4)
扫描 83 只标的 + 11 只板块 ETF → 判断"这个市健康吗"
输出: cfg.data_dir / 'market_breadth.json'

指标:
  %>MA50 / %>MA200 — 多少股票在趋势之上
  涨跌比             — 今天涨的 vs 跌的
  52周新高/新低      — 极端情绪检测
  板块健康度排名     — 按%>MA200排序
  ETF 月表现         — 资金流向
"""

import json
import time
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from eagle_eye.core.config import cfg
from eagle_eye.core.logger import get_logger
from eagle_eye.broker.alpaca_client import get_alpaca_client
from eagle_eye.strategy.indicator_engine import calc_sma, calc_volatility

logger = get_logger('strategy.breadth')

# ─── 扫描标的 ───
# 83只 + 11只板块ETF
STOCKS = {
    # 科技 (21)
    'AAPL': 'tech', 'MSFT': 'tech', 'NVDA': 'tech', 'GOOGL': 'tech',
    'AMZN': 'tech', 'META': 'tech', 'AVGO': 'tech', 'TSLA': 'tech',
    'AMD': 'tech', 'INTC': 'tech', 'QCOM': 'tech', 'TXN': 'tech',
    'MU': 'tech', 'AMAT': 'tech', 'CRM': 'tech', 'ADBE': 'tech',
    'ORCL': 'tech', 'CSCO': 'tech', 'ACN': 'tech', 'IBM': 'tech', 'NFLX': 'tech',
    # AI (12)
    'ARM': 'ai', 'PLTR': 'ai', 'SNOW': 'ai', 'CRWD': 'ai',
    'NOW': 'ai', 'PANW': 'ai', 'UBER': 'ai', 'DASH': 'ai',
    'SQ': 'ai', 'SHOP': 'ai', 'ZS': 'ai', 'DDOG': 'ai',
    # 消费 (10)
    'WMT': 'consumer', 'HD': 'consumer', 'COST': 'consumer', 'MCD': 'consumer',
    'SBUX': 'consumer', 'NKE': 'consumer', 'DIS': 'consumer',
    'PG': 'consumer', 'PEP': 'consumer', 'KO': 'consumer',
    # 金融 (9)
    'JPM': 'finance', 'BAC': 'finance', 'WFC': 'finance', 'C': 'finance',
    'V': 'finance', 'MA': 'finance', 'GS': 'finance', 'MS': 'finance', 'BLK': 'finance',
    # 医药 (8)
    'LLY': 'pharma', 'UNH': 'pharma', 'MRK': 'pharma', 'ABBV': 'pharma',
    'PFE': 'pharma', 'TMO': 'pharma', 'DHR': 'pharma', 'ISRG': 'pharma',
    # 工业 (7)
    'CAT': 'industrial', 'BA': 'industrial', 'GE': 'industrial',
    'HON': 'industrial', 'UPS': 'industrial', 'LIN': 'industrial', 'NEE': 'industrial',
    # 通讯 (2)
    'T': 'telecom', 'VZ': 'telecom',
    # 能源 (3)
    'XOM': 'energy', 'CVX': 'energy', 'COP': 'energy',
    # 军工 (3)
    'LMT': 'defense', 'RTX': 'defense', 'NOC': 'defense',
    # 资源 (2)
    'FCX': 'resources', 'NEM': 'resources',
}

# 板块ETF: symbol → sector_name, 用于资金流向判断
SECTOR_ETFS = {
    'XLK': 'tech', 'XLF': 'finance', 'XLV': 'pharma', 'XLY': 'consumer',
    'XLI': 'industrial', 'XLE': 'energy', 'XLP': 'consumer_staples',
    'XLU': 'utilities', 'XLB': 'materials', 'XLRE': 'realestate', 'XLC': 'telecom',
}

SECTOR_NAMES = {
    'tech': '科技', 'ai': 'AI/云', 'consumer': '消费', 'consumer_staples': '必需消费',
    'finance': '金融', 'pharma': '医药', 'industrial': '工业', 'telecom': '通讯',
    'energy': '能源', 'defense': '军工', 'resources': '资源', 'utilities': '公用事业',
    'materials': '原材料', 'realestate': '房地产',
}


def _scan_one(sym, sector):
    """扫描单只股票的健康度"""
    try:
        client = get_alpaca_client()
        # 需要200根日K算MA200 → days=300, limit=250
        bars = client.get_bars(sym, days=300, limit=250) or client.get_bars(sym, days=85, limit=70)
        if not bars or len(bars) < 5:
            return None

        closes = [b['c'] for b in bars]
        current = closes[-1]
        prev = closes[-2] if len(closes) >= 2 else current
        chg_pct = (current - prev) / prev * 100 if prev > 0 else 0

        ma50 = calc_sma(closes, 50)
        ma200 = calc_sma(closes, 200) if len(closes) >= 200 else None

        above_ma50 = current > ma50 if ma50 else None
        above_ma200 = current > ma200 if ma200 else None

        # 52周新高/新低 (用全部数据近似)
        high_52w = max(closes[-min(len(closes), 252):])
        low_52w = min(closes[-min(len(closes), 252):])
        near_high = current >= high_52w * 0.97
        near_low = current <= low_52w * 1.03

        vol_20d = calc_volatility(closes, 20) if len(closes) >= 21 else None

        return {
            'symbol': sym,
            'sector': sector,
            'price': round(current, 2),
            'chg_pct': round(chg_pct, 2),
            'above_ma50': above_ma50,
            'above_ma200': above_ma200,
            'ma50': round(ma50, 2) if ma50 else None,
            'ma200': round(ma200, 2) if ma200 else None,
            'near_52w_high': near_high,
            'near_52w_low': near_low,
            'vol_20d': vol_20d,
        }
    except Exception:
        return None


def _scan_etf(sym, sector):
    """扫描ETF（月表现 + 健康度）"""
    try:
        client = get_alpaca_client()
        bars = client.get_bars(sym, days=85, limit=70)
        if not bars or len(bars) < 22:
            return None

        closes = [b['c'] for b in bars]
        current = closes[-1]
        ret_1m = (closes[-1] / closes[-21] - 1) * 100 if len(closes) >= 22 else None
        ma50 = calc_sma(closes, 50)
        above_ma50 = current > ma50 if ma50 else None

        return {
            'symbol': sym,
            'sector': sector,
            'price': round(current, 2),
            'ret_1m': round(ret_1m, 1) if ret_1m else None,
            'above_ma50': above_ma50,
        }
    except Exception:
        return None


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    t0 = time.time()

    # ─── 并行扫描83只个股 ───
    print(f'🔬 扫描 {len(STOCKS)} 只个股（MA50/MA200/涨跌/新高等）...')
    stock_results = []
    completed = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_scan_one, sym, sec): sym
                   for sym, sec in STOCKS.items()}
        for f in as_completed(futures):
            r = f.result()
            completed += 1
            if r:
                stock_results.append(r)
            if completed % 20 == 0:
                print(f'  [{completed}/{len(STOCKS)}]')

    elapsed_stocks = time.time() - t0
    print(f'  ⏱ 个股完成: {len(stock_results)}/{len(STOCKS)} ({elapsed_stocks:.0f}s)')

    # ─── 并行扫描11只ETF ───
    print(f'\n📊 扫描 {len(SECTOR_ETFS)} 只板块ETF...')
    etf_results = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_scan_etf, sym, sec): sym
                   for sym, sec in SECTOR_ETFS.items()}
        for f in as_completed(futures):
            r = f.result()
            if r:
                etf_results.append(r)

    # ─── 汇总统计 ───
    total_stocks = len(stock_results)
    if total_stocks == 0:
        print('❌ 无有效数据')
        return

    # %>MA50 / %>MA200
    above_ma50_count = sum(1 for r in stock_results if r['above_ma50'] is True)
    above_ma200_count = sum(1 for r in stock_results if r['above_ma200'] is True)
    ma200_available = sum(1 for r in stock_results if r['above_ma200'] is not None)

    pct_above_ma50 = round(above_ma50_count / total_stocks * 100, 1)
    pct_above_ma200 = round(above_ma200_count / ma200_available * 100, 1) if ma200_available > 0 else None

    # 涨跌比
    advancers = sum(1 for r in stock_results if r['chg_pct'] > 0)
    decliners = sum(1 for r in stock_results if r['chg_pct'] < 0)
    ad_ratio = round(advancers / decliners, 2) if decliners > 0 else 99

    # 新高/新低
    new_highs = sum(1 for r in stock_results if r['near_52w_high'])
    new_lows = sum(1 for r in stock_results if r['near_52w_low'])

    # 综合健康度
    if pct_above_ma200 and pct_above_ma200 >= 65 and ad_ratio >= 1.2:
        health = 'HEALTHY'
    elif pct_above_ma200 and pct_above_ma200 >= 50:
        health = 'NORMAL'
    elif pct_above_ma200 and pct_above_ma200 >= 35:
        health = 'WEAK'
    else:
        health = 'SICK'

    # ─── 板块健康度 ───
    sector_health = {}
    for r in stock_results:
        sec = r['sector']
        if sec not in sector_health:
            sector_health[sec] = {'count': 0, 'above_ma50': 0, 'above_ma200': 0, 'ma200_avail': 0}
        sector_health[sec]['count'] += 1
        if r['above_ma50']: sector_health[sec]['above_ma50'] += 1
        if r['above_ma200'] is not None:
            sector_health[sec]['ma200_avail'] += 1
            if r['above_ma200']: sector_health[sec]['above_ma200'] += 1

    sector_ranking = []
    for sec, stats in sector_health.items():
        pct50 = round(stats['above_ma50'] / stats['count'] * 100, 1) if stats['count'] > 0 else 0
        pct200 = round(stats['above_ma200'] / stats['ma200_avail'] * 100, 1) if stats['ma200_avail'] > 0 else 0
        sector_ranking.append({
            'sector': sec,
            'name': SECTOR_NAMES.get(sec, sec),
            'stocks': stats['count'],
            'pct_above_ma50': pct50,
            'pct_above_ma200': pct200,
        })
    sector_ranking.sort(key=lambda x: x['pct_above_ma200'], reverse=True)

    # ─── ETF 月表现 ───
    etf_ranking = sorted(
        [e for e in etf_results if e['ret_1m'] is not None],
        key=lambda x: x['ret_1m'] or 0, reverse=True
    )

    result = {
        'timestamp': now.isoformat(),
        'health': health,
        'summary': {
            'total_scanned': total_stocks,
            'pct_above_ma50': pct_above_ma50,
            'pct_above_ma200': pct_above_ma200,
            'advancers': advancers,
            'decliners': decliners,
            'ad_ratio': ad_ratio,
            'new_highs': new_highs,
            'new_lows': new_lows,
            'health_label': {
                'HEALTHY': '🟢 健康', 'NORMAL': '🟡 正常',
                'WEAK': '🟠 偏弱', 'SICK': '🔴 病态',
            }.get(health, '⚪ 未知'),
        },
        'sector_ranking': sector_ranking,
        'etf_performance': [{
            'symbol': e['symbol'],
            'sector': e['sector'],
            'name': SECTOR_NAMES.get(e['sector'], e['sector']),
            'ret_1m': e['ret_1m'],
        } for e in etf_ranking],
        'stocks': stock_results,
    }

    output_path = cfg.data_dir / 'market_breadth.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)

    # ─── 可读输出 ───
    print(f'\n{"="*55}')
    print(f'📊 市场广度 | {now.strftime("%Y-%m-%d %H:%M")} | {result["summary"]["health_label"]}')
    print(f'{"="*55}')
    print(f'  %>MA50: {pct_above_ma50}% | %>MA200: {pct_above_ma200}%')
    print(f'  涨 {advancers} / 跌 {decliners} | 涨跌比 {ad_ratio}')
    print(f'  52周新高附近: {new_highs} | 新低附近: {new_lows}')
    print()
    print(f'板块健康度 (%>MA200):')
    for sr in sector_ranking[:8]:
        bar = '█' * int(sr['pct_above_ma200'] / 5)
        print(f'  {sr["name"]:6s}: {bar} {sr["pct_above_ma200"]:.0f}%')
    if etf_ranking:
        print(f'\nETF月表现 TOP5:')
        for e in etf_ranking[:5]:
            sign = '+' if (e['ret_1m'] or 0) > 0 else ''
            print(f'  {e["symbol"]:5s} [{e["sector"]:10s}]: {sign}{e["ret_1m"]}%')

    elapsed = time.time() - t0
    print(f'\n⏱ 总耗时: {elapsed:.0f}s')
    print(f'✅ 已保存: {output_path}')


if __name__ == '__main__':
    main()
