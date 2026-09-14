"""
ops/behavior_fingerprint.py — 行为指纹 (V7.1 RC1)

Daily metrics report. Measures:
  - Signals generated (from signal_decay scans)
  - Orders generated (from audit_log ORDER_INTENT events)
  - Orders executed (from audit_log ORDER_STATE → SUBMITTED/FILLED)
  - Average Kelly allocation (from kelly_engine/trade_history)
  - Total exposure (portfolio utilization)
  - Stop triggers (from audit_log RISK_EVENT stop-loss events)
  - Market regime (from market_env.json)

Generates daily JSON report. Enables: regression detection, drift monitoring,
performance attribution, compliance verification.

Usage:
    from eagle_eye.ops.behavior_fingerprint import generate_fingerprint
    report = generate_fingerprint()
    # Or as cron: python -m eagle_eye.ops.behavior_fingerprint

Constitution: Observer only. Reads data, produces report. Never trades.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from eagle_eye.core.config import cfg
from eagle_eye.core.logger import get_logger

logger = get_logger('ops.fingerprint')

DATA_DIR = cfg.data_dir
OUTPUT_FILE = DATA_DIR / 'behavior_fingerprint.json'


def generate_fingerprint(date: Optional[str] = None) -> dict:
    """
    生成行为指纹报告

    Args:
        date: 日期字符串 'YYYY-MM-DD'，None = 今天

    Returns:
        指纹报告 dict
    """
    if date is None:
        today = datetime.now(timezone.utc)
    else:
        today = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)

    start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    report = {
        'fingerprint_id': f'fp_{today.strftime("%Y%m%d")}',
        'date': today.strftime('%Y-%m-%d'),
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'metrics': {},
        'drift_indicators': [],
        'stability_score': None,
    }

    # ─── 1. Signals generated ────────────────────────
    signals = _count_signals(start, end)
    report['metrics']['signals_generated'] = signals

    # ─── 2. Orders generated ──────────────────────────
    orders = _count_orders(start, end)
    report['metrics']['orders'] = orders

    # ─── 3. Average Kelly ─────────────────────────────
    kelly = _read_kelly_metrics()
    report['metrics']['kelly'] = kelly

    # ─── 4. Total exposure ────────────────────────────
    exposure = _read_exposure()
    report['metrics']['exposure'] = exposure

    # ─── 5. Stop triggers ─────────────────────────────
    stops = _count_stop_triggers(start, end)
    report['metrics']['stop_triggers'] = stops

    # ─── 6. Market regime ─────────────────────────────
    regime = _read_market_regime()
    report['metrics']['market_regime'] = regime

    # ─── 7. Drift indicators ──────────────────────────
    drift = _compute_drift(report['metrics'])
    report['drift_indicators'] = drift

    # ─── 8. Stability score (0-100) ───────────────────
    report['stability_score'] = _compute_stability(drift)

    # ─── Save ─────────────────────────────────────────
    _save_report(report)

    return report


def _count_signals(start: datetime, end: datetime) -> dict:
    """从 signal_decay.json 统计信号数"""
    try:
        path = DATA_DIR / 'signal_decay.json'
        if not path.exists():
            return {'total': 0, 'critical': 0, 'warning': 0, 'watch': 0,
                    'clean': 0, 'source': 'signal_decay.json', 'status': 'file_missing'}
        with open(path) as f:
            data = json.load(f)
        summary = data.get('summary', {})
        return {
            'total': len(data.get('checks', [])),
            'critical': summary.get('critical', 0),
            'warning': summary.get('warning', 0),
            'watch': summary.get('watch', 0),
            'clean': summary.get('clean', 0),
            'source': 'signal_decay.json',
            'timestamp': data.get('timestamp', ''),
        }
    except Exception as e:
        return {'total': 0, 'source': 'signal_decay.json', 'error': str(e)}


def _count_orders(start: datetime, end: datetime) -> dict:
    """从 audit_log 统计订单数"""
    try:
        from eagle_eye.ops.audit_engine import query_events
        intents = query_events(
            event_type='ORDER_INTENT',
            since=start.strftime('%Y-%m-%d %H:%M:%S'),
            until=end.strftime('%Y-%m-%d %H:%M:%S'),
            limit=1000,
        )
        submitted = query_events(
            event_type='ORDER_STATE',
            since=start.strftime('%Y-%m-%d %H:%M:%S'),
            until=end.strftime('%Y-%m-%d %H:%M:%S'),
            limit=1000,
        )
        # Count SUBMITTED state transitions (actual executions)
        executed = [e for e in submitted
                    if e.get('details', '') and 'SUBMITTED' in str(e.get('details', ''))]

        buys = [i for i in intents if _parse_side(i) == 'buy']
        sells = [i for i in intents if _parse_side(i) == 'sell']

        return {
            'intents_generated': len(intents),
            'intents_buy': len(buys),
            'intents_sell': len(sells),
            'submitted_to_broker': len(executed),
            'execution_rate': round(len(executed) / len(intents), 3) if intents else 0,
            'source': 'audit_log',
        }
    except ImportError:
        return {'intents_generated': 0, 'source': 'audit_log',
                'status': 'audit_engine_unavailable'}


def _read_kelly_metrics() -> dict:
    """从 trade_history.json 读取 Kelly 指标"""
    try:
        path = DATA_DIR / 'trade_history.json'
        if not path.exists():
            return {'avg_kelly_pct': None, 'source': 'trade_history.json',
                    'status': 'file_missing'}
        with open(path) as f:
            data = json.load(f)
        kelly = data.get('kelly', {})
        return {
            'avg_kelly_pct': kelly.get('kelly_half_pct'),
            'kelly_full_pct': kelly.get('kelly_full_pct'),
            'win_rate': kelly.get('win_rate'),
            'odds_ratio': kelly.get('odds_ratio'),
            'total_trades': kelly.get('total_trades'),
            'recommendation': kelly.get('recommendation'),
            'source': 'trade_history.json',
        }
    except Exception as e:
        return {'avg_kelly_pct': None, 'source': 'trade_history.json',
                'error': str(e)}


def _read_exposure() -> dict:
    """从 us_portfolio.json 读取仓位暴露"""
    try:
        path = DATA_DIR / 'us_portfolio.json'
        if not path.exists():
            return {'utilization': None, 'source': 'us_portfolio.json',
                    'status': 'file_missing'}
        with open(path) as f:
            data = json.load(f)
        acct = data.get('account', {})
        return {
            'utilization': acct.get('utilization'),
            'equity': acct.get('equity'),
            'cash': acct.get('cash'),
            'gap_dollars': acct.get('gap_dollars'),
            'position_count': len(data.get('positions', [])),
            'sector_count': len(data.get('sector_allocation', {})),
            'drawdown': acct.get('drawdown'),
            'source': 'us_portfolio.json',
        }
    except Exception as e:
        return {'utilization': None, 'source': 'us_portfolio.json',
                'error': str(e)}


def _count_stop_triggers(start: datetime, end: datetime) -> dict:
    """从 audit_log 统计止损触发"""
    try:
        from eagle_eye.ops.audit_engine import query_events
        events = query_events(
            event_type='RISK_EVENT',
            since=start.strftime('%Y-%m-%d %H:%M:%S'),
            until=end.strftime('%Y-%m-%d %H:%M:%S'),
            limit=1000,
        )
        stop_events = [e for e in events
                       if 'stop' in str(e.get('details', '')).lower()
                       or '止损' in str(e.get('details', ''))]
        return {
            'total_risk_events': len(events),
            'stop_loss_triggers': len(stop_events),
            'source': 'audit_log',
        }
    except ImportError:
        return {'total_risk_events': 0, 'stop_loss_triggers': 0,
                'source': 'audit_log', 'status': 'unavailable'}


def _read_market_regime() -> dict:
    """从 market_env.json 读取市场状态"""
    try:
        path = DATA_DIR / 'market_env.json'
        if not path.exists():
            return {'regime': 'UNKNOWN', 'source': 'market_env.json',
                    'status': 'file_missing'}
        with open(path) as f:
            data = json.load(f)
        macro = data.get('macro', {})
        breadth = data.get('breadth', {})
        return {
            'regime': macro.get('regime', 'UNKNOWN'),
            'vix': macro.get('vix'),
            'breadth_health': breadth.get('health'),
            'pct_above_ma200': breadth.get('pct_above_ma200'),
            'ad_ratio': breadth.get('ad_ratio'),
            'source': 'market_env.json',
        }
    except Exception as e:
        return {'regime': 'UNKNOWN', 'source': 'market_env.json',
                'error': str(e)}


def _compute_drift(metrics: dict) -> list:
    """计算漂移指标 — 与历史基线对比"""
    drift = []
    baselines = _load_baseline()

    # Kelly drift
    kelly = metrics.get('kelly', {}).get('avg_kelly_pct')
    baseline_kelly = baselines.get('avg_kelly_pct')
    if kelly and baseline_kelly:
        delta = kelly - baseline_kelly
        if abs(delta) > 5:
            drift.append({
                'metric': 'avg_kelly_pct',
                'current': kelly,
                'baseline': baseline_kelly,
                'delta': round(delta, 1),
                'severity': 'WARNING' if abs(delta) > 10 else 'INFO',
                'message': f'Kelly allocation drifted {delta:+.1f}% from baseline',
            })

    # Exposure drift
    util = metrics.get('exposure', {}).get('utilization')
    baseline_util = baselines.get('utilization')
    if util is not None and baseline_util is not None:
        delta = (util - baseline_util) * 100
        if abs(delta) > 15:
            drift.append({
                'metric': 'utilization',
                'current': round(util * 100, 1),
                'baseline': round(baseline_util * 100, 1),
                'delta': round(delta, 1),
                'severity': 'WARNING',
                'message': f'Portfolio exposure drifted {delta:+.1f}% from baseline',
            })

    # Signal drift
    signals = metrics.get('signals_generated', {}).get('total', 0)
    baseline_signals = baselines.get('avg_daily_signals', 0)
    if signals and baseline_signals:
        if baseline_signals > 0:
            delta_pct = (signals - baseline_signals) / baseline_signals * 100
            if abs(delta_pct) > 50:
                drift.append({
                    'metric': 'signals_generated',
                    'current': signals,
                    'baseline': baseline_signals,
                    'delta_pct': round(delta_pct, 1),
                    'severity': 'INFO',
                    'message': f'Signal volume changed {delta_pct:+.0f}% from baseline',
                })

    return drift


def _compute_stability(drift: list) -> int:
    """计算稳定性评分 0-100"""
    if not drift:
        return 100
    warnings = sum(1 for d in drift if d.get('severity') == 'WARNING')
    infos = sum(1 for d in drift if d.get('severity') == 'INFO')
    return max(0, 100 - warnings * 20 - infos * 5)


def _load_baseline() -> dict:
    """加载历史基线（7天/30天滚动平均）"""
    # 简化：使用硬编码基线（后续可从历史指纹计算）
    return {
        'avg_kelly_pct': 11.6,
        'utilization': 0.50,
        'avg_daily_signals': 15,
    }


def _save_report(report: dict):
    """保存指纹报告"""
    try:
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f'指纹报告已保存: {OUTPUT_FILE}')
    except Exception as e:
        logger.error(f'保存指纹报告失败: {e}')


def _parse_side(event: dict) -> str:
    """从审计事件中解析买卖方向"""
    details = event.get('details', '')
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except json.JSONDecodeError:
            return 'unknown'
    if isinstance(details, dict):
        return details.get('side', 'unknown')
    return 'unknown'


def get_latest_fingerprint() -> Optional[dict]:
    """获取最新的指纹报告"""
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return None


# ─── CLI ────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='V7.1 行为指纹生成器')
    parser.add_argument('--date', type=str, default=None,
                       help='日期 YYYY-MM-DD (默认今天)')
    args = parser.parse_args()

    report = generate_fingerprint(date=args.date)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
