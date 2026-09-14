# Eagle Eye Execution Layer — Constitutional Review

**Date**: 2026-07-05  
**Constitution**: Eagle Eye Execution Constitution v1.0  
**Reviewer**: Hermes Agent (deepseek-v4-pro)  
**Scope**: `eagle_eye/execution/`, `eagle_eye/broker/`, `eagle_eye/risk/`

---

## 1. Current Responsibilities of TradeExecutor

### File: `execution/trade_executor.py` (583 lines)

| # | Responsibility | Lines | Correct Layer? | Verdict |
|:--|:---|---|:---:|:---:|
| 1 | `load_event_buy_signals()` — parse market_events JSON, extract ticker/priority | 55–75 | ❌ Strategy | **Must Move** |
| 2 | `load_negative_bias_set()` — extract 🔴-marked symbols from event data | 77–84 | ❌ Strategy | **Must Move** |
| 3 | `get_buy_threshold()` — determine min buy_score based on utilization + event priority | 86–90 | ❌ Portfolio/Strategy | **Must Move** |
| 4 | `check_account_risk()` — drawdown calculation, emergency halving, audit logging | 111–137 | ❌ Risk | **Must Move** |
| 5 | `check_position_utilization()` — mode→target_util mapping, gap calculation | 139–148 | ❌ Portfolio | **Must Move** |
| 6 | `v7_safety_check()` — thin wrapper: lock + degraded + clock | 155–169 | ✅ Orchestration | OK |
| 7 | `_block_buys()` — thin delegation to lock/degraded | 171–172 | ✅ Orchestration | OK |
| 8 | `main()` — event-driven buys (209–216) | — | ❌ Strategy | **Must Move** |
| 9 | `main()` — sell→buy pair logic (219–241) | — | ❌ Portfolio | **Must Move** |
| 10 | `main()` — add-to-existing holdings (244–256) | — | ❌ Portfolio | **Must Move** |
| 11 | `main()` — hard constraint forced deployment (261–296) | — | ❌ Portfolio | **Must Move** |
| 12 | `main()` — screener-based new buys (302–326) | — | ❌ Strategy | **Must Move** |
| 13 | `main()` — report rendering (331–361) | — | ⚠️ Presentation | Borderline |
| 14 | `report_mode()` — data marshalling for JSON report | 368–407 | ✅ Orchestration | OK |
| 15 | `execute_mode()` — P0 guardrail chain + order submission | 410–526 | ✅ Orchestration | OK |
| 16 | `stops_mode()` — stop/TP/trail orchestration | 529–560 | ✅ Orchestration | OK |
| 17 | `run_cli()` — CLI argument parsing | 567–583 | ✅ Orchestration | OK |

### Summary

TradeExecutor currently owns **11 items that violate Rule 1** (business logic, not orchestration). It is a 583-line god object. It directly calculates:

- Drawdown thresholds and emergency actions
- Position utilization targets and gaps
- Buy thresholds and event signal scoring
- Sell→buy pairing logic with budget allocation
- Hard constraint deployment with candidate ranking
- Screener-based buy candidate selection

**These must be extracted before new execution functionality is added.**

### File: `execution/position_manager.py` (314 lines)

| # | Responsibility | Lines | Correct Layer? | Verdict |
|:--|:---|---|:---:|:---:|
| 1 | State file load/save (`load_state`, `save_state`) | 36–50 | ✅ Position | OK |
| 2 | Highest price tracking (`get_highest`, `set_highest`) | 53–80 | ✅ Position | OK |
| 3 | Trail stop calculation (`get_trail_stop`) | 83–95 | ✅ Position | OK |
| 4 | Sector mapping (`SECTOR_MAP`, `get_sector`) | 100–115 | ✅ Position | OK |
| 5 | Data fetching (`__get_daily_bars`, `__get_us_price`, `__get_volatility`, `get_bars`) | 120–161 | ⚠️ Infrastructure | Borderline |
| 6 | **`analyze()` — full technical analysis** | 166–255 | ❌ Strategy | **MUST MOVE** |
| 7 | **`tech_snapshot()` — batch technical snapshot** | 261–314 | ❌ Strategy | **Must Move** |

### Summary

PositionManager violates Rule 3. `analyze()` is a 90-line function that computes:

- RSI(14) with buy/sell signal thresholds
- Bollinger Bands(20) with position scoring
- SMA(5/20) with trend classification
- Volume metrics with confirmation scoring (+2/-2/-1)
- MACD with crossover detection (+3/-2/+1)
- ATR calculation
- 20-day volatility
- Buy score aggregation (0→+8 typical range)
- Sell reason generation (RSI extreme + drawdown)

