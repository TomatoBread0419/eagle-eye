"""
execution/candidate_tracker.py — 候选历史追踪器 (V7.1 P0)

记录每次扫描中候选的出现，维护连续扫描计数。
供 §6 多周期确认门和 §6.1 Seed Position 豁免使用。

用法:
    from eagle_eye.execution.candidate_tracker import record_scan, get_consecutive_count

    # 扫描完成后调用
    record_scan(['INTC', 'ABBV', 'MCD'], with_details={
        'INTC': {'score': 50, 'sector': 'tech', 'kelly_pct': 16.5, 'rsi': 50.1},
        'ABBV': {'score': 19, 'sector': 'pharma', 'kelly_pct': 6.6, 'rsi': 53.3},
    })

    # 查询某标的连续出现次数
    count = get_consecutive_count('INTC')  # → 1
"""

from datetime import date, datetime
from typing import Dict, List, Optional

from eagle_eye.core.logger import get_logger
from eagle_eye.storage.db import db

logger = get_logger('execution.candidate')


def record_scan(
    symbols: List[str],
    scan_date: Optional[date] = None,
    with_details: Optional[Dict[str, dict]] = None,
):
    """
    记录一次扫描中出现的候选。

    逻辑：
    1. 新出现的候选：scan_count = 1
    2. 昨天也出现的候选：scan_count = previous_count + 1
    3. 昨天出现但今天没出现的：重置为 0（中断连续性）

    Args:
        symbols: 本次扫描中出现在 buy_candidates 的 symbol 列表
        scan_date: 扫描日期，默认今天
        with_details: {symbol: {score, sector, kelly_pct, rsi}}
    """
    today = scan_date or date.today()
    details = with_details or {}

    try:
        with db.transaction() as conn:
            # 获取昨天有记录的 symbol
            yesterday_rows = conn.execute(
                'SELECT symbol, scan_count FROM candidate_history WHERE scan_date = ?',
                (today.isoformat(),)
            ).fetchall()

            # 如果今天已经记录过，跳过（幂等）
            if yesterday_rows:
                logger.debug(f'扫描 {today} 已记录，跳过')
                return

            # 获取所有历史记录中最近的 scan_count
            all_history = {}
            for row in conn.execute(
                'SELECT symbol, scan_count, scan_date FROM candidate_history ORDER BY scan_date DESC'
            ).fetchall():
                if row['symbol'] not in all_history:
                    all_history[row['symbol']] = row['scan_count']

            # 记录今天的候选
            for sym in symbols:
                prev_count = all_history.get(sym, 0)
                new_count = prev_count + 1 if prev_count > 0 else 1
                detail = details.get(sym, {})

                conn.execute(
                    '''INSERT OR REPLACE INTO candidate_history
                       (symbol, scan_date, scan_count, last_seen, score, sector, kelly_pct, rsi)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (
                        sym,
                        today.isoformat(),
                        new_count,
                        datetime.now().isoformat(),
                        detail.get('score'),
                        detail.get('sector'),
                        detail.get('kelly_pct'),
                        detail.get('rsi'),
                    )
                )

                # 检查 §6.1 seed eligibility
                rsi_val = detail.get('rsi')
                kelly_val = detail.get('kelly_pct')
                is_seed = (
                    rsi_val is not None and 40 <= rsi_val <= 70
                    and kelly_val is not None and kelly_val <= 8.0
                )
                conn.execute(
                    'UPDATE candidate_history SET is_seed_eligible = ? WHERE symbol = ? AND scan_date = ?',
                    (1 if is_seed else 0, sym, today.isoformat())
                )

        logger.info(f'候选记录: {len(symbols)} 只 → candidate_history ({today})')
    except Exception as e:
        logger.error(f'候选记录失败: {e}')


def get_consecutive_count(symbol: str) -> int:
    """查询 symbol 的连续扫描出现次数（最近一次记录的 scan_count）。"""
    try:
        row = db.fetchone(
            'SELECT scan_count FROM candidate_history WHERE symbol = ? ORDER BY scan_date DESC LIMIT 1',
            (symbol,)
        )
        return row['scan_count'] if row else 0
    except Exception as e:
        logger.warning(f'查询 {symbol} 候选历史失败: {e}')
        return 0


def get_eligible_seeds() -> List[dict]:
    """获取今天标记为 seed-eligible 的候选。"""
    try:
        today = date.today().isoformat()
        rows = db.fetchall(
            '''SELECT symbol, sector, score, kelly_pct, rsi, scan_count
               FROM candidate_history
               WHERE scan_date = ? AND is_seed_eligible = 1
               ORDER BY score DESC''',
            (today,)
        )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f'查询 seed candidates 失败: {e}')
        return []
