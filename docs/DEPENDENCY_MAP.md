# Eagle Eye Dependency Map

**Version:** 1.0
**Generated:** 2026-06-19
**Scope:** Complete data flow and dependency mapping for Eagle Eye V6/V7.1 LTS stock trading system

---

## 1. PRIMARY DATA FLOW: Market Data → Scanner → AI → Policy → OMS → Broker

```
┌─────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  MARKET DATA │──▶│   SCANNER    │──▶│   AI (LLM)   │──▶│   POLICY     │
│              │   │              │   │              │   │              │
│ yfinance     │   │ us_screener  │   │ deepseek-v4  │   │ auto_approv- │
│ Alpaca bars  │   │ .py          │   │ -flash       │   │ al_policy.md │
│ Google RSS   │   │              │   │              │   │              │
│ Sogou WeChat │   │              │   │              │   │              │
│ FRED CSV     │   │              │   │              │   │              │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │                  │                  │                  │
       │    ┌─────────────┘                  │                  │
       │    │                                │                  │
       ▼    ▼                                ▼                  ▼
┌─────────────┐                    ┌──────────────┐   ┌──────────────┐
│ us_report.py│───────────────────▶│  us_trader.py│──▶│  ALPACA API  │
│ (aggregator)│                    │  (OMS/V7.1)  │   │  (Broker)    │
└─────────────┘                    └──────────────┘   └──────────────┘
```

---

## 2. LINK-BY-LINK DEPENDENCY DETAIL

### 2.1 MARKET DATA → SCANNER

| Component | Details |
|-----------|---------|
| **Implementing Files** | `~/.hermes/scripts/us_screener.py` (lines 1-859) |
| **Version** | V2.5 (GARP动量扫描器) — standalone script, not yet migrated to V7 module |
| **Data Sources** | |
| - Price bars (OHLCV) | Alpaca IEX API via `us_common.get_daily_bars()` |
| - Fundamental (PE/Beta/Div) | yfinance via `us_common.get_yf_metrics()` — **rate-limited from China** |
| - Market events | `~/stock_trader/market_events_latest.json` (read) |
| - Portfolio state | `~/stock_trader/us_portfolio.json` (read, for sector gap analysis) |
| - Calibrated params | `~/stock_trader/calibrated_params.json` (read, for Kelly sigmoid) |
| **External Packages** | `yfinance` (optional, graceful degradation), `requests` (for us_signal_decay Alpaca calls) |
| **External APIs** | Alpaca Data API v2 (`https://data.alpaca.markets/v2/stocks`) |
| **Failure Mode** | yfinance rate-limited → fundamentals return empty dict, scanner still runs on price data. Alpaca API timeout → 3 retries with 3s sleep, symbol skipped on failure. Network down → entire scan fails, no JSON output. |

### 2.2 SCANNER → AI

| Component | Details |
|-----------|---------|
| **Implementing Files** | `~/.hermes/scripts/us_report.py` (aggregator, 416 lines) |
| **Version** | V5+ (report generator), feeds into V7.1 LTS AI decision loop |
| **Data Flow** | us_report.py reads us_watchlist.json + us_portfolio.json + market_env.json + signal_decay.json + market_events_latest.json → generates unified markdown report → AI (deepseek-v4-flash) reads report and makes trading decisions |
| **AI Model** | `deepseek-v4-flash` (provider: deepseek) |
| **External Dependencies** | Hermes Agent LLM gateway, deepseek API |
| **Failure Mode** | Any JSON missing → report still generates with available data (graceful degradation via `load_json` returning None). AI timeout → cron job fails with `last_status: error`. AI hallucination → mitigated by policy validator (§2.4). |

### 2.3 AI → POLICY

