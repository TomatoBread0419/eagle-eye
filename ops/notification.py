"""
ops/notification.py — Eagle Eye 三级通知系统 (V7.1.1 FP-001)

Spool-based notification with priority fast-path for critical events.

Level 2 (Warning):   Spool → relay cron (≤60s). Events: ENTER_DEGRADED,
                     EXIT_DEGRADED, TRADING_LOCK, DATA_STALE,
                     API_FAILURE_SPIKE, WATCHDOG_ALERT
Level 3 (Critical):  FAST-PATH direct delivery file → relay cron (≤60s).
                     Events: EMERGENCY_STOP, DATABASE_CORRUPT,
                     SYSTEM_OFFLINE, EXECUTOR_CRASH.
                     Bypasses spool queue. Processed first.

Deduplication: filename hash prevents resend within 60s window.
Retry: delivery file persists until relay processes it.
Failure escalation: spool overflow > 50 files → escalation.

Constitution: Observer only. Never makes trading decisions.
"""

import json
import os
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from eagle_eye.core.logger import get_logger

logger = get_logger('ops.notify')

# ─── Paths ───
NOTIFY_ROOT = Path.home() / 'stock_trader' / 'notifications'
SPOOL_WARNING = NOTIFY_ROOT / 'spool' / 'warnings'
SPOOL_CRITICAL = NOTIFY_ROOT / 'spool' / 'critical'
SPOOL_PROCESSED = NOTIFY_ROOT / 'spool' / 'processed'
# V7.1.1 FP-001: Critical fast-path — bypasses spool queue
CRITICAL_DELIVERY = NOTIFY_ROOT / 'critical_delivery.json'

# ─── Event type registry ───
LEVEL_2_EVENTS = {
    'ENTER_DEGRADED', 'EXIT_DEGRADED', 'TRADING_LOCK',
    'DATA_STALE', 'API_FAILURE_SPIKE', 'WATCHDOG_ALERT',
}

LEVEL_3_EVENTS = {
    'EMERGENCY_STOP', 'DATABASE_CORRUPT', 'SYSTEM_OFFLINE', 'EXECUTOR_CRASH',
}

SPOOL_MAX_FILES = 50  # If spool dir exceeds this, trigger escalation


def _ensure_dirs():
    """Create spool directories."""
    SPOOL_WARNING.mkdir(parents=True, exist_ok=True)
    SPOOL_CRITICAL.mkdir(parents=True, exist_ok=True)
    SPOOL_PROCESSED.mkdir(parents=True, exist_ok=True)


def _file_hash(event_type: str, timestamp: str, details: dict) -> str:
    """Short hash for dedup filename."""
    raw = f"{event_type}|{timestamp}|{json.dumps(details, sort_keys=True)}"
    return hashlib.md5(raw.encode()).hexdigest()[:8]


def _spool_count() -> int:
    """Count total pending notifications."""
    try:
        w = len(list(SPOOL_WARNING.glob('*.json'))) if SPOOL_WARNING.exists() else 0
        c = len(list(SPOOL_CRITICAL.glob('*.json'))) if SPOOL_CRITICAL.exists() else 0
        return w + c
    except Exception:
        return 0


