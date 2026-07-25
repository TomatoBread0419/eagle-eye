# Eagle Eye Failover Plan

**Version:** 1.0
**Created:** 2026-06-19
**System:** Pad5 Android/Termux, 24h running
**Goal:** Survive 14 days without owner intervention

---

## Executive Summary

The Eagle Eye system has **partial resilience** with significant gaps. Stop-loss orders
are server-side on Alpaca (they survive local outages). The cron/gateway system has
auto-restart capability, but **no Termux:Boot auto-start is configured** — a full phone
reboot requires manual intervention. The degraded mode and trading lock provide safety
rails during API failures.

---

## Scenario 1: Phone Dies / Reboots

### What happens:
- **Termux auto-start:** ❌ NOT CONFIGURED. No Termux:Boot script found at
  `~/.termux/boot/`. After reboot, Termux does NOT start automatically.
- **Hermes gateway auto-start:** ❌ NO. Gateway must be started manually or via Termux.
- **Cron resume:** ❌ NO. Cron is managed by the Hermes gateway process. If gateway
  is not running, no cron jobs execute.

### Impact:
- All scheduled cron jobs stop (US trading decisions, screener, market monitoring)
- No new trades can be executed
- No notifications sent via WeChat
- **Server-side stop-loss orders on Alpaca continue working** (they live on Alpaca's servers)

### Recovery:
1. Owner must manually open Termux on the phone
2. Start the Hermes gateway (typically `hermes gateway` or similar)
3. Gateway auto-detects cron jobs in `~/.hermes/cron/jobs.json` and resumes scheduling
4. Startup log shows: "启动检查... DNS 正常 → 启动网关... → 启动完成"

### Risk Level: 🔴 HIGH
**Mitigation:** Install Termux:Boot and create auto-start script at `~/.termux/boot/start_hermes.sh`

---

## Scenario 2: Termux Crashes

### What happens:
- **Termux auto-restart:** ❌ NO. Android does not auto-restart crashed Termux sessions.
- **Hermes gateway:** Dies with Termux. No watchdog outside Termux to restart it.
- **Cron resume:** ❌ NO until gateway is restarted.

### Evidence from logs:
Startup log shows frequent "启动网关..." entries (gateway was down, being restarted),
indicating this happens regularly. The startup script checks DNS and gateway status,
then starts gateway if needed.

### Impact:
- Same as phone reboot — all automated trading stops
- Server-side stop-loss orders still active on Alpaca
- Pending cron job runs are missed (no catch-up mechanism found)

### Recovery:
- If Termux is still open: Re-run startup script
- If Termux closed: Must reopen Termux manually

### Risk Level: 🔴 HIGH
**Mitigation:** Android "Keep Alive" notification, or Termux:Boot with persistent service

---

## Scenario 3: Storage Corruption

### Critical files (in order of importance):

| File | Purpose | Backup? |
|------|---------|---------|
| `~/stock_trader/eagle_eye.db` | Main trading database (positions, orders, audit) | ❌ No auto-backup |
| `~/stock_trader/us_portfolio.json` | Portfolio snapshot | ✅ Manual backup exists |
| `~/stock_trader/us_risk_state.json` | Risk state tracking | ✅ Manual backup exists |
| `~/stock_trader/us_recent_stops.json` | Recent stop-loss records | ✅ Manual backup exists |
| `~/stock_trader/us_pending_replacements.json` | Pending order replacements | ✅ Manual backup exists |
| `~/stock_trader/signal_decay.json` | Signal decay analysis | ✅ Manual backup exists |
| `~/stock_trader/calibrated_params.json` | Strategy parameters | ✅ Manual backup exists |
| `~/stock_trader/market_env.json` | Market environment state | ✅ Manual backup exists |
| `~/.hermes/state.db` | Hermes session/state database | ❌ No auto-backup |
| `~/.hermes/cron/jobs.json` | Cron job definitions | ❌ No auto-backup |

### Existing backups:
- `~/stock_trader/backup_json_20260618_100945/` — Snapshot from 2026-06-18
  Contains: portfolio, risk_state, recent_stops, pending_replacements, screener,
  watchlist, signal_decay, calibrated_params, compliance_report, market_env,
  market_breadth, macro_context, earnings_cache, market_events

### Recovery:
- Hermes has a backup module: `~/.hermes/hermes-agent/hermes_cli/backup.py`
  - `hermes backup` creates zip of `~/.hermes/` (excluding hermes-agent repo)
  - `hermes import` restores from backup zip
- **No automated periodic backups configured** — backups are manual only

### Risk Level: 🟡 MEDIUM
**Mitigation:** Set up daily automated backup via cron job, store backups off-device

---

## Scenario 4: Network Outage

### What happens to pending orders:
- **Alpaca behavior:** Orders already submitted to Alpaca remain on Alpaca's servers.
  They will execute if price conditions are met, regardless of local connectivity.
- **New orders:** Cannot be submitted during outage. Cron jobs will fail with
  connection errors (evidence: `RuntimeError: Connection error` in cron logs).
- **Stop-loss orders:** ✅ SAFE — they are server-side on Alpaca.

### System behavior during outage:
1. Cron job attempts API call → fails
2. After 4 consecutive failures → **Degraded Mode** activates automatically
   - Blocks: new positions, adding to existing positions
   - Allows: stop-loss exits, position reductions
3. Notification spool queues alerts (will send when connectivity returns)
4. Trading lock activates (blocks all trading)
5. Watchdog detects API failure spike

### Recovery:
- When network returns, next cron cycle succeeds → degraded mode exits after 3
  consecutive successful API checks (~3 cron cycles)
- Queued notifications in spool directory are processed by relay

### Risk Level: 🟡 MEDIUM
**Mitigation:** Server-side stop-losses provide the critical safety net

---

## Scenario 5: Power Outage / Battery Depletion

### Battery considerations:
- Pad5 is presumably plugged in 24/7 for continuous operation
- If unplugged: battery drain depends on screen state, background processes
- Android battery optimization may kill Termux in background

### What happens:
- Same as phone reboot (Scenario 1)
- No UPS or external battery backup
- Server-side stop-losses remain active on Alpaca

### Risk Level: 🟡 MEDIUM
**Mitigation:** Keep device plugged in, disable Android battery optimization for Termux

---

## Scenario 6: Alpaca API Down

### Retry logic:
- Eagle Eye has built-in retry with exponential backoff (in AlpacaClient)
- After 4 consecutive failures → **Degraded Mode** activates
  ```python
  # From eagle_eye/risk/degraded_mode.py
  _DEGRADED_FAILURE_THRESHOLD = 4  # 4 consecutive failures triggers degraded
  ```
- Degraded mode rules:
  - ❌ No new positions
  - ❌ No adding to existing positions
  - ✅ Allow stop-loss exits
  - ✅ Allow position reductions
- Recovery: 3 consecutive successful API checks → exit degraded mode

### Trading Lock:
- Activates when API is unhealthy
- Blocks ALL trading until API recovers
- Cannot be bypassed (Constitution iron law)

### Watchdog monitoring:
- `check_api_failure_spike()` alerts when failures >= 10
- `check_degraded_mode_duration()` alerts if degraded > 8 hours

### Risk Level: 🟢 LOW
**Mitigation:** Existing safety rails are comprehensive

---

## Scenario 7: DeepSeek API Down

### Current configuration:
- Primary model: `deepseek-v4-flash` (used by most cron jobs)
- Some jobs use `mimo-v2.5` (xiaomi provider)

### Impact:
- Cron jobs that require LLM reasoning will fail
- Jobs using `no_agent: true` (script-only) will still run
- The main US trading decision job (`美股AI决策`) requires DeepSeek

### Fallback:
- ❌ No automatic model fallback configured
- Jobs fail with error, logged in `last_error` field
- Next scheduled run will retry with same model

### Evidence from logs:
- `last_error: "RuntimeError: [Errno 32] Broken pipe"` seen on multiple jobs
- This suggests LLM connection issues have occurred

### Risk Level: 🟡 MEDIUM
**Mitigation:** Configure fallback model in cron job definitions, or use provider failover

---

## Scenario 8: Gateway Killed by Android

### Known issue:
Android aggressively kills background processes. The gateway is known to be killed.

### Evidence:
Startup log shows frequent "启动网关..." (gateway restart) entries throughout the day,
indicating the gateway dies and gets restarted by the startup script.

### Current resilience:
- Startup script runs periodically (appears to be every ~30-60 minutes based on log)
- Script checks if gateway is running, restarts if not
- Gateway has memory monitoring (`gateway.memory_monitor`) every 300 seconds
- Memory baseline: ~82-91MB RSS, grows to ~268MB under load

### Gap:
- Between gateway death and next startup check, cron jobs are missed
- No instant restart mechanism (depends on startup script schedule)

### Risk Level: 🟡 MEDIUM
**Mitigation:** More frequent startup checks, or use Termux foreground service

---

## Critical Safety Rails (Always Active)

### 1. Server-Side Stop-Loss Orders
All positions have stop-loss orders submitted to Alpaca:
- These execute even if the local system is completely offline
- Stop prices are set at 8-14% below entry (based on current portfolio)
- This is the PRIMARY safety net for the 14-day survival goal

### 2. Trading Lock System
```python
# Blocks trading when:
- Database unhealthy
- API unhealthy  
- Market data missing
- Market closed
- Degraded mode active
- Manual lock
```

### 3. Degraded Mode
```python
# After 4 consecutive API failures:
- No new positions
- No adding to existing positions
- Allow stop-loss exits
- Allow position reductions
```

### 4. Notification Spool
- Warning events: spooled, delivered within 60 seconds
- Critical events: fast-path delivery, bypasses queue
- Events: EMERGENCY_STOP, DATABASE_CORRUPT, SYSTEM_OFFLINE, EXECUTOR_CRASH

### 5. Watchdog Checks
- Stuck jobs detection (>120 minutes)
- Trading lock duration alert (>4 hours)
- Degraded mode duration alert (>8 hours)
- API failure spike detection (>=10 failures)
- Data staleness checks (market data >12h, screener >48h)
- Position coverage check (naked positions without stops)

---

## Recommended Improvements

### Priority 1 (Critical for 14-day goal):
1. **Install Termux:Boot** and create auto-start script
2. **Disable Android battery optimization** for Termux
3. **More frequent startup checks** (every 5-10 minutes instead of 30-60)

### Priority 2 (Important):
4. **Automated daily backups** of critical JSON files and databases
5. **Off-device backup** (cloud sync or remote copy)
6. **Model fallback** for DeepSeek API failures

### Priority 3 (Nice to have):
7. **External monitoring** (heartbeat check from external service)
8. **Remote access** for emergency intervention
9. **Catch-up mechanism** for missed cron jobs

---

## Quick Reference: What Survives What

| Component | Phone Reboot | Termux Crash | Network Outage | Alpaca Down | DeepSeek Down |
|-----------|--------------|--------------|----------------|-------------|---------------|
| Stop-loss orders | ✅ | ✅ | ✅ | ✅ | ✅ |
| New trades | ❌ | ❌ | ❌ | ❌ | ❌ |
| Cron jobs | ❌ | ❌ | ❌ | ⚠️ fails | ⚠️ fails |
| Notifications | ❌ | ❌ | ⚠️ queued | ✅ | ✅ |
| Degraded mode | ❌ (reset) | ❌ (reset) | ✅ activates | ✅ activates | ❌ |
| Trading lock | ❌ (reset) | ❌ (reset) | ✅ activates | ✅ activates | ❌ |

---

## Emergency Recovery Checklist

If system has been down and you need to recover:

1. [ ] Open Termux on Pad5
2. [ ] Check gateway status: look for "网关已在运行" in startup log
3. [ ] If gateway not running: run startup script to restart
4. [ ] Check cron jobs: `cat ~/.hermes/cron/jobs.json | grep last_status`
5. [ ] Check for errors: `tail -50 ~/.hermes/logs/errors.log`
6. [ ] Verify Alpaca connectivity: check if any cron job ran successfully recently
7. [ ] Check portfolio status: visit Alpaca web dashboard to confirm positions
8. [ ] Review missed cron outputs: `ls ~/.hermes/cron/output/`
9. [ ] Check notification spool for queued alerts: `ls ~/stock_trader/notifications/spool/`

---

*This plan should be reviewed after any significant outage event.*