| Component | Details |
|-----------|---------|
| **Implementing Files** | `~/stock_trader/auto_approval_policy.md` v1.1 (221 lines), `eagle_eye/risk/policy_validator.py` (328 lines) |
| **Version** | V7.1 LTS (policy validator is a V7 module) |
| **Policy Rules Enforced** | |
| - §2 Sell Discipline | Requires ≥2 triggers for sell (MACD death cross, stop loss, TP tier, sector >30%, position >18%, fundamental deterioration) |
| - §3 Liquidation Constraint | No same-day full clear: >10% position → max 50% reduction, 5-10% → max 66%, <5% → full exit OK |
| - §5 Hard Constraints | Single position ≤18%, sector ≤30%, active sectors ≥4, exposure ≤90%, single trade ≤15% equity |
| - §6 Multi-Cycle Gate | Candidate must appear in 2-3 consecutive scans before entry allowed |
| - §6.1 Seed Exemption | Gap sector candidate can enter as seed (≤5%) when active sectors <4, RSI 40-70, Kelly ≤8% |
| **External Dependencies** | `eagle_eye.storage.db` (SQLite, for candidate_tracker consecutive counts) |
| **Failure Mode** | Policy validator rejects order → OrderIntent marked `policy_rejected`, logged but not executed. Policy file missing → validator uses hardcoded defaults from `auto_approval_policy.md` constants. SQLite locked → candidate_tracker returns 0, multi-cycle gate blocks all entries (safe default). |

### 2.4 POLICY → OMS

| Component | Details |
|-----------|---------|
| **Implementing Files** | `eagle_eye/execution/trade_executor.py` (583 lines), `~/.hermes/scripts/us_trader.py` (72-line thin CLI wrapper) |
| **Version** | V7.1 LTS — thin entry delegates to `eagle_eye.execution.trade_executor` |
| **V6 Fallback** | `~/.hermes/scripts/us_trader_v6.py` exists as legacy backup |
| **OMS Functions** | `--report` (read-only), `--execute '{...}'` (order execution), `--stops` (stop/TP management) |
| **Sub-Modules** | |
| - position_manager | `eagle_eye/execution/position_manager.py` — state load/save, highest tracking, tech analysis |
| - order_manager | `eagle_eye/execution/order_manager.py` — API calls, order placement, replacement logging |
| - stop_loss_manager | `eagle_eye/execution/stop_loss_manager.py` — trailing stops, blacklist, ghost stop detection |
| - take_profit_manager | `eagle_eye/execution/take_profit_manager.py` — TP1 (+20%) and TP2 (+35%) execution |
| - order_intent | `eagle_eye/execution/order_intent.py` — OrderIntent dataclass with policy metadata |
| - order_state_machine | `eagle_eye/execution/order_state_machine.py` — order lifecycle tracking |
| **Risk Guards (V7)** | |
| - trading_lock | `eagle_eye/risk/trading_lock.py` — emergency lock prevents all trades |
| - degraded_mode | `eagle_eye/risk/degraded_mode.py` — API 4x fail → no new positions, exits only |
| **Failure Mode** | Order rejected by Alpaca → logged, no retry (wash trade protection). Stop order cancel deadlock → system never cancels stops, only PATCHes qty. Position state file corrupt → `load_state` returns empty dict, system operates on Alpaca API truth. |

### 2.5 OMS → BROKER (Alpaca)

| Component | Details |
|-----------|---------|
| **Implementing Files** | `eagle_eye/broker/alpaca_client.py` (373 lines), `eagle_eye/core/http.py` |
| **Version** | V7.1 Phase 2.5 (Alpaca adapter is V7-only) |
| **V6 Path** | `~/.hermes/scripts/us_common.py` — `url_get()` direct HTTP to Alpaca |
| **API Endpoints** | |
| - Account | `GET /v2/account` — equity, cash, buying power |
| - Positions | `GET /v2/positions` — current holdings |
| - Orders | `GET /v2/orders`, `POST /v2/orders` — place/query orders |
| - Stop Orders | `POST /v2/orders` (type=stop), `PATCH /v2/orders/{id}` — stop management |
| - Bars | `GET /v2/stocks/{symbol}/bars` — historical OHLCV |
| **API Keys** | `~/.hermes/.env` → `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_BASE_URL` |
| **Base URL** | `https://paper-api.alpaca.markets` (paper trading, no real money) |
| **Data URL** | `https://data.alpaca.markets/v2/stocks` |
| **Failure Mode** | DNS failure → `eagle_heartbeat.py` detects via `socket.getaddrinfo`. HTTP 403 wash trade → order blocked, must reduce stop qty first. HTTP 429 rate limit → wait and retry. `pending_cancel` deadlock → never cancel stops, only PATCH. API down 4x consecutive → degraded_mode activates. |

