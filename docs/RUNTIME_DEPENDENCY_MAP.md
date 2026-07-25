# RUNTIME_DEPENDENCY_MAP

**Version:** 1.0
**Generated:** 2026-06-19
**Scope:** Runtime infrastructure dependency chain from hardware to broker execution
**Status:** DOCUMENTATION ONLY — No architectural changes permitted (14-day freeze active)
**Related:** DEPENDENCY_MAP.md (data flow), FAILOVER_PLAN.md (recovery procedures)

---

## 1. RUNTIME STACK OVERVIEW

```
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 1: ANDROID HARDWARE (Xiaomi Pad 5)                       │
│   ↓                                                             │
│ LAYER 2: TERMUX RUNTIME                                         │
│   ↓                                                             │
│ LAYER 3: HERMES GATEWAY (Node.js + iLink)                      │
│   ↓                                                             │
│ LAYER 4: SCHEDULER (Hermes Cron Engine)                         │
│   ↓                                                             │
│ LAYER 5: CRON SESSION (Python + AI Model)                       │
│   ↓                                                             │
│ LAYER 6: AI_DECISION (deepseek-v4-flash)                        │
│   ↓                                                             │
│ LAYER 7: OMS (eagle_eye modules)                                │
│   ↓                                                             │
│ LAYER 8: BROKER (Alpaca Paper Trading API)                      │
└─────────────────────────────────────────────────────────────────┘
```

Each layer depends on ALL layers below it. Failure at any lower layer
cascades upward. No layer can skip its dependency chain.

---

## 2. LAYER-BY-LAYER DEPENDENCY MAP

### LAYER 1: ANDROID HARDWARE

| Dependency | SPOF | Criticality | Owner Action |
|------------|:----:|:-----------:|--------------|
| Xiaomi Pad 5 battery | YES | P0 — ALL GONE | Keep plugged in 24/7. Battery swelling → replace Pad. |
| Android 13 OS | YES | P0 — ALL GONE | No action. OS auto-updates are safe (Termux survives). |
| WiFi network | YES | P0 — ALL GONE | Dual-band router. Ethernet adapter if WiFi unstable. |
| Android power management | YES | P0 — ALL GONE | Termux:WakeLock held by gateway. Verify `termux-wake-lock` active. |
| `/data/user/0` partition (107G) | YES | P1 — DEGRADED | Monitor usage. >85% → clean usr/tmp/. Current: ~82G/77%. |
| Termux:Boot (auto-start) | YES | P1 — COLD START | Without it, manual restart after reboot. Verify installed. |

**Notes:**
- Pad is powered 24/7. Power loss → all processes die → requires manual restart.
- Android Doze mode can kill background processes. Termux:WakeLock prevents this.
- `termux-wake-lock` must be held by the Hermes gateway process for survival.

---

### LAYER 2: TERMUX RUNTIME

| Dependency | SPOF | Criticality | Owner Action |
|------------|:----:|:-----------:|--------------|
| Termux app process | YES | P0 — ALL GONE | Killed by Android OOM → Termux:Boot restarts on reboot. |
| Python 3.13 | YES | P0 — ALL GONE | `pkg upgrade python` safe. Venv survives upgrades. |
| sitecustomize.py (DNS fix) | YES | P1 — DEGRADED | Location: `~/.local/lib/python3.13/site-packages/sitecustomize.py`. DoH fix for 198.18.0.x hijack. Missing → Alpaca timeouts. |
| mihomo proxy daemon | YES | P1 — DEGRADED | SOCKS5:7891. `proxy_start.py status/start`. Down → Google News RSS blocked, yfinance blocked. Alpaca direct works. |
| `$PREFIX/tmp/` writable | NO | P2 — MINOR | Termux /tmp is read-only. Use `~/`, `~/stock_trader/logs/`, `$PREFIX/tmp/`. |
| `pip` packages (requests, yfinance, pandas) | NO | P2 — MINOR | Reinstallable. `pip install requests yfinance pandas tzdata`. |
| DNS resolution | YES | P1 — DEGRADED | 198.18.0.x hijack detected. sitecustomize.py DoH fallback. hosts file pin for Alpaca. |

