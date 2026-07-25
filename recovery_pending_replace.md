# Recovery: Stop Order Pending_Replace Deadlock
## Created: 2026-06-29 00:40 BJT

## Root Cause
PATCH operations on stop orders during closed market (Sunday ET) created replacement chains that Alpaca can't resolve until market open.

- DIS: PATCH 30→1, then tried PATCH 1→30 (failed 422)
- AMAT: PATCH 20→13, then tried PATCH 13→20 (failed 422)

## Current State
- DIS: 30 shares held, 1 active stop (qty=1 @ $94.85), 30 pending_replace
- AMAT: 20 shares held, 13 active stop (qty=13 @ $506.13), 20 pending_replace
- All other 7 positions: ✅ fully covered

## Fix (execute at market open - BJT 21:30+)

```python
import requests, os

env = dict(...)
base = env.get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
headers = {'APCA-API-KEY-ID': env.get('ALPACA_API_KEY',''), 'APCA-API-SECRET-KEY': env.get('ALPACA_SECRET_KEY','')}

# Step 1: Cancel the small active stops (these are the replacements)
# DIS: cancel qty=1 stop
orders = requests.get(f'{base}/v2/orders?status=open&symbols=DIS', ...).json()
for o in orders:
    if o['type'] == 'stop' and o['qty'] == '1' and o['status'] == 'new':
        requests.delete(f'{base}/v2/orders/{o["id"]}', ...)
        print(f'Cancelled DIS qty=1 stop')

# AMAT: cancel qty=13 stop
orders = requests.get(f'{base}/v2/orders?status=open&symbols=AMAT', ...).json()
for o in orders:
    if o['type'] == 'stop' and o['qty'] == '13' and o['status'] == 'new':
        requests.delete(f'{base}/v2/orders/{o["id"]}', ...)
        print(f'Cancelled AMAT qty=13 stop')

# Step 2: Place fresh stops at full qty
# DIS: stop 30 @ $94.85
requests.post(f'{base}/v2/orders', json={
    'symbol': 'DIS', 'qty': 30, 'side': 'sell',
    'type': 'stop', 'stop_price': '94.85', 'time_in_force': 'gtc'
}, ...)

# AMAT: stop 20 @ $506.13
requests.post(f'{base}/v2/orders', json={
    'symbol': 'AMAT', 'qty': 20, 'side': 'sell',
    'type': 'stop', 'stop_price': '506.13', 'time_in_force': 'gtc'
}, ...)
```

## Risk
- Between now (00:40 BJT Mon) and market open (21:30 BJT Mon):
  - DIS: 29/30 shares unprotected — gap risk of ~$2,741 (29 × $94.85)
  - AMAT: 7/20 shares unprotected — gap risk of ~$3,542 (7 × $506.13)
- Market is closed → no intraday risk, only overnight gap risk