---

## 3. SUPPORTING DATA PIPELINES

### 3.1 Market Environment Pipeline

```
market_env.py (V6 merged) → market_env.json
  ├── Part 1: 宏观温度计 (VIX/DXY/10Y-2Y/FOMC)
  │   ├── yfinance: ^VIX, DX-Y.NYB, ^TNX, ^FVX
  │   ├── Fallback: Alpaca VIXY ETF, FRED CSV (DGS2)
  │   └── FOMC: hardcoded calendar
  └── Part 2: 市场广度 (%>MA50, %>MA200, 涨跌比, 新高新低)
      ├── 83 stocks + 11 sector ETFs
      └── Alpaca IEX bars API
```

| File | Version | Reads | Writes |
|------|---------|-------|--------|
| `~/.hermes/scripts/market_env.py` | V6 (2026-06-15) | Alpaca API, yfinance, FRED CSV | `~/stock_trader/market_env.json` |
| `~/.hermes/scripts/market_breadth.py` | V5 (merged into market_env) | Alpaca API | `~/stock_trader/market_breadth.json` |
| `~/.hermes/scripts/macro_context.py` | V5 (merged into market_env) | yfinance, FRED | `~/stock_trader/macro_context.json` |

**Note:** `market_env.json` is the V6 canonical file. `macro_context.json` and `market_breadth.json` are legacy V5 outputs. `us_report.py` reads `market_env.json` first, falls back to legacy files.

### 3.2 Signal Decay Pipeline

```
us_signal_decay.py → signal_decay.json
  ├── Reads: Alpaca positions API
  ├── Reads: Alpaca bars API (per holding)
  └── Checks: RSI>75, MACD death cross, price<MA50, price<MA20, PnL>25%
```

| File | Version | Reads | Writes |
|------|---------|-------|--------|
| `~/.hermes/scripts/us_signal_decay.py` | V5 (2026-06-14) | Alpaca API (positions + bars) | `~/stock_trader/signal_decay.json` |

**Failure Mode:** Alpaca API timeout for individual symbol → symbol skipped with error message. `requests` library import failure → fallback to `urllib`.

### 3.3 Kelly Position Pipeline

```
us_kelly.py → trade_history.json
  ├── Reads: Alpaca orders API (90 days, paginated 500/page)
  ├── FIFO match: buy-sell pairing
  └── Output: win_rate, odds_ratio, kelly_full_pct, half_kelly
```

| File | Version | Reads | Writes |
|------|---------|-------|--------|
| `~/.hermes/scripts/us_kelly.py` | V5 (2026-06-14) | Alpaca API (orders history) | `~/stock_trader/trade_history.json` |

**Failure Mode:** Alpaca pagination → max 5 pages (2500 orders). Empty order history → Kelly defaults to conservative 5% allocation.

### 3.4 Parameter Calibration Pipeline

```
calibrator.py → calibrated_params.json
  ├── Reads: trade_history.json (win rate, odds)
  ├── Reads: us_screener_log.json (score distributions)
  ├── Reads: us_risk_state.json (stop outcomes)
  ├── Reads: ai_weight_config.json (current weights)
  └── Output: sigmoid params, stop tiers, score weights, sector bonuses, regime
```

| File | Version | Reads | Writes |
|------|---------|-------|--------|
| `~/.hermes/scripts/calibrator.py` | V1 (2026-06-17) | trade_history.json, us_screener_log.json, us_risk_state.json, ai_weight_config.json | `~/stock_trader/calibrated_params.json` |

**Failure Mode:** Missing input files → uses hardcoded defaults. Insufficient trade data → calibration_quality marked "low". Output consumed by `us_screener.py` Kelly function.

### 3.5 News/Events Pipeline

