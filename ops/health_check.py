"""
ops/health_check.py — Comprehensive health checker (Phase 6A)
OBSERVER MODULE: Read-only assessment. No trading decisions.
"""

import os
import time
from datetime import datetime, timezone
from pathlib import Path

from eagle_eye.core.config import cfg
from eagle_eye.core.logger import get_logger
from eagle_eye.storage.db import db

logger = get_logger('ops.health')

FRESHNESS_THRESHOLDS = {
    'market_env.json': 24, 'us_watchlist.json': 24,
    'signal_decay.json': 4, 'us_portfolio.json': 24,
    'us_risk_state.json': 48,
}
CRITICAL_FILES = ['us_risk_state.json', 'market_env.json']
LOG_SIZE_WARN_BYTES = 50 * 1024 * 1024


def check_database() -> dict:
    """Check SQLite connectivity and integrity."""
    result = {'healthy': False, 'details': '', 'file_size_mb': 0.0, 'table_count': 0}
    db_path = cfg.db_path

    if db_path.exists():
        result['file_size_mb'] = round(db_path.stat().st_size / (1024 * 1024), 2)
    else:
        result['details'] = f'Database file missing: {db_path}'
        logger.warning(result['details'])
        return result

    try:
        with db.connect() as conn:
            integrity = conn.execute('PRAGMA integrity_check').fetchone()
            if integrity and integrity[0] != 'ok':
                result['details'] = f'Integrity check failed: {integrity[0]}'
                logger.error(result['details'])
                return result
            quick = conn.execute('PRAGMA quick_check').fetchone()
            if quick and quick[0] != 'ok':
                result['details'] = f'Quick check failed: {quick[0]}'
                logger.error(result['details'])
                return result
        result['healthy'] = True
        result['details'] = 'ok'
        try:
            result['table_count'] = len(db.tables())
        except Exception:
            result['table_count'] = -1
        if result['file_size_mb'] > 100:
            logger.warning(f'DB large ({result["file_size_mb"]:.1f} MB), consider VACUUM')
    except Exception as e:
        result['details'] = f'DB connection failed: {e}'
        logger.error(result['details'])
    return result


def check_api() -> dict:
    """Check Alpaca API connectivity."""
    result = {'healthy': False, 'details': '', 'failure_count': 0,
              'market_open': None, 'clock': None}
    try:
        from eagle_eye.broker.alpaca_client import get_alpaca_client
        client = get_alpaca_client()
    except Exception as e:
        result['details'] = f'Cannot init AlpacaClient: {e}'
        logger.error(result['details'])
        return result

    result['failure_count'] = client.api_failure_count
    if client.is_healthy():
        result['healthy'] = True
        result['details'] = 'API reachable'
    else:
        result['details'] = f'API unreachable (failures: {result["failure_count"]})'

    clock = client.get_clock()
    if clock:
        result['clock'] = clock
        result['market_open'] = clock.get('is_open', False)
    return result


def check_data_freshness() -> dict:
    """Check critical data file timestamps."""
    result = {'healthy': False, 'details': '', 'files': {}, 'missing': [], 'stale': []}
    now = time.time()
    all_ok = True

    for filename, max_hours in FRESHNESS_THRESHOLDS.items():
        filepath = cfg.data_dir / filename
        info = {'exists': False, 'age_hours': None, 'status': 'missing'}

        if filepath.exists():
            info['exists'] = True
            age_hours = (now - filepath.stat().st_mtime) / 3600
            info['age_hours'] = round(age_hours, 1)
            if age_hours <= max_hours:
                info['status'] = 'fresh'
            else:
                info['status'] = 'stale'
                result['stale'].append({'filename': filename,
                    'age_hours': round(age_hours, 1), 'max_hours': max_hours})
                all_ok = False
                logger.warning(f'{filename} stale: {age_hours:.1f}h (max {max_hours}h)')
        else:
            result['missing'].append(filename)
            all_ok = False
        result['files'][filename] = info

    for crit in CRITICAL_FILES:
        if not (cfg.data_dir / crit).exists() and crit not in result['missing']:
            result['missing'].append(crit)
            all_ok = False

    result['healthy'] = all_ok
    if all_ok:
        result['details'] = 'All data files fresh'
    elif result['missing']:
        result['details'] = f'Missing: {", ".join(result["missing"])}'
    else:
        result['details'] = f'Stale: {", ".join(s["filename"] for s in result["stale"])}'
    return result


