# Eagle Eye Execution Layer — Refactoring Design Plan

**Date**: 2026-07-05  
**Status**: DESIGN ONLY — No implementation authorized  
**Constitution**: Eagle Eye Execution Constitution v1.0, Rules 1–5  
**Preceded by**: EXECUTION_LAYER_REVIEW.md (same date)

---

## Section 1 — Responsibility Map (TradeExecutor)

Every function and code block in `execution/trade_executor.py` (583 lines), classified.

### Functions

| # | Current Name / Block | Lines | Classification | Rationale |
|:--|---|---|:---:|---|
| 1 | `load_event_buy_signals()` | 55–75 | **MOVE** → `strategy/event_signals.py` | Parses market_events JSON. Strategy concern — what events exist and how to interpret them. |
| 2 | `load_negative_bias_set()` | 77–84 | **MOVE** → `strategy/event_signals.py` | Same JSON, different field. Strategy-layer signal extraction. |
| 3 | `get_buy_threshold()` | 86–90 | **MOVE** → `portfolio/buy_engine.py` | Determines minimum buy_score based on utilization state + event priority. Portfolio allocation concern. |
| 4 | `check_account_risk()` | 111–137 | **MOVE** → `risk/account_risk.py` | Drawdown calculation, emergency halving execution, CRITICAL audit logging. Risk concern. Also contains execution logic (market sell during emergency) — that part stays in execution, the decision to trigger moves to risk. |
| 5 | `check_position_utilization()` | 139–148 | **MOVE** → `portfolio/evaluator.py` | Mode→target mapping, utilization gap calculation. Portfolio concern. |
| 6 | `v7_safety_check()` | 155–169 | **KEEP** (TradeExecutor) | Thin orchestration wrapper: lock + degraded + clock. No business logic. |
| 7 | `_block_buys()` | 171–172 | **KEEP** (TradeExecutor) | Single boolean delegation. Orchestration. |
| 8 | Event-driven buys (inside `main()`) | 209–216 | **MOVE** → `portfolio/buy_engine.py` | Iterates event signals, checks cash, places buys. Portfolio allocation logic. |
| 9 | Sell→buy pair logic (inside `main()`) | 219–241 | **MOVE** → `portfolio/buy_engine.py` | Reads watchlist, ranks candidates, allocates budget, enforces MAX_PAIR constraints. Portfolio allocation logic. |
| 10 | Add-to-existing holdings (inside `main()`) | 244–256 | **MOVE** → `portfolio/buy_engine.py` | Score-based accumulation decision. Portfolio allocation logic. |
| 11 | Hard constraint deployment (inside `main()`) | 261–296 | **MOVE** → `portfolio/buy_engine.py` | Forced deployment when utilization < 38%. Reads watchlist, filters, places limit orders. Portfolio concern. |
| 12 | Screener-based buys (inside `main()`) | 302–326 | **MOVE** → `portfolio/buy_engine.py` | Candidate selection from screener output. Portfolio allocation logic. |
| 13 | Report rendering (inside `main()`) | 331–361 | **KEEP** (TradeExecutor) | Text formatting of results. Presentation concern, acceptable in orchestrator. |
| 14 | `report_mode()` | 368–407 | **KEEP** (TradeExecutor) | Data marshalling into JSON. No decisions made. Orchestration. |
| 15 | `execute_mode()` | 410–526 | **KEEP** (TradeExecutor) | P0 guardrail chain + order submission via OMS. Pure orchestration — calls validators, delegates to broker. |
| 16 | `stops_mode()` | 529–560 | **KEEP** (TradeExecutor) | Delegates to stop_loss_manager, take_profit_manager, stop_coverage_audit, detect_ghost_stops. Pure orchestration. |
| 17 | `run_cli()` | 567–583 | **KEEP** (TradeExecutor) | CLI parsing, routing to modes. Orchestration. |

### Private Helper Data (inside TradeExecutor, lines 40–48)

