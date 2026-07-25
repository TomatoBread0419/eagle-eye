# CORE TRADING CHAIN — Eagle Eye Stock Trading System

**Version:** 1.0
**Generated:** 2026-06-19
**Scope:** The minimal chain from market data to broker fill. If ANY link in this
chain breaks, trades cannot execute correctly.

**Criticality Rule:** "If Owner disappears for 14 days and this component
disappears, can Owner lose money?" → YES = Critical.

---

## 1. ASCII CHAIN DIAGRAM

```
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                        CORE TRADING CHAIN                                  │
 │                        (End-to-End Data Flow)                             │
 └─────────────────────────────────────────────────────────────────────────────┘

 ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
 │  MARKET  │    │ SCANNER  │    │    AI    │    │  POLICY  │
 │   DATA   │───▶│          │───▶│ RECOMM-  │───▶│ VALIDA-  │
 │          │    │          │    │ ENDATION │    │   TOR    │
 └──────────┘    └──────────┘    └──────────┘    └──────────┘
                                                      │
  us_common.py     us_screener   us_report.py +       │
  Alpaca IEX API   .py (GARP    deepseek-v4-flash     │
  yfinance         momentum)    (AI decision)          │
                                                      ▼
 ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
 │  BROKER  │    │  BROKER  │    │   OMS    │    │ POLICY   │
 │   FILL   │◀───│  (ALPACA │◀───│          │◀───│ VALIDA-  │
 │          │    │   API)   │    │          │    │   TOR    │
 └──────────┘    └──────────┘    └──────────┘    └──────────┘
                      │
                      │           us_trader.py
  Order status        │           eagle_eye/execution/
  via Alpaca API      │           trade_executor.py
  polling              │           policy_validator.py
                      │
                  eagle_eye/
                  broker/
                  alpaca_client.py
```

```
 DETAILED LINK-BY-LINK:

 ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
 │  1. MARKET DATA │────▶│  2. SCANNER     │────▶│  3. AI RECOMM-  │
 │                 │     │                 │     │    ENDATION     │
 │ us_common.py    │     │ us_screener.py  │     │ us_report.py    │
 │ Alpaca IEX bars │     │ (78-stock       │     │ (aggregates all │
 │ yfinance fundas │     │  universe)      │     │  data into      │
 │ FRED CSV        │     │                 │     │  structured     │
 │ market_env.json │     │ Outputs:        │     │  report)        │
 │                 │     │ us_watchlist.json│    │                 │
 │ Outputs:        │     │ us_screener_    │     │ deepseek-v4-    │
 │ raw price data  │     │ log.json        │     │ flash reads     │
 │ OHLCV bars      │     │                 │     │ report, emits   │
 └─────────────────┘     └─────────────────┘     │ BUY/SELL/HOLD   │
                                                  └────────┬────────┘
                                                           │
                                                           ▼
 ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
 │  6. BROKER      │◀────│  5. OMS         │◀────│  4. POLICY      │
 │  (ALPACA API)   │     │                 │     │    VALIDATOR    │
 │                 │     │ us_trader.py    │     │                 │
 │ alpaca_client.  │     │ (thin CLI)      │     │ policy_valida-  │
 │ py (V7)         │     │                 │     │ tor.py +        │
 │                 │     │ trade_executor. │     │ auto_approval_  │
 │ POST /v2/orders │     │ py (orchestrator)│    │ policy.md       │
 │ PATCH /v2/      │     │                 │     │                 │
 │ orders/{id}     │     │ order_manager.py│     │ Checks:         │
 │                 │     │ stop_loss_mgr   │     │ - Position caps │
 │                 │     │ take_profit_mgr │     │ - Sector limits │
 └────────┬────────┘     └─────────────────┘     │ - Trade counts  │
          │                                       │ - Drawdown      │
          ▼                                       └─────────────────┘
 ┌─────────────────┐
 │  7. BROKER FILL │
 │                 │
 │ Alpaca executes │
 │ order, returns  │
 │ fill status     │
 │                 │
 │ us_risk_state.  │
 │ json updated    │
 └─────────────────┘
```

---

