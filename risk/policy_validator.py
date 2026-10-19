"""
risk/policy_validator.py — Auto-Approval Policy v1.1 硬守卫 (V7.1 P0)

所有 OrderIntent 必须经过此验证器。
只能返回 PASS 或 REJECT。不生成交易建议。

宪法铁律 #11: Policy Validator 是交易前的最后一道防线。

Checks:
  1. Active Sectors ≥ 4 (Minimum)
  2. Seed Position eligibility under §6.1
  3. Exposure: position ≤ 18%, sector ≤ 30%, total ≤ 90%
  4. Candidate multi-cycle confirmation (§6)

用法:
    from eagle_eye.risk.policy_validator import validate_order_intent
    ok, reason = validate_order_intent(intent, state)
    if not ok:
        intent.mark_policy_rejected(reason)
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, Dict, List, Tuple

from eagle_eye.core.logger import get_logger

logger = get_logger('risk.policy')

# ─── Policy Constants (from auto_approval_policy.md v1.1) ───

MAX_SINGLE_POSITION = 0.18
MAX_SECTOR_WEIGHT = 0.30
MAX_TOTAL_EXPOSURE = 0.90
ACTIVE_MINIMUM = 4
ACTIVE_HEALTHY = 5
ACTIVE_TARGET = 6
SEED_MAX_KELLY = 0.08
SEED_MAX_SIZE = 0.05
SEED_RSI_MIN = 40
SEED_RSI_MAX = 70
CANDIDATE_CYCLES_REQUIRED = 2


@dataclass
class PortfolioState:
    """Snapshot of portfolio for policy validation."""
    equity: float = 0.0
    cash: float = 0.0
    positions: Dict[str, dict] = field(default_factory=dict)  # {sym: {size%, sector, pnl%, rsi}}
    sectors: Dict[str, float] = field(default_factory=dict)    # {sector: weight%}
    active_sectors: int = 0
    stop_coverage: int = 0
    total_holdings: int = 0


def _get_active_sectors(sectors: Dict[str, float]) -> int:
    """Count sectors with ≥3% allocation."""
    return sum(1 for w in sectors.values() if w >= 0.03)


def _get_candidate_scan_count(symbol: str) -> int:
    """Query candidate_history for consecutive scan appearances."""
    try:
        from eagle_eye.storage.db import db
        row = db.fetchone(
            'SELECT scan_count FROM candidate_history WHERE symbol = ? ORDER BY last_seen DESC LIMIT 1',
            (symbol,)
        )
        return row['scan_count'] if row else 0
    except Exception:
        return 0  # DB not available → conservative: treat as 0


def _has_contradictory_signals(symbol_info: dict) -> bool:
    """
    Check for contradictory signal combinations.
    Per §6.1: death cross + volume spike combo, or death cross alone with RSI < 45.
    """
    signals = symbol_info.get('signals', {})
    has_death_cross = signals.get('death_cross', False)
    has_volume_spike = signals.get('volume_spike', False)
    rsi = symbol_info.get('rsi', 50)

    if has_death_cross and has_volume_spike:
        return True
    if has_death_cross and rsi is not None and rsi < 45:
        return True
    return False


def _dashboard_exists_today() -> bool:
    """Check if today's Dashboard exists."""
    try:
        from pathlib import Path
        today = date.today().strftime('%Y-%m-%d')
        dashboard_path = Path.home() / 'stock_trader' / f'dashboard_{today}.md'
        return dashboard_path.exists()
    except Exception:
        return False


# ════════════════════════════════════════════════════
# Individual checks (each returns PASS/REJECT + reason)
# ════════════════════════════════════════════════════

def check_dashboard_gate() -> Tuple[bool, str]:
    """
    §7: Dashboard → Trade Decision → Execution.
    No Dashboard = no trading.
    """
    if _dashboard_exists_today():
        return True, 'Dashboard exists for today'
    return False, 'REJECTED: No Dashboard for today. Pipeline requires Dashboard → Trade Decision → Execution.'


def check_active_sectors(sectors: Dict[str, float]) -> Tuple[bool, str]:
    """§5: Active Sectors must be ≥ Minimum (4)."""
    active = _get_active_sectors(sectors)
    if active >= ACTIVE_MINIMUM:
        return True, f'Active Sectors={active} ≥ {ACTIVE_MINIMUM}'
    return False, f'REJECTED: Active Sectors={active} < Minimum({ACTIVE_MINIMUM}). Check §6.1 Seed Position eligibility.'