This is a **full strategy engine** living inside a position-state module. It belongs in `strategy/indicator_engine.py` or a new `strategy/scorer.py`.

---

## 2. Proposed Responsibilities After Refactoring

### TradeExecutor → Orchestrator Only

```python
# trade_executor.py — AFTER refactoring (~150 lines max)

def main(mode='normal'):
    """Orchestrate: gather data → delegate → present results."""
    safety = v7_safety_check()
    if safety['trading_locked']:
        return report_locked(safety)

    # 1. Gather
    state = load_position_state()
    acct, equity, cash = get_portfolio()
    holdings = get_holdings()
    risk_state = risk.check_account_risk(equity, cash, state, holdings)  # ← moved to risk/
    portfolio_state = portfolio.evaluate(equity, cash, holdings, mode)    # ← moved to portfolio/

    # 2. Delegate (no business logic here)
    trail_results = stop_loss_manager.update(holdings, state)            # ← stays in execution/
    tp_results = take_profit_manager.execute(holdings, state)             # ← stays in execution/
    buy_orders = portfolio.generate_buy_orders(                           # ← NEW in portfolio/
        equity, cash, holdings, risk_state, portfolio_state
    )

    # 3. Execute buy orders (orchestration only)
    buy_results = [execute_single(o) for o in buy_orders if portfolio.can_buy(o)]

    # 4. Report
    save_position_state(state)
    return render_report(equity, cash, holdings, trail_results, tp_results, buy_results)

# report_mode() — unchanged (already pure marshalling)
# execute_mode() — unchanged (already pure orchestration + P0 guardrails)
# stops_mode() — unchanged (already pure orchestration)
```

### New Modules to Create

| New Module | Extracts From | Extracted Functions |
|---|---|---|
| `strategy/event_signals.py` | trade_executor L55–90 | `load_event_buy_signals`, `load_negative_bias_set`, `get_buy_threshold` |
| `risk/account_risk.py` | trade_executor L111–148 | `check_account_risk`, `check_position_utilization` |
| `portfolio/buy_engine.py` | trade_executor L207–326 | All buy logic: event buys, sell→buy pair, add-to-existing, hard constraint, screener buys |
| `strategy/scorer.py` | position_manager L166–255 | `analyze()` — ALL technical indicator computation + buy/sell signal generation |
| `strategy/tech_snapshot.py` | position_manager L261–314 | `tech_snapshot()` — batch technical snapshot |

### PositionManager → Pure Position State

After extracting `analyze()` and `tech_snapshot()`:

```python
# position_manager.py — AFTER refactoring (~160 lines)

# State management
load_state() / save_state()
get_highest() / set_highest()
get_trail_stop()

# Metadata
SECTOR_MAP / get_sector()

# Data access (thin wrappers around AlpacaClient)
get_bars() / get_daily_bars()
get_us_price()
get_volatility()
```

**No strategy calculations. No buy/sell scores. No signal generation. Only position state + data access.**

---

## 3. Dependency Graph

### Current (Before Refactoring)

```
trade_executor.py (583 lines — GOD OBJECT)
├── imports strategy/indicator_engine (calc_rsi, get_volatility_stop_pct)
├── contains risk logic (check_account_risk, check_position_utilization)
├── contains strategy logic (event signals, buy thresholds)
├── contains portfolio logic (sell→buy pair, hard constraint, screener buys)
├── delegates to position_manager (analyze, get_sector, etc.)
├── delegates to order_manager (get_portfolio, place_market_order, etc.)
├── delegates to stop_loss_manager (update_trail_stops, stop_coverage_audit)
└── delegates to take_profit_manager (execute_take_profit)

position_manager.py (314 lines)
├── contains strategy logic (analyze: RSI, MACD, Bollinger, volume, scoring)
├── contains tech analysis (tech_snapshot)
├── delegates to strategy/indicator_engine (calc_rsi, calc_sma, etc.)
└── delegates to broker/alpaca_client (get_bars, get_last_price)

stop_loss_manager.py ← depends on position_manager (get_highest, get_trail_stop)
take_profit_manager.py ← depends on position_manager (get_trail_stop)
order_manager.py ← only depends on broker/alpaca_client
```

### Proposed (After Refactoring)