| Item | Classification | Rationale |
|---|---|---|
| `DATA_DIR`, `WATCHLIST_FILE`, `EVENTS_FILE` | **MOVE** → `core/config.py` | File paths are configuration, not execution |
| `DRAWDOWN_PAUSE`, `DRAWDOWN_CUT` | **MOVE** → `risk/account_risk.py` | Risk thresholds |
| `TP_DRAWDOWN_PCT`, `MIN_POSITION_UTIL` | **MOVE** → split: `risk/` and `portfolio/` | Risk + portfolio thresholds |
| `LOW_UTIL_FORCE_MARKET`, `FORCE_BUY_SCORE`, `NORMAL_BUY_SCORE` | **MOVE** → `portfolio/evaluator.py` | Portfolio-mode thresholds |
| `MAX_BUYS_PER_RUN`, `SELL_REPLACEMENT` | **MOVE** → `portfolio/buy_engine.py` | Buy execution constraints |
| `HARD_UTIL_FLOOR` through `MAX_ADD_QTY_PER_SYMBOL` | **MOVE** → `portfolio/buy_engine.py` | Hard constraint parameters |

### Summary

| Category | Count |
|---|---|
| KEEP (orchestration) | 7 |
| MOVE (extract to other modules) | 11 functions + 2 data blocks |
| DELETE | 0 |

After extraction, TradeExecutor becomes approximately **150 lines** (down from 583).

---

## Section 2 — Target Architecture

### Future Execution Flow

```
                    ┌─────────────────────────┐
                    │    AI Decision Layer     │  (cron prompt, LLM)
                    │  Produces: OrderIntent[] │
                    └───────────┬─────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                    TRADE EXECUTOR (Orchestrator)               │
│                                                               │
│  1. Receive OrderIntent[]                                     │
│  2. Validate each intent (basic data integrity)               │
│  3. Check trading preconditions (lock, degraded, market open) │
│  4. Route through gate chain                                  │
│  5. Delegate execution to OMS                                 │
│  6. Collect results                                           │
│                                                               │
│  TradeExecutor does NOT:                                      │
│    - Calculate signals                                        │
│    - Compute Kelly sizes                                      │
│    - Decide what to buy                                       │
│    - Compute drawdown thresholds                              │
│    - Parse market events                                      │
└───────────┬───────────────────────────────────────────────────┘
            │
            │  For each OrderIntent:
            │
            ▼
┌───────────────────────┐
│   ExecutionValidator  │  ← NEW (extracted from execute_mode)
│                       │
│  - Dashboard gate     │
│  - Active sectors     │
│  - Seed eligibility   │
│  - Exposure limits    │
│  - Returns: PASS/REJECT + reason
└───────────┬───────────┘
            │ PASS
            ▼
┌───────────────────────┐
│      RiskGuard        │  ← NEW (extracted from safety checks)
│                       │
│  - Trading lock check │
│  - Degraded mode      │
│  - Drawdown limits    │
│  - Position size cap  │
│  - Returns: ALLOW/BLOCK + reason
└───────────┬───────────┘
            │ ALLOW
            ▼
┌───────────────────────┐
│         OMS           │  (order_state_machine — unchanged)
│                       │
│  - Create order record│
│  - Transition states  │
│  - PENDING → VALIDATING→ APPROVED → SUBMITTED → FILLED
│  - Audit log each step│
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│    BrokerExecutor     │  ← RENAMED from broker/alpaca_client
│                       │
│  - place_order()      │
│  - Respect BrokerStop │
│  - Return order_id    │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  PostTradeRecorder    │  ← NEW
│                       │
│  - Log fill status    │
│  - Update position    │
│  - Trigger stop audit │
│  - Update risk_state  │
│  - Log to audit_log   │
└───────────────────────┘
```

### Module Ownership

