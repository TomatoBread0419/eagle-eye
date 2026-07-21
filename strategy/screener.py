"""
strategy/screener.py — GARP 动量扫描器 (V7.1 native)
Phase 2.1: 从 us_screener.py 提取评分逻辑，使用 V7 原生的
indicator_engine / alpaca_client / allocation_engine。
"""
import json, os, math, time, sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from eagle_eye.broker.alpaca_client import get_alpaca_client
from eagle_eye.strategy.indicator_engine import (
    calc_rsi, calc_sma, calc_volatility, calc_volume_metrics,
    calc_macd, calc_atr, get_yf_metrics,
)
from eagle_eye.portfolio.allocation_engine import kelly_position_sizes
from eagle_eye.core.config import cfg

# ── Paths (keep backward compat with V6) ─────────────────────────────
SRC_DIR = os.path.expanduser('~/stock_trader')
WATCHLIST_FILE = os.path.join(SRC_DIR, 'us_watchlist.json')
EVENTS_FILE = os.path.join(SRC_DIR, 'market_events_latest.json')
PORTFOLIO_FILE = os.path.join(SRC_DIR, 'us_portfolio.json')
UNIVERSE_FILE = os.path.join(SRC_DIR, 'scan_universe.json')

# ── UNIVERSE loaded from JSON (single source of truth) ───────────────
UNIVERSE = {}
DEFENSE_SECTOR_BONUS = {}

def _load_universe():
    """Load scan pool from scan_universe.json. Merges base + dynamic_additions."""
    global UNIVERSE, DEFENSE_SECTOR_BONUS
    try:
        with open(UNIVERSE_FILE) as f:
            data = json.load(f)
        # Merge base universe + dynamic additions
        universe = dict(data.get('universe', {}))
        try:
            for item in data.get('dynamic_additions', []):
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    universe[item[0]] = item[1]
        except Exception as e:
            print(f'⚠️ dynamic_additions 解析失败: {e}', file=sys.stderr)
        UNIVERSE = universe
        DEFENSE_SECTOR_BONUS = data.get('defense_bonus', {})
        return universe
    except Exception as e:
        print(f'⚠️ 无法加载 scan_universe.json: {e}', file=sys.stderr)
        # Fallback to minimal hardcoded set if JSON missing
        if not UNIVERSE:
            UNIVERSE = {'SPY': 'etf', 'QQQ': 'etf'}
            DEFENSE_SECTOR_BONUS = {}
        return UNIVERSE

_load_universe()

# ── Weight config ─────────────────────────────────────────────────────
_weights = None

