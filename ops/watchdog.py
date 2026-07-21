"""ops/watchdog.py — System health watchdog (Phase 6A)
Detects stuck jobs, crashes, unhealthy states. NEVER makes trading decisions.
Observer module: read-only + record + alert only."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from eagle_eye.core.config import cfg
from eagle_eye.core.logger import get_logger
from eagle_eye.storage.db import db
from eagle_eye.risk.trading_lock import trading_lock
from eagle_eye.risk.degraded_mode import degraded_mode

logger = get_logger('ops.watchdog')

try:
    from eagle_eye.broker.alpaca_client import get_alpaca_client
    _HAS_ALPACA = True
except Exception:
    _HAS_ALPACA = False


def _alert(severity, check, message, details=None):
    return {'timestamp': datetime.now(timezone.utc).isoformat(),
            'severity': severity, 'check': check,
            'message': message, 'details': details or {}}


def _dur_h(delta): return round(delta.total_seconds() / 3600, 1)


# ─── Individual checks ────────────────────────────────

def check_stuck_jobs(timeout_minutes=120):
    """Find scheduler_jobs stuck in RUNNING state > timeout minutes."""
    alerts = []
    try:
        with db.connect() as conn:
            cutoff = (datetime.now(timezone.utc) -
                      timedelta(minutes=timeout_minutes)).isoformat()
            rows = conn.execute(
                "SELECT job_name, last_run, status, duration_sec "
                "FROM scheduler_jobs WHERE status='running' AND last_run<?",
                (cutoff,)).fetchall()
        for row in rows:
            j = dict(row)
            alerts.append(_alert('CRITICAL', 'stuck_jobs',
                f'Job stuck: {j["job_name"]} running since {j["last_run"]}',
                {'job_name': j['job_name'], 'last_run': j['last_run'],
                 'timeout_minutes': timeout_minutes}))
    except Exception as e:
        logger.error(f'check_stuck_jobs: {e}')
        alerts.append(_alert('WARNING', 'stuck_jobs',
                             f'Query failed: {e}', {'error': str(e)}))
    return alerts


def check_trading_lock_duration(max_hours=4):
    """Alert if trading_lock active > max_hours."""
    if not trading_lock.is_locked or not trading_lock.locked_at:
        return []
    dur = datetime.now(timezone.utc) - trading_lock.locked_at
    h = _dur_h(dur)
    if dur > timedelta(hours=max_hours):
        return [_alert('CRITICAL', 'trading_lock_duration',
            f'Trading lock {h}h (threshold: {max_hours}h). '
            f'Reasons: {trading_lock.reason_names()}',
            {'locked_at': trading_lock.locked_at.isoformat(),
             'duration_hours': h, 'reasons': trading_lock.reason_names()})]
    if dur > timedelta(hours=max_hours * 0.75):
        return [_alert('WARNING', 'trading_lock_duration',
            f'Trading lock approaching {max_hours}h: {h}h elapsed',
            {'duration_hours': h, 'reasons': trading_lock.reason_names()})]
    return []


def check_degraded_mode_duration(max_hours=8):
    """Alert if degraded mode persists > max_hours."""
    if not degraded_mode.is_degraded() or not degraded_mode.entered_at:
        return []
    dur = datetime.now(timezone.utc) - degraded_mode.entered_at
    h = _dur_h(dur)
    if dur > timedelta(hours=max_hours):
        return [_alert('CRITICAL', 'degraded_duration',
            f'Degraded mode {h}h (threshold: {max_hours}h). '
            f'Reason: {degraded_mode.reason}',
            {'entered_at': degraded_mode.entered_at.isoformat(),
             'duration_hours': h, 'reason': degraded_mode.reason,
             'state': degraded_mode.state.name})]
    if dur > timedelta(hours=max_hours * 0.75):
        return [_alert('WARNING', 'degraded_duration',
            f'Degraded approaching {max_hours}h: {h}h elapsed',
            {'duration_hours': h, 'reason': degraded_mode.reason})]
    return []


def check_api_failure_spike(threshold=10):
    """Alert if API failure count from AlpacaClient > threshold."""
    if not _HAS_ALPACA:
        return []
    try:
        client = get_alpaca_client()
        count = client.api_failure_count
        if count >= threshold:
            return [_alert('CRITICAL', 'api_failure_spike',
                f'API failures {count} >= threshold {threshold}',
                {'failure_count': count, 'threshold': threshold,
                 'last_failure': client.last_failure_time.isoformat()
                 if client.last_failure_time else None})]
        if count >= threshold * 0.7:
            return [_alert('WARNING', 'api_failure_spike',
                f'API failures {count} approaching {threshold}',
                {'failure_count': count})]
    except Exception as e:
        logger.error(f'api_failure_spike: {e}')
    return []


def check_data_staleness():
    """Alert if critical data files too old. Market >12h, screener >48h."""
    alerts = []
    data_dir = cfg.data_dir
    db_path = cfg.db_path
    if not data_dir.exists():
        return [_alert('CRITICAL', 'data_staleness',
                       f'Data directory missing: {data_dir}')]
    now = datetime.now(timezone.utc)
    # DB staleness
    if db_path.exists():
        age = now - datetime.fromtimestamp(db_path.stat().st_mtime, tz=timezone.utc)
        if age > timedelta(hours=24):
            alerts.append(_alert('CRITICAL', 'data_staleness',
                f'DB stale: {_dur_h(age)}h', {'file': str(db_path),
                 'age_hours': _dur_h(age)}))
    # Market data + screener staleness
    specs = {'market_data': (('*VIX*', '*SPY*', '*market*', '*.csv'), 6, 12),
             'screener': (('*screener*', '*watchlist*', '*scan*'), 24, 48)}
    for category, (globs, warn_h, crit_h) in specs.items():
        newest = None
        for pat in globs:
            for f in data_dir.glob(pat):
                mt = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                if newest is None or mt > newest:
                    newest = mt
        if newest is None and db_path.exists():
            newest = datetime.fromtimestamp(db_path.stat().st_mtime, tz=timezone.utc)
        if newest:
            age = _dur_h(now - newest)
            if (now - newest) > timedelta(hours=crit_h):
                alerts.append(_alert('CRITICAL', 'data_staleness',
                    f'{category} stale: {age}h (crit: {crit_h}h)',
                    {'category': category, 'age_hours': age}))
            elif (now - newest) > timedelta(hours=warn_h):
                alerts.append(_alert('WARNING', 'data_staleness',
                    f'{category} aging: {age}h (warn: {warn_h}h)',
                    {'category': category, 'age_hours': age}))
    return alerts


def check_position_coverage():
    """Check held positions have stop-loss orders. Alert, NEVER place orders."""
    if not _HAS_ALPACA:
        return []
    try:
        client = get_alpaca_client()
        positions = client.get_positions()
        if not positions:
            return []
        orders = client.get_orders(status='open', limit=500)
        covered = {o.get('symbol') for o in orders
                   if o.get('type') == 'stop' and o.get('side') == 'sell'}
        uncovered = [p.get('symbol') for p in positions
                     if p.get('symbol') not in covered]
        if uncovered:
            return [_alert('WARNING', 'position_coverage',
                f'{len(uncovered)}/{len(positions)} positions lack stop-loss: '
                f'{", ".join(uncovered[:10])}'
                + ('...' if len(uncovered) > 10 else ''),
                {'total': len(positions), 'uncovered': len(uncovered),
                 'uncovered_list': uncovered})]
    except Exception as e:
        logger.error(f'position_coverage: {e}')
        return [_alert('WARNING', 'position_coverage',
                       f'Check failed: {e}', {'error': str(e)})]
    return []


# ─── Full scan ────────────────────────────────────────

def full_watchdog_scan():
    """Run all checks. Returns {alerts, status: CLEAN|WARNINGS|CRITICAL, ...}."""
    start = datetime.now(timezone.utc)
    all_alerts = []
    checks = [
        ('stuck_jobs', check_stuck_jobs),
        ('trading_lock_duration', check_trading_lock_duration),
        ('degraded_duration', check_degraded_mode_duration),
        ('api_failure_spike', check_api_failure_spike),
        ('data_staleness', check_data_staleness),
        ('position_coverage', check_position_coverage),
    ]
    summary = {}
    for name, fn in checks:
        try:
            results = fn()
            all_alerts.extend(results)
            sevs = {}
            for a in results:
                s = a['severity']
                sevs[s] = sevs.get(s, 0) + 1
            summary[name] = {'alerts': len(results), 'severity_counts': sevs}
        except Exception as e:
            logger.error(f'Watchdog check {name} raised: {e}')
            all_alerts.append(_alert('WARNING', name, f'{name} error: {e}',
                                     {'error': str(e)}))
            summary[name] = {'alerts': 1, 'error': str(e)}

    sev_set = {a['severity'] for a in all_alerts}
    status = 'CRITICAL' if 'CRITICAL' in sev_set else \
             'WARNINGS' if 'WARNING' in sev_set else 'CLEAN'
    elapsed = (datetime.now(timezone.utc) - start).total_seconds()

    logfn = {'CLEAN': logger.info, 'WARNINGS': logger.warning,
             'CRITICAL': logger.critical}[status]
    logfn(f'Watchdog scan {status} ({len(all_alerts)} alerts, {elapsed:.2f}s)')

    try:
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO health_checks (component,status,details) VALUES (?,?,?)",
                ('watchdog', 'ok' if status == 'CLEAN' else 'warning',
                 json.dumps({'status': status, 'alert_count': len(all_alerts),
                             'alerts': all_alerts[:20]}, default=str)))
            conn.commit()
    except Exception as e:
        logger.warning(f'Persist watchdog result: {e}')

    return {'alerts': all_alerts, 'status': status,
            'scan_time': start.isoformat(),
            'elapsed_seconds': round(elapsed, 2),
            'check_summary': summary}
