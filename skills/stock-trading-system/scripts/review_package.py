#!/usr/bin/env python3
"""Eagle Eye Daily Review Package — 8 sections, raw data only, no opinions."""
import sys, os, json, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

# ═══ Env ═══
env = {}
for line in open(os.path.expanduser('~/.hermes/.env')):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip().strip('"').strip("'")

KEY = env.get('ALPACA_API_KEY', '')
SECRET = env.get('ALPACA_SECRET_KEY', '')
BASE = env.get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
HEADERS = {'APCA-API-KEY-ID': KEY, 'APCA-API-SECRET-KEY': SECRET, 'Content-Type': 'application/json'}

def api_get(path):
    req = urllib.request.Request(f'{BASE}{path}', headers=HEADERS)
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

DATA_DIR = os.path.expanduser('~/stock_trader')

# ═══ Sector mapping from scan_universe.json (single source of truth) ═══
_UNIVERSE_FILE = os.path.join(DATA_DIR, 'scan_universe.json')
UNIVERSE = {}
SECTOR_MAP = {}
_DATA = {}
try:
    _DATA = json.load(open(_UNIVERSE_FILE))
    universe_base = _DATA.get('universe', {})
    dynamic = _DATA.get('dynamic_additions', [])
    combined = dict(universe_base)
    if isinstance(dynamic, list):
        for item in dynamic:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                combined[item[0]] = item[1]
    for sym, sec in combined.items():
        SECTOR_MAP[sym] = sec
        UNIVERSE.setdefault(sec, []).append(sym)
except Exception as e:
    print(f'⚠️ 无法加载 scan_universe.json: {e}', file=sys.stderr)
    # Minimal fallback
    UNIVERSE = {'tech': ['SPY'], 'ai': ['QQQ']}
    SECTOR_MAP = {'SPY': 'tech', 'QQQ': 'ai'}

TARGET_ALLOC = _DATA.get('target_alloc', {
    'tech': 20.0, 'ai': 15.0, 'finance': 12.0, 'consumer': 10.0, 'pharma': 8.0,
    'industrial': 8.0, 'energy': 7.0, 'defense': 5.0, 'resources': 5.0,
    'space': 5.0, 'telecom': 5.0
})

# ═══ Fetch live data ═══
account = api_get('/v2/account')
positions = api_get('/v2/positions')
orders = api_get('/v2/orders?status=open&limit=50')
all_orders = api_get('/v2/orders?status=all&direction=desc&limit=200')

equity = float(account['equity'])
cash = float(account['cash'])
last_equity = float(account.get('last_equity', equity))
drawdown = (equity / last_equity - 1) * 100 if last_equity else 0
utilization = ((equity - cash) / equity * 100) if equity > 0 else 0

# ═══ Market env ═══
try:
    me = json.load(open(f'{DATA_DIR}/market_env.json'))
    macro = me.get('macro', {})
    breadth = me.get('breadth', {})
    regime = macro.get('regime', 'unknown')
    vix_val = macro.get('vix', 0)
    dxy_val = macro.get('dxy', 0)
    spread_val = macro.get('spread', 0)
    b_summary = breadth.get('summary', {}) if isinstance(breadth, dict) else {}
    pct_ma50 = b_summary.get('pct_above_ma50', 0)
    advancers = b_summary.get('advancers', 0)
    decliners = b_summary.get('decliners', 0)
    new_highs = b_summary.get('new_highs', 0)
    new_lows = b_summary.get('new_lows', 0)
except:
    regime = 'unknown'
    vix_val = dxy_val = spread_val = pct_ma50 = advancers = decliners = new_highs = new_lows = 0

# ═══ FOMC ═══
fomc_dates = [datetime(2026,1,28), datetime(2026,3,18), datetime(2026,5,6),
              datetime(2026,6,17), datetime(2026,7,29), datetime(2026,9,16),
              datetime(2026,11,4), datetime(2026,12,16)]
now = datetime.now()
future = [d for d in fomc_dates if d > now]
fomc_days = (future[0] - now).days if future else -1
fomc_just_passed = any((now - d).days in (0,1) for d in fomc_dates)