def check_exposure(position_pct: float, sector_pct: float, total_exposure: float) -> Tuple[bool, str]:
    """
    §5: Hard constraints on position, sector, and total exposure.
    Returns PASS only if ALL three pass.
    """
    if position_pct > MAX_SINGLE_POSITION:
        return False, f'REJECTED: Position {position_pct*100:.1f}% > max {MAX_SINGLE_POSITION*100:.0f}%'
    if sector_pct > MAX_SECTOR_WEIGHT:
        return False, f'REJECTED: Sector {sector_pct*100:.1f}% > max {MAX_SECTOR_WEIGHT*100:.0f}%'
    if total_exposure > MAX_TOTAL_EXPOSURE:
        return False, f'REJECTED: Total exposure {total_exposure*100:.1f}% > max {MAX_TOTAL_EXPOSURE*100:.0f}%'
    return True, f'Position {position_pct*100:.1f}% / Sector {sector_pct*100:.1f}% / Total {total_exposure*100:.1f}% — all within limits'


def check_candidate_confirmation(symbol: str, is_seed: bool = False) -> Tuple[bool, str]:
    """
    §6: Multi-cycle confirmation gate.
    §6.1: Seed Position exempt from cycle requirement.
    """
    if is_seed:
        return True, 'Seed Position — exempt from §6 multi-cycle gate'

    count = _get_candidate_scan_count(symbol)
    if count >= CANDIDATE_CYCLES_REQUIRED:
        return True, f'{symbol} confirmed: {count} consecutive scans (≥{CANDIDATE_CYCLES_REQUIRED})'
    return False, f'REJECTED: {symbol} only {count}/{CANDIDATE_CYCLES_REQUIRED} scan cycles. Wait for confirmation.'


def check_seed_eligibility(
    symbol: str,
    sector: str,
    sectors: Dict[str, float],
    rsi: Optional[float],
    kelly_pct: Optional[float],
    signals: Dict[str, bool],
) -> Tuple[bool, str]:
    """
    §6.1: Structural Exemption for Seed Position.
    ALL conditions must be met.
    """
    active = _get_active_sectors(sectors)

    # 1. Active Sectors < Minimum?
    if active >= ACTIVE_MINIMUM:
        return False, f'§6.1 not active: Active Sectors={active} ≥ Minimum({ACTIVE_MINIMUM})'

    # 2. Gap Sector?
    sector_weight = sectors.get(sector, 0.0)
    if sector_weight >= 0.03:
        return False, f'{sector} at {sector_weight*100:.1f}% — not a gap sector'

    # 3. RSI in range?
    if rsi is None:
        return False, 'RSI data missing'
    if rsi < SEED_RSI_MIN or rsi > SEED_RSI_MAX:
        return False, f'RSI={rsi:.1f} outside [{SEED_RSI_MIN}-{SEED_RSI_MAX}] seed range'

    # 4. No contradictory signals?
    if _has_contradictory_signals({'signals': signals, 'rsi': rsi}):
        return False, 'Contradictory signals detected (death cross + volume spike or death cross with RSI < 45)'

    # 5. Kelly ≤ 8%? — [SUPERSEDED 2026-10-19] kelly 数据被审计证伪，降级为信息性记录，不再决定新仓资格。
    # 依据：perf_retro_20261019（美元 FIFO 重算真凯利 −4.24%、自报 matched_trades=325 无逐笔明细不可审计）。
    # 固定风险约束不变：size ≤ 5%（订单创建时）、check_exposure 敞口上限、RSI/gap/信号一致性判定全部保留。
    if kelly_pct is not None and kelly_pct > SEED_MAX_KELLY * 100:
        get_logger(__name__).info(f'[KELLY-ADVISORY-ONLY] {symbol}: Kelly={kelly_pct:.1f}% > {SEED_MAX_KELLY*100:.0f}%（仅记录，不再拒绝）')

    # 6. Size ≤ 5%?
    # (checked at order creation — this validator confirms eligibility)

    return True, (
        f'🌱 Seed eligible: {symbol} ({sector}) | '
        f'RSI={rsi:.1f} | Kelly={kelly_pct:.1f}% ' if kelly_pct else ''
        f'| Active Sectors={active}<{ACTIVE_MINIMUM}'
    )


# ════════════════════════════════════════════════════
# Main validation entry point
# ════════════════════════════════════════════════════

