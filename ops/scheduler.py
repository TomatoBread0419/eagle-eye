"""
ops/scheduler.py — Lightweight job scheduler (Phase 6A)
OBSERVER MODULE: Job tracking and scheduling. No trading decisions.
Uses SQLite for persistence via eagle_eye.storage.db.
"""

import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from eagle_eye.core.logger import get_logger
from eagle_eye.storage.db import db

logger = get_logger('ops.scheduler')

VALID_STATUSES = ('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'TIMEOUT')
TABLE = 'ops_jobs'

CREATE_TABLE = f'''
CREATE TABLE IF NOT EXISTS {TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    schedule TEXT,
    command TEXT,
    status TEXT DEFAULT 'PENDING',
    last_run TIMESTAMP,
    next_run TIMESTAMP,
    last_duration_ms INTEGER,
    last_error TEXT,
    run_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)'''


def _ensure_table():
    """Create table + indexes if missing."""
    try:
        with db.connect() as conn:
            conn.execute(CREATE_TABLE)
            conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{TABLE}_status ON {TABLE}(status)')
            conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{TABLE}_next ON {TABLE}(next_run)')
            conn.commit()
    except Exception as e:
        logger.error(f'Cannot create {TABLE}: {e}')


_ensure_table()


# ─── Schedule parsing ─────────────────────────────────────

def _parse_interval(schedule: str) -> Optional[timedelta]:
    """Parse 'every Xh', 'every Xm', 'every Xs'."""
    import re
    s = schedule.strip().lower()
    if not s.startswith('every '):
        return None
    m = re.match(r'^(\d+)\s*(h|m|s|hour|min|sec|hours|mins|secs)$', s[6:].strip())
    if not m:
        return None
    val, unit = int(m.group(1)), m.group(2)[0]
    return {'h': timedelta(hours=val), 'm': timedelta(minutes=val),
            's': timedelta(seconds=val)}.get(unit)


def _cron_field_match(value: int, field: str) -> bool:
    """Check if value matches a cron field (number, *, range, list, step)."""
    if field == '*':
        return True
    if ',' in field:
        return any(_cron_field_match(value, f.strip()) for f in field.split(','))
    if '-' in field:
        try:
            lo, hi = map(int, field.split('-'))
            return lo <= value <= hi
        except (ValueError, IndexError):
            return False
    if '/' in field:
        base, step = field.split('/')
        try:
            step = int(step)
            if base == '*':
                return value % step == 0
            base_val = int(base)
            return value >= base_val and (value - base_val) % step == 0
        except ValueError:
            return False
    try:
        return value == int(field)
    except ValueError:
        return False


def _cron_matches(dt: datetime, fields: List[str]) -> bool:
    """Check if datetime matches 5-field cron."""
    return (_cron_field_match(dt.minute, fields[0]) and
            _cron_field_match(dt.hour, fields[1]) and
            _cron_field_match(dt.day, fields[2]) and
            _cron_field_match(dt.month, fields[3]) and
            _cron_field_match((dt.weekday() + 1) % 7, fields[4]))


def _next_cron(schedule: str) -> Optional[datetime]:
    """Find next cron match within 7 days."""
    fields = schedule.strip().split()
    if len(fields) != 5:
        return None
    now = datetime.now().replace(second=0, microsecond=0)
    for _ in range(60 * 24 * 7):
        now += timedelta(minutes=1)
        if _cron_matches(now, fields):
            return now
    return None


def _compute_next(schedule: str) -> Optional[datetime]:
    """Compute next run time from schedule string."""
    now = datetime.now(timezone.utc)
    interval = _parse_interval(schedule)
    if interval:
        return now + interval
    cron_dt = _next_cron(schedule)
    if cron_dt:
        return cron_dt.replace(tzinfo=timezone.utc)
    logger.warning(f'Unparseable schedule: {schedule}')
    return None


def _row_to_dict(row) -> dict:
    """Convert sqlite3.Row to plain dict."""
    return {k: row[k] for k in row.keys()}


# ─── Public API ────────────────────────────────────────────

def register_job(name: str, schedule: str, command: str = '') -> bool:
    """Register or update a job."""
    next_run = _compute_next(schedule)
    try:
        with db.connect() as conn:
            exists = conn.execute(
                f'SELECT id FROM {TABLE} WHERE name = ?', (name,)
            ).fetchone()
            if exists:
                conn.execute(f'''UPDATE {TABLE} SET schedule=?, command=?,
                    next_run=?, updated_at=CURRENT_TIMESTAMP WHERE name=?''',
                    (schedule, command, next_run, name))
            else:
                conn.execute(f'''INSERT INTO {TABLE} (name, schedule, command, next_run)
                    VALUES (?,?,?,?)''', (name, schedule, command, next_run))
            conn.commit()
        logger.info(f'Job registered: {name} ({schedule})')
        return True
    except Exception as e:
        logger.error(f'Register failed {name}: {e}')
        return False


def start_job(name: str) -> bool:
    """Mark job as RUNNING."""
    now = datetime.now(timezone.utc)
    try:
        with db.connect() as conn:
            row = conn.execute(
                f'SELECT id FROM {TABLE} WHERE name = ?', (name,)
            ).fetchone()
            if not row:
                logger.warning(f'Job not found: {name}')
                return False
            conn.execute(f'''UPDATE {TABLE} SET status='RUNNING', last_run=?,
                updated_at=CURRENT_TIMESTAMP WHERE name=?''', (now, name))
            conn.commit()
        logger.info(f'Job started: {name}')
        return True
    except Exception as e:
        logger.error(f'Start failed {name}: {e}')
        return False


def finish_job(name: str, success: bool = True, error: str = None,
               duration_ms: int = 0) -> bool:
    """Mark job SUCCESS or FAILED, update counters and next run."""
    status = 'SUCCESS' if success else 'FAILED'
    try:
        with db.connect() as conn:
            row = conn.execute(
                f'SELECT schedule FROM {TABLE} WHERE name = ?', (name,)
            ).fetchone()
            if not row:
                return False
            next_run = _compute_next(row['schedule']) if row['schedule'] else None
            if success:
                conn.execute(f'''UPDATE {TABLE} SET status=?, last_duration_ms=?,
                    last_error=NULL, next_run=?, run_count=run_count+1,
                    updated_at=CURRENT_TIMESTAMP WHERE name=?''',
                    (status, duration_ms, next_run, name))
            else:
                conn.execute(f'''UPDATE {TABLE} SET status=?, last_duration_ms=?,
                    last_error=?, next_run=?, run_count=run_count+1,
                    fail_count=fail_count+1, updated_at=CURRENT_TIMESTAMP
                    WHERE name=?''',
                    (status, duration_ms, error or '', next_run, name))
            conn.commit()
        if success:
            logger.info(f'Job done: {name} ({duration_ms}ms)')
        else:
            logger.error(f'Job failed: {name} — {error or "unknown"}')
        return True
    except Exception as e:
        logger.error(f'Finish failed {name}: {e}')
        return False


def list_jobs(status: str = None) -> list:
    """List jobs, optionally filtered by status."""
    try:
        with db.connect() as conn:
            if status and status in VALID_STATUSES:
                rows = conn.execute(
                    f'SELECT * FROM {TABLE} WHERE status=? ORDER BY name',
                    (status,)).fetchall()
            else:
                rows = conn.execute(
                    f'SELECT * FROM {TABLE} ORDER BY name').fetchall()
        return [_row_to_dict(r) for r in rows]
    except Exception as e:
        logger.error(f'List failed: {e}')
        return []


def get_job(name: str) -> Optional[dict]:
    """Get single job details."""
    try:
        with db.connect() as conn:
            row = conn.execute(
                f'SELECT * FROM {TABLE} WHERE name = ?', (name,)
            ).fetchone()
        return _row_to_dict(row) if row else None
    except Exception as e:
        logger.error(f'Get failed {name}: {e}')
        return None


def get_overdue_jobs(timeout_minutes: int = 120) -> list:
    """Find RUNNING jobs stuck past timeout."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
    try:
        with db.connect() as conn:
            rows = conn.execute(f'''SELECT * FROM {TABLE}
                WHERE status='RUNNING' AND last_run < ?
                ORDER BY last_run''', (cutoff,)).fetchall()
        overdue = [_row_to_dict(r) for r in rows]
        if overdue:
            logger.warning(f'Overdue jobs: {[j["name"] for j in overdue]}')
        return overdue
    except Exception as e:
        logger.error(f'Overdue check failed: {e}')
        return []


def get_next_due() -> list:
    """Get jobs due now (next_run <= now, not RUNNING)."""
    now = datetime.now(timezone.utc)
    try:
        with db.connect() as conn:
            rows = conn.execute(f'''SELECT * FROM {TABLE}
                WHERE next_run <= ? AND status IN ('PENDING','FAILED','SUCCESS')
                ORDER BY next_run''', (now,)).fetchall()
        return [_row_to_dict(r) for r in rows]
    except Exception as e:
        logger.error(f'Due check failed: {e}')
        return []


def job_summary() -> dict:
    """Summary: totals, status breakdown, success rate, overdue count."""
    try:
        with db.connect() as conn:
            rows = conn.execute(
                f'SELECT status, run_count, fail_count FROM {TABLE}').fetchall()
        summary = {
            'total_jobs': len(rows),
            'by_status': {s: 0 for s in VALID_STATUSES},
            'success_rate': 0.0, 'total_runs': 0, 'total_failures': 0,
            'overdue': 0,
        }
        runs = fails = 0
        for row in rows:
            st = row['status']
            if st in summary['by_status']:
                summary['by_status'][st] += 1
            runs += row['run_count'] or 0
            fails += row['fail_count'] or 0
        summary['total_runs'] = runs
        summary['total_failures'] = fails
        summary['success_rate'] = round(1 - fails / max(runs, 1), 4) if runs else 1.0
        summary['overdue'] = len(get_overdue_jobs())
        return summary
    except Exception as e:
        logger.error(f'Summary failed: {e}')
        return {'total_jobs': 0, 'by_status': {s: 0 for s in VALID_STATUSES},
                'success_rate': 0.0, 'total_runs': 0, 'total_failures': 0, 'overdue': 0}


def mark_timed_out_jobs(timeout_minutes: int = 120) -> int:
    """Mark stuck RUNNING jobs as TIMEOUT."""
    overdue = get_overdue_jobs(timeout_minutes)
    count = 0
    for job in overdue:
        try:
            with db.connect() as conn:
                conn.execute(f'''UPDATE {TABLE} SET status='TIMEOUT',
                    fail_count=fail_count+1, last_error='Timed out',
                    updated_at=CURRENT_TIMESTAMP WHERE name=?''', (job['name'],))
                conn.commit()
            count += 1
            logger.warning(f'Job timed out: {job["name"]}')
        except Exception as e:
            logger.error(f'Mark timeout failed {job["name"]}: {e}')
    return count