```
market_news.py (utility) ← used by market-event-monitor skill (cron)
  ├── Google News RSS (English)
  └── Sogou WeChat search (Chinese)

market-event-monitor cron job → market_events_latest.json
  ├── Uses: Google RSS + Sogou WeChat (via market_news.py)
  ├── Uses: terminal + web tool access
  └── Output: sector assessments, buy opportunities, market data
```

| File | Version | Reads | Writes |
|------|---------|-------|--------|
| `~/.hermes/scripts/market_news.py` | V4+ | Google News RSS, Sogou WeChat | N/A (utility) |
| `~/stock_trader/update_market_data.py` | V6 | qt.gtimg.cn (CN/HK prices) | `~/stock_trader/market_events_latest.json` (patch) |

**Failure Mode:** Google RSS blocked in China → `proxy_patch.py` auto-applies SOCKS5 proxy via mihomo. Sogou rate limit → fallback to cached results. Proxy down → Google fails, Sogou still works.

### 3.6 Compliance Audit Pipeline

```
compliance_audit.py → compliance_report.json
  ├── Reads: us_screener.py, us_trader.py, us_common.py (source code scanning)
  └── Checks: 20 user preference rules have code implementation
```

| File | Version | Reads | Writes |
|------|---------|-------|--------|
| `~/.hermes/scripts/compliance_audit.py` | V1 (2026-06-17) | Source code of scripts (regex scan) | `~/stock_trader/compliance_report.json` |

### 3.7 Contract Validation Pipeline

```
contract_validator.py → stdout (pass/fail)
  ├── Validates: trade_history.json, market_env.json, calibrated_params.json,
  │              us_watchlist.json, us_risk_state.json, signal_decay.json,
  │              us_portfolio.json, compliance_report.json
  └── Checks: required fields, field types
```

| File | Version | Reads | Writes |
|------|---------|-------|--------|
| `~/.hermes/scripts/contract_validator.py` | V1 (2026-06-18) | 8 JSON files | stdout only |

---

## 4. CRON JOB DEPENDENCIES

### 4.1 Active Cron Jobs

| Cron Job ID | Name | Schedule | Model | Script/Skill | WeChat Delivery |
|-------------|------|----------|-------|-------------|-----------------|
| `a638e8d39d5d` | 美股AI决策 | `10 21-5 * * 1-5` | deepseek-v4-flash | us_report.py + us_trader.py | **Yes** (o9cq800...) |
| `b735145148c4` | 美股GARP扫描 | `0 8 * * 1-5` | deepseek-v4-flash | us_screener.py | **Yes** (o9cq800...) |
| `d65b06eddcad` | 市场事件监控 | `0 */2 * * 1-5` | deepseek-v4-flash | market-event-monitor skill | local only |
| `147cc7f5088a` | 早间速报 | `0 9 * * 1-5` | deepseek-v4-flash | market-event-monitor skill | local only |
| `d3f17ab4ca86` | 午间速报 | `0 12 * * 1-5` | deepseek-v4-flash | market-event-monitor skill | local only |
| `28139eb5e759` | 美股盘后扫描 | `0 6 * * 1-5` | deepseek-v4-flash | market-event-monitor skill | **Yes** (o9cq800...) |
| `ea3e2530b0b7` | 持仓专题卡片 | `30 9 * * 1-5` | deepseek-v4-flash | Alpaca API direct | **Yes** (o9cq800...) |
| `0ca23f29fbde` | 凯利仓位计算 | `30 5 * * 6` | deepseek-v4-flash | us_kelly.py | **Yes** (o9cq800...) |
| `156e40a9c859` | 市场环境采集 | `30 20 * * 1-5` | deepseek-v4-flash | market_env.py | local only |
| `1da0dc5f927c` | 参数自校准 | `0 6 * * 6` | (none) | calibrator.py | local only |
| `8604888631f4` | 规则合规审计 | `10 6 * * 6` | (none) | compliance_audit.py | local only |
| `154d0c4e4f81` | Eagle Eye 日报 | `0 8 * * *` | deepseek-v4-flash | review_package.py | **Yes** (o9cq800...) |

### 4.2 Paused/Disabled Cron Jobs