## 2. COMPONENT-BY-COMPONENT DETAIL

### 2.1 MARKET DATA

| Field | Value |
|-------|-------|
| **Files** | `~/.hermes/scripts/us_common.py` (shared data layer, 329 lines) |
| | `~/.hermes/scripts/market_env.py` (VIX/DXY/yields/breadth, 401 lines) |
| | Alpaca IEX Data API (`data.alpaca.markets/v2/stocks`) |
| | yfinance (PE/Beta/Dividend for fundamentals) |
| | FRED CSV (2Y Treasury yield fallback) |
| **Critical** | **YES** — Without market data, scanner has nothing to score. Blind trades = money lost. |
| **What it does** | Fetches OHLCV price bars, fundamental metrics (PE/Beta/Div), macro indicators (VIX/DXY/yields), and market breadth (83 stocks + 11 sector ETFs). |
| **Dependencies** | Alpaca API keys (`~/.hermes/.env`), network connectivity, yfinance library |
| **Outputs** | Raw price data (OHLCV), `market_env.json`, `macro_context.json`, `market_breadth.json` |
| **Failure mode if removed** | No price data → scanner cannot score → no watchlist → AI has nothing to decide on → zero new trades for 14 days. Existing positions run with NO stop updates if this also blocks `us_trader.py --stops`. Owner's capital is at market risk with no active management. |

### 2.2 SCANNER

| Field | Value |
|-------|-------|
| **Files** | `~/.hermes/scripts/us_screener.py` (859 lines, GARP momentum scanner V2) |
| **Critical** | **YES** — Without scanner, no new candidates are found. But more critically: scanner also produces the watchlist that feeds into the AI decision cycle. |
| **What it does** | Scans 78-stock universe using GARP + momentum strategy, applies technical filters (RSI/MACD/MA), multi-cycle gate, and outputs ranked buy candidates. |
| **Dependencies** | Market data (OHLCV from Alpaca), `market_events_latest.json`, `us_portfolio.json` (for sector gap), `calibrated_params.json` (for Kelly sigmoid), `us_recent_stops.json` (blacklist) |
| **Outputs** | `us_watchlist.json` (ranked candidates), `us_screener_log.json` (scoring details) |
| **Failure mode if removed** | No new candidates generated → AI decision cycle runs on stale watchlist → no new entries. Existing positions still managed by `--stops`. Owner misses opportunities but does NOT lose money on existing positions. However, over 14 days, sector rotation and market shifts may leave portfolio suboptimal. |

### 2.3 AI RECOMMENDATION

| Field | Value |
|-------|-------|
| **Files** | `~/.hermes/scripts/us_report.py` (416 lines, report aggregator) |
| | deepseek-v4-flash model (via Hermes Agent LLM gateway) |
| | Cron job `a638e8d39d5d` (hourly during trading hours, `10 21-5 * * 1-5`) |
| **Critical** | **YES** — AI recommendation is the sole decision-maker for new trades. Without it, no BUY/SELL signals are generated. However, mechanical stops still run independently. |
| **What it does** | Aggregates watchlist + portfolio + market env + signal decay + market events into structured report; deepseek-v4-flash reads report and emits structured BUY/SELL/HOLD decisions with ticker, size, reasoning. |
| **Dependencies** | `us_watchlist.json` (from scanner), `us_portfolio.json`, `market_env.json`, `signal_decay.json`, `market_events_latest.json`, `trade_history.json`, `us_risk_state.json` |
| **Outputs** | AI decision JSON with action (BUY/SELL), ticker, position size, reasoning — fed to `us_trader.py --execute` |
| **Failure mode if removed** | No new BUY/SELL decisions → no new trades placed for 14 days. Existing positions remain held. Mechanical stops (`--stops`) may still run if called independently. Owner's capital is idle but not actively losing — unless market drops and stops aren't updated. |

### 2.4 POLICY VALIDATOR

