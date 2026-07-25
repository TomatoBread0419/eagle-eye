Notification Architecture Report
═══════════════════════════════════════════
Eagle Eye V7.1.1 — WeChat Delivery SLA
2026-06-18
═══════════════════════════════════════════

1. TRIGGER SOURCE
─────────────────

LEVEL 1 (Heartbeat)
  Source:    eagle_heartbeat.py (hourly cron, no_agent)
  Trigger:   Cron schedule (0 * * * *)
  Checks:    DNS, Alpaca API, Dashboard, open orders,
             executor_success gap, scheduler activity gap,
             emergency_stop flag, degraded_mode flag,
             policy violations, heartbeat gap
  Output:    Always (heartbeat message every hour)

LEVEL 2 (Warning)
  Source:    Notification spool → ops_notify_relay.py (1min cron)
  Trigger:   trade_executor, degraded_mode, heartbeat
  Events:
    ENTER_DEGRADED      — degraded_mode._enter_degraded()
    EXIT_DEGRADED       — degraded_mode._exit_recovering()
    TRADING_LOCK        — trading_lock.check() detects lock
    DATA_STALE          — heartbeat: data file age > 24h
    API_FAILURE_SPIKE   — degraded_mode: 4+ failures in window
    WATCHDOG_ALERT      — cron_watchdog: stuck/delivery errors
  Output:    Only when events exist (silent otherwise)

LEVEL 3 (Critical)
  Source:    Notification spool → ops_notify_relay.py (1min cron)
  Trigger:   trade_executor, heartbeat
  Events:
    EMERGENCY_STOP      — drawdown > 20%
    DATABASE_CORRUPT    — DB query failure cascade
    SYSTEM_OFFLINE      — heartbeat gap > 2 hours
    EXECUTOR_CRASH      — executor_success gap > 90 minutes
  Output:    Only when events exist (silent otherwise)

2. DELIVERY LATENCY
───────────────────

LEVEL 1:  < 60 minutes (hourly cron)
LEVEL 2:  < 60 seconds  (1min relay cron from spool write)
LEVEL 3:  < 60 seconds  (1min relay cron from spool write)

Bottleneck: 1-minute relay cron resolution.
Events written to spool at t=0 → relay picks up at t=0-60s.

3. RETRY MECHANISM
──────────────────

Spool-based persistence:
  - Files remain in spool/ until relay processes them.
  - If relay fails (cron error), files accumulate.
  - If spool exceeds 50 files → WATCHDOG_ALERT escalation.
  - Relay output goes to stdout → no_agent delivery → WeChat.
  - If WeChat rate-limits → delivery fails → cron_watchdog detects.

4. DEDUPLICATION
────────────────

Per-event hash-based dedup:
  - filename = {event_type}_{bj_time}_{md5(event+timestamp+details)[:8]}
  - Same event within 60 seconds → same hash → skip write.
  - Processed files moved to spool/processed/ (audit trail).

Level 1 heartbeat: no dedup needed (always different timestamp).

5. FAILURE ESCALATION
─────────────────────

Spool overflow (>50 files):
  → logger.critical + relay processes all in next tick

WeChat rate limit:
  → delivery error → cron_watchdog (5min) detects
  → subsequent relay attempts may also fail
  → heartbeat continues independently (separate cron)

Complete system death (Android kills Termux):
  → No crons fire → no heartbeats → no spool writes
  → On restart: heartbeat detects gap > 2h → SYSTEM_OFFLINE
  → SYSTEM_OFFLINE written to spool → next relay delivers

6. RECOVERY NOTIFICATION
────────────────────────

Heartbeat gap restores:
  trigger: check_heartbeat_gap() sees gap < 2h + prev system_offline
  action:  logs system_restored to audit_log
  message: "✅ SYSTEM_RESTORED" tag in heartbeat output

Degraded mode exit:
  trigger: degraded_mode._exit_recovering()
  action:  EXIT_DEGRADED spooled → relay delivers within 60s

Emergency stop active:
  persists until manual reset → every heartbeat reports it
  recovery: owner manually deletes .emergency_stop file

═══════════════════════════════════════════

CRON INVENTORY (V7.1.1)

Job                    Schedule        Deliver   Type
─────────────────────  ──────────────  ────────  ────────
Eagle Eye Heartbeat    0 * * * *       WeChat    no_agent
Ops Notification Relay * * * * *       WeChat    no_agent
Cron交付监控            */5 * * * *     WeChat    no_agent
美股AI决策              10 21-5 * * 1-5  WeChat  LLM
市场事件监控            0 */2 * * 1-5   WeChat    LLM
信号衰减检测            0 21,23,1,3 * * 1-5 WeChat LLM
GARP扫描                0 8 * * 1-5     WeChat    LLM
市场环境采集            30 20 * * 1-5   local     LLM
(other 6 jobs)          various         various   various

═══════════════════════════════════════════