# ═══ Watchlist ═══
try:
    wl = json.load(open(f'{DATA_DIR}/us_watchlist.json'))
    buy_candidates = wl.get('buy_candidates', [])
    kelly_allocations = wl.get('kelly_allocations', {})
    all_ranked = wl.get('all_ranked', [])
    critical_alerts = wl.get('critical_alerts', [])
except:
    buy_candidates = []; kelly_allocations = {}; all_ranked = []; critical_alerts = []

# ═══ Scan log (full fields) ═══
try:
    slog = json.load(open(f'{DATA_DIR}/us_screener_log.json'))
    scan_results = slog.get('results', [])
    scan_errors = slog.get('errors', [])
except:
    scan_results = []; scan_errors = []

# Build scan lookup by symbol
scan_by_sym = {}
for r in scan_results:
    scan_by_sym[r['symbol']] = r

# ═══ Risk state ═══
try:
    risk_state = json.load(open(f'{DATA_DIR}/us_risk_state.json'))
    risk_positions = risk_state.get('positions', {})
except:
    risk_positions = {}

# ═══ Signal decay ═══
try:
    sd = json.load(open(f'{DATA_DIR}/signal_decay.json'))
    decay_alerts = {a.get('symbol'): a for a in sd.get('alerts', [])}
except:
    decay_alerts = {}

# ═══ Recent stops ═══
try:
    rs = json.load(open(f'{DATA_DIR}/us_recent_stops.json'))
    recent_stop_syms = {item.get('symbol','') for item in rs}
except:
    recent_stop_syms = set()

# ═══ Stop coverage ═══
stop_syms = {o['symbol'] for o in orders if o.get('type') == 'stop' and o.get('side') == 'sell'}
has_open_sell = {o['symbol'] for o in orders if o.get('side') == 'sell' and o.get('type') != 'stop'}
protected = stop_syms | has_open_sell
position_syms = {p['symbol'] for p in positions}
ghost_stops = stop_syms - position_syms
unprotected = position_syms - protected

# ═══ OUTPUT ═══
dt = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
print(f'# Eagle Eye Daily Review Package\n')
print(f'**Generated**: {dt} BJT | Market: {"OPEN" if datetime.now(timezone(timedelta(hours=-4))).hour >= 9 else "CLOSED"}\n')
print('---\n')

# ━━ 1. Portfolio Snapshot ━━
print('## 1. Portfolio Snapshot\n')
print(f'| Field | Value |')
print(f'|-------|-------|')
print(f'| Date | {datetime.now().strftime("%Y-%m-%d")} |')
print(f'| Total Equity | ${equity:,.2f} |')
print(f'| Cash | ${cash:,.2f} |')
print(f'| Exposure | {utilization:.1f}% |')
print(f'| Active Sectors | {len(active_sectors := set(SECTOR_MAP.get(p["symbol"], "unknown") for p in positions))} |')
print(f'| Drawdown | {drawdown:+.2f}% |')
print(f'| Holding Count | {len(positions)} |')

print()
print('| Symbol | Shares | Mkt Value | Cost Basis | P&L % | Sector | Weight % | Stop % | Signal |')
print('|--------|--------|-----------|------------|-------|--------|----------|--------|--------|')
for p in positions:
    sym = p['symbol']
    qty = int(float(p['qty']))
    mv = float(p['market_value'])
    cost = float(p['cost_basis'])
    pnl_pct = float(p['unrealized_plpc']) * 100
    sector = SECTOR_MAP.get(sym, 'unknown')
    weight = mv / equity * 100
    da = decay_alerts.get(sym, {})
    decay_level = da.get('level', 'CLEAN')
    print(f'| {sym} | {qty} | ${mv:,.0f} | ${cost:,.0f} | {pnl_pct:+.1f}% | {sector} | {weight:.1f}% | 8% | {decay_level} |')

print()