def check_system() -> dict:
    """Check disk space, log size, and process."""
    result = {'healthy': False, 'details': '', 'disk_free_gb': 0.0,
              'disk_used_pct': 0.0, 'log_size_mb': 0.0,
              'process_running': False, 'warnings': []}
    all_ok = True

    # Disk
    try:
        check_path = cfg.data_dir if cfg.data_dir.exists() else Path.home()
        stat = os.statvfs(str(check_path))
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
        total_gb = (stat.f_blocks * stat.f_frsize) / (1024 ** 3)
        result['disk_free_gb'] = round(free_gb, 2)
        result['disk_used_pct'] = round((1 - free_gb / max(total_gb, 0.001)) * 100, 1)
        if free_gb < 0.1:
            all_ok = False
            result['warnings'].append(f'Disk low: {free_gb:.2f} GB free')
    except Exception as e:
        result['warnings'].append(f'Disk check failed: {e}')
        all_ok = False

    # Log size
    log_file = cfg.log_file
    if log_file.exists():
        result['log_size_mb'] = round(log_file.stat().st_size / (1024 * 1024), 2)
        if log_file.stat().st_size > LOG_SIZE_WARN_BYTES:
            result['warnings'].append(f'Log large: {result["log_size_mb"]:.1f} MB')

    # Process check
    try:
        found = False
        for pid_path in Path('/proc').iterdir():
            if not pid_path.name.isdigit():
                continue
            cmdline = pid_path / 'cmdline'
            if cmdline.exists():
                try:
                    data = cmdline.read_bytes()
                    if b'eagle_eye' in data or b'main.py' in data:
                        found = True
                        break
                except (OSError, PermissionError):
                    continue
        result['process_running'] = found
    except Exception:
        result['process_running'] = True

    result['healthy'] = all_ok
    result['details'] = f'Disk {result["disk_free_gb"]:.1f} GB free' if all_ok else \
        '; '.join(result['warnings'])
    return result


def full_health_report() -> dict:
    """
    Run all health checks, return comprehensive report.
    Overall: HEALTHY (all pass), DEGRADED (non-critical failures),
             UNHEALTHY (critical failures).
    """
    report = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'overall': 'UNHEALTHY',
        'database': check_database(),
        'api': check_api(),
        'data_freshness': check_data_freshness(),
        'system': check_system(),
        'trading_lock': {},
        'degraded_mode': {},
    }

    # Trading lock state
    try:
        from eagle_eye.risk.trading_lock import trading_lock
        report['trading_lock'] = {
            'is_locked': trading_lock.is_locked,
            'reasons': trading_lock.reason_names(),
            'locked_at': trading_lock.locked_at.isoformat()
                if trading_lock.locked_at else None,
        }
    except Exception as e:
        report['trading_lock'] = {'error': str(e)}

    # Degraded mode state
    try:
        from eagle_eye.risk.degraded_mode import degraded_mode
        report['degraded_mode'] = {
            'state': degraded_mode.state.name,
            'is_degraded': degraded_mode.is_degraded(),
            'is_recovering': degraded_mode.is_recovering(),
            'entered_at': degraded_mode.entered_at.isoformat()
                if degraded_mode.entered_at else None,
            'reason': degraded_mode.reason or 'N/A',
        }
    except Exception as e:
        report['degraded_mode'] = {'error': str(e)}

    # Overall status
    critical = []
    non_critical = []

    if not report['database']['healthy']:
        critical.append('database')
    if not report['api']['healthy']:
        non_critical.append('api')
    missing_critical = [f for f in report['data_freshness'].get('missing', [])
                        if f in CRITICAL_FILES]
    if missing_critical:
        critical.append('critical_data_missing')
    elif not report['data_freshness']['healthy']:
        non_critical.append('data_stale')
    if not report['system']['healthy']:
        if report['system']['disk_free_gb'] < 0.1:
            critical.append('disk_full')
        else:
            non_critical.append('system_warning')
    if report['degraded_mode'].get('is_degraded'):
        non_critical.append('degraded_mode')

    if critical:
        report['overall'] = 'UNHEALTHY'
        logger.critical(f'System unhealthy: {critical}')
    elif non_critical:
        report['overall'] = 'DEGRADED'
        logger.warning(f'System degraded: {non_critical}')
    else:
        report['overall'] = 'HEALTHY'

    return report