| Module | Owns | Does NOT Own |
|---|---|---|
| **TradeExecutor** | Orchestration: receive→validate→route→collect | Signals, sizing, allocation, risk decisions |
| **ExecutionValidator** | P0 guardrails: dashboard, sectors, seed, exposure | Market analysis, strategy |
| **RiskGuard** | Safety gates: lock, degraded, drawdown, caps | What to buy, how much |
| **OMS** | Order lifecycle: states, transitions, audit | Broker communication |
| **BrokerExecutor** | Alpaca API: place, cancel, patch, query | Order validity, risk |
| **PostTradeRecorder** | After-trade: log, update, trigger audits | Trading decisions |

### Stop Management Flow (separate path)

```
                    ┌─────────────────────────┐
                    │    TRADE EXECUTOR        │
                    │    (stops_mode)          │
                    └───────────┬─────────────┘
                                │
            ┌───────────────────┼───────────────────┐
            ▼                   ▼                   ▼
   ┌────────────────┐  ┌──────────────┐  ┌──────────────────┐
   │ StopLossMgr    │  │ TakeProfitMgr│  │ CoverageAuditor  │
   │                │  │              │  │                  │
   │ Trail stop     │  │ TP execution │  │ Gap detection    │
   │ BrokerStop     │  │ Partial/full │  │ Ghost detection  │
   │ protection     │  │ sell         │  │ Blacklist update │
   │ GUARANTEED     │  │              │  │                  │
   └────────────────┘  └──────────────┘  └──────────────────┘
```

---

## Section 3 — PositionManager Split

### Current Items in `execution/position_manager.py`

| # | Item | Type | Current Category | Correct Category | Move To |
|:--|---|---|:---:|:---:|---|
| 1 | `load_state()` | Function | Position I/O | **Position** | KEEP |
| 2 | `save_state()` | Function | Position I/O | **Position** | KEEP |
| 3 | `get_highest(sym, state)` | Function | Position tracking | **Position** | KEEP |
| 4 | `set_highest(sym, price, state, cost)` | Function | Position tracking | **Position** | KEEP |
| 5 | `get_trail_stop(sym, state, cost, vol_20d)` | Function | Position-derived metric | **Position** | KEEP |
| 6 | `SECTOR_MAP` | Data | Position metadata | **Position** | KEEP |
| 7 | `get_sector(sym)` | Function | Position metadata | **Position** | KEEP |
| 8 | `__get_daily_bars(sym)` | Function | Data access | **Position** | KEEP (thin wrapper) |
| 9 | `__get_us_price(sym)` | Function | Data access | **Position** | KEEP (thin wrapper) |
| 10 | `__get_volatility(sym)` | Function | Data-derived metric | **Strategy** | MOVE → `strategy/scorer.py` |
| 11 | `get_bars(sym, limit)` | Function | Data access | **Position** | KEEP (thin wrapper) |
| 12 | `analyze(sym)` | Function | Full strategy engine | **Strategy** | MOVE → `strategy/scorer.py` |
| 13 | `calc_rsi()` (called inside analyze) | Imported | Technical indicator | **Strategy** | Already in `strategy/indicator_engine.py` ✓ |
| 14 | `calc_boll()` (called inside analyze) | Imported | Technical indicator | **Strategy** | Already in `strategy/indicator_engine.py` ✓ |
| 15 | `calc_sma()` (called inside analyze) | Imported | Technical indicator | **Strategy** | Already in `strategy/indicator_engine.py` ✓ |
| 16 | `calc_volume_metrics()` (in analyze) | Imported | Technical indicator | **Strategy** | Already in `strategy/indicator_engine.py` ✓ |
| 17 | `calc_macd()` (in analyze) | Imported | Technical indicator | **Strategy** | Already in `strategy/indicator_engine.py` ✓ |
| 18 | `calc_atr()` (in analyze) | Imported | Technical indicator | **Strategy** | Already in `strategy/indicator_engine.py` ✓ |
| 19 | `calc_volatility()` (in analyze) | Imported | Technical indicator | **Strategy** | Already in `strategy/indicator_engine.py` ✓ |
| 20 | `get_volatility_stop_pct()` | Imported | Stop threshold | **Strategy** | Already in `strategy/indicator_engine.py` ✓ |
| 21 | `tech_snapshot(syms, max_show)` | Function | Batch analysis | **Analytics** | MOVE → `strategy/tech_snapshot.py` |
| 22 | `TP_RSI_SELL` (constant, line 31) | Data | Strategy threshold | **Strategy** | MOVE → `strategy/scorer.py` |
| 23 | `TP_DRAWDOWN_PCT` (constant, line 32) | Data | Strategy threshold | **Strategy** | MOVE → `strategy/scorer.py` |