| Cron Job ID | Name | Schedule | Status | Reason |
|-------------|------|----------|--------|--------|
| `d2378848e547` | 港股盘中事件监控 | `30 9-15 * * 1-5` | **paused** | Connection error |
| `5bbde6a44f31` | Cron交付监控 | `*/5 * * * *` | **paused** | (manual) |
| `31bbb6eeb546` | 信号衰减检测 | `0 21,23,1,3 * * 1-5` | **paused** | (manual) |
| `8bce957367ec` | Eagle Eye Heartbeat | `0 6,9,15,21 * * *` | **paused** | (manual) |
| `f185a347cd9f` | Ops Notification Relay | `* * * * *` | **paused** | (manual) |
| `8290d4140d57` | Scheduler Receipt | `*/5 * * * *` | **paused** | (manual) |

### 4.3 Cron Dependency Chain

```
INDEPENDENT (can run in any order):
  market_env.py          → market_env.json
  us_screener.py         → us_watchlist.json, us_screener_log.json
  market-event-monitor   → market_events_latest.json
  us_kelly.py            → trade_history.json (weekly)
  calibrator.py          → calibrated_params.json (weekly, reads trade_history.json)
  compliance_audit.py    → compliance_report.json (weekly)

DEPENDENT (must run after scan):
  us_report.py           → reads us_watchlist.json, market_env.json, signal_decay.json
                           → us_portfolio.py (called via subprocess)
                           → generates unified report for AI

DEPENDENT (must run after AI decision):
  us_trader.py --execute → reads us_watchlist.json, us_risk_state.json
                           → calls Alpaca API to place orders

DEPENDENT (must run after orders placed):
  us_trader.py --stops   → reads us_risk_state.json
                           → updates trailing stops on Alpaca

DEPENDENCY GRAPH:
  [market_env.py] ──┐
  [us_screener.py] ─┤
  [market-events] ──┼──▶ [us_report.py] ──▶ [AI Decision] ──▶ [us_trader.py --execute]
  [us_kelly.py] ────┤                                          ──▶ [us_trader.py --stops]
  [signal_decay.py] ┘
```

---

## 5. WECHAT DELIVERY DEPENDENCIES

### 5.1 Delivery Path

```
Script Output → Hermes Agent Gateway → iLink WeChat API → Owner's WeChat
                       │
                       ├── Direct delivery (cron jobs with deliver="weixin")
                       └── Spool delivery (V7.1 notification system)
                           ├── ops_notify_relay.py (every 1 min, reads spool)
                           ├── eagle_heartbeat.py (every 4h, health checks)
                           └── ops_scheduler_receipt.py (every 5 min, failure alerts)
```

### 5.2 WeChat Push Policy V3 (Effective)

| Notification Type | Frequency | Max/Day | Trigger |
|-------------------|-----------|---------|---------|
| Daily Investment Review | 1/day | 1 | First AI_DECISION cycle complete |
| Trade Executed | On fill | 0-5 | Real order filled on Alpaca |
| Critical Alert | On event | 0-3 | EMERGENCY_STOP, OFFLINE>60min, AI missed ≥2 cycles, drawdown>10%, broker fail ≥30min |
| **Daily Total Cap** | — | **8** | Hard limit |

### 5.3 Permanently Blocked (WeChat Push Policy V3)

Eagle Heartbeat, Scheduler Receipt, Watchdog SUCCESS, Health Check SUCCESS,
Market Environment, Signal Decay, SUCCESS, ONLINE, RESTORED, WARNING, YELLOW, INFO

### 5.4 WeChat Failure Modes

| Failure | Symptom | Detection |
|---------|---------|-----------|
| Rate limit | `iLink sendmessage rate limited: ret=-2` | `cron_watchdog.py` checks gateway logs |
| Connection refused | `Cannot connect to host ilinkai.weixin.qq.com:443` | Gateway log + ops_scheduler_receipt |
| Gateway dead | No delivery at all | `cron_watchdog.py` checks gateway process |
| Spool overflow | >50 unprocessed notifications | `eagle_eye/ops/notification.py` escalation |

---

## 6. ALPACA API DEPENDENCIES

### 6.1 Scripts That Call Alpaca API