def _load_weights():
    """Load weights from ai_weight_config.json, with P1.3 validation."""
    global _weights
    if _weights:
        return _weights
    defaults = {
        'score_weights': {'ret_1m': 0.55, 'ret_3m': 0.28, 'ret_short': 0.12},
        'rsi_scoring': {'normal_threshold': 80, 'defensive_threshold': 65,
                        'normal_penalty': -10, 'extreme_threshold': 90, 'extreme_penalty': -15},
        'volatility_scoring': {'low_vol_threshold': 20, 'low_vol_bonus': 3,
                               'mid_vol_threshold': 30, 'mid_vol_bonus': 1,
                               'high_vol_threshold': 40, 'high_vol_penalty': -1,
                               'extreme_vol_threshold': 50, 'extreme_vol_penalty': -3},
        'ma_scoring': {'uptrend_bonus': 3, 'cross_bonus': 2},
        'volume_scoring': {'bullish_confirmation': 3, 'divergence_penalty': -3, 'bearish_penalty': -2},
        'macd_scoring': {'golden_cross': 3, 'death_cross': -2, 'above_zero_bonus': 1},
        'rs_vs_spy_scoring': {'strong_rs_threshold': 5.0, 'strong_rs_bonus': 2,
                              'moderate_rs_threshold': 2.0, 'moderate_rs_bonus': 1,
                              'weak_rs_threshold': -5.0, 'weak_rs_penalty': -2},
        'sector_gap_scoring': {'large_gap_threshold': 0.03, 'large_gap_bonus': 5,
                               'medium_gap_threshold': 0.02, 'medium_gap_bonus': 3,
                               'small_gap_threshold': 0.01, 'small_gap_bonus': 2},
        'yfinance_scoring': {'beta_high_threshold': 2.0, 'beta_high_penalty': -2,
                             'beta_mid_threshold': 1.5, 'beta_mid_penalty': -1,
                             'beta_low_threshold': 0.5, 'beta_low_bonus': 1,
                             'pe_expensive_threshold': 50, 'pe_expensive_penalty': -2,
                             'pe_fair_low': 10, 'pe_fair_high': 25, 'pe_fair_bonus': 2,
                             'pe_moderate_high': 35, 'pe_moderate_bonus': 1,
                             'div_yield_threshold': 0.02, 'div_yield_bonus': 1},
        'buy_filter': {'defensive_rsi_limit': 65, 'normal_rsi_limit': 78,
                       'min_momentum_score': 3, 'defensive_max_volatility': 45},
        'defense_sector_bonus': DEFENSE_SECTOR_BONUS,
    }
    weight_path = os.path.join(SRC_DIR, 'ai_weight_config.json')
    try:
        with open(weight_path) as f:
            cfg_data = json.load(f)
        merged = {}
        for section, dvals in defaults.items():
            merged[section] = {**dvals, **(cfg_data.get(section, {}))}

        # P1.3: validate against design defaults
        design = cfg_data.get('_design_defaults', {})
        if design:
            violations = []
            for section, baseline in design.items():
                if section.startswith('_') or section not in merged:
                    continue
                current = merged[section]
                for key, base_val in baseline.items():
                    if not isinstance(base_val, (int, float)):
                        continue
                    cur = current.get(key)
                    if cur is None or abs(base_val) < 1e-9:
                        continue
                    drift = abs(cur - base_val) / abs(base_val)
                    if drift > 0.20:
                        violations.append(f'{section}.{key}: {cur}→{base_val} ({drift*100:.0f}%)')
                        current[key] = base_val
            if violations:
                print(f'⚠️ P1.3 SCREENER: {len(violations)} weights clamped to baseline', file=sys.stderr)
        _weights = merged
    except:
        _weights = defaults
    return _weights

# ── Scan helpers ──────────────────────────────────────────────────────

def _get_bars(symbol, days=100):
    """Adapter: AlpacaClient → bars compatible with indicator_engine."""
    client = get_alpaca_client()
    raw = client.get_bars(symbol, days=days)
    if not raw or len(raw) < 20:
        return None
    # AlpacaClient returns [{'t':'...','o':...,'h':...,'l':...,'c':...,'v':...}]
    # Convert to normalized format
    bars = []
    for b in raw:
        bars.append({
            't': b.get('t', '')[:10] if b.get('t') else '',
            'o': float(b['o']),
            'c': float(b['c']),
            'h': float(b['h']),
            'l': float(b['l']),
            'v': int(b['v']),
        })
    return bars

def _get_price(symbol):
    client = get_alpaca_client()
    return client.get_last_price(symbol)

def _load_sector_gaps():
    try:
        with open(PORTFOLIO_FILE) as f:
            pf = json.load(f)
        gaps = {}
        for sector, info in pf.get('sector_gaps', {}).items():
            gaps[sector] = info.get('target_weight', 0) - info.get('current_weight', 0)
        return gaps
    except:
        return {}

# ── Read-only event alerts ────────────────────────────────────────────

def _read_event_alerts():
    """P1.1: READ-ONLY. Returns critical alerts list. Never modifies scores."""
    critical_alerts = []
    try:
        with open(EVENTS_FILE) as f:
            data = json.load(f)
    except:
        return critical_alerts
    assessments = data.get('summary', {}).get('assessments', [])
    for a in assessments:
        if not isinstance(a, dict):
            continue
        direction = a.get('direction', '')
        significant = a.get('significant', False)
        hot = a.get('hot_events', []) or []
        is_bear = '🔴' in direction and ('利空' in direction or '风险' in direction)
        if is_bear and significant:
            alert = f"🔴 {a.get('sector', '')}: {direction}"
            if hot:
                alert += f" [{','.join(hot[:3])}]"
            critical_alerts.append(alert)
    return critical_alerts

# ── Single stock scan ─────────────────────────────────────────────────

