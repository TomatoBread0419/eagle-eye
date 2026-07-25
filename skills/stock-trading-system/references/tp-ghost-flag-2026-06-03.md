# Tiered TP "Ghost Flag" — ORCL Case 2026-06-03

**Class:** §8.5a silent failure mode
**Severity:** High — missed mechanical sell, profit not locked
**Root cause:** LLM in cron run set `state['ORCL_tp1_done'] = True` but never placed the actual sell order

## Symptoms (fingerprint)

```json
// us_risk_state.json
{
  "ORCL_tp1_done": true,        // ← LLM said it executed
  "ORCL_tp2_done": false
}

// But in market:
- position: ORCL qty=5 (unchanged from buy)
- open orders: sell ORCL stop qty=5 (NOT PATCHed to 4)
- last 24h fills for ORCL: zero
```

**Detection:** state flag says done, but filled-orders API shows no matching sell.

## Detection Script (paste into cron agent)

```python
import sys, json
sys.path.insert(0, '$HOME/stock_trader')
from us_trader import api_get, get_holdings

state = json.load(open('us_risk_state.json'))
ghosts = []
for sym in ['ORCL', 'IBM', 'AMAT']:  # expand to all positions
    if state.get(f'{sym}_tp1_done') or state.get(f'{sym}_tp2_done'):
        # check actual fill
        filled = api_get(f'/orders?status=filled&limit=20&after=2026-05-01T00:00:00Z')
        matches = [o for o in (filled or []) if o['symbol']==sym and o['side']=='sell']
        if not matches:
            h = next((p for p in get_holdings() if p['symbol']==sym), None)
            if h and h['pnl_pct'] > 18:
                ghosts.append((sym, h['pnl_pct']))
print('GHOST TPs detected:', ghosts)
```

## Recovery (mechanical, no user ask — §11.5 自主判断)

```python
# 1. PATCH stop qty 5 -> 4 (frees 1 share from held_for_orders)
url = TRADE_URL + '/orders/' + stop_id
data = json.dumps({'qty': '4'}).encode()
req = urllib.request.Request(url, data=data, headers=alpaca_headers, method='PATCH')
resp = urllib.request.urlopen(req, timeout=15)
# expect 200 with new order id

# 2. Place market sell of freed 1 share
result = place_market_order(sym, 1, 'sell', dedupe=True)
# expect 200 with pending_new status (will fill at next market open)

# 3. Update state
state[f'{sym}_tp1_executed_at'] = iso_now
state[f'{sym}_tp1_locked_profit'] = round((current - avg) * 1, 2)
json.dump(state, open('us_risk_state.json','w'), indent=2)
```

## Why PATCH is safe (not blocked by §8.2)

§8.2 死锁 applies to `pending_cancel` orders. PATCH on a healthy stop does NOT enter `pending_cancel` — it atomically replaces the order (new id) without the cancel/pend cycle. Alpaca accepts PATCH for qty reduction on `new` and `accepted` stop orders. Confirmed 2026-06-03 21:23 BJT for ORCL.

## What to do at market open (21:30 BJT)

The `pending_new` market sell will fill within the first minute of the 09:30 ET open. Monitor the filled-orders list at 21:35 BJT. If filled, update `highest` tracking in state (highest should still be $245.06 for the 4 remaining shares — same price level).

## Prevention (not yet implemented)

The proper fix is in us_trader.py: the TP check should run **before** the LLM prompt and use the **filled-orders API** as ground truth, not state flags. Specifically:

```python
# In us_trader.py, before any LLM reasoning about TP:
filled = api_get('/orders?status=filled&limit=100')
syms_with_real_tp1_fills = {o['symbol'] for o in filled if 'tp1' in o.get('client_order_id','')}

for h in get_holdings():
    if h['pnl_pct'] >= 20 and h['symbol'] not in syms_with_real_tp1_fills:
        # Real TP1 trigger, force execute
        sell_qty = max(1, int(h['qty'] * 0.33))
        patch_stop_qty(h['symbol'], h['qty'] - sell_qty)
        place_market_order(h['symbol'], sell_qty, 'sell')
```

Add `tp1` to the client_order_id when placing the sell so this verification works.

## Cross-references

- §8.5a — LLM override of generated TP signals (the underlying bug class)
- §8.5b — Ghost TP recovery (this file)
- §8.2 — Pending cancel deadlock (NOT triggered by PATCH)
- §11.5 — 自主判断权 (cron agent executes mechanical TP without asking)
