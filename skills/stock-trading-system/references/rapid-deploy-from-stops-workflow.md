# Rapid Deployment from Stops — Cron Workflow (2026-07-03 Verified)

## Trigger

A single `--stops` tick liquidates **multiple positions** (trail stop + TP double-fire), creating a large cash spike (>$5K). Utilization drops below 25%. The cron session must deploy immediately into gap sectors, handle the double-fire shorts, and re-arm stops — all in one tick.

## Sequence (verified 2026-07-03: 4 stops + 3 seed buys + 4 short closes + full rearm in <5 min)

### Phase 1: Collect Real-Time State

Ignore stale report data. Pull fresh from Alpaca immediately after `--stops`:

```python
positions = requests.get(f'{base}/v2/positions', headers=headers, timeout=30).json()
acct = requests.get(f'{base}/v2/account', headers=headers, timeout=30).json()
```

**Check for unintended shorts first** — the #1 risk from double-fire:

```python
shorts = [p for p in positions if int(float(p['qty'])) < 0]
if shorts:
    # Priority 0: close all shorts before doing anything else
    for p in shorts:
        requests.post(f'{base}/v2/orders', json={
            'symbol': p['symbol'], 'qty': str(abs(int(float(p['qty'])))),
            'side': 'buy', 'type': 'market', 'time_in_force': 'day'
        }, headers=headers, timeout=15)
```

The shorts consume no net cash (the double-sell deposited, the buy-to-close withdraws the same), but they MUST be closed first because they affect equity, buying power, and sector calculations.

### Phase 2: Assess Sector Gaps After Losses

Compute active sectors from real-time positions. The policy validator may report fewer active sectors than you calculate — do NOT debug the discrepancy, just route through seed position path. Key question: which sector(s) were just liquidated? Fill those first.

**2026-07-03 instance:** 4 tech/ai stops (AMAT, AMD, ARM, INTC) → tech from 9.7% → 0%. Clear gap.

### Phase 3: Pre-Screen Candidates for Seed Eligibility

For each gap-fill candidate, pull real-time bars and calculate RSI **before** submitting any order:

```python
from us_common import get_daily_bars, calc_rsi
bars = get_daily_bars(sym, api_key, secret, days=30)
rsi = calc_rsi([b['c'] for b in bars], 14)
if 40 <= rsi <= 70:
    # seed-eligible
```

Do NOT trust report RSI values — they may be stale by 30-60 min.

**Seed gate (from policy_validator) blocks if:**
- RSI < 40 or > 70 (strict)
- Missing `rsi` or `sector` fields in order JSON
- Sector not a gap (already ≥3%)

For buys that fail the RSI gate (e.g. BAC at 71.0, XOM at 25.4), record a DEPLOY_GAP note and move on. They will become eligible in a future tick when RSI shifts.

### Phase 4: Create Dashboard + Submit Seed Orders

If `dashboard_{date}.md` doesn't exist, create one. Provide trade intent and reason for each seed order. Submit with `_seed: true`, `rsi`, `sector` fields:

```json
{"symbol": "MU", "qty": 10, "side": "buy",
 "_seed": true, "rsi": 48.6, "sector": "tech",
 "reason": "Fill tech gap after 4 tech stops"}
```

Submit all seed orders in a single `--execute` call. The policy validator processes each independently — passing ones execute, failing ones reject without affecting the batch.

### Phase 5: Post-Trade Cleanup (Critical)

Within the same tick, **immediately after `--execute` confirms submission**:

1. **Set `highest = entry_cost` in risk_state** for each new position (prevents false drawdown sells next --stops tick):

```python
state = json.load(open(risk_path))
for sym in new_positions:
    if sym in state.get('positions', {}):
        state['positions'][sym]['highest'] = entry
        state['positions'][sym]['tp1_done'] = False
        state['positions'][sym]['tp2_done'] = False
```

2. **Remove liquidated positions from risk_state** (their stale highest would corrupt future calculations if symbols are re-bought):

```python
active_syms = {p['symbol'] for p in positions if int(float(p['qty'])) > 0}
for sym in list(state.get('positions', {}).keys()):
    if sym not in active_syms:
        del state['positions'][sym]
```

3. **Place stop orders for new positions** (use volatility-based pricing):

```
MU: 10% stop (V136% tech)
COHR: 10% stop (V107% tech)
LMT: 9% stop (V37% defense)
```

4. **Verify all positions have coverage** — check stop+sell qty >= position qty for every active position.

### Phase 6: Count the Cash Paradox

Calculate net cash change:

```
net_deployment = cash_before_stops - cash_after_seed_buys
```

If net_deployment < 0 (more deployed than freed), Cash Paradox satisfied. If net > $2K (freed more than deployed), add a DEPLOY_GAP note.

## Example Metrics (2026-07-03)

| Metric | Before | After |
|--------|:------:|:-----:|
| Equity | $103,652 | $103,569 |
| Cash | $69,667 | $68,074 |
| Utilization | 20.9% | 34.3% |
| Positions | 14 | 13 |
| Stops triggered | — | 4 full + 1 partial |
| Shorts created | 0 | 4 (immediately closed) |
| New seed buys | — | 3 (MU/COHR/LMT) |
| Net deployed | — | $13,919 |
| Stop coverage | partial | 100% |

## Sector Filling Summary (2026-07-03)

| Sector | Pre-loss | Post-stops | Post-buys | Delta |
|--------|:--------:|:----------:|:---------:|:-----:|
| Tech | 9.7% | 0% | 5.4% | -4.3% (still rebuilding) |
| Defense | 0% | 0% | 1.6% | +1.6% (new) |
| AI/cloud | 7.3% | 5.5% | 5.5% | -1.8% (ARM lost) |
| Energy | 0% | 0% | 0% | — (gap persists, RSI too low for seed) |

## Pitfalls

- **Do NOT re-buy stopped-out symbols** (7-day blacklist: AMAT, AMD, ARM, INTC are blocked from re-entry)
- **Seed positions bypass multi-cycle candidate confirmation** (Gate 2) but still must pass RSI + sector + exposure gates
- **Partial seed batch execution** is normal — some pass, some reject. Rejected ones need a separate future tick when RSI or market conditions change
- **When Active Sectors < 4**, EVERY order needs seed fields, even sells. Sell orders skip the gap-sector check but still need `_seed: true`, `rsi`, `sector`.