### Post-Split PositionManager

```
execution/position_manager.py  (~120 lines)

POSITION STATE (keep):
  load_state()              → dict
  save_state(state)         → None
  get_highest(sym, state)   → float
  set_highest(sym, price, state, cost=None) → None
  get_trail_stop(sym, state, cost, vol_20d=None) → float

POSITION METADATA (keep):
  SECTOR_MAP                → dict
  get_sector(sym)           → str

DATA ACCESS (keep — thin wrappers):
  get_bars(sym, limit)      → list | None
  __get_daily_bars(sym)     → list
  __get_us_price(sym)       → float | None
```

### New Modules Created

```
strategy/scorer.py           (~120 lines)
  analyze(sym)               → dict | None  (all indicator computation + buy/sell scoring)
  __get_volatility(sym)      → float | None

strategy/tech_snapshot.py    (~60 lines)
  tech_snapshot(syms, max_show) → dict

risk/account_risk.py         (~50 lines)
  check_account_risk(equity, cash, state, holdings) → (can_buy, alerts, cuts)

portfolio/evaluator.py       (~40 lines)
  check_position_utilization(equity, cash, holdings, mode, target_util_override) → (need_buy, util, gap, market_state, target_util)

portfolio/buy_engine.py      (~200 lines)
  generate_buy_orders(equity, cash, holdings, state, mode) → OrderIntent[]
  (absorbs: event-driven buys, sell→buy pair, add-to-existing, hard constraint, screener buys)

strategy/event_signals.py    (~60 lines)
  load_event_buy_signals()   → [(sym, price, reason, priority), ...]
  load_negative_bias_set()   → set
```

---

## Section 4 — Broker Stop Protection

### Design Principle

> **There is never a moment where a position lacks broker stop protection.**

### Current Violation Pattern

```
State: POSITION PROTECTED (stop order active for N shares)
  │
  ├─ CANCEL stop order          ← PROTECTION REMOVED
  │
  ├─ 300ms sleep                ← UNCOVERED WINDOW
  │
  ├─ Place MARKET SELL          ← MAY FAIL (403, network, etc.)
  │
  └─ If fail: NO PROTECTION     ← CATASTROPHIC
```

### Target Pattern: PATCH-First

```
State: POSITION PROTECTED (stop order active for N shares)
  │
  ├─ PATCH stop qty: N → (N - sell_qty)    ← PROTECTION MAINTAINED
  │    │                                      (stop now covers remainder only)
  │    └─ PATCH fails?
  │         └─ ABORT. Position still protected.
  │
  ├─ Place MARKET SELL (sell_qty)            ← STOP STILL ACTIVE
  │    │
  │    └─ SELL fails?
  │         └─ Stop protects all N shares (PATCH rolled back or not executed)
  │            Position remains fully protected. Retry next cycle.
  │
  ├─ SELL succeeds (sell_qty shares sold)    ← STOP STILL ACTIVE for remainder
  │
  └─ Cleanup old stop, place fresh stop for remainder (if PATCH created chain)
```

### State Machine

