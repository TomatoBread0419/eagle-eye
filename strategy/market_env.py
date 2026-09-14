#!/usr/bin/env python3
# DEPRECATED (2026-09-12): 运行时活体采集器是 ~/.hermes/scripts/market_env.py
# （cron e565b9a8723b 调度）。本模块不被任何运行路径调用（见 docs/ARCHITECTURE-CURRENT.md §1-§2），
# 仅为 strategy/__init__.py re-export 兼容保留，勿在此添加功能。
"""
market_env.py — 市场环境扫描 (合并版 v7.1 2026-06-18)
合并 macro_context + market_breadth → 单脚本单JSON

功能:
  Part 1: 宏观温度计 — VIX/DXY/10Y-2Y利差/FOMC → regime
  Part 2: 市场广度 — %>MA200/涨跌比/新高新低 → health

输出: cfg.data_dir / market_env.json
兼容输出: cfg.data_dir / macro_context.json, market_breadth.json
"""

import json
import time
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from eagle_eye.core.config import cfg
from eagle_eye.core.logger import get_logger
from eagle_eye.broker.alpaca_client import get_alpaca_client
from eagle_eye.strategy.indicator_engine import calc_sma, calc_volatility

logger = get_logger('market_env')

# 模块级 Alpaca 客户端（所有扫描函数共享）
client = get_alpaca_client()


# ============================================================
# Part 1: 宏观温度计
# ============================================================

def yf_quick(symbol):
    """快速获取 yfinance 最新价，失败返回 None"""
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        try:
            return t.fast_info.last_price
        except:
            info = t.get_info()
            return info.get('regularMarketPrice') or info.get('previousClose')
    except Exception:
        return None


def get_vix():
    vix = yf_quick('^VIX')
    if vix is not None and vix > 0:
        return round(vix, 1)
    try:
        bars = client.get_bars('VIXY', days=5, limit=1)
        if bars:
            return round(bars[-1]['c'], 1)
    except:
        pass
    return None


def get_dxy():
    dxy = yf_quick('DX-Y.NYB')
    return round(dxy, 1) if dxy else None


def get_10y_yield():
    y = yf_quick('^TNX')
    return round(y, 2) if y else None


def get_2y_yield():
    y = yf_quick('^FVX')  # 5年期近似
    if y is not None:
        return round(y, 2)
    try:
        from eagle_eye.core.http import http_get
        url = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2&cosd=2026-01-01&coed=2026-12-31'
        code, body = http_get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if code == 200 and body:
            lines = body.strip().split('\n')
            if len(lines) >= 2:
                last = lines[-1].split(',')
                if len(last) >= 2:
                    return round(float(last[1]), 2)
    except:
        pass
    return None


def get_fomc_calendar():
    meetings = [
        ('2026-01-28', '2026-01-29'), ('2026-03-18', '2026-03-19'),
        ('2026-05-06', '2026-05-07'), ('2026-06-17', '2026-06-18'),
        ('2026-07-29', '2026-07-30'), ('2026-09-16', '2026-09-17'),
        ('2026-11-04', '2026-11-05'), ('2026-12-16', '2026-12-17'),
    ]
    today = datetime.now(timezone(timedelta(hours=8))).date()
    next_meeting, days_until = None, None
    for start, end in meetings:
        sd = datetime.strptime(start, '%Y-%m-%d').date()
        if sd >= today:
            next_meeting, days_until = start, (sd - today).days
            break
    return {'next_meeting': next_meeting, 'days_until': days_until}


def interpret_macro(vix, dxy, spread):
    """宏观判断 → NORMAL / CAUTIOUS / CRISIS"""
    warnings = []
    if vix:
        if vix > 35: warnings.append(f'VIX={vix} 极度恐慌')
        elif vix > 25: warnings.append(f'VIX={vix} 恐慌')
        elif vix < 12: warnings.append(f'VIX={vix} 过度自满')
    if dxy:
        if dxy > 108: warnings.append(f'DXY={dxy} 强美元逆风')
        elif dxy < 98: warnings.append(f'DXY={dxy} 弱美元顺风')
    if spread is not None:
        if spread < 0: warnings.append(f'10Y-2Y倒挂{spread:.2f}% 衰退预警')
        elif spread < 0.3: warnings.append(f'利差仅{spread:.2f}% 偏窄')

    if len(warnings) >= 2: regime = 'CAUTIOUS'
    elif any('恐慌' in w or '倒挂' in w for w in warnings): regime = 'CAUTIOUS'
    elif any('极度' in w for w in warnings): regime = 'CRISIS'
    else: regime = 'NORMAL'
    return regime, warnings


# ============================================================
# Part 2: 市场广度
# ============================================================