# ━━ 2. Sector Distribution ━━
print('## 2. Sector Distribution\n')
print('| Sector | Weight % | Target % | Gap % | Status | Holdings |')
print('|--------|----------|----------|-------|--------|----------|')
sector_values = {}
sector_counts = {}
for p in positions:
    sec = SECTOR_MAP.get(p['symbol'], 'unknown')
    sector_values[sec] = sector_values.get(sec, 0) + float(p['market_value'])
    sector_counts[sec] = sector_counts.get(sec, 0) + 1
for sec in sorted(TARGET_ALLOC.keys()):
    sv = sector_values.get(sec, 0)
    weight = sv / equity * 100
    target = TARGET_ALLOC[sec]
    gap = weight - target
    status = 'UNDERWEIGHT' if gap < -2 else ('OVERWEIGHT' if gap > 2 else 'NORMAL')
    count = sector_counts.get(sec, 0)
    print(f'| {sec} | {weight:.1f}% | {target:.1f}% | {gap:+.1f}% | {status} | {count} |')
print()

# ━━ 3. Market Environment ━━
print('## 3. Market Environment\n')
print(f'| Indicator | Value | Status |')
print(f'|-----------|-------|--------|')
print(f'| Regime | {regime} | {"⚠️ FOMC just passed" if fomc_just_passed else "Normal"} |')
print(f'| VIX | {vix_val} | {"Calm" if vix_val < 20 else "Elevated"} |')
print(f'| DXY | {dxy_val} | — |')
print(f'| 10Y-2Y Spread | {spread_val} | — |')
print(f'| Breadth (%>MA50) | {pct_ma50}% | — |')
print(f'| Advancers/Decliners | {advancers}/{decliners} | — |')
print(f'| New Highs/Lows | {new_highs}/{new_lows} | — |')
print(f'| Days to next FOMC | {fomc_days} | — |')
print()

# ━━ 4. Candidate Universe ━━
print('## 4. Candidate Universe (Top 10)\n')
print('| # | Symbol | Sector | Score | RSI | Vol | MACD | RS vs SPY | ATR% | Vol20d | Kelly% | Win% | Leader |')
print('|---|--------|--------|-------|-----|-----|------|-----------|------|--------|--------|------|--------|')
for i, c in enumerate(buy_candidates[:10]):
    sym = c if isinstance(c, str) else c.get('symbol', '?')
    sr = scan_by_sym.get(sym, {})
    ka = kelly_allocations.get(sym, {}) if isinstance(kelly_allocations, dict) else {}
    sec = sr.get('sector', SECTOR_MAP.get(sym, '?'))
    score = sr.get('momentum_score', 0)
    rsi = sr.get('rsi14', '?')
    vol_sig = sr.get('vol_signal', '?')
    macd = sr.get('macd_signal', '?')
    rs_sig = sr.get('rs_signal', '?')
    atr_pct = sr.get('atr_pct', '?')
    vol20d = sr.get('vol_20d', '?')
    kelly_pct = ka.get('kelly_pct', 0)
    win_prob = ka.get('win_prob', 0)
    leader = '👑 YES' if sr.get('sector_leader') else 'NO'
    print(f'| {i+1} | {sym} | {sec} | {score:.0f} | {rsi} | {vol_sig} | {macd} | {rs_sig} | {atr_pct}% | {vol20d}% | {kelly_pct:.1f}% | {win_prob:.1%} | {leader} |')
print()

# ━━ 5. Risk Audit ━━
print('## 5. Risk Audit\n')
print('| Symbol | Stop Covered | Stop % | Ghost | Unprotected | Blacklisted | Signal Decay |')
print('|--------|--------------|--------|-------|-------------|-------------|-------------|')
for p in positions:
    sym = p['symbol']
    cov = 'YES' if sym in protected else 'NO'
    ghost = 'YES' if sym in ghost_stops else 'NO'
    unprot = 'YES' if sym in unprotected else 'NO'
    black = 'YES' if sym in recent_stop_syms else 'NO'
    da = decay_alerts.get(sym, {})
    decay = da.get('level', 'CLEAN')
    reasons = da.get('reasons', [])
    decay_str = decay if decay == 'CLEAN' else f'{decay} ({"; ".join(reasons)})'
    print(f'| {sym} | {cov} | 8% | {ghost} | {unprot} | {black} | {decay_str} |')