**Notes:**
- Termux is an Android app, not a system service. Android can kill it under memory pressure.
- The mihomo proxy is a separate process started by `proxy_start.py`. It has no auto-restart mechanism beyond what cron provides.
- `PYTHONUNBUFFERED=1` must be set for cron scripts (background process output buffering issue).

---

### LAYER 3: HERMES GATEWAY

| Dependency | SPOF | Criticality | Owner Action |
|------------|:----:|:-----------:|--------------|
| Hermes Gateway process (Node.js) | YES | P0 — ALL GONE | Single process. Crashes → no cron execution, no WeChat delivery, no AI. |
| iLink WeChat API connection | YES | P1 — WECHAT DEAD | `ilinkai.weixin.qq.com:443`. Disconnected → messages queued in spool. Auto-reconnect. |
| Gateway .env configuration | YES | P1 — SILENT FAIL | `~/.hermes/.env` must have valid API keys. Missing keys → silent auth failures. |
| Gateway log rotation | NO | P2 — MINOR | `~/.hermes/logs/gateway.log`. No rotation configured. Grows until disk full. |
| WeChat Push Policy V3 | NO | P3 — NONE | Policy is enforced at prompt level, not code. Incorrect policy → noisy/silent notifications, no trading impact. |

**Notes:**
- The gateway is the ONLY process that bridges Hermes AI to the outside world (cron, WeChat, tools).
- If gateway dies, cron jobs stop firing but existing stop orders on Alpaca remain active (protection continues).
- iLink disconnection window: check `gateway.log` for `Cannot connect to host ilinkai.weixin.qq.com`. Messages during disconnection are queued and delivered on reconnect.
- Gateway log timestamps = Hermes receipt time ≠ user message send time (queue delivery delay).

---

### LAYER 4: SCHEDULER (Hermes Cron Engine)

| Dependency | SPOF | Criticality | Owner Action |
|------------|:----:|:-----------:|--------------|
| Hermes scheduler process | YES | P0 — ALL GONE | Runs inside gateway. Gateway death = scheduler death. |
| Cron job definitions | YES | P1 — SILENT FAIL | Jobs defined in `~/.hermes/cron/`. Missing job → that pipeline stops silently. |
| System clock accuracy | YES | P1 — WRONG TIME | `ntpd` or manual sync. Wrong clock → jobs fire at wrong time or miss market windows. |
| Timezone (Asia/Shanghai BJT) | YES | P1 — WRONG TIME | All schedules are BJT. DST changes → 1h offset in market window. |
| deliver target (`o9cq800...`) | NO | P2 — NO PUSH | WeChat delivery target. Wrong target → messages go to wrong chat. Trading unaffected. |
| Cron job health (last_status) | NO | P3 — STALE DATA | Monitor via `cronjob action='list'`. Persistent `error` → investigate. |

**Notes:**
- 12 active cron jobs. 6 paused (V3 push policy closed them).
- Market-critical crons: `美股AI决策` (hourly during market), `美股GARP扫描` (daily 08:00), `Eagle Eye日报` (daily 08:00).
- Weekend crons: `凯利仓位计算` (Sat 05:30), `参数自校准` (Sat 06:00), `规则合规审计` (Sat 06:10).
- Cron failure detection: `ops_scheduler_receipt.py` (paused in V3). Manual check: `cronjob action='list'`.

---

### LAYER 5: CRON SESSION (Python + AI Model)