```
trade_executor.py (~150 lines — PURE ORCHESTRATOR)
├── risk/account_risk.py              ← check_account_risk, drawdown alerts
├── portfolio/evaluator.py            ← check_position_utilization, gap analysis
├── portfolio/buy_engine.py           ← ALL buy decision logic
├── strategy/event_signals.py         ← event parsing, bias extraction
├── strategy/scorer.py                ← analyze(), buy/sell signal generation
├── strategy/tech_snapshot.py         ← batch technical snapshot
├── execution/position_manager.py     ← PURE position state (no strategy!)
├── execution/order_manager.py        ← Alpaca order CRUD
├── execution/stop_loss_manager.py    ← trail stop + coverage audit
├── execution/take_profit_manager.py  ← TP execution
├── execution/order_intent.py         ← data carrier (unchanged)
├── execution/order_state_machine.py  ← state tracking (unchanged)
├── execution/candidate_tracker.py    ← multi-cycle confirmation (unchanged)
├── risk/policy_validator.py          ← P0 guardrails (unchanged)
├── risk/trading_lock.py              ← trading lock (unchanged)
└── risk/degraded_mode.py             ← degraded mode (unchanged)

Clean dependency flow:
  strategy/ ─── provides signals, scores ───→ portfolio/
  portfolio/ ─── generates buy orders ──────→ execution/trade_executor
  execution/  ─── orchestrates, never calculates
  risk/       ─── validates, never decides
  broker/     ─── communicates, never reasons
```

---

## 4. Confirmation: Broker Stop Protection

### Current Violations

**Violation 1: `stop_loss_manager.update_trail_stops()` (line 125–131)**

```python
# CURRENT: Cancel broker stop BEFORE market sell — UNCOVERED WINDOW
stop_order = existing_stops.get(sym)
if stop_order:
    cancel_order(stop_order['id'])      # ← Broker protection REMOVED
    time.sleep(0.3)                      # ← 300ms gap with NO protection
order = place_market_order(sym, int(qty), 'sell')  # ← May fail here
```

**Violation 2: `take_profit_manager.execute_take_profit()` (line 109–114)**

```python
# CURRENT: Cancel broker stop BEFORE market sell — UNCOVERED WINDOW
stop_order = existing_stops.get(sym)
if stop_order:
    cancel_order(stop_order['id'])      # ← Broker protection REMOVED
    time.sleep(0.3)                      # ← 300ms gap with NO protection
order = place_market_order(sym, sell_qty, 'sell')  # ← May fail here
```

### Root Cause

Alpaca's wash-trade protection (403: "potential wash trade detected") prevents placing a market sell while a stop order exists on the same symbol. This creates a fundamental tension:

**Constitution says**: "never delete broker stop before replacement"  
**Alpaca says**: "cannot sell while stop order exists"

### Proposed Resolution: "PATCH-First, Cancel-After" Pattern

Instead of Cancel→Sell, use PATCH→Sell→Cancel:

```
BEFORE (violation):
  CANCEL stop → 300ms gap → MARKET SELL → (may fail)

AFTER (constitutional):
  PATCH stop qty to (holdings - sell_qty) → MARKET SELL → CANCEL old stop
                                            ↑ still protected    ↑ cleanup
```

For full-position sale (sell_qty == holdings):
```
  PATCH stop qty to 1 → MARKET SELL (holdings - 1) → stop protects remaining 1
```

For partial sale (sell_qty < holdings):
```
  PATCH stop qty to (remaining) → MARKET SELL (sell_qty) → stop protects remainder
```

### Implementation

```python
def _sell_with_stop_protection(sym, sell_qty, holding_qty, cost, vol_20d, existing_stops):
    """Constitutional sell: never remove broker protection before execution."""
    remaining = holding_qty - sell_qty

    if sell_qty >= holding_qty:
        # Full sale: leave 1 share behind, protected by stop
        sell_qty = holding_qty - 1
        remaining = 1

    stop_order = existing_stops.get(sym)
    if stop_order:
        # Step 1: PATCH stop to protect remaining shares (keeps protection alive)
        from eagle_eye.broker.alpaca_client import get_alpaca_client
        get_alpaca_client().patch_order(stop_order['id'], {'qty': remaining})

    # Step 2: Sell with stop still protecting remainder
    order = place_market_order(sym, sell_qty, 'sell')

    if order and order.get('id'):
        # Step 3: Clean up old stop if needed, place fresh stop for remainder
        if stop_order and remaining > 0:
            cancel_order(stop_order['id'])  # Safe now — sell already executed
            new_stop = get_trail_stop(sym, state, cost, vol_20d=vol_20d)
            place_stop_order(sym, remaining, new_stop)
        return order
    return None
```

### Affected Functions

| Function | File | Fix |
|---|---|---|
| `update_trail_stops()` L125–131 | stop_loss_manager.py | PATCH-first pattern |
| `execute_take_profit()` L109–114 | take_profit_manager.py | PATCH-first pattern |