| Script | API Calls | Purpose |
|--------|-----------|---------|
| `us_common.py` | `GET /v2/stocks/{symbol}/bars` | Daily OHLCV bars for technical indicators |
| `us_screener.py` | `GET /v2/stocks/{symbol}/bars` (×87 parallel) | Scan universe for scoring |
| `us_trader.py` | `GET /v2/account`, `GET /v2/positions`, `GET /v2/orders`, `POST /v2/orders`, `PATCH /v2/orders/{id}` | Full OMS operations |
| `us_portfolio.py` | `GET /v2/account`, `GET /v2/positions` | Portfolio snapshot |
| `us_signal_decay.py` | `GET /v2/positions`, `GET /v2/stocks/{symbol}/bars` | Decay detection per holding |
| `us_kelly.py` | `GET /v2/orders?status=closed` | 90-day order history |
| `market_env.py` | `GET /v2/stocks/{symbol}/bars` | VIXY fallback, breadth scan |
| `market_breadth.py` | `GET /v2/stocks/{symbol}/bars` (×94) | 83 stocks + 11 ETFs |
| `eagle_heartbeat.py` | `GET /v2/account` | Health check ping |
| `review_package.py` | `GET /v2/account`, `GET /v2/positions`, `GET /v2/orders` | Daily review report |

### 6.2 API Key Source

```
~/.hermes/.env → ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL
     ↑
~/stock_trader/config.py (reads from env, fallback defaults)
     ↑
All scripts import from config.py or read .env directly
```

### 6.3 Alpaca Rate Limits & Known Issues

| Issue | Impact | Workaround |
|-------|--------|------------|
| Rate limit (429) | Scan blocked | 3-retry with 3s sleep in `url_get()` |
| Wash trade (403) | Order rejected | Reduce stop qty first, then sell |
| Stop cancel deadlock | `pending_cancel` state | **Never cancel stops** — only PATCH qty |
| DNS failure | No connectivity | `eagle_heartbeat.py` detects, triggers degraded mode |
| Ghost stops | Stop orders for closed positions | Don't cancel — let Alpaca expire naturally |

---

## 7. DATA FILE DEPENDENCY MATRIX

### 7.1 JSON Files (~/stock_trader/)

| File | Writer(s) | Reader(s) | Frequency |
|------|-----------|-----------|-----------|
| `market_env.json` | market_env.py | us_report.py, calibrator.py | Daily 20:30 BJT |
| `macro_context.json` | macro_context.py (V5 legacy) | us_report.py (fallback) | Deprecated |
| `market_breadth.json` | market_breadth.py (V5 legacy) | us_report.py (fallback) | Deprecated |
| `market_events_latest.json` | market-event-monitor cron, update_market_data.py | us_screener.py, us_report.py, us_trader.py | Every 2h |
| `us_watchlist.json` | us_screener.py | us_report.py, us_trader.py | Daily 08:00 BJT |
| `us_screener_log.json` | us_screener.py | calibrator.py | Daily 08:00 BJT |
| `us_portfolio.json` | us_portfolio.py (subprocess) | us_report.py, us_screener.py | Every AI decision cycle |
| `us_risk_state.json` | us_trader.py | us_trader.py, us_report.py, calibrator.py | Every trade execution |
| `us_recent_stops.json` | us_trader.py | us_screener.py (blacklist), us_report.py | Every stop event |
| `us_pending_replacements.json` | us_trader.py | us_trader.py | Sell→buy pairs |
| `trade_history.json` | us_kelly.py | calibrator.py, us_report.py | Weekly Sat |
| `signal_decay.json` | us_signal_decay.py | us_report.py | Every 2h (when active) |
| `calibrated_params.json` | calibrator.py | us_screener.py (Kelly), us_trader.py | Weekly Sat |
| `compliance_report.json` | compliance_audit.py | Human review | Weekly Sat |
| `ai_weight_config.json` | AI (first cycle) or manual | us_screener.py (weights), calibrator.py | Daily AI adjustment |
| `earnings_cache.json` | us_screener.py | us_screener.py (24h cache) | Per scan |
| `behavior_fingerprint.json` | eagle_eye/ops/behavior_fingerprint.py | Audit system | On-demand |