print()

# ━━ 6. Pending Orders ━━
print('## 6. Pending Orders\n')
print('| Symbol | Side | Qty | Type | Created | Status |')
print('|--------|------|-----|------|---------|--------|')
for o in orders:
    if o['status'] in ('new', 'accepted', 'pending_new'):
        print(f'| {o["symbol"]} | {o["side"]} | {o["qty"]} | {o["type"]} | {o.get("created_at","")[0:10]} | {o["status"]} |')
print()

# ━━ 7. Policy Status ━━
print('## 7. Policy Status\n')
violations = []
checks = [('Exposure ≤ 85%', utilization <= 85),
          ('Single Pos ≤ 20%', all(float(p['market_value'])/equity*100 <= 20 for p in positions)),
          ('Min 3 Sectors', len(active_sectors) >= 3),
          ('No Naked Positions', len(unprotected) == 0),
          ('No Ghost Orders Ignored', len(ghost_stops) == 0),
          ('FOMC Rules Followed', not fomc_just_passed or utilization <= 85)]
print('| Policy | Status | Detail |')
print('|--------|--------|--------|')
for name, ok in checks:
    print(f'| {name} | {"PASS" if ok else "FAIL"} | — |')
    if not ok:
        violations.append(name)
print(f'\n**Violations**: {len(violations)} ({", ".join(violations) if violations else "CLEAN"})')
print()

# ━━ 8. Dashboard — Decision Rationale ━━
print('## 8. Dashboard — Decision Rationale\n')
print('### Market Context')
print(f'- **Regime**: {regime} — ', end='')
if regime == 'NORMAL':
    print('Standard rules apply. No FOMC override.')
elif regime == 'CAUTIOUS':
    print('Elevated caution. Defense sectors get bonus. Position sizing conservative.')
elif regime == 'CRISIS':
    print('Crisis mode. No new positions. Mechanical stops only.')
else:
    print('Unknown regime. Defaulting to cautious.')
print(f'- **VIX {vix_val}**: ', end='')
if vix_val < 20:
    print('Low volatility. Standard stop-loss (8%).')
elif vix_val < 30:
    print('Elevated. Volatility stops widened to upper tier.')
else:
    print('High. Maximum stop width (10%).')
print(f'- **FOMC**: {fomc_days} days until next meeting. ', end='')
if fomc_just_passed:
    print('⚠️ FOMC just passed — no new positions until market digests.')
else:
    print('Standard trading allowed.')
print()

print('### Sector View')
underweight_sectors = []
overweight_sectors = []
for sec in sorted(TARGET_ALLOC.keys()):
    sv = sector_values.get(sec, 0)
    weight = sv / equity * 100
    target = TARGET_ALLOC[sec]
    if weight < target - 2:
        underweight_sectors.append((sec, target - weight))
    elif weight > target + 2:
        overweight_sectors.append((sec, weight - target))
if underweight_sectors:
    print(f'- **Underweight**: {", ".join(f"{s}(-{g:.1f}%)" for s,g in underweight_sectors[:5])}')
if overweight_sectors:
    print(f'- **Overweight**: {", ".join(f"{s}(+{g:.1f}%)" for s,g in overweight_sectors[:3])}')
if not underweight_sectors and not overweight_sectors:
    print('- All sectors within target range.')
print()

print('### Signal Summary')
for p in positions:
    sym = p['symbol']
    da = decay_alerts.get(sym, {})
    if da.get('level') == 'CRITICAL':
        print(f'- ⛔ **{sym}** (CRITICAL): {"; ".join(da.get("reasons",[]))}')
for p in positions:
    sym = p['symbol']
    da = decay_alerts.get(sym, {})
    if da.get('level') == 'WARNING':
        print(f'- ⚠️ **{sym}** (WARNING): {"; ".join(da.get("reasons",[]))}')
print()

print('### Event Context')
if critical_alerts:
    print(f'- **Critical Alerts**: {len(critical_alerts)} pending')
    for a in critical_alerts[:5]:
        print(f'  - {a}')
else:
    print('- No critical events.')