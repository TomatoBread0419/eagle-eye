# 14-Day Autonomous Test Plan

**Version:** 1.0
**Created:** 2026-06-19
**System:** Pad5 Android/Termux, 24h running, Alpaca paper trading
**Goal:** Prove the system can survive 14 days with ZERO owner intervention
**Authority:** OWNER_MANDATE_v1.1 Section 9

---

## 1. Pre-Test Checklist

Every item below MUST be verified and signed off before Day 1 begins.

### Infrastructure
- [ ] Pad5 is plugged into stable power (USB-C + wall adapter)
- [ ] Android battery optimization is DISABLED for Termux
- [ ] Termux:KeepAlive notification is active (prevents OS kill)
- [ ] Termux:Boot installed and `~/.termux/boot/start_hermes.sh` exists
- [ ] Gateway is running (verify with startup log check)
- [ ] All cron jobs are loaded in `~/.hermes/cron/jobs.json`
- [ ] Network connectivity is stable (WiFi or cellular fallback)

### Trading Safety
- [ ] All open positions have server-side stop-loss orders on Alpaca
- [ ] Cash guard verified: current cash >= 20% of portfolio
- [ ] Position guard verified: no position exceeds 18% of portfolio
- [ ] Sector guard verified: no sector exceeds 25% of portfolio
- [ ] Trading lock is OFF (not manually locked)
- [ ] Degraded mode is OFF (API healthy)
- [ ] Monthly trade count is below 25

### Notifications
- [ ] WeChat push V3 is configured and tested (3 types only)
- [ ] Notification spool directory exists and is writable
- [ ] Trade Executed notification verified with a test
- [ ] Risk Alert notification verified with a test
- [ ] Daily Summary notification verified with a test

### Data & Backups
- [ ] `eagle_eye.db` is intact (no corruption)
- [ ] All critical JSON files exist and are valid JSON
- [ ] Manual backup taken: `~/stock_trader/backup_pre_test_YYYYMMDD/`
- [ ] Hermes backup created: `hermes backup`
- [ ] Cron job for daily backup is installed (or manual backup scheduled)

### Monitoring
- [ ] Watchdog cron jobs are active (stuck jobs, lock duration, degraded mode, API spikes)
- [ ] Data staleness checks are active (market data <12h, screener <48h)
- [ ] Position coverage check active (no naked positions without stops)

### Documentation
- [ ] FAILOVER_PLAN.md reviewed and understood
- [ ] OWNER_MANDATE_v1.1 hard guards are coded, not just documented
- [ ] Emergency recovery checklist from FAILOVER_PLAN.md is printed/accessible

---

## 2. Test Timeline (Day 1–14)

### Phase 1: Validation (Days 1–3)
**Goal:** Confirm all systems are working correctly in live market conditions.

| Day | Date | Milestone | Market |
|-----|------|-----------|--------|
| 1 | T+0 | Test begins. Verify all cron jobs fire on schedule. Confirm Daily Summary arrives. | Open |
| 2 | T+1 | Verify at least one trade decision cycle completes without error. Check guard enforcement. | Open |
| 3 | T+2 | End of first 3-day window. Zero manual interventions so far = Phase 1 PASS. | Open |

### Phase 2: Normal Operations (Days 4–7)
**Goal:** System operates through a full trading week without issues.

| Day | Date | Milestone | Market |
|-----|------|-----------|--------|
| 4 | T+3 | First Monday of test. Verify weekend-to-weekday transition. | Open |
| 5 | T+4 | Mid-week. Verify no cron job drift or schedule degradation. | Open |
| 6 | T+5 | Friday close. Verify system handles market close correctly (no stale orders). | Open → Close |
| 7 | T+6 | Saturday. Verify no trading activity occurs. No cron jobs attempt trades. | Closed |

### Phase 3: Stress Window (Days 8–10)
**Goal:** System survives the weekend and another full week begins.

| Day | Date | Milestone | Market |
|-----|------|-----------|--------|
| 8 | T+7 | Sunday. System remains idle. No phantom activity. | Closed |
| 9 | T+8 | Monday open. System resumes trading decisions. Gateway survived weekend. | Open |
| 10 | T+9 | Mid-week. 10 days completed. 0 critical incidents so far = Stress PASS. | Open |

### Phase 4: Completion (Days 11–14)
**Goal:** Full 14-day cycle completed.