| Dependency | SPOF | Criticality | Owner Action |
|------------|:----:|:-----------:|--------------|
| Python 3.13 in cron session | YES | P0 — NO EXECUTION | Cron uses system Python. Broken Python → all scripts fail. |
| `eagle_eye` package importable | YES | P0 — NO EXECUTION | `~/eagle_eye/` must be on Python path. `sys.path` or `python3 -m eagle_eye.main`. |
| `~/.hermes/.env` loaded | YES | P1 — NO API ACCESS | Alpaca keys, DeepSeek key loaded into cron environment. Missing → all API calls fail. |
| V6 scripts (`~/.hermes/scripts/`) | YES | P1 — PARTIAL FAIL | us_screener.py, us_report.py, us_trader.py still V6 standalone. Missing → specific pipeline fails. |
| SQLite database (`eagle_eye.db`) | YES | P1 — PARTIAL FAIL | V7 modules use SQLite. Missing/corrupt → candidate_tracker, order_state_machine fail. V6 scripts unaffected. |
| JSON state files (`~/stock_trader/*.json`) | NO | P2 — STALE DATA | Missing JSON → graceful degradation (None/default values). System runs on stale data. |
| Skills loaded (`stock-trading-system`) | NO | P3 — NONE | Skill provides context to AI. Missing → AI has less system knowledge but cron prompt carries instructions. |

**Notes:**
- Each cron job runs in a fresh session with no memory of previous runs.
- The AI reads its prompt (self-contained instructions) + loaded skills + injected context (memory, cron output from prior jobs).
- `context_from` field on cron jobs chains output from upstream jobs (e.g., AI decision reads scanner output).

---

### LAYER 6: AI_DECISION (deepseek-v4-flash)

| Dependency | SPOF | Criticality | Owner Action |
|------------|:----:|:-----------:|--------------|
| DeepSeek API availability | YES | P0 — NO DECISIONS | `api.deepseek.com`. Down → AI cron fails, no new trades, mechanical stops still run if --stops called separately. |
| DeepSeek API key | YES | P0 — NO DECISIONS | In `~/.hermes/.env`. Expired/invalid → all AI crons fail with auth error. |
| Token budget (41B/¥39 Plan Lite) | YES | P1 — THROTTLED | Monthly cap. Exceeded → API rejects. Current usage ~2.85B tokens/month, 88-97% cache hit rate. |
| model=`deepseek-v4-flash` | NO | P2 — DEGRADED | Can switch to `mimo-v2.5-pro` or `deepseek-v4-pro`. Different quality but functional. |
| Prompt injection (cron prompt) | NO | P3 — WRONG DECISION | Cron prompt carries all trading rules. Malformed prompt → AI makes bad decisions. |
| `auto_approval_policy.md` | NO | P3 — POLICY BYPASS | Policy file read by AI. Missing → AI lacks guardrails but policy_validator.py (code) still enforces. |

**Notes:**
- AI = Recommendation Engine, NOT executor. AI generates OrderIntents, policy_validator + hard guards + OMS + broker execute.
- If DeepSeek is down, mechanical stops (`us_trader.py --stops`) can still be called manually.
- The AI's decisions are constrained by: (1) prompt instructions, (2) policy_validator.py, (3) hard guards in OMS, (4) Alpaca wash trade protection.
- AI cannot bypass any code-level guard. Even a hallucinated "BUY 10000 shares" is rejected by position/sector/exposure limits.

---

### LAYER 7: OMS (eagle_eye modules)

| Dependency | SPOF | Criticality | Owner Action |
|------------|:----:|:-----------:|--------------|
| `broker/alpaca_client.py` | YES | P0 — NO TRADES | Single entry point for ALL Alpaca API calls. Import failure → entire OMS dead. |
| `risk/trading_lock.py` | YES | P0 — LOCKED OUT | Auto-locks on: DB unhealthy, API unhealthy, market data missing, market closed, degraded mode. Lock = zero trades. |
| `risk/degraded_mode.py` | YES | P1 — RESTRICTED | 4x consecutive API fail → no new positions, exits only. 3x success → auto-recover. |
| `risk/policy_validator.py` | YES | P1 — REJECTED | Every OrderIntent passes through. Policy violation → order rejected. |
| `execution/trade_executor.py` | YES | P0 — NO TRADES | Orchestrator. Coordinates position_manager, order_manager, stop_loss, take_profit. |
| `execution/order_state_machine.py` | NO | P2 — AUDIT LOSS | Tracks PENDING→VALIDATING→APPROVED→SUBMITTED→FILLED→COMPLETED. Failure → lost audit trail but orders still execute. |
| `execution/candidate_tracker.py` | NO | P2 — WRONG GATES | Multi-cycle candidate tracking. Failure → multi-cycle gate defaults to 0 (blocks all entries, safe default). |
| `us_risk_state.json` | NO | P2 — STALE STOPS | Tracks per-position highest price for trailing stops. Corrupt → `load_state` returns empty dict, re-fetches from Alpaca API truth. |

