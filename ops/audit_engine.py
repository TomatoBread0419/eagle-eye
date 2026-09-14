"""ops/audit_engine.py — Append-only audit log (Phase 6A)
Records all significant events. Never modifies trading state.
APPEND-ONLY: all writes are INSERT, never UPDATE/DELETE (except prune_events).
Observer module: record + alert only."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from eagle_eye.core.logger import get_logger
from eagle_eye.storage.db import db

logger = get_logger('ops.audit')

_AUDIT_TABLE = """CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL,
    severity TEXT DEFAULT 'INFO',
    source TEXT,
    symbol TEXT,
    action TEXT,
    details TEXT,
    user_notified INTEGER DEFAULT 0)"""
_AUDIT_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_audit_log_type ON audit_log(event_type)",
    "CREATE INDEX IF NOT EXISTS idx_audit_log_sev ON audit_log(severity)",
    "CREATE INDEX IF NOT EXISTS idx_audit_log_sym ON audit_log(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log(timestamp)",
]
_schema_ok = False

_FMT = '%Y-%m-%d %H:%M:%S'  # SQLite-compatible, no T, no timezone


def _ensure_schema():
    global _schema_ok
    if _schema_ok:
        return
    with db.connect() as conn:
        conn.execute(_AUDIT_TABLE)
        for s in _AUDIT_INDEXES:
            try:
                conn.execute(s)
            except Exception:
                pass
        conn.commit()
    _schema_ok = True


def _js(d):
    """JSON-serialize details, return None if d is None."""
    if d is None:
        return None
    return json.dumps(d, default=str, ensure_ascii=False)


def _row(r):
    d = dict(r)
    if d.get('details'):
        try:
            d['details'] = json.loads(d['details'])
        except (json.JSONDecodeError, TypeError):
            pass
    return d


def _summ(d, n=120):
    if d is None:
        return ''
    if isinstance(d, str):
        return d[:n]
    m = d.get('message', str(d)) if isinstance(d, dict) else str(d)
    return str(m)[:n]


def _ts_now():
    return datetime.now(timezone.utc).strftime(_FMT)


def _ts_ago(**kw):
    return (datetime.now(timezone.utc) - timedelta(**kw)).strftime(_FMT)


# ─── Core: log_event ─────────────────────────────────

def log_event(event_type, severity='INFO', source=None,
              symbol=None, details=None):
    """Record an event. APPEND ONLY. Returns event_id or None."""
    _ensure_schema()
    try:
        et, sv = event_type.upper(), severity.upper()
        with db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO audit_log (event_type,severity,source,symbol,details) "
                "VALUES (?,?,?,?,?)",
                (et, sv, source, symbol, _js(details)))
            conn.commit()
        eid = cur.lastrowid
        lf = {'CRITICAL': logger.critical, 'WARNING': logger.warning}
        lf.get(sv, logger.debug)(f'AUDIT [{et}] {source or ""} — {_summ(details)}')
        return eid
    except Exception as e:
        logger.error(f'log_event failed: {e}')
        return None


# ─── Specialized loggers ──────────────────────────────

def log_order_intent(intent):
    """Record an OrderIntent object."""
    try:
        s = getattr(intent, 'side', None)
        return log_event(
            'ORDER_INTENT', 'INFO',
            f"execution.{getattr(intent, 'decision_source', 'unknown')}",
            getattr(intent, 'symbol', None), {
                'side': str(s) if s else None,
                'qty': getattr(intent, 'qty', None),
                'order_type': str(getattr(intent, 'order_type', '')),
                'time_in_force': getattr(intent, 'time_in_force', None),
                'limit_price': getattr(intent, 'limit_price', None),
                'stop_price': getattr(intent, 'stop_price', None),
                'status': str(getattr(intent, 'status', '')),
                'reason': getattr(intent, 'reason', ''),
                'priority': getattr(intent, 'priority', 0),
            })
    except Exception as e:
        logger.error(f'log_order_intent: {e}')
        return None


def log_order_state_change(order_id, from_state, to_state, reason=''):
    """Record order state machine transition."""
    sv = 'WARNING' if to_state in ('FAILED', 'CANCELLED') else 'INFO'
    return log_event('ORDER_STATE', sv, 'execution.order_state_machine',
                     details={'order_id': order_id, 'from_state': from_state,
                              'to_state': to_state, 'reason': reason})


def log_position_change(symbol, change_type, qty_before, qty_after, price=None):
    """Record position quantity change."""
    sv = 'WARNING' if change_type == 'close' else 'INFO'
    return log_event('POSITION_CHANGE', sv, 'execution.position_manager',
                     symbol=symbol,
                     details={'change_type': change_type, 'qty_before': qty_before,
                              'qty_after': qty_after,
                              'delta': qty_after - qty_before, 'price': price})


def log_risk_event(message, severity='WARNING', details=None):
    """Record risk-related event."""
    return log_event('RISK_EVENT', severity, 'risk',
                     details={'message': message, **(details or {})})


def log_degraded_mode_event(state, reason=''):
    """Record degraded mode state change."""
    sv = ('CRITICAL' if state == 'DEGRADED' else
          'WARNING' if state == 'RECOVERING' else 'INFO')
    return log_event('DEGRADED_MODE', sv, 'risk.degraded_mode',
                     details={'state': state, 'reason': reason})


def log_trading_lock_event(is_locked, reasons=None):
    """Record trading lock state change."""
    return log_event('TRADING_LOCK', 'CRITICAL' if is_locked else 'INFO',
                     'risk.trading_lock',
                     details={'is_locked': is_locked, 'reasons': reasons or []})


# ─── Query ────────────────────────────────────────────

def query_events(event_type=None, symbol=None, severity=None,
                 since=None, until=None, limit=100):
    """Query audit log. Returns list of event dicts, most recent first."""
    _ensure_schema()
    cl, pr = [], []
    if event_type:
        cl.append("event_type=?")
        pr.append(event_type.upper())
    if symbol:
        cl.append("symbol=?")
        pr.append(symbol)
    if severity:
        cl.append("severity=?")
        pr.append(severity.upper())
    if since:
        cl.append("timestamp>=?")
        pr.append(since)
    if until:
        cl.append("timestamp<?")
        pr.append(until)
    wh = ("WHERE " + " AND ".join(cl)) if cl else ""
    try:
        with db.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM audit_log {wh} ORDER BY timestamp DESC LIMIT ?",
                tuple(pr + [limit])).fetchall()
        return [_row(r) for r in rows]
    except Exception as e:
        logger.error(f'query_events: {e}')
        return []


def get_recent_events(hours=24, limit=100):
    """Get recent events for dashboard display."""
    return query_events(since=_ts_ago(hours=hours), limit=limit)


def get_event_counts(hours=24):
    """Get event counts by type for past N hours."""
    _ensure_schema()
    try:
        since = _ts_ago(hours=hours)
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT event_type, COUNT(*) as cnt FROM audit_log "
                "WHERE timestamp>=? GROUP BY event_type", (since,)).fetchall()
        return {r['event_type']: r['cnt'] for r in rows}
    except Exception as e:
        logger.error(f'get_event_counts: {e}')
        return {}


def export_audit_log(filepath, since=None, until=None):
    """Export audit log to JSON file. Returns count exported."""
    _ensure_schema()
    try:
        events = query_events(since=since, until=until, limit=100_000)
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({
                'exported_at': _ts_now(),
                'filters': {'since': since, 'until': until},
                'count': len(events), 'events': events,
            }, f, indent=2, default=str, ensure_ascii=False)
        logger.info(f'Exported {len(events)} audit events to {filepath}')
        return len(events)
    except Exception as e:
        logger.error(f'export_audit_log: {e}')
        return 0


def prune_events(older_than_days=90):
    """Remove events older than N days. ONLY DELETE in audit module."""
    _ensure_schema()
    try:
        cutoff = _ts_ago(days=older_than_days)
        with db.connect() as conn:
            cur = conn.execute("DELETE FROM audit_log WHERE timestamp<?", (cutoff,))
            conn.commit()
        n = cur.rowcount
        if n:
            logger.info(f'Pruned {n} audit events >{older_than_days}d')
        return n
    except Exception as e:
        logger.error(f'prune_events: {e}')
        return 0