| Day | Date | Milestone | Market |
|-----|------|-----------|--------|
| 11 | T+10 | Verify monthly trade count approaching limit. Guard should restrict if near 25. | Open |
| 12 | T+11 | Verify no accumulation of stale data or log bloat. | Open |
| 13 | T+12 | Second weekend begins. System enters idle mode. | Open → Close |
| 14 | T+13 | **TEST COMPLETE.** Final audit. Compile results. | Closed |

---

## 3. Monitoring Points (Automated, No Manual Intervention)

These checks run via cron or watchdog and must NOT require owner action.

### Every 10 Minutes
- Gateway heartbeat (is gateway process alive?)
- Cron scheduler health (is jobs.json being read?)

### Every 30 Minutes
- API failure counter (< 10 failures = OK, >= 10 = alert)
- Degraded mode status (OFF = OK, ON for > 8 hours = alert)

### Every Hour
- Trading lock status (should be OFF during market hours unless triggered)
- Stuck job detection (no job running > 120 minutes)

### Every Trading Day (at market close ± 30 min)
- Daily Summary notification sent
- Position count and cash percentage
- Trade count for the day (should be <= 4, emergency stops exempt)
- All positions have active stop-loss orders

### Every Weekend (Saturday morning)
- No trades executed in past 24h (market closed)
- No phantom cron activity (no job errors from market-closed attempts)
- Gateway still running (no crash during idle period)

### Daily (Off-hours)
- Database integrity check
- JSON file validity check
- Disk space check (>100MB free)
- Data staleness: market data <12h old, screener <48h old

---

## 4. Success Criteria

The test PASSES if and only if ALL of the following are true after 14 days:

| Criterion | Requirement |
|-----------|-------------|
| Critical incidents | **0** (zero) |
| Manual interventions | **0** (zero) — no restarts, no dashboard logins, no emergency actions |
| Guard violations | **0** — no position exceeded 18%, no sector exceeded 25%, cash never dropped below 20% |
| Duplicate orders | **0** — no duplicate trades submitted |
| Missed orders | **0** — every intended trade was attempted (failures due to Alpaca rejection are OK) |
| Runaway trading | **0** — daily trades never exceeded 4 (excluding emergency stops), monthly never exceeded 25 |
| Notification delivery | 100% of Trade Executed, Risk Alert, and Daily Summary notifications delivered |
| Uptime | >= 95% of scheduled cron jobs executed successfully |
| Recovery | Any gateway/termux crash self-recovered without owner action |

### Test Verdict
- **PASS:** All criteria met. System is certified autonomous.
- **PARTIAL PASS:** 1–2 non-critical issues (e.g., 1 missed notification). Document and fix.
- **FAIL:** Any critical criterion violated. See Section 7 (Rollback Plan).

---

## 5. Failure Criteria

The test FAILS immediately if ANY of the following occur:

### Critical Failures (Test Aborted)
1. **Guard bypass:** A trade was executed that violated a hard guard (position >18%, sector >25%, cash <20%)
2. **Runaway trading:** More than 4 trades in a single day (excluding emergency stops) OR more than 25 in a month
3. **Duplicate order:** The same trade was submitted twice
4. **Owner intervention required:** Owner had to restart Termux, restart gateway, manually lock trading, or take any emergency action
5. **Data corruption:** `eagle_eye.db` or critical JSON files became corrupted
6. **Stop-loss missing:** A position existed without a server-side stop-loss order on Alpaca

### Non-Critical Failures (Document, Do Not Abort)
7. **Missed notification:** A Daily Summary or Trade Executed notification was not delivered (1 occurrence tolerable)
8. **Gateway crash with self-recovery:** Gateway died but restarted automatically within 30 minutes
9. **Cron job failure:** A single cron run failed but subsequent runs succeeded (1–2 occurrences tolerable)
10. **Degraded mode activation:** API issues triggered degraded mode, system recovered within 8 hours

### Escalation Rules
- 1 non-critical failure: Log it, continue test
- 3+ non-critical failures of the same type: Escalate to critical, abort test
- 1 critical failure: Abort test immediately, execute rollback plan

---

## 6. Metrics to Track (Automated)

All metrics below must be logged automatically by cron jobs or watchdog. No manual logging.