**Status: VIOLATION CONFIRMED. Fix required per Constitution Rule 2.**

### Note on Alpaca PATCH Constraints

- PATCH can only reduce qty (not increase)
- PATCH qty must be ≥ 1 (qty=0 rejected)
- PATCH in closed market → pending_replace chain → avoid (per existing rules)
- Therefore: PATCH-first pattern only applies during market hours. Outside market hours, defer sell to next open.

---

## 5. Confirmation: PositionManager State Ownership

### Current State

position_manager.py currently contains:

| Function | Type | Constitutional? |
|---|---|---|
| `load_state()`, `save_state()` | Position state I/O | ✅ Yes |
| `get_highest()`, `set_highest()` | Highest price tracking | ✅ Yes |
| `get_trail_stop()` | Stop price from position state | ✅ Yes |
| `get_sector()`, `SECTOR_MAP` | Position metadata | ✅ Yes |
| `__get_daily_bars()`, `__get_us_price()` | Data access (thin wrapper) | ⚠️ Borderline |
| `__get_volatility()` | Data-derived metric | ⚠️ Borderline |
| `get_bars()` | Hourly + daily bar fetch | ⚠️ Borderline |
| **`analyze()`** | **Full strategy — RSI, MACD, Bollinger, volume, scoring** | ❌ **VIOLATION** |
| **`tech_snapshot()`** | **Batch technical snapshot** | ❌ **VIOLATION** |

### Proposed State

```python
# position_manager.py — AFTER extraction

# ✅ POSITION STATE (keeps)
load_state()          → dict
save_state(state)     → None
get_highest(sym, state) → float
set_highest(sym, price, state, cost=None) → None
get_trail_stop(sym, state, cost, vol_20d=None) → float

# ✅ METADATA (keeps)
SECTOR_MAP           → dict
get_sector(sym)      → str

# ✅ DATA ACCESS (keeps — thin wrappers over AlpacaClient)
get_bars(sym, limit=30)           → list | None
__get_daily_bars(sym)             → list
__get_us_price(sym)               → float | None
__get_volatility(sym)             → float | None

# ❌ STRATEGY (moves to strategy/scorer.py)
analyze(sym)           → dict | None   → strategy/scorer.py
tech_snapshot(syms, max_show=10) → dict → strategy/tech_snapshot.py
```

**Status: VIOLATION CONFIRMED for `analyze()` and `tech_snapshot()`. Extraction required per Constitution Rule 3.**

---

## 6. Summary of Findings

| Rule | Status | Violation | Severity | Fix |
|:---:|:---:|---|---|:---:|
| **Rule 1** | ❌ VIOLATED | TradeExecutor contains 11 business-logic functions (event parsing, risk calculation, portfolio allocation, buy decision logic, drawdown emergency actions) | **HIGH** | Extract to `strategy/`, `risk/`, `portfolio/` modules |
| **Rule 2** | ❌ VIOLATED | `update_trail_stops()` and `execute_take_profit()` both cancel broker stops BEFORE executing market sells, creating uncovered windows | **CRITICAL** | Implement PATCH-first pattern: reduce stop qty before sell, cancel only after sell confirmed |
| **Rule 3** | ❌ VIOLATED | `position_manager.py::analyze()` is a 90-line strategy engine computing RSI/MACD/Bollinger/volume scoring | **HIGH** | Extract to `strategy/scorer.py` |
| **Rule 4** | ✅ COMPLIANT | This review was conducted before any implementation | — | — |
| **Rule 5** | ⚠️ RISK | Execution layer is at 583 lines (TradeExecutor) + 314 lines (PositionManager) with scope creep; future additions without refactoring will worsen | **MEDIUM** | Refactor before adding features per Constitution |

### Priority

1. **CRITICAL — Rule 2**: Broker stop protection gap (security risk, immediate)
2. **HIGH — Rule 1**: TradeExecutor god object extraction (architectural debt, blocks future work)
3. **HIGH — Rule 3**: PositionManager strategy logic extraction (architectural clarity)
4. **MEDIUM — Rule 5**: Freeze new execution features until refactoring complete

### Next Steps

1. **Do not modify `trade_executor.py` or `position_manager.py`** until this review is approved
2. Create extraction plan for all identified violations
3. Implement Rule 2 fix (PATCH-first pattern) as a standalone patch — zero strategy changes
4. Extract strategy logic from PositionManager to `strategy/scorer.py`
5. Extract business logic from TradeExecutor to dedicated modules
6. Verify all extractions via behavior fingerprint comparison (shadow_mode)