**Notes:**
- trading_lock is the ultimate kill switch. It checks 5 conditions before allowing ANY trade. Cannot be bypassed by AI or scripts.
- degraded_mode is the "limp home" mode. API failing → stop trying new things, just protect existing positions.
- policy_validator enforces: sell discipline (≥2 triggers), no same-day full clear, hard constraints (18%/30%/90%), multi-cycle candidate gate.
- Emergency stop (`ops/emergency_stop.py`) → sets trading_lock permanently. Requires manual reset.

---

### LAYER 8: BROKER (Alpaca Paper Trading API)

| Dependency | SPOF | Criticality | Owner Action |
|------------|:----:|:-----------:|--------------|
| Alpaca Paper API (`paper-api.alpaca.markets`) | YES | P0 — NO TRADES | All order execution. Down → orders fail but stop orders already on Alpaca server continue to protect. |
| Alpaca Data API (`data.alpaca.markets`) | YES | P1 — NO SCANNING | Price bars for scanner. Down → screener fails, AI makes decisions on stale data. |
| Alpaca API keys | YES | P0 — NO TRADES | In `~/.hermes/.env`. Invalid → all API calls return 401. |
| DNS resolution to Alpaca | YES | P0 — NO TRADES | 198.18.0.x hijack risk. sitecustomize.py DoH fix + hosts file pin for 198.18.0.24. |
| Internet connectivity (outbound HTTPS) | YES | P0 — NO TRADES | Required for all API calls. China → Alpaca is direct (not blocked). Google/yfinance need proxy. |
| Paper trading mode | NO | P3 — NONE | Paper API vs live. All positions are simulated. No real money at risk. |
| Alpaca rate limits (429) | NO | P2 — DELAYED | 3-retry with 3s sleep in `url_get()`. Scanner (87 symbols) is parallelized. |
| Wash trade protection (403) | NO | P2 — BLOCKED | Stop order locks position. Must PATCH stop qty first, then sell. |
| Stop order cancel deadlock | NO | P2 — LOCKED | `pending_cancel` state. **NEVER cancel stops** — only PATCH qty. |

**Notes:**
- Alpaca server-side stop orders are the LAST LINE OF DEFENSE. Even if the entire local system dies, stop orders continue to execute on Alpaca's servers.
- Ghost stop orders (stale stops for closed positions) are harmless. Never cancel them.
- Alpaca orders submitted during US market close have `status="new"` and execute at next open.
- Market hours: BJT 21:30–04:00 (US 9:30AM–4:00PM). Pre-market/after-hours not enabled.

---

## 3. SPOF SUMMARY

### P0 SPOFs (System-wide failure)

| SPOF | Layer | Impact | Mitigation |
|------|-------|--------|------------|
| Pad power loss | L1 | Everything dies | Keep plugged in. UPS if possible. |
| Termux killed by Android | L2 | Everything dies | Termux:WakeLock + Termux:Boot. |
| Gateway process crash | L3 | No cron, no WeChat, no AI | Manual restart. No auto-restart mechanism. |
| DeepSeek API down | L6 | No AI decisions | Mechanical stops still work if called manually. |
| Alpaca API down | L8 | No trades, no data | Server-side stops still active. degraded_mode activates. |
| Internet down | L8 | No API access | All external calls fail. Local Python/Jupyter unaffected. |
| DNS failure to Alpaca | L8 | No API access | sitecustomize.py DoH fallback. hosts file pin. |

### P1 SPOFs (Degraded operation)

| SPOF | Layer | Impact | Mitigation |
|------|-------|--------|------------|
| mihomo proxy down | L2 | Google News + yfinance blocked | `proxy_start.py start`. Alpaca direct works. |
| iLink disconnected | L3 | WeChat delivery paused | Auto-reconnect. Messages queued in spool. |
| Scheduler clock wrong | L4 | Jobs fire at wrong time | ntpd sync. Manual check. |
| Alpaca Data API down | L8 | Scanner fails | AI uses stale watchlist. |
| degraded_mode activated | L7 | No new positions | Auto-recovers after 3x API success. |