### Trading Metrics
| Metric | Source | Frequency | Alert Threshold |
|--------|--------|-----------|-----------------|
| Daily trade count | `eagle_eye.db` orders table | Per trade | > 4 (excl. stops) |
| Monthly trade count | `eagle_eye.db` orders table | Daily | >= 23 (warn), >= 25 (block) |
| Position count | Alpaca API | Daily | > 10 (warn) |
| Largest position % | Alpaca API | Daily | > 15% (warn), > 18% (critical) |
| Sector concentration % | Alpaca API | Daily | > 20% (warn), > 25% (critical) |
| Cash % | Alpaca API | Daily | < 25% (warn), < 20% (critical) |
| Portfolio drawdown | Alpaca API | Daily | > 10% (warn), > 12% (pause buys), > 20% (reduce) |

### System Metrics
| Metric | Source | Frequency | Alert Threshold |
|--------|--------|-----------|-----------------|
| Gateway uptime | Startup log | Every 10 min | Down > 10 min |
| Cron job success rate | `jobs.json` last_status | Per run | < 80% over 24h |
| API failure count | Degraded mode counter | Every 30 min | >= 10 |
| Degraded mode duration | Degraded mode state | Every 30 min | > 8 hours |
| Trading lock duration | Lock state | Every hour | > 4 hours |
| Database size | File system | Daily | > 500MB |
| Disk free space | File system | Daily | < 100MB |
| Memory usage (RSS) | Gateway monitor | Every 5 min | > 400MB |
| Stuck jobs | Cron scheduler | Every hour | Any job > 120 min |

### Notification Metrics
| Metric | Source | Frequency | Alert Threshold |
|--------|--------|-----------|-----------------|
| Trade Executed sent | WeChat relay log | Per trade | Not sent within 5 min |
| Risk Alert sent | WeChat relay log | Per event | Not sent within 1 min |
| Daily Summary sent | WeChat relay log | Daily | Not sent by 22:00 local |
| Spool queue depth | Spool directory | Hourly | > 10 queued items |

---

## 7. Rollback Plan If Test Fails

### Immediate Actions (Within 5 Minutes of Failure Detection)

1. **Activate trading lock:**
   ```
   # If gateway is running, activate lock
   # This blocks ALL trading immediately
   ```

2. **Verify all positions have stop-losses:**
   ```
   # Check Alpaca for any naked positions
   # If found, immediately submit stop-loss orders
   ```

3. **Notify owner via WeChat:**
   ```
   # Send critical alert: "14-DAY TEST FAILED - [reason]"
   # This is the ONE notification that always goes through
   ```

### Triage (Within 30 Minutes)

4. **Classify the failure:**
   - Guard bypass? → Deeper investigation, potential position unwinding
   - Runaway trading? → Count excess orders, assess exposure
   - System crash? → Check if self-recovery is possible
   - Data corruption? → Restore from backup

5. **If positions are at risk:**
   - Server-side stop-losses are the primary protection
   - If stops are missing: manually submit stops via Alpaca web dashboard
   - If exposure is too high: place manual sell orders to reduce

### Recovery (Within 2 Hours)

6. **Fix root cause:**
   - Gateway crash? → Restart gateway, investigate memory/process issue
   - Cron failure? → Check job definitions, restart scheduler
   - API issue? → Check Alpaca status, wait for recovery
   - Data corruption? → Restore from `backup_pre_test_YYYYMMDD/`

7. **Resync state:**
   - Re-read positions from Alpaca
   - Update local database to match
   - Verify all guards are correctly calculated

### Decision Point

8. **Can the test resume?**
   - YES: If failure was non-critical, root cause is fixed, and no positions were harmed
   - NO: If failure was critical, positions were affected, or root cause is systemic
   - If NO: Freeze system (lock trading), await owner manual review

### Post-Failure

9. **Document everything:**
   - Exact time of failure
   - Root cause analysis
   - Actions taken
   - Positions affected
   - Resolution

10. **Update FAILOVER_PLAN.md** with lessons learned

---

## 8. Day-by-Day Expected Behavior (Typical Trading Week)

### Monday
| Time (ET) | Expected Behavior |
|-----------|-------------------|
| 06:00 | Pre-market: Gateway running, cron scheduler active |
| 06:30 | Market data feed warming up |
| 09:30 | Market open: Trading lock should be OFF, screener may run |
| 09:30–16:00 | Trading decision cycles run per cron schedule |
| 16:00 | Market close: No new orders after close |
| 20:00 | Daily Summary notification sent via WeChat |