| Field | Value |
|-------|-------|
| **Files** | `~/eagle_eye/risk/policy_validator.py` (328 lines) |
| | `~/stock_trader/auto_approval_policy.md` v1.1 (221 lines, the policy rules) |
| **Critical** | **YES** — This is the LAST safety gate before orders reach the broker. Without it, AI hallucinations or buggy scanner output can produce oversized, concentrated, or wash-trade orders that directly lose money. |
| **What it does** | Validates every OrderIntent against hard constraints before execution: position cap (15%/18%), sector limit (25%/30%), cash reserve (20%), daily trade cap (4), monthly trade cap (25), drawdown circuit breaker (12%/20%), multi-cycle gate, sell discipline (≥2 triggers), liquidation constraints. |
| **Dependencies** | `eagle_eye/execution/candidate_tracker.py` (SQLite consecutive scan counts), `us_risk_state.json` (current state), `auto_approval_policy.md` (rules source) |
| **Outputs** | Approved/Rejected decision per OrderIntent. Rejected orders logged as `policy_rejected`. |
| **Failure mode if removed** | **CATASTROPHIC.** AI can recommend 100% allocation to one stock. No sector limits enforced. No drawdown breaker. No trade count limits. Over 14 days, unchecked AI decisions could concentrate portfolio, violate wash trade rules, or ignore drawdown — all leading to direct capital loss. This is the single most critical safety component. |

### 2.5 OMS (Order Management System)

| Field | Value |
|-------|-------|
| **Files** | `~/.hermes/scripts/us_trader.py` (72 lines, thin CLI wrapper) |
| | `~/eagle_eye/execution/trade_executor.py` (583 lines, main orchestrator) |
| | `~/eagle_eye/execution/order_manager.py` (236 lines, API order calls) |
| | `~/eagle_eye/execution/position_manager.py` (314 lines, position state) |
| | `~/eagle_eye/execution/stop_loss_manager.py` (346 lines, trailing stops) |
| | `~/eagle_eye/execution/take_profit_manager.py` (133 lines, TP1/TP2) |
| | `~/eagle_eye/execution/order_intent.py` (198 lines, OrderIntent dataclass) |
| | `~/eagle_eye/execution/order_state_machine.py` (404 lines, lifecycle) |
| | `~/eagle_eye/risk/trading_lock.py` (277 lines, emergency lock) |
| | `~/eagle_eye/risk/degraded_mode.py` (289 lines, API fail restriction) |
| **Critical** | **YES** — OMS is the bridge between validated decisions and actual orders. Without it, no orders reach the broker. But more critically: stop-loss management lives here. Without OMS, existing positions have NO trailing stops, NO take-profit execution. Owner's capital is fully exposed to market downside for 14 days. |
| **What it does** | Orchestrates full order lifecycle: receives validated OrderIntent, manages position state, places orders via Alpaca API, executes trailing stops and take-profit levels, handles wash-trade avoidance (never cancel stops, only PATCH qty). |
| **Dependencies** | Approved OrderIntents (from policy validator), Alpaca API connection, `us_risk_state.json`, `us_portfolio.json` |
| **Outputs** | Alpaca API orders (POST/PATCH), updated `us_risk_state.json`, updated `us_pending_replacements.json`, updated `us_recent_stops.json` |
| **Failure mode if removed** | No new orders placed → safe for new trades (nothing happens). **BUT**: No stop-loss updates → existing positions have zero downside protection. No take-profit execution → winners don't lock in gains. Over 14 days, a market crash hits unprotected positions with full force. This is CRITICAL for capital preservation. |

### 2.6 BROKER (Alpaca API Client)

| Field | Value |
|-------|-------|
| **Files** | `~/eagle_eye/broker/alpaca_client.py` (373 lines, V7 adapter) |
| | `~/eagle_eye/core/http.py` (321 lines, HTTP helpers) |
| | `~/.hermes/scripts/us_common.py` (V6 fallback, `url_get()`) |
| | `~/stock_trader/config.py` (30 lines, API key wrapper) |
| **Critical** | **YES** — This is the API transport layer. Without it, zero orders reach Alpaca. Same failure mode as OMS: existing positions unprotected. |
| **What it does** | Translates internal order calls into Alpaca REST API requests: account info, position queries, order placement (market/limit/stop), order modification (PATCH), historical bars. Handles rate limiting (429), wash trade rejection (403), retry logic. |
| **Dependencies** | Alpaca API keys (`~/.hermes/.env` → `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`), network connectivity, `ALPACA_BASE_URL` (paper: `https://paper-api.alpaca.markets`) |
| **Outputs** | Alpaca order responses (order_id, status, filled_qty, filled_avg_price), position data, account data |
| **Failure mode if removed** | Same as OMS — no orders reach the broker. API 4x consecutive failure triggers `degraded_mode` (exits only, no new positions). DNS failure detected by `eagle_heartbeat.py`. Over 14 days: existing positions fully unprotected, no stops, no TP. |