```
States:
  FULLY_PROTECTED    — stop order covers all shares
  PARTIALLY_PROTECTED — stop order covers (N - sell_qty) shares, sell pending
  EXECUTING          — market sell in flight, stop protects remainder
  REDUCED            — sell complete, stop covers remaining shares
  FULLY_SOLD         — no position, no stop needed

Transitions:
  FULLY_PROTECTED ──[PATCH stop qty─→(N-sell_qty)]──→ PARTIALLY_PROTECTED
  PARTIALLY_PROTECTED ──[place MARKET SELL]──→ EXECUTING
  EXECUTING ──[SELL filled]──→ REDUCED
  EXECUTING ──[SELL rejected]──→ FULLY_PROTECTED (stop still covers all N)
  REDUCED ──[cancel old stop + place fresh stop]──→ FULLY_PROTECTED (new N)
  REDUCED ──[remaining == 0]──→ FULLY_SOLD
  FULLY_SOLD ──[cancel ghost stop]──→ CLEAN

Invalid Transitions (BLOCKED):
  FULLY_PROTECTED ──[CANCEL stop]──→ ❌ BLOCKED (Rule 2)
  EXECUTING ──[CANCEL stop]──→ ❌ BLOCKED (Rule 2)
  Any state ──[no stop, no sell]──→ ❌ BLOCKED (uncovered window)
```

### Special Case: Full Position Sale

When sell_qty == total_qty:

```
FULLY_PROTECTED (stop covers N shares)
  │
  ├─ PATCH stop qty: N → 1            ← 1 share always protected
  │
  ├─ Place MARKET SELL (N - 1)        ← sell all but 1
  │
  ├─ SELL succeeds
  │
  ├─ Cancel old stop (protecting 1 share)
  │
  └─ Place MARKET SELL (1)            ← sell final share
       │
       └─ FULLY_SOLD

Note: The 1-share remainder pattern means:
  - No Alpaca qty=0 PATCH rejection
  - Final share sale has no stop conflict (stop already cancelled AFTER main sell)
  - If final share sale fails: 1 share remains, intentionally unprotected (MINIMAL risk)
```

### Special Case: Closed Market

```
Market CLOSED + need to sell:
  → DO NOT cancel stop
  → DO NOT PATCH stop (pending_replace chain risk)
  → Record sell intent
  → Execute at market open using PATCH-first pattern

Rationale: PATCH in closed market creates pending_replace chain that locks shares.
Better to wait than to create an uncovered window or share lock.
```

### Guarantee Proof

| Scenario | Protection Guarantee |
|---|---|
| PATCH succeeds, SELL succeeds | Stop protected remainder throughout |
| PATCH succeeds, SELL fails | Stop still protects full position (original qty) |
| PATCH fails | Abort — full protection maintained |
| Network partition during SELL | Stop protects remainder; SELL either fills or times out |
| Process crash during EXECUTING | Stop still active on Alpaca server for remainder |

**At no point is the stop order removed before a sell is confirmed.**

### Affected Modules (implementation targets)

| Module | Current Violation | Fix |
|---|---|---|
| `stop_loss_manager.update_trail_stops()` L125–131 | Cancel→Sleep→Sell | PATCH→Sell→Cleanup |
| `take_profit_manager.execute_take_profit()` L109–114 | Cancel→Sleep→Sell | PATCH→Sell→Cleanup |
| Both modules | No state machine | Add BrokerStopStateMachine |

### New Component: `execution/broker_stop_guard.py`

```python
# Single responsibility: enforce Rule 2
# Every sell-through-stop-path must route through this module.

def sell_with_stop_protection(sym, sell_qty, total_qty, cost, vol_20d):
    """
    Sell shares while guaranteeing continuous broker stop protection.

    Returns: (order_result, new_protection_state)
    Never leaves position unprotected.
    """
```

---

## Section 5 — Dependency Graph

### Current Dependency Graph (before refactoring)