### 7.2 SQLite Database

| Database | Writer(s) | Reader(s) | Purpose |
|----------|-----------|-----------|---------|
| `~/stock_trader/eagle_eye.db` | eagle_eye modules (V7) | eagle_heartbeat.py, candidate_tracker, notification system | Central V7 state store |

### 7.3 Config/Environment Files

| File | Reader(s) | Purpose |
|------|-----------|---------|
| `~/.hermes/.env` | All scripts (via config.py or direct) | Alpaca API keys, secrets |
| `~/stock_trader/config.py` | us_screener.py, market_env.py, market_breadth.py, us_portfolio.py | API key wrapper |
| `~/stock_trader/auto_approval_policy.md` | AI decision loop, policy_validator.py | Trading rules |
| `~/.hermes/wechat_push_policy_v3.md` | AI decision loop | Notification rules |

---

## 8. V6 vs V7 MODULE MAPPING

### 8.1 V6 Scripts (Standalone, ~/.hermes/scripts/)

| Script | Status | V7 Equivalent |
|--------|--------|---------------|
| `us_common.py` | **Active** (imported by all) | `eagle_eye/core/http.py`, `eagle_eye/strategy/indicator_engine.py` |
| `us_screener.py` | **Active** (not yet migrated) | — |
| `us_report.py` | **Active** (not yet migrated) | — |
| `us_trader.py` | **Active** (thin V7 wrapper) | `eagle_eye/execution/trade_executor.py` |
| `us_portfolio.py` | **Active** (subprocess from us_report) | `eagle_eye/portfolio/portfolio_manager.py` |
| `us_kelly.py` | **Active** (not yet migrated) | `eagle_eye/portfolio/kelly_engine.py` |
| `us_signal_decay.py` | **Active** (not yet migrated) | `eagle_eye/strategy/signal_decay.py` |
| `market_env.py` | **Active** (V6 merged version) | `eagle_eye/strategy/market_env.py` |
| `market_breadth.py` | **V5 legacy** (merged into market_env) | `eagle_eye/strategy/market_breadth.py` |
| `macro_context.py` | **V5 legacy** (merged into market_env) | — |
| `calibrator.py` | **Active** (weekly) | — |
| `compliance_audit.py` | **Active** (weekly) | `eagle_eye/ops/audit_engine.py` |
| `contract_validator.py` | **Active** (on-demand) | — |
| `market_news.py` | **Active** (utility) | — |
| `proxy_start.py` | **Active** (infrastructure) | — |
| `proxy_patch.py` | **Active** (auto-imported) | — |
| `us_trader_v6.py` | **Legacy backup** | — |

### 8.2 V7 Modules (eagle_eye package, ~/eagle_eye/)

