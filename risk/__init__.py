"""
risk/ — 风控层

V7.1 Phase 2.5: 降级模式 + 交易锁。
V7.1 P0: Policy Validator + Dashboard Gate.
Constitution 铁律 #2: 永不绕过风险引擎。
"""

from eagle_eye.risk.degraded_mode import DegradedMode, DegradedState, degraded_mode
from eagle_eye.risk.trading_lock import TradingLock, LockReason, trading_lock
from eagle_eye.risk.policy_validator import (
    validate_order_intent,
    check_dashboard_gate,
    check_active_sectors,
    check_exposure,
    check_candidate_confirmation,
    check_seed_eligibility,
    quick_portfolio_snapshot,
)

__all__ = [
    'DegradedMode', 'DegradedState', 'degraded_mode',
    'TradingLock', 'LockReason', 'trading_lock',
    'validate_order_intent',
    'check_dashboard_gate',
    'check_active_sectors',
    'check_exposure',
    'check_candidate_confirmation',
    'check_seed_eligibility',
    'quick_portfolio_snapshot',
]