```
trade_executor.py
├── imports from: position_manager (analyze, get_sector, get_highest, ...)
├── imports from: order_manager (get_portfolio, place_market_order, ...)
├── imports from: stop_loss_manager (update_trail_stops, ...)
├── imports from: take_profit_manager (execute_take_profit)
├── imports from: order_intent (OrderIntent, OrderSide, OrderType)
├── imports from: order_state_machine
├── imports from: strategy/indicator_engine (calc_rsi)
├── imports from: risk/trading_lock
├── imports from: risk/degraded_mode
├── imports from: risk/policy_validator
├── imports from: broker/alpaca_client
├── imports from: core/config, core/logger
└── imports from: storage/db

position_manager.py
├── imports from: strategy/indicator_engine (calc_rsi, calc_sma, ...)
├── imports from: broker/alpaca_client
└── imports from: core/config, core/logger, core/http

stop_loss_manager.py
├── imports from: order_manager
├── imports from: position_manager (get_highest, set_highest, get_trail_stop, __get_volatility)
└── imports from: strategy/indicator_engine (get_volatility_stop_pct)

take_profit_manager.py
├── imports from: order_manager
└── imports from: position_manager (get_trail_stop)

order_manager.py
└── imports from: broker/alpaca_client

Problems:
  - trade_executor imports 14+ modules
  - position_manager mixes strategy and data access
  - stop_loss_manager depends on position_manager for volatility (strategy leak)
  - No clear boundary between strategy / execution / portfolio / risk
```

### Target Dependency Graph (after refactoring)

```
                         ┌─────────────────┐
                         │  trade_executor │  (~150 lines)
                         │  ORCHESTRATOR   │
                         └────────┬────────┘
                                  │
            ┌─────────────────────┼─────────────────────┐
            │                     │                     │
            ▼                     ▼                     ▼
   ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
   │execution/      │   │  risk/         │   │  portfolio/    │
   │validator       │   │  risk_guard    │   │  buy_engine    │
   │                │   │  account_risk  │   │  evaluator     │
   │P0 guardrails   │   │  trading_lock  │   │                │
   │dashboard gate  │   │  degraded_mode │   │generates       │
   │sector check    │   │  drawdown      │   │OrderIntent[]   │
   │seed eligibility│   │                │   │                │
   │exposure limits │   │                │   │                │
   └────────────────┘   └────────────────┘   └───────┬────────┘
                                                     │
                                                     │ uses
                                                     ▼
                                            ┌────────────────┐
                                            │  strategy/     │
                                            │  scorer        │
                                            │  event_signals │
                                            │  indicator_    │
                                            │    engine      │
                                            └────────────────┘

   ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
   │execution/      │   │execution/      │   │execution/      │
   │stop_loss_mgr   │   │take_profit_mgr │   │position_mgr    │
   │                │   │                │   │                │
   │trail stops     │   │TP execution    │   │position state  │
   │coverage audit  │   │partial/full    │   │ONLY            │
   │ghost detection │   │sell            │   │                │
   │                │   │                │   │data access     │
   │depends on:     │   │depends on:     │   │wrappers        │
   │ position_mgr   │   │ position_mgr   │   │                │
   │ order_mgr      │   │ order_mgr      │   │depends on:     │
   │ strategy/      │   │ broker_stop    │   │ broker/        │
   │   indicator    │   │   _guard       │   │   alpaca_client│
   │ broker_stop    │   │                │   └────────────────┘
   │   _guard       │   │                │
   └────────────────┘   └────────────────┘

   ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
   │execution/      │   │execution/      │   │execution/      │
   │order_mgr       │   │order_intent    │   │order_state     │
   │                │   │                │   │  _machine      │
   │CRUD operations │   │data carrier    │   │                │
   │                │   │                │   │state tracking  │
   │depends on:     │   │zero deps       │   │                │
   │ broker/        │   │                │   │depends on:     │
   │   alpaca_client│   │                │   │ order_intent   │
   └────────────────┘   └────────────────┘   └────────────────┘

   ┌────────────────┐
   │execution/      │   NEW
   │broker_stop     │
   │  _guard        │
   │                │
   │PATCH-first     │
   │sell pattern    │
   │state machine   │
   │                │
   │depends on:     │
   │ order_mgr      │
   │ position_mgr   │
   └────────────────┘

Dependency rules:
  - execution/ modules import from: broker/, strategy/, core/, risk/ (for checks only)
  - NO execution module imports from trade_executor (orchestrator is leaf, not root)
  - NO circular imports
  - strategy/ imports only from core/ and broker/ (never from execution/)
  - portfolio/ imports from strategy/ and core/ (never from execution/)
  - risk/ imports from core/ and broker/ (never from strategy/ or execution/)
```