### 2.7 BROKER FILL (Alpaca Execution)

| Field | Value |
|-------|-------|
| **Files** | No local code — this is Alpaca's server-side execution engine |
| | Fill status polled via `eagle_eye/broker/alpaca_client.py` (`GET /v2/orders`) |
| **Critical** | **YES** — This is where real money moves (in paper mode: simulated). If Alpaca cannot fill, the entire chain upstream is moot. |
| **What it does** | Alpaca matches the order against market liquidity, executes the trade, and returns fill confirmation (filled_qty, filled_avg_price, status). |
| **Dependencies** | Valid order submitted by OMS, US market hours (9:30-16:00 ET), Alpaca operational status |
| **Outputs** | Filled order confirmation → us_trader.py updates `us_risk_state.json`, logs to `us_recent_stops.json` |
| **Failure mode if removed** | If Alpaca is down: no fills, no stops execute. Orders queue in `pending_new` state. `degraded_mode` activates after 4 failures. If Alpaca rejects (wash trade 403): order blocked, must reduce stop qty first. Over 14 days: positions frozen in whatever state they were in before the outage. |

---

## 3. HARD GUARD INTEGRATION (OWNER_MANDATE_v1.1)

These hard guards are enforced at the **Policy Validator** (§2.4) and partially
at the **OMS** (§2.5) level:

| Guard | Limit | Enforced By | Chain Position |
|-------|-------|-------------|----------------|
| Cash Reserve | ≥20% of equity | policy_validator.py | §2.4 Policy Validator |
| Single Position (entry) | ≤15% of equity | policy_validator.py | §2.4 Policy Validator |
| Single Position (max) | ≤18% of equity | policy_validator.py + stop_loss_manager.py | §2.4 + §2.5 |
| Single Sector | ≤25% (warn) / ≤30% (block) | policy_validator.py | §2.4 Policy Validator |
| Daily Trade Count | ≤4 trades/day | policy_validator.py | §2.4 Policy Validator |
| Monthly Trade Count | ≤25 trades/month | policy_validator.py | §2.4 Policy Validator |
| Drawdown Circuit Breaker | 12% (halt new) / 20% (liquidate) | policy_validator.py + trading_lock.py | §2.4 + §2.5 |

If ANY guard is violated, the order is **rejected** at §2.4 and never reaches §2.5-§2.7.

---

## 4. CRITICALITY SUMMARY

```
Chain Component        Critical?   Can Owner Lose Money If Removed for 14 Days?
─────────────────────  ─────────   ─────────────────────────────────────────────
1. Market Data         YES         YES — blind trading, no data for stops
2. Scanner             YES*        YES* — no new entries, but stops still run
3. AI Recommendation   YES*        YES* — no new trades, but stops still run
4. Policy Validator    YES !!      YES — CATASTROPHIC — unchecked AI orders
5. OMS                 YES         YES — no stops, no TP, positions unprotected
6. Broker (Alpaca)     YES         YES — same as OMS, no orders reach market
7. Broker Fill         YES         YES — Alpaca down means frozen positions

* Scanner and AI are critical for NEW trades but existing positions
  are still protected by stops IF OMS+Broker are operational.

!! Policy Validator is the #1 safety component. Its removal allows
   unchecked AI decisions to reach the broker — the highest-risk scenario.
```

---

## 5. MINIMUM VIABLE CHAIN (What Must Work for Safe Trading)

For the Owner to be safe during a 14-day absence, ALL 7 links must function:

```
Market Data ──▶ Scanner ──▶ AI ──▶ Policy ──▶ OMS ──▶ Broker ──▶ Fill
    ✅            ✅        ✅      ✅         ✅       ✅         ✅
```

If **any single link** fails:
- **Without Policy Validator (§2.4)**: Most dangerous — AI can issue unconstrained orders
- **Without OMS/Broker (§2.5/§2.6)**: Existing positions have no stop protection
- **Without Scanner/AI (§2.2/§2.3)**: No new trades, but existing stops still work (IF OMS runs independently)

**Recommended minimum for 14-day Owner absence:**
1. Policy Validator must be active (hard constraint enforcement)
2. OMS `--stops` must run on schedule (trailing stop updates)
3. Broker connection must be live (Alpaca API reachable)
4. Market data must flow (for stop price calculations)

---

## 6. CRON SCHEDULE FOR CHAIN COMPONENTS

| Chain Step | Cron Job | Schedule | Script |
|------------|----------|----------|--------|
| §2.2 Scanner | `b735145148c4` | `0 8 * * 1-5` (daily 08:00 BJT) | us_screener.py |
| §2.3 AI Decision | `a638e8d39d5d` | `10 21-5 * * 1-5` (hourly trading) | us_report.py + us_trader.py |
| §2.5 Stops | via AI Decision cron | same as above | us_trader.py --stops |
| §2.1 Market Env | `156e40a9c859` | `30 20 * * 1-5` (daily 20:30 BJT) | market_env.py |
| §2.1 Signal Decay | `31bbb6eeb546` | `0 21,23,1,3 * * 1-5` (**PAUSED**) | us_signal_decay.py |

**NOTE:** Signal decay detection cron is PAUSED. This means the AI decision
cycle may be missing signal decay data for existing positions.

---

## 7. FILES REFERENCED IN THIS DOCUMENT

| # | File Path | Role in Chain |
|---|-----------|---------------|
| 1 | `~/.hermes/scripts/us_common.py` | §2.1 Market Data (shared HTTP layer) |
| 2 | `~/.hermes/scripts/market_env.py` | §2.1 Market Data (environment scan) |
| 3 | `~/.hermes/scripts/us_screener.py` | §2.2 Scanner |
| 4 | `~/.hermes/scripts/us_report.py` | §2.3 AI Recommendation (report aggregator) |
| 5 | `~/eagle_eye/risk/policy_validator.py` | §2.4 Policy Validator |
| 6 | `~/stock_trader/auto_approval_policy.md` | §2.4 Policy Validator (rules source) |
| 7 | `~/.hermes/scripts/us_trader.py` | §2.5 OMS (thin CLI wrapper) |
| 8 | `~/eagle_eye/execution/trade_executor.py` | §2.5 OMS (main orchestrator) |
| 9 | `~/eagle_eye/execution/order_manager.py` | §2.5 OMS (API order calls) |
| 10 | `~/eagle_eye/execution/position_manager.py` | §2.5 OMS (position state) |
| 11 | `~/eagle_eye/execution/stop_loss_manager.py` | §2.5 OMS (trailing stops) |
| 12 | `~/eagle_eye/execution/take_profit_manager.py` | §2.5 OMS (TP execution) |
| 13 | `~/eagle_eye/execution/order_intent.py` | §2.5 OMS (order intent data) |
| 14 | `~/eagle_eye/execution/order_state_machine.py` | §2.5 OMS (lifecycle) |
| 15 | `~/eagle_eye/risk/trading_lock.py` | §2.5 OMS (emergency lock) |
| 16 | `~/eagle_eye/risk/degraded_mode.py` | §2.5 OMS (API fail restriction) |
| 17 | `~/eagle_eye/broker/alpaca_client.py` | §2.6 Broker |
| 18 | `~/eagle_eye/core/http.py` | §2.6 Broker (HTTP helpers) |
| 19 | `~/stock_trader/config.py` | §2.6 Broker (API keys) |
| 20 | `~/.hermes/.env` | §2.6 Broker (Alpaca credentials) |

---

*End of CORE_TRADING_CHAIN.md*