# 83只个股 + 11只ETF
STOCKS = {
    'AAPL': 'tech', 'MSFT': 'tech', 'NVDA': 'tech', 'GOOGL': 'tech',
    'AMZN': 'tech', 'META': 'tech', 'AVGO': 'tech', 'TSLA': 'tech',
    'AMD': 'tech', 'INTC': 'tech', 'QCOM': 'tech', 'TXN': 'tech',
    'MU': 'tech', 'AMAT': 'tech', 'CRM': 'tech', 'ADBE': 'tech',
    'ORCL': 'tech', 'CSCO': 'tech', 'ACN': 'tech', 'IBM': 'tech', 'NFLX': 'tech',
    'ARM': 'ai', 'PLTR': 'ai', 'SNOW': 'ai', 'CRWD': 'ai',
    'NOW': 'ai', 'PANW': 'ai', 'UBER': 'ai', 'DASH': 'ai',
    'SQ': 'ai', 'SHOP': 'ai', 'ZS': 'ai', 'DDOG': 'ai',
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
    'RKLB': 'space', 'RDW': 'space', 'ASTS': 'space', 'LUNR': 'space', 'PL': 'space',
}

SECTOR_ETFS = {
    'XLK': 'tech', 'XLF': 'finance', 'XLV': 'pharma', 'XLY': 'consumer',
    'XLI': 'industrial', 'XLE': 'energy', 'XLP': 'consumer_staples',
    'XLU': 'utilities', 'XLB': 'materials', 'XLRE': 'realestate', 'XLC': 'telecom',
}

SECTOR_NAMES = {
    'tech': '科技', 'ai': 'AI/云', 'consumer': '消费', 'consumer_staples': '必需消费',
    'finance': '金融', 'pharma': '医药', 'industrial': '工业', 'telecom': '通讯',
    'energy': '能源', 'defense': '军工', 'resources': '资源', 'space': '航天',
    'utilities': '公用事业', 'materials': '原材料', 'realestate': '房地产',
}


def _scan_one(sym, sector):
    """扫描单只股票健康度"""
    try:
        bars = client.get_bars(sym, days=300, limit=250) \
            or client.get_bars(sym, days=85, limit=70)
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

        high_52w = max(closes[-min(len(closes), 252):])
        low_52w = min(closes[-min(len(closes), 252):])
        near_high = current >= high_52w * 0.97
        near_low = current <= low_52w * 1.03

        return {
            'symbol': sym, 'sector': sector, 'price': round(current, 2),
            'chg_pct': round(chg_pct, 2),
            'above_ma50': above_ma50, 'above_ma200': above_ma200,
            'near_52w_high': near_high, 'near_52w_low': near_low,
        }
    except:
        return None


def _scan_etf(sym, sector):
    """扫描ETF月表现"""
    try:
        bars = client.get_bars(sym, days=85, limit=70)
        if not bars or len(bars) < 22:
            return None
        closes = [b['c'] for b in bars]
        ret_1m = (closes[-1] / closes[-21] - 1) * 100
        return {
            'symbol': sym, 'sector': sector,
            'name': SECTOR_NAMES.get(sector, sector),
            'ret_1m': round(ret_1m, 1),
        }
    except:
        return None


def interpret_breadth(pct_ma200, ad_ratio):
    """广度判断 → HEALTHY / NORMAL / WEAK / SICK"""
    if pct_ma200 and pct_ma200 >= 65 and ad_ratio >= 1.2:
        return 'HEALTHY'
    elif pct_ma200 and pct_ma200 >= 50:
        return 'NORMAL'
    elif pct_ma200 and pct_ma200 >= 35:
        return 'WEAK'
    return 'SICK'


# ============================================================
# 主流程
# ============================================================