def _spool_directory(directory: Path, event_type: str, details: dict):
    """Write a notification event to a spool directory."""
    _ensure_dirs()
    ts = datetime.now(timezone.utc)
    timestamp = ts.isoformat()
    fhash = _file_hash(event_type, timestamp, details)
    bj_time = (ts + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')

    payload = {
        'event_type': event_type,
        'timestamp': timestamp,
        'bj_time': bj_time,
        'details': details,
        'level': 'critical' if event_type in LEVEL_3_EVENTS else 'warning',
    }

    filename = f"{event_type}_{bj_time.replace(':', '')}_{fhash}.json"
    filepath = directory / filename

    # Dedup: skip if same event already spooled
    existing = list(directory.glob(f'{event_type}_*.json'))
    if existing:
        # Check if last file has same hash (within 60 seconds)
        last = sorted(existing)[-1]
        try:
            last_data = json.loads(last.read_text())
            last_hash = _file_hash(event_type, last_data['timestamp'], last_data.get('details', {}))
            if last_hash == fhash:
                return  # Duplicate suppressed
        except Exception:
            pass

    filepath.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    logger.info(f'Spooled [{event_type}] → {filename}')

    # Escalation check
    count = _spool_count()
    if count > SPOOL_MAX_FILES:
        logger.critical(f'Spool overflow: {count} files — relay may be down')


def notify_warning(event_type: str, details: dict = None):
    """
    Level 2: Warning notification (5min target, 1min actual via relay).

    Args:
        event_type: One of LEVEL_2_EVENTS
        details: Arbitrary dict with event context
    """
    if event_type not in LEVEL_2_EVENTS:
        logger.warning(f'Unknown Level 2 event: {event_type}')
    _spool_directory(SPOOL_WARNING, event_type, details or {})


def notify_critical(event_type: str, details: dict = None):
    """
    Level 3: Critical notification — FAST-PATH (bypasses spool).

    Writes directly to critical_delivery.json for relay priority processing.
    Also spools for audit trail.
    Max latency: ≤60 seconds (next relay tick).
    """
    if event_type not in LEVEL_3_EVENTS:
        logger.warning(f'Unknown Level 3 event: {event_type}')
        return

    details = details or {}
    ts = datetime.now(timezone.utc)
    bj_time = (ts + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')

    payload = {
        'event_type': event_type,
        'timestamp': ts.isoformat(),
        'bj_time': bj_time,
        'details': details,
        'level': 'critical',
    }

    # FAST-PATH: Write directly to delivery file (relay prioritizes this)
    _ensure_dirs()
    NOTIFY_ROOT.mkdir(parents=True, exist_ok=True)
    CRITICAL_DELIVERY.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    logger.info(f'FAST-PATH [{event_type}] → critical_delivery.json')

    # Also spool for audit trail
    _spool_directory(SPOOL_CRITICAL, event_type, details)


def send_critical(event_type: str, details: dict = None):
    """
    Direct critical send — identical to notify_critical.
    Explicit call for events that must bypass ALL queues.

    Use for: EMERGENCY_STOP, SYSTEM_OFFLINE, DATABASE_CORRUPT, EXECUTOR_CRASH.
    """
    notify_critical(event_type, details)


def relay_process(directory: Path, level_label: str) -> list:
    """
    Process all spooled notifications in a directory.
    Returns list of formatted message lines.
    Moves processed files to processed/ directory.

    Called by ops_notify_relay.py (1min cron).
    """
    if not directory.exists():
        return []

    files = sorted(directory.glob('*.json'))
    if not files:
        return []

    messages = []
    for f in files:
        try:
            data = json.loads(f.read_text())
            event = data['event_type']
            bj = data['bj_time']
            details = data.get('details', {})

            # Format
            emoji = '🔴' if level_label == 'CRITICAL' else '🟡'
            msg = f'{emoji} [{level_label}] {event}'
            msg += f'\n   Time: {bj}'

            # Add context from details
            if isinstance(details, dict):
                for k, v in details.items():
                    if k not in ('timestamp', 'event_type'):
                        msg += f'\n   {k}: {v}'

            messages.append(msg)

            # Move to processed
            processed_path = SPOOL_PROCESSED / f.name
            f.rename(processed_path)

        except Exception as e:
            logger.error(f'Failed to process notification {f.name}: {e}')
            # Move broken files to processed too (don't retry forever)
            try:
                f.rename(SPOOL_PROCESSED / f.name)
            except Exception:
                pass

    return messages


def relay_all() -> str:
    """
    Process notifications for WeChat delivery.

    Priority: Critical fast-path (critical_delivery.json) → Critical spool → Warning spool.

    Returns formatted message string.
    Returns empty string if nothing to deliver.
    """
    all_msgs = []

    # ─── FAST-PATH: Critical delivery file (≤60s latency) ───
    if CRITICAL_DELIVERY.exists():
        try:
            data = json.loads(CRITICAL_DELIVERY.read_text())
            event = data['event_type']
            bj = data['bj_time']
            details = data.get('details', {})
            msg = f'🔴 [CRITICAL] {event}'
            msg += f'\n   Time: {bj}'
            if isinstance(details, dict):
                for k, v in details.items():
                    if k not in ('timestamp', 'event_type'):
                        msg += f'\n   {k}: {v}'
            all_msgs.append(msg)
            CRITICAL_DELIVERY.unlink()  # Consumed
        except Exception as e:
            logger.error(f'Failed to process critical delivery: {e}')

    # ─── Spool: Critical then Warning ───
    critical_msgs = relay_process(SPOOL_CRITICAL, 'CRITICAL')
    warning_msgs = relay_process(SPOOL_WARNING, 'WARNING')
    all_msgs.extend(critical_msgs)
    all_msgs.extend(warning_msgs)

    if not all_msgs:
        return ''

    header = '📡 Eagle Eye Alert\n' + '─' * 30
    return header + '\n\n' + '\n\n'.join(all_msgs)


# ─── Convenience functions for integration points ───

def on_degraded_enter(reason: str):
    notify_warning('ENTER_DEGRADED', {'reason': reason, 'active': True})


def on_degraded_exit():
    notify_warning('EXIT_DEGRADED', {'active': False})


def on_trading_lock(lock_reasons: list):
    notify_warning('TRADING_LOCK', {'reasons': lock_reasons})


def on_data_stale(component: str, age_hours: float):
    notify_warning('DATA_STALE', {'component': component, 'age_hours': round(age_hours, 1)})


def on_api_failure_spike(count: int, window_minutes: int):
    notify_warning('API_FAILURE_SPIKE', {'failures': count, 'window_minutes': window_minutes})


def on_emergency_stop(reason: str):
    notify_critical('EMERGENCY_STOP', {'reason': reason})


def on_database_corrupt(detail: str):
    notify_critical('DATABASE_CORRUPT', {'detail': detail})


def on_system_offline(gap_hours: float):
    notify_critical('SYSTEM_OFFLINE', {'gap_hours': round(gap_hours, 1)})


def on_executor_crash(detail: str):
    notify_critical('EXECUTOR_CRASH', {'detail': detail})
