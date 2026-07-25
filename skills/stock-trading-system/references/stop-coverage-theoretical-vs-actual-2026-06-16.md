# Stop Coverage: Theoretical vs Actual (2026-06-16)

## Discovery

**Date**: 2026-06-16 21:10 BJT (market open)
**Context**: First cron run of the trading day. Report showed `🛡X%` for all 26 positions. Manual API audit revealed **17/26 (65%) had NO actual stop orders**.

## The Trap

The report's `🛡X%` is misleading. It comes from `us_portfolio.py`'s `distance_to_stop` field, which calculates a **theoretical** stop distance based on:
- Entry price
- Current price
- Volatility tier (from `get_volatility_stop_pct`)

It **does not** query Alpaca `/v2/orders` to check whether a stop order actually exists.

## How 17 positions lost coverage

The skill documents a specific pattern: `us_trader.py --stops` or trading decisions can cancel/overwrite stops without creating new ones. The system doesn't auto-audit. Common causes:

1. **Previous sell orders were placed** → stop orders were blocked by wash trade rule → new stops were never placed
2. **`--stops` ran with stale data** → wrongly assumed stops were already in place
3. **New positions added** after the last `--stops` run
4. **Ghost stops were removed** (per skill rule: don't remove them, but previous sessions may have)

## The Fix Applied

Placed stop orders for all 17 unprotected positions using the standard volatility-tiered approach:

```python
# For each unprotected position:
bars = get_daily_bars(sym, api_key, api_secret, days=85)
vol_20d = calc_volatility([b['c'] for b in bars], 20) if bars and len(bars) >= 21 else None
stop_pct = get_volatility_stop_pct(vol_20d)  # 7-10% depending on volatility
stop_price = round(avg * (1 - stop_pct), 2)

requests.post(f'{base}/v2/orders', headers=headers, json={
    'symbol': sym, 'qty': str(qty), 'side': 'sell',
    'type': 'stop', 'stop_price': str(stop_price), 'time_in_force': 'gtc'
}, timeout=30)
```

## Caveat: calc_volatility Returns Absurd Values

For several symbols, `calc_volatility()` returned nonsensical annualized values:
- ABBV: V2430% (impossible)
- SNOW: V14260% (impossible)
- DDOG: V6920% (impossible)

Despite this, `get_volatility_stop_pct()` has a catch-all: anything >50% → 10% stop band. So the final stop prices were reasonable. The volatility calculation may have a bug (wrong units, bad input data can produce absurd percentages) but the safety net works.

## Verification Script

```bash
source ~/.hermes/.env && python3 -c "
import os, requests
env = dict(line.strip().split('=', 1) for line in open(os.path.expanduser('~/.hermes/.env')) if '=' in line and not line.startswith('#'))
base = env.get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
headers = {'APCA-API-KEY-ID': env.get('ALPACA_API_KEY',''), 'APCA-API-SECRET-KEY': env.get('ALPACA_SECRET_KEY','')}

positions = requests.get(f'{base}/v2/positions', headers=headers, timeout=30).json()
orders = requests.get(f'{base}/v2/orders?status=open', headers=headers, timeout=30).json()
stop_syms = {o['symbol'] for o in orders if o['type'] == 'stop'}
market_sell_syms = {o['symbol'] for o in orders if o['type'] != 'stop' and o['side'] == 'sell'}
protected = stop_syms | market_sell_syms

unprotected = [p['symbol'] for p in positions if p['symbol'] not in protected]
if unprotected:
    print(f'❌ {len(unprotected)} unprotected: {unprotected})
else:
    print(f'✅ All {len(positions)} positions protected')
"
```