def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    t0 = time.time()

    # ─── Part 1: 宏观 ───
    print('🌡️ 宏观环境采集...')
    vix = get_vix()
    dxy = get_dxy()
    y10 = get_10y_yield()
    y2 = get_2y_yield()
    spread = round(y10 - y2, 2) if (y10 and y2) else None
    fomc = get_fomc_calendar()
    regime, macro_warnings = interpret_macro(vix, dxy, spread)
    macro_emoji = {'NORMAL': '🟢', 'CAUTIOUS': '🟡', 'CRISIS': '🔴'}.get(regime, '⚪')

    print(f'  {macro_emoji} {regime} | VIX={vix or "?"} DXY={dxy or "?"} 利差={spread or "?"}%')
    if fomc['next_meeting']:
        print(f'  FOMC: {fomc["next_meeting"]} ({fomc["days_until"]}天后)')

    # ─── Part 2: 广度 ───
    print(f'\n🔬 市场广度扫描 ({len(STOCKS)}只)...')
    stock_results = []
    completed = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_scan_one, sym, sec): sym for sym, sec in STOCKS.items()}
        for f in as_completed(futures):
            r = f.result()
            completed += 1
            if r:
                stock_results.append(r)
            if completed % 20 == 0:
                print(f'  [{completed}/{len(STOCKS)}]')

    print(f'  ⏱ 个股: {len(stock_results)}/{len(STOCKS)}')

    # ETF
    etf_results = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_scan_etf, sym, sec): sym for sym, sec in SECTOR_ETFS.items()}
        for f in as_completed(futures):
            r = f.result()
            if r:
                etf_results.append(r)

    # 汇总
    total = len(stock_results)
    if total == 0:
        print('❌ 无有效数据')
        return

    above50 = sum(1 for r in stock_results if r['above_ma50'] is True)
    above200 = sum(1 for r in stock_results if r['above_ma200'] is True)
    ma200_avail = sum(1 for r in stock_results if r['above_ma200'] is not None)

    pct_ma50 = round(above50 / total * 100, 1)
    pct_ma200 = round(above200 / ma200_avail * 100, 1) if ma200_avail > 0 else None

    advancers = sum(1 for r in stock_results if r['chg_pct'] > 0)
    decliners = sum(1 for r in stock_results if r['chg_pct'] < 0)
    ad_ratio = round(advancers / decliners, 2) if decliners > 0 else 99

    new_highs = sum(1 for r in stock_results if r['near_52w_high'])
    new_lows = sum(1 for r in stock_results if r['near_52w_low'])

    health = interpret_breadth(pct_ma200, ad_ratio)
    health_label = {
        'HEALTHY': '🟢 健康', 'NORMAL': '🟡 正常',
        'WEAK': '🟠 偏弱', 'SICK': '🔴 病态',
    }.get(health, '⚪ 未知')

    # 板块健康度
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
            'sector': sec, 'name': SECTOR_NAMES.get(sec, sec),
            'stocks': stats['count'], 'pct_above_ma50': pct50, 'pct_above_ma200': pct200,
        })
    sector_ranking.sort(key=lambda x: x['pct_above_ma200'], reverse=True)

    etf_ranking = sorted(
        [e for e in etf_results if e['ret_1m'] is not None],
        key=lambda x: x['ret_1m'] or 0, reverse=True
    )

    elapsed = time.time() - t0

    # ─── 合并输出 ───
    result = {
        'timestamp': now.isoformat(),
        # 宏观
        'macro': {
            'regime': regime,
            'regime_emoji': macro_emoji,
            'vix': vix, 'dxy': dxy,
            'yield_10y': y10, 'yield_2y': y2, 'spread_10y2y': spread,
            'fomc': fomc,
            'warnings': macro_warnings,
        },
        # 广度
        'breadth': {
            'health': health,
            'health_label': health_label,
            'pct_above_ma50': pct_ma50,
            'pct_above_ma200': pct_ma200,
            'advancers': advancers, 'decliners': decliners,
            'ad_ratio': ad_ratio,
            'new_highs': new_highs, 'new_lows': new_lows,
            'sector_ranking': sector_ranking,
            'etf_performance': etf_ranking,
        },
        '_meta': {'elapsed_s': round(elapsed, 1), 'version': '7.1'},
    }

    # 确保输出目录存在
    cfg.data_dir.mkdir(parents=True, exist_ok=True)

    output_main = cfg.data_dir / 'market_env.json'
    with open(output_main, 'w') as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)

    # 兼容旧路径：写入独立的 macro_context.json 和 market_breadth.json
    for old_key in ('macro', 'breadth'):
        try:
            old_path = cfg.data_dir / f'{"macro_context" if old_key == "macro" else "market_breadth"}.json'
            with open(old_path, 'w') as f:
                json.dump(result[old_key], f, indent=2, ensure_ascii=False, default=str)
        except:
            pass

    # ─── 可读输出 ───
    print(f'\n{"="*55}')
    print(f'📊 市场环境 | {now.strftime("%Y-%m-%d %H:%M")}')
    print(f'{"="*55}')
    print(f'{macro_emoji} 宏观: {regime}')
    if macro_warnings:
        for w in macro_warnings:
            print(f'  ⚠️ {w}')
    print(f'{health_label} 广度')
    print(f'  %>MA50: {pct_ma50}% | %>MA200: {pct_ma200}%')
    print(f'  涨{advancers}/跌{decliners} | 比{ad_ratio}')
    print(f'  新高{new_highs} | 新低{new_lows}')
    print(f'\n板块:')
    for sr in sector_ranking[:8]:
        bar = '█' * int(sr['pct_above_ma200'] / 5)
        print(f'  {sr["name"]:6s}: {bar} {sr["pct_above_ma200"]:.0f}%')
    if etf_ranking:
        print(f'\nETF月表现 TOP5:')
        for e in etf_ranking[:5]:
            sign = '+' if (e['ret_1m'] or 0) > 0 else ''
            print(f'  {e["symbol"]:5s} [{e["name"]:6s}]: {sign}{e["ret_1m"]}%')
    print(f'\n⏱ {elapsed:.0f}s → {output_main}')

    logger.info(f'市场环境扫描完成 regime={regime} health={health} '
                f'pct_ma200={pct_ma200}% ad_ratio={ad_ratio} elapsed={elapsed:.1f}s')


if __name__ == '__main__':
    main()