### Tuesday–Thursday
Same as Monday. Normal operations. Cron jobs fire on schedule.
Expected: 0–4 trades per day depending on signals and guard limits.

### Friday
| Time (ET) | Expected Behavior |
|-----------|-------------------|
| 09:30–16:00 | Normal trading (last day of the week) |
| 16:00 | Market close. System enters weekend mode. |
| 16:01+ | No trading-related cron jobs should execute |
| 20:00 | Daily Summary (includes weekly summary) |

### Weekday Night (Any Day)
| Behavior | Expected |
|----------|----------|
| Trading | NONE (market closed) |
| Cron jobs | Only non-trading jobs (backups, health checks) |
| Gateway | Running, consuming minimal resources |
| Notifications | Risk Alerts only if critical event occurs |

---

## 9. Weekend Behavior

### Saturday
| Time | Expected Behavior |
|------|-------------------|
| All day | Market CLOSED. Zero trading activity. |
| All day | Trading-related cron jobs: should detect market is closed and exit early |
| 09:00 | Weekend health check: gateway alive, database OK, disk space OK |
| 12:00 | No activity expected |
| 20:00 | No Daily Summary (market was closed) |

### Sunday
| Time | Expected Behavior |
|------|-------------------|
| All day | Market CLOSED. Zero trading activity. |
| All day | Same as Saturday — idle mode |
| 22:00 | Pre-market prep: some systems may begin scanning for Monday signals |

### What Must NOT Happen on Weekends
- No trade submissions to Alpaca
- No "phantom" decisions made with stale Friday data
- No excessive log entries from retrying market-closed operations
- No cron jobs failing repeatedly because market is closed

### What SHOULD Happen on Weekends
- Gateway stays alive (no crashes from idle period)
- Health checks continue (database, disk, API connectivity)
- Notification spool is empty (no queued undelivered alerts)
- Memory usage stable or decreasing (no memory leak during idle)

---

## 10. Edge Cases

### 10.1 Market Holiday (e.g., July 4th, Labor Day)
**Expected:** Same as weekend. Market is closed. System enters idle mode.
**Risk:** Cron job may not recognize the holiday and attempt to trade.
**Mitigation:** System should check `is_market_open()` before any trade action.
**Verify:** On a holiday during the 14-day window, confirm zero trade attempts in logs.

### 10.2 Half-Day (Early Close at 13:00 ET)
**Expected:** System trades normally 09:30–13:00, then enters idle mode.
**Risk:** System may attempt trades after 13:00 because it expects close at 16:00.
**Mitigation:** Market hours check must use actual calendar (not hardcoded 09:30–16:00).
**Verify:** On an early-close day, confirm no trade attempts after 13:00.

### 10.3 Early Close Due to Technical Issue
**Expected:** If Alpaca closes trading early (rare), system detects API rejection.
**Mitigation:** Alpaca returns `market_closed` errors, system stops trading.
**Verify:** Check logs for graceful handling of market-closed API responses.

### 10.4 Network Outage During Market Hours
**Expected:**
1. API calls fail
2. After 4 failures → degraded mode activates
3. Trading lock activates
4. Notification queued in spool
5. When network returns → degraded mode exits after 3 consecutive successes
6. Queued notifications delivered

**Verify:** Check that degraded mode triggers correctly and recovers within 8 hours.

### 10.5 Gateway Crash During Active Trading
**Expected:**
1. Gateway dies
2. Startup script detects within 10–30 minutes
3. Gateway restarts
4. Cron scheduler resumes
5. Any in-flight trade is lost (acceptable — order was either submitted or not)
6. Next cron cycle picks up where it left off

**Verify:** Check logs for gateway restart events. Time from crash to recovery should be <30 min.

### 10.6 Alpaca API Rate Limit
**Expected:**
1. Exponential backoff in AlpacaClient
2. If persistent → degraded mode activates
3. No duplicate orders from retries (idempotency key required)

**Verify:** Check that order submissions use unique client_order_id.

### 10.7 Phone Reboot (No Termux:Boot)
**Expected:** System is offline until owner manually opens Termux and starts gateway.
**Risk:** This is the highest-risk scenario. Server-side stops are the only protection.
**Mitigation:** Termux:Boot must be installed before test begins (Pre-Test Checklist).