def _scan_one(sym, sector, is_defensive, sector_gaps, spy_ret_1m, spy_ret_3m):
    """Scan one stock. Pure function — all deps injected."""
    W = _load_weights()
    bars = _get_bars(sym, 100)
    if not bars or len(bars) < 20:
        return None

    closes = [b['c'] for b in bars]
    current = closes[-1]
    price = _get_price(sym) or current
    if not price or price < 5:
        return None

    n = len(closes)
    ret_1m = (closes[-1]/closes[-21]-1)*100 if n >= 22 else None
    ret_3m = (closes[-1]/closes[-63]-1)*100 if n >= 64 else None
    if ret_1m is None: ret_1m = (closes[-1]/closes[0]-1)*100
    if ret_3m is None and n >= 42: ret_3m = (closes[-1]/closes[21]-1)*100
    ret_short = (closes[-1]/closes[-5]-1)*100 if n >= 6 else 0

    rsi14 = calc_rsi(closes, 14)
    ma20 = calc_sma(closes, 20)
    ma50 = calc_sma(closes, 50) if n >= 50 else None
    ma_uptrend = ma20 and current > ma20
    ma_cross = ma50 and ma20 and ma20 > ma50 if ma50 else False
    vol_20d = calc_volatility(closes, 20)

    score = 0
    sw = W['score_weights']
    if ret_1m is not None: score += ret_1m * sw['ret_1m']
    if ret_3m is not None: score += ret_3m * sw['ret_3m']
    score += ret_short * sw['ret_short']

    rs = W['rsi_scoring']
    threshold = rs['defensive_threshold'] if is_defensive else rs['normal_threshold']
    if rsi14 and rsi14 > rs['extreme_threshold']:
        score += rs['extreme_penalty']
    elif rsi14 and rsi14 > threshold:
        score += rs['normal_penalty']

    if ma_uptrend: score += W['ma_scoring']['uptrend_bonus']
    if ma_cross: score += W['ma_scoring']['cross_bonus']

    vs = W['volatility_scoring']
    if vol_20d is not None:
        if vol_20d < vs['low_vol_threshold']: score += vs['low_vol_bonus']
        elif vol_20d < vs['mid_vol_threshold']: score += vs['mid_vol_bonus']
        elif vol_20d > vs['extreme_vol_threshold']: score += vs['extreme_vol_penalty']
        elif vol_20d > vs['high_vol_threshold']: score += vs['high_vol_penalty']

    volumes = [b['v'] for b in bars]
    vm = calc_volume_metrics(volumes, closes)
    vol_signal = ''
    vol_sc = W['volume_scoring']
    if vm:
        conf = vm.get('confirmation', 'neutral')
        if conf == 'bullish':
            score += vol_sc['bullish_confirmation']; vol_signal = '📈放量上涨'
        elif conf == 'divergence':
            score += vol_sc['divergence_penalty']; vol_signal = '⚠️缩量虚涨'
        elif conf == 'bearish':
            score += vol_sc['bearish_penalty']; vol_signal = '📉放量下跌'
        elif vm.get('vol_spike'): vol_signal = f'🔥量比{vm.get("vol_ratio",1):.1f}x'
        elif vm.get('vol_dry'): vol_signal = f'🏜量比{vm.get("vol_ratio",1):.1f}x'

    macd_line, signal_line, histogram, crossover = calc_macd(closes)
    macd_signal = ''
    ms = W['macd_scoring']
    if crossover == 'golden':
        score += ms['golden_cross']; macd_signal = '🔱金叉'
    elif crossover == 'death':
        score += ms['death_cross']; macd_signal = '☠️死叉'
    elif histogram and histogram > 0:
        score += ms['above_zero_bonus']

    highs = [b['h'] for b in bars]
    lows = [b['l'] for b in bars]
    atr = calc_atr(highs, lows, closes)
    atr_pct = round(atr/price*100, 1) if atr and price else None

    rs_signal = ''
    rs_cfg = W['rs_vs_spy_scoring']
    if spy_ret_1m is not None and ret_1m is not None:
        rs_1m = ret_1m - spy_ret_1m
        if rs_1m > rs_cfg['strong_rs_threshold']:
            score += rs_cfg['strong_rs_bonus']; rs_signal = f'RS+{rs_1m:.0f}%'
        elif rs_1m > rs_cfg['moderate_rs_threshold']:
            score += rs_cfg['moderate_rs_bonus']
        elif rs_1m < rs_cfg['weak_rs_threshold']:
            score += rs_cfg['weak_rs_penalty']; rs_signal = f'RS{rs_1m:.0f}%'

    # yfinance
    yf_cfg = W['yfinance_scoring']
    yf = get_yf_metrics(sym)
    yf_score = 0
    yf_details = []
    if yf:
        beta = yf.get('beta')
        if beta is not None:
            if beta > yf_cfg['beta_high_threshold']:
                yf_score += yf_cfg['beta_high_penalty']; yf_details.append(f'β{beta:.1f}')
            elif beta > yf_cfg['beta_mid_threshold']:
                yf_score += yf_cfg['beta_mid_penalty']; yf_details.append(f'β{beta:.1f}')
            elif beta < yf_cfg['beta_low_threshold']:
                yf_score += yf_cfg['beta_low_bonus']; yf_details.append(f'β{beta:.1f}')
        fwd_pe = yf.get('forward_pe')
        if fwd_pe is not None:
            if fwd_pe > yf_cfg['pe_expensive_threshold']:
                yf_score += yf_cfg['pe_expensive_penalty']; yf_details.append(f'PE{fwd_pe:.0f}')
            elif yf_cfg['pe_fair_low'] <= fwd_pe <= yf_cfg['pe_fair_high']:
                yf_score += yf_cfg['pe_fair_bonus']; yf_details.append(f'PE{fwd_pe:.0f}')
            elif yf_cfg['pe_fair_high'] < fwd_pe <= yf_cfg['pe_moderate_high']:
                yf_score += yf_cfg['pe_moderate_bonus']; yf_details.append(f'PE{fwd_pe:.0f}')
        div_y = yf.get('dividend_yield')
        if div_y is not None and div_y > yf_cfg['div_yield_threshold']:
            yf_score += yf_cfg['div_yield_bonus']; yf_details.append(f'Div{div_y*100:.1f}%')
    score += yf_score

    if is_defensive:
        score += W['defense_sector_bonus'].get(sector, 0)

    sgs = W['sector_gap_scoring']
    gap_weight = sector_gaps.get(sector, 0)
    if gap_weight > sgs['large_gap_threshold']: score += sgs['large_gap_bonus']
    elif gap_weight > sgs['medium_gap_threshold']: score += sgs['medium_gap_bonus']
    elif gap_weight > sgs['small_gap_threshold']: score += sgs['small_gap_bonus']

    trend = '上涨' if ma_uptrend else ('下跌' if ma20 and current < ma20 and ma50 and current < ma50 else '震荡')

    return {
        'symbol': sym, 'sector': sector, 'price': round(price, 2),
        'momentum_score': round(score, 1),
        'ret_1m': round(ret_1m, 1) if ret_1m else None,
        'ret_3m': round(ret_3m, 1) if ret_3m else None,
        'ret_short': round(ret_short, 1), 'rsi14': rsi14,
        'vol_20d': vol_20d, 'trend': trend,
        'ma_uptrend': ma_uptrend, 'ma_cross': ma_cross,
        'vol_signal': vol_signal,
        'vol_confirmation': vm.get('confirmation', 'neutral') if vm else 'neutral',
        'macd_signal': macd_signal, 'macd_histogram': histogram,
        'rs_signal': rs_signal, 'atr': atr, 'atr_pct': atr_pct,
        'yf_score': yf_score, 'yf_details': ','.join(yf_details) if yf_details else '',
    }

