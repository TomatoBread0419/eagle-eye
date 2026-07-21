"""
ops/ — 运维 & 安全层 (V7.1 RC1)

OBSERVER modules — NEVER make trading decisions.
Read-only + record + alert + guard only.

Modules:
  health_check.py        — DB/API/data/system health monitoring
  scheduler.py           — Job registry, status tracking, execution timing
  watchdog.py            — Stuck jobs, crash detection, unhealthy states
  audit_engine.py        — Append-only event log (orders, risk, lock, degraded)
  shadow_mode.py         — Paper trading safety net (RC1)
  behavior_fingerprint.py — Daily metrics report (RC1)
  emergency_stop.py      — Global kill switch (RC1)
"""

from eagle_eye.ops.health_check import (
    check_database, check_api, check_data_freshness,
    check_system, full_health_report,
)
from eagle_eye.ops.scheduler import (
    register_job, start_job, finish_job, list_jobs,
    get_job, get_overdue_jobs, get_next_due, job_summary,
)
from eagle_eye.ops.watchdog import (
    check_stuck_jobs, check_trading_lock_duration,
    check_degraded_mode_duration, check_api_failure_spike,
    check_data_staleness, check_position_coverage,
    full_watchdog_scan,
)
from eagle_eye.ops.audit_engine import (
    log_event, log_order_intent, log_order_state_change,
    log_position_change, log_risk_event, log_degraded_mode_event,
    log_trading_lock_event, query_events, get_recent_events,
    get_event_counts, export_audit_log, prune_events,
)
from eagle_eye.ops.shadow_mode import shadow_mode
from eagle_eye.ops.behavior_fingerprint import generate_fingerprint, get_latest_fingerprint
from eagle_eye.ops.emergency_stop import emergency_stop
from eagle_eye.ops.notification import (
    notify_warning, notify_critical,
    on_degraded_enter, on_degraded_exit, on_trading_lock,
    on_data_stale, on_api_failure_spike,
    on_emergency_stop, on_database_corrupt, on_system_offline, on_executor_crash,
    relay_all,
)

__all__ = [
    # Health
    'check_database', 'check_api', 'check_data_freshness',
    'check_system', 'full_health_report',
    # Scheduler
    'register_job', 'start_job', 'finish_job', 'list_jobs',
    'get_job', 'get_overdue_jobs', 'get_next_due', 'job_summary',
    # Watchdog
    'check_stuck_jobs', 'check_trading_lock_duration',
    'check_degraded_mode_duration', 'check_api_failure_spike',
    'check_data_staleness', 'check_position_coverage',
    'full_watchdog_scan',
    # Audit
    'log_event', 'log_order_intent', 'log_order_state_change',
    'log_position_change', 'log_risk_event', 'log_degraded_mode_event',
    'log_trading_lock_event', 'query_events', 'get_recent_events',
    'get_event_counts', 'export_audit_log', 'prune_events',
    # RC1
    'shadow_mode', 'generate_fingerprint', 'get_latest_fingerprint',
    'emergency_stop',
    # V7.1.1 Notification
    'notify_warning', 'notify_critical',
    'on_degraded_enter', 'on_degraded_exit', 'on_trading_lock',
    'on_data_stale', 'on_api_failure_spike',
    'on_emergency_stop', 'on_database_corrupt', 'on_system_offline', 'on_executor_crash',
    'relay_all',
]