### 10.8 Phone Reboot (With Termux:Boot)
**Expected:**
1. Phone reboots
2. Termux auto-starts
3. `~/.termux/boot/start_hermes.sh` runs
4. Gateway starts
5. Cron scheduler resumes
6. System detects it was offline and logs the gap

**Verify:** Simulate reboot (if possible) before test begins to confirm boot script works.

### 10.9 DeepSeek API Down
**Expected:**
1. LLM-dependent cron jobs fail
2. Script-only jobs (`no_agent: true`) continue
3. No phantom trades from failed reasoning
4. Next cron cycle retries

**Verify:** Check that failed LLM jobs log errors but do NOT produce bad trades.

### 10.10 Disk Full
**Expected:**
1. Watchdog detects low disk space (<100MB)
2. Risk Alert notification sent
3. System continues operating (small logs, no new features)
4. If critical (<10MB): system locks trading to prevent data corruption

**Verify:** Check disk space monitoring in watchdog.

---

## Appendix A: Test Start Command Sequence

```bash
# 1. Run all pre-test checks
# 2. Take backup
# 3. Log test start time
echo "$(date -Iseconds) | 14-DAY AUTONOMY TEST STARTED" >> ~/stock_trader/docs/test_log.txt

# 4. Verify gateway
# 5. Verify cron
# 6. Verify Alpaca connectivity
# 7. Verify notifications
# 8. Begin 14-day countdown
```

## Appendix B: Daily Audit Commands (Run via Cron)

```bash
# These should be automated, not run manually
# Check guard status
# Check trade count
# Check position sizes
# Check cash %
# Check gateway health
# Check notification delivery
# Log results to ~/stock_trader/docs/autonomy_audit_log.jsonl
```

## Appendix C: Test Completion Checklist

After 14 days:

- [ ] Compile all metrics from Section 6
- [ ] Count critical incidents (target: 0)
- [ ] Count manual interventions (target: 0)
- [ ] Count guard violations (target: 0)
- [ ] Count duplicate orders (target: 0)
- [ ] Count gateway crash-recovery events
- [ ] Count cron job failures
- [ ] Count missed notifications
- [ ] Review any degraded mode activations
- [ ] Calculate system uptime percentage
- [ ] Write final test report
- [ ] Archive all logs for the 14-day period
- [ ] Update FAILOVER_PLAN.md with findings

---

## Appendix D: Calendar Grid

Mark the actual test dates here once the start date is confirmed:

| Day | Date | Day of Week | Market Status | Notes |
|-----|------|-------------|---------------|-------|
| 1 | _TBD_ | _TBD_ | _TBD_ | |
| 2 | _TBD_ | _TBD_ | _TBD_ | |
| 3 | _TBD_ | _TBD_ | _TBD_ | |
| 4 | _TBD_ | _TBD_ | _TBD_ | |
| 5 | _TBD_ | _TBD_ | _TBD_ | |
| 6 | _TBD_ | _TBD_ | _TBD_ | |
| 7 | _TBD_ | _TBD_ | _TBD_ | |
| 8 | _TBD_ | _TBD_ | _TBD_ | |
| 9 | _TBD_ | _TBD_ | _TBD_ | |
| 10 | _TBD_ | _TBD_ | _TBD_ | |
| 11 | _TBD_ | _TBD_ | _TBD_ | |
| 12 | _TBD_ | _TBD_ | _TBD_ | |
| 13 | _TBD_ | _TBD_ | _TBD_ | |
| 14 | _TBD_ | _TBD_ | _TBD_ | |

---

## Appendix E: Key Risk Scenarios Ranked

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| 1 | Phone reboot without Termux:Boot | Medium | Critical | Install Termux:Boot (pre-test) |
| 2 | Android kills gateway | High | Medium | KeepAlive notification, startup script |
| 3 | Network outage | Medium | Medium | Server-side stops, degraded mode |
| 4 | DeepSeek API down | Medium | Low | Script-only fallback, retry next cycle |
| 5 | Alpaca API down | Low | Medium | Degraded mode, trading lock |
| 6 | Storage corruption | Low | Critical | Daily backups, pre-test backup |
| 7 | Market holiday unrecognized | Low | Low | is_market_open() check |
| 8 | Disk full | Low | Medium | Disk space monitoring |

---

*This plan is governed by OWNER_MANDATE_v1.1. When uncertain: simpler, safer, lower frequency, more stable.*