# ── Main scan ─────────────────────────────────────────────────────────

def run_scan(mode='normal'):
    """Run full GARP momentum scan. Uses V7 alpaca_client natively."""
    client = get_alpaca_client()
    W = _load_weights()

    symbols = list(UNIVERSE.keys())
    is_defensive = (mode == 'defensive')
    sector_gaps = _load_sector_gaps()
    critical_alerts = _read_event_alerts()

    print(f'🚀 GARP动量扫描器 V7 native | {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print(f'扫描池: {len(symbols)} 只股票 (并行10线程)')

    # SPY baseline
    spy_ret_1m = spy_ret_3m = None
    spy_bars = _get_bars('SPY', 85)
    if spy_bars and len(spy_bars) >= 63:
        spy_closes = [b['c'] for b in spy_bars]
        spy_ret_1m = (spy_closes[-1]/spy_closes[-21]-1)*100 if len(spy_closes) >= 22 else None
        spy_ret_3m = (spy_closes[-1]/spy_closes[-63]-1)*100

    results = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {
            ex.submit(_scan_one, sym, UNIVERSE[sym], is_defensive,
                      sector_gaps, spy_ret_1m, spy_ret_3m): sym
            for sym in symbols
        }
        for i, future in enumerate(as_completed(futures), 1):
            sym = futures[future]
            try:
                r = future.result()
                if r:
                    results.append(r)
            except Exception as e:
                print(f'  [{i}/{len(symbols)}] {sym} ERROR: {e}', file=sys.stderr)

    elapsed = time.time() - t0
    results.sort(key=lambda x: x['momentum_score'], reverse=True)

    # Sector ranking
    sector_stocks = {}
    for r in results:
        sector_stocks.setdefault(r['sector'], []).append(r)
    for sec, stocks in sector_stocks.items():
        stocks.sort(key=lambda x: x['momentum_score'], reverse=True)
        for i, r in enumerate(stocks):
            r['sector_rank'] = i + 1
            r['sector_total'] = len(stocks)
            r['sector_leader'] = i < 2

    # Buy candidates (skip leaders, filter RSI/momentum)
    buy_candidates = []
    bf = W['buy_filter']
    rsi_limit = bf['defensive_rsi_limit'] if is_defensive else bf['normal_rsi_limit']
    for r in results:
        if r.get('sector_leader'):
            continue
        if r['rsi14'] and r['rsi14'] > rsi_limit:
            continue
        if r['momentum_score'] < bf['min_momentum_score']:
            continue
        if not r['ma_uptrend']:
            continue
        if is_defensive and r['vol_20d'] and r['vol_20d'] > bf['defensive_max_volatility']:
            continue
        buy_candidates.append(r)

    # Kelly
    kelly_map = {}
    if buy_candidates:
        sized = kelly_position_sizes(
            [{'symbol': r['symbol'], 'score': r['momentum_score'],
              'atr_pct': r.get('atr_pct') or 3.0} for r in buy_candidates]
        )
        kelly_map = {k['symbol']: k for k in sized}

    # Print summary (compact)
    print(f'\n⏱ 扫描完成: {elapsed:.0f}秒 ({len(symbols)/elapsed:.1f}只/秒)')
    print(f'成功 {len(results)} / 候选买入 {len(buy_candidates)}')
    if critical_alerts:
        print(f'⚠️ 重大事件: {len(critical_alerts)}')

    # TOP20 preview
    print(f'\n📋 TOP10:')
    for i, r in enumerate(results[:10], 1):
        print(f'  #{i:2d} {r["symbol"]:6s} [{r["sector"]:9s}] score={r["momentum_score"]:+7.1f}  '
              f'1M={r["ret_1m"]:+5.1f}%  RSI={r["rsi14"]}' if r.get('rsi14') else f'  #{i:2d} {r["symbol"]:6s} [{r["sector"]:9s}] score={r["momentum_score"]:+7.1f}')

    # Write JSON (backward compat)
    watchlist = {
        'timestamp': datetime.now().isoformat(),
        'total_scanned': len(symbols),
        'success': len(results),
        'errors': 0,
        'market_narrative': 'neutral',
        'is_defensive': is_defensive,
        'sector_gaps': {s: round(g, 4) for s, g in sector_gaps.items()},
        'buy_candidates': [r['symbol'] for r in buy_candidates[:10]],
        'top10': [r['symbol'] for r in results[:10]],
        'all_ranked': [{'symbol': r['symbol'], 'score': r['momentum_score'],
                        'price': r['price'], 'sector': r['sector']} for r in results[:20]],
        'kelly_allocations': {sym: {'kelly_pct': v['kelly_pct'], 'win_prob': v.get('p_est', 0),
                                     'odds': v.get('b_est', 0), 'score': v['score']}
                              for sym, v in kelly_map.items()},
        'critical_alerts': critical_alerts,
    }
    with open(WATCHLIST_FILE, 'w') as f:
        json.dump(watchlist, f, indent=2)
    print(f'\n✅ 结果已保存到 {WATCHLIST_FILE}')

    return watchlist, results


# ── CLI ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='GARP Momentum Scanner V7 native')
    parser.add_argument('--mode', choices=['aggressive','normal','cautious','defensive'],
                        default='normal')
    args = parser.parse_args()
    run_scan(mode=args.mode)