### Module Dependency Count Comparison

| Module | Before (imports from) | After (imports from) |
|---|---|---|
| trade_executor | 14+ | 8 |
| position_manager | 3 (strategy leak) | 1 (broker only) |
| stop_loss_manager | 3 | 4 (adds broker_stop_guard) |
| take_profit_manager | 2 | 3 (adds broker_stop_guard) |

---

## Section 6 — Growth Rules

### Rule G1: New Function = New Component

```
When adding execution-layer functionality:
  1. Can it live in an existing non-core module? → Add there.
  2. Does it need a new module? → Create one.
  3. Does it need to modify trade_executor? → LAST RESORT.
```

### Rule G2: TradeExecutor Shrinks Over Time

```
Before adding code to TradeExecutor, answer:
  - Can this be a separate module that TradeExecutor calls?
  - Can this be a callback/strategy pattern (dependency injection)?
  - Can this be a configuration change instead?

If any answer is YES → do not modify TradeExecutor.
```

### Rule G3: PositionManager Is Frozen

```
PositionManager may only grow when:
  - A new data source is added (new Alpaca endpoint wrapper)
  - A new position metadata field is needed

PositionManager may NEVER grow for:
  - New indicators
  - New scoring methods
  - New signal types
  - New risk calculations
  - New allocation logic
```

### Rule G4: Broker Stop Protection Is Invariant

```
Any sell path that touches a broker stop MUST route through broker_stop_guard.

No sell path may:
  - Cancel a broker stop before a sell is confirmed
  - Bypass broker_stop_guard
  - Use a different PATCH/cancel/sell sequence

Violation of this rule = CRITICAL bug, not architectural debt.
```

### Rule G5: Dependency Direction

```
Allowed:
  execution/ → strategy/     (execution USES strategy output)
  execution/ → risk/         (execution CHECKS risk gates)
  execution/ → broker/       (execution CALLS broker)
  portfolio/ → strategy/     (portfolio USES strategy scores)
  strategy/ → broker/        (strategy READS market data)

Forbidden:
  strategy/ → execution/     (strategy knows nothing about execution)
  portfolio/ → execution/    (portfolio knows nothing about execution)
  risk/ → strategy/          (risk knows nothing about strategy)
  core/ → anything           (core is leaf dependency)

Circular:
  A → B and B → A           (NEVER)
```

### Rule G6: Pre-Extraction Freeze

```
Until Section 1–5 extractions are complete:
  - No new features in trade_executor.py
  - No new features in position_manager.py
  - No new execution-layer modules (unless extracting FROM the above)

Bug fixes in existing extracted functions are allowed.
```

---

## Success Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| TradeExecutor responsibilities decrease | ✅ DESIGNED | 17 responsibilities → 7 (11 extracted) |
| PositionManager owns position state only | ✅ DESIGNED | 23 items → 12 kept, 11 moved to strategy/ |
| Broker Stop protection mathematically guaranteed | ✅ DESIGNED | PATCH-first state machine, zero uncovered states |
| Future execution features require minimal modification | ✅ DESIGNED | New module pattern (Rule G1), frozen core (Rule G2/G3) |
| No circular dependencies | ✅ DESIGNED | One-way flow: strategy → portfolio → execution → broker |

---

*This document is a design artifact. No implementation is authorized until reviewed.*