def validate_order_intent(intent, portfolio_state: dict) -> Tuple[bool, str]:
    """
    Validate an OrderIntent against Auto-Approval Policy v1.1.

    Args:
        intent: OrderIntent object (from eagle_eye.execution.order_intent)
        portfolio_state: dict with keys:
            - equity: float
            - cash: float
            - positions: {symbol: {size_pct, sector, pnl_pct, rsi}}
            - sectors: {sector_name: weight_pct}
            - symbol_info: {symbol: {rsi, kelly_pct, signals_dict}} (optional, for seed check)

    Returns:
        (PASS: bool, reason: str)
    """
    reasons = []

    # ─── Gate 0: Dashboard must exist ───
    dashboard_ok, dashboard_reason = check_dashboard_gate()
    if not dashboard_ok:
        reasons.append(dashboard_reason)
        return False, ' | '.join(reasons)

    # ─── Gate 1: Active Sectors ───
    sectors = portfolio_state.get('sectors', {})
    active_ok, active_reason = check_active_sectors(sectors)
    if not active_ok:
        # If Active Sectors < 4, check if this is a valid Seed Position
        symbol_info = portfolio_state.get('symbol_info', {}).get(intent.symbol, {})
        is_seed = portfolio_state.get('_seed_intent', False)

        if is_seed:
            seed_ok, seed_reason = check_seed_eligibility(
                symbol=intent.symbol,
                sector=intent.sector or '',
                sectors=sectors,
                rsi=symbol_info.get('rsi'),
                kelly_pct=symbol_info.get('kelly_pct'),
                signals=symbol_info.get('signals', {}),
            )
            if seed_ok:
                reasons.append(seed_reason)
            else:
                reasons.append(f'REJECTED: Active Sectors < {ACTIVE_MINIMUM} AND Seed Position ineligible: {seed_reason}')
                return False, ' | '.join(reasons)
        else:
            reasons.append(active_reason)
            return False, ' | '.join(reasons)
    else:
        reasons.append(active_reason)

    # ─── Gate 2: Candidate Confirmation ───
    is_seed = portfolio_state.get('_seed_intent', False)
    conf_ok, conf_reason = check_candidate_confirmation(intent.symbol, is_seed=is_seed)
    if not conf_ok:
        reasons.append(conf_reason)
        return False, ' | '.join(reasons)
    reasons.append(conf_reason)

    # ─── Gate 3: Exposure limits ───
    positions = portfolio_state.get('positions', {})
    pos_data = positions.get(intent.symbol, {})
    position_pct = pos_data.get('size_pct', 0)
    sector_name = intent.sector or pos_data.get('sector', '')
    sector_pct = sectors.get(sector_name, 0)
    total_exposure = 1.0 - (portfolio_state.get('cash', 0) / max(portfolio_state.get('equity', 1), 1))

    exp_ok, exp_reason = check_exposure(position_pct, sector_pct, total_exposure)
    if not exp_ok:
        reasons.append(exp_reason)
        return False, ' | '.join(reasons)
    reasons.append(exp_reason)

    # ─── ALL PASSED ───
    return True, 'PASS | ' + ' | '.join(reasons)


def quick_portfolio_snapshot() -> dict:
    """
    Build a portfolio_state dict from live Alpaca data.
    Used by execute_mode to feed into validate_order_intent.
    """
    try:
        from eagle_eye.execution.order_manager import get_portfolio, get_holdings
        from eagle_eye.execution.position_manager import get_sector, load_state

        acct, equity, cash = get_portfolio()
        if not acct:
            return {'equity': 0, 'cash': 0, 'positions': {}, 'sectors': {}}

        holdings = get_holdings()
        state = load_state()

        positions = {}
        sectors = {}
        for h in holdings:
            sym = h['symbol']
            size_pct = h.get('market', 0) / equity if equity > 0 else 0
            sector = get_sector(sym)
            pnl_pct = h.get('pnl_pct', 0)

            positions[sym] = {
                'size_pct': size_pct,
                'sector': sector,
                'pnl_pct': pnl_pct,
                'rsi': None,  # requires analyze() call — skip for speed
            }

            sectors[sector] = sectors.get(sector, 0) + size_pct

        active = sum(1 for w in sectors.values() if w >= 0.03)

        return {
            'equity': equity,
            'cash': cash,
            'positions': positions,
            'sectors': sectors,
            'active_sectors': active,
            'total_holdings': len(holdings),
            'timestamp': datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f'Failed to build portfolio snapshot: {e}')
        return {'equity': 0, 'cash': 0, 'positions': {}, 'sectors': {}, 'error': str(e)}