---

## 4. CRITICAL PATH: TRADE EXECUTION

The longest unbroken dependency chain for a single trade:

```
Android battery alive
  → Termux process running
    → Gateway process running
      → Scheduler fires cron job
        → Cron session starts Python
          → AI model responds (DeepSeek API)
            → OrderIntent created
              → policy_validator passes (PASS)
                → trading_lock unlocked
                  → degraded_mode not active
                    → alpaca_client.place_order()
                      → DNS resolves correctly
                        → Alpaca API reachable
                          → No wash trade conflict
                            → Order submitted
                              → Market open (BJT 21:30-04:00)
                                → Order filled
```

**Chain length: 16 links.** Any single link breaks the chain.
**Mitigation: Server-side stop orders on Alpaca survive ALL local failures.**

---

## 5. AUTONOMY WINDOW

When the Pad is on and Termux is running but Hermes gateway is down:

| Component | Status | Notes |
|-----------|--------|-------|
| Alpaca stop orders | ✅ ACTIVE | Server-side, independent of local system |
| Python scripts (manual) | ✅ WORK | Can run `us_trader.py --stops` directly |
| Cron jobs | ❌ DEAD | No automatic execution |
| AI decisions | ❌ DEAD | No LLM calls |
| WeChat notifications | ❌ DEAD | No gateway to deliver |

**Maximum autonomous protection window:** Indefinite — Alpaca stop orders persist until triggered or the market closes the position.

---

## 6. KNOWN GAPS (Owner Action Required)

| # | Gap | Risk | Recommendation |
|---|-----|------|----------------|
| 1 | No gateway auto-restart | Gateway crash → silent failure until manual check | Investigate s6-overlay supervision for gateway process |
| 2 | No disk space monitoring | Full disk → all writes fail silently | Add cron watchdog for `/data/user/0` > 90% |
| 3 | No mihomo auto-restart | Proxy down → Google News + yfinance fail | Already handled: `proxy_start.py start` in market_env cron |
| 4 | Gateway log no rotation | Log grows until disk full | Add logrotate or size-based rotation |
| 5 | No battery level monitoring | Battery dies → total system failure | Add Termux API battery check in heartbeat |
| 6 | Single Pad, no redundancy | Hardware failure → total loss | Accept risk (paper trading) or add cloud backup |
| 7 | DeepSeek API key expiry | Silent auth failure | Monitor `last_status` in cron job list |
| 8 | SQLite lock contention | Concurrent V7 writes can deadlock | WAL mode enabled, but single-writer still blocks |

---

## 7. RECOVERY ORDER (Cold Start)

If everything is down, restart in this exact order:

```
1. Power on Pad (if off)
2. Open Termux app
3. Run: termux-wake-lock
4. Check proxy: python3 ~/.hermes/scripts/proxy_start.py status
   (If down: python3 ~/.hermes/scripts/proxy_start.py start)
5. Hermes gateway auto-starts (Termux:Boot)
6. Verify gateway: hermes status
7. Verify cron: (inside Hermes session) cronjob action='list'
8. Verify Alpaca: python3 -c "import socket; print(socket.getaddrinfo('paper-api.alpaca.markets',443)[0][4][0])"
9. Run health check: cd ~ && python3 -m eagle_eye.main health
10. Run stop coverage audit (see SKILL.md "止损覆盖审计")
```

**Time to recover:** ~2 minutes (manual steps 2-10).
**Risk during recovery:** Alpaca server-side stops are active throughout. No gap in protection.

---

## 8. DOCUMENT CONTROL

| Field | Value |
|-------|-------|
| Owner Mandate | V1.1 — 14-day freeze active |
| CORE_TRADING_CHAIN | FROZEN — no modifications permitted |
| SIMPLIFICATION_PLAN | NOT approved for bulk execution |
| Deletions | 1 per 24h, individual approval required |
| This document | Documentation only, no architectural changes |

---

*End of Runtime Dependency Map*