| Module | Purpose | Depends On |
|--------|---------|------------|
| `core/config.py` | Configuration loader | ~/.hermes/.env |
| `core/http.py` | HTTP helpers (alpaca_get/post/patch/delete) | — |
| `core/cache.py` | In-memory cache | — |
| `core/logger.py` | Structured logging | — |
| `broker/alpaca_client.py` | Alpaca API adapter (single entry point) | core/http.py, core/config.py |
| `execution/trade_executor.py` | Trade orchestrator (CLI entry) | All execution/*, risk/*, broker/* |
| `execution/position_manager.py` | Position state, tech analysis | core/http.py |
| `execution/order_manager.py` | Order CRUD, API calls | broker/alpaca_client.py |
| `execution/stop_loss_manager.py` | Trailing stops, blacklist | position_manager, order_manager |
| `execution/take_profit_manager.py` | TP1/TP2 execution | order_manager |
| `execution/order_intent.py` | OrderIntent dataclass | — |
| `execution/order_state_machine.py` | Order lifecycle tracking | storage/db.py |
| `execution/candidate_tracker.py` | Multi-cycle candidate tracking | storage/db.py |
| `portfolio/portfolio_manager.py` | Portfolio analysis | broker/alpaca_client.py |
| `portfolio/kelly_engine.py` | Kelly position sizing | — |
| `portfolio/allocation_engine.py` | Sector allocation | — |
| `strategy/market_env.py` | Market environment (V7 port) | — |
| `strategy/market_breadth.py` | Market breadth (V7 port) | — |
| `strategy/indicator_engine.py` | Technical indicators | — |
| `strategy/signal_decay.py` | Signal decay detection | — |
| `risk/policy_validator.py` | Auto-approval policy enforcement | execution/candidate_tracker |
| `risk/trading_lock.py` | Emergency trading lock | — |
| `risk/degraded_mode.py` | Degraded mode (API fail → restricted) | — |
| `ops/notification.py` | Spool-based notification system | — |
| `ops/emergency_stop.py` | Emergency stop handler | — |
| `ops/behavior_fingerprint.py` | Behavior fingerprinting | — |
| `ops/shadow_mode.py` | Shadow mode (dry-run) | — |
| `ops/watchdog.py` | System watchdog | — |
| `ops/scheduler.py` | Internal scheduler | — |
| `ops/health_check.py` | Health check | — |
| `ops/audit_engine.py` | Audit engine | — |
| `storage/db.py` | SQLite connection manager | eagle_eye.db |
| `storage/models.py` | Data models | — |
| `storage/repositories.py` | Repository pattern | storage/db.py |
| `storage/repos/*.py` | Per-domain repos | storage/db.py |
| `storage/migrate.py` | DB migrations | storage/db.py |
| `main.py` | CLI entry point | All modules |

---

## 9. NETWORK/INFRASTRUCTURE DEPENDENCIES

### 9.1 Proxy (mihomo/clash-meta)

```
proxy_start.py → mihomo daemon (SOCKS5 :7891, HTTP :7890)
  ├── proxy_patch.py → auto-patches urllib for SOCKS5
  ├── Used by: market_news.py (Google RSS access)
  ├── Used by: market-event-monitor cron (web searches)
  └── Config: ~/.config/mihomo/config.yaml
```

### 9.2 External Service Map

| Service | Endpoint | Used By | Fallback |
|---------|----------|---------|----------|
| Alpaca Paper Trading | paper-api.alpaca.markets | All trading scripts | None (critical path) |
| Alpaca Data (IEX) | data.alpaca.markets | Price bars, market data | yfinance (partial) |
| Yahoo Finance | query1.finance.yahoo.com | VIX, DXY, yields, fundamentals | Alpaca VIXY, FRED CSV |
| Google News RSS | news.google.com | market_news.py, event monitor | Sogou WeChat (CN) |
| Sogou WeChat | weixin.sogou.com | market_news.py (Chinese sources) | Google RSS (EN) |
| FRED | fred.stlouisfed.org | 2Y yield fallback | Hardcoded |
| DeepSeek API | api.deepseek.com | AI decision model | None (cron fails) |
| iLink WeChat API | ilinkai.weixin.qq.com | WeChat push delivery | Spool queue (retry) |
| qt.gtimg.cn | qt.gtimg.cn | CN/HK market data (update_market_data.py) | None |

---

## 10. FAILURE CASCADE SCENARIOS

### 10.1 Full System Failure Chain

```
Internet Down
  → Alpaca API unreachable → degraded_mode activates
  → Scanner fails → no us_watchlist.json
  → AI decision cron runs but no new data → stale decisions
  → us_trader.py --stops fails → stops not updated
  → eagle_heartbeat.py detects → SYSTEM_OFFLINE notification
  → WeChat push (if gateway alive) → Critical Alert
```

### 10.2 AI Model Failure

```
DeepSeek API down
  → AI decision cron job fails (last_status: error)
  → No new trades placed (safe — no execution without AI)
  → Mechanical stops still run via us_trader.py --stops (if called)
  → ops_scheduler_receipt.py detects failure → alert
```

### 10.3 WeChat Rate Limit Chain

```
WeChat rate limited (ret=-2)
  → Daily Investment Review not delivered
  → Trade Executed notifications queued in spool
  → ops_notify_relay.py retries next minute
  → After 8 messages/day → auto-silent (push policy V3)
  → No impact on trading (WeChat is output-only)
```

---

*End of Dependency Map*
