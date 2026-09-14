"""
risk/degraded_mode.py — 降级模式（V7.1 Phase 2.5）

API 连续 4 次失败 → 进入降级模式。
降级模式规则：
  - 禁止新建仓位（no new positions）
  - 禁止加仓（no adding to existing positions）
  - 允许止损退出（allow stop-loss exits）
  - 允许减仓（allow reducing positions）

这是 Constitution 铁律 #12（始终保护资本优先）和
Memory Charter「系统不健康时禁止交易」的执行层实现。

用法：
    from eagle_eye.risk.degraded_mode import degraded_mode
    if degraded_mode.is_degraded():
        if degraded_mode.can_exit('AAPL'):
            ...  # 允许卖出
        if degraded_mode.can_open('NVDA', side='buy'):
            ...  # 会被拒绝
"""

from datetime import datetime, timezone
from enum import Enum, auto
from typing import Optional

from eagle_eye.core.logger import get_logger

logger = get_logger('risk.degraded')

# ─── 降级触发阈值 ────────────────────────────────────
_DEGRADED_FAILURE_THRESHOLD = 4  # 连续 4 次 API 失败


class DegradedState(Enum):
    """系统状态"""
    NORMAL = auto()       # 正常运行
    DEGRADED = auto()     # 降级模式（API 连续失败）
    RECOVERING = auto()   # 恢复中（API 恢复但仍需验证）


class DegradedMode:
    """
    降级模式管理器

    单例——全局共享降级状态。
    不修改任何交易逻辑，仅提供查询接口。
    """

    def __init__(self):
        self._state = DegradedState.NORMAL
        self._entered_at: Optional[datetime] = None
        self._recovered_at: Optional[datetime] = None
        self._recovery_checks: int = 0
        self._recovery_check_threshold = 3  # 恢复后需 3 次成功验证才退出降级
        self._reason: str = ''

    # ─── 状态查询 ────────────────────────────────────

    @property
    def state(self) -> DegradedState:
        """当前状态"""
        return self._state

    @property
    def entered_at(self) -> Optional[datetime]:
        """进入降级模式的时间"""
        return self._entered_at

    @property
    def reason(self) -> str:
        """进入降级模式的原因"""
        return self._reason

    def is_degraded(self) -> bool:
        """是否处于降级模式"""
        return self._state == DegradedState.DEGRADED

    def is_recovering(self) -> bool:
        """是否处于恢复验证中"""
        return self._state == DegradedState.RECOVERING

    def is_normal(self) -> bool:
        """是否正常运行"""
        return self._state == DegradedState.NORMAL

    # ─── 操作权限查询（降级模式下的买卖约束）────────

    def can_open_position(self, symbol: str, side: str = 'buy') -> bool:
        """
        是否允许新建仓位

        降级模式下：拒绝所有 buy，允许所有 sell
        """
        if self._state == DegradedState.NORMAL:
            return True
        if self._state == DegradedState.DEGRADED:
            if side == 'sell':
                return True  # 允许退出
            logger.warning(f'降级模式: 拒绝新仓位 {side} {symbol}')
            return False
        # RECOVERING: 允许所有操作（API 已验证恢复）
        return True

    def can_add_position(self, symbol: str) -> bool:
        """
        是否允许加仓已有持仓

        降级模式下：拒绝
        """
        if self._state == DegradedState.NORMAL:
            return True
        if self._state == DegradedState.DEGRADED:
            logger.warning(f'降级模式: 拒绝加仓 {symbol}')
            return False
        return True

    def can_exit_position(self, symbol: str) -> bool:
        """
        是否允许退出持仓

        降级模式下：允许（保护资本，必须能止损）
        """
        # 即使在 DEGRADED 状态下也允许退出
        # 资本保全 > 一切
        return True

    def can_reduce_position(self, symbol: str, current_qty: int,
                            reduce_qty: int) -> bool:
        """
        是否允许减仓（部分卖出）

        降级模式下：允许（减仓 = 降低风险）
        """
        if self._state == DegradedState.NORMAL:
            return True
        if self._state == DegradedState.DEGRADED:
            if reduce_qty < current_qty:
                return True  # 减仓允许
            if reduce_qty == current_qty:
                return True  # 全仓退出也允许
            logger.warning(f'降级模式: 拒绝加仓 (sell {reduce_qty} > current {current_qty})')
            return False
        return True

    # ─── 状态转换 ────────────────────────────────────

    def check_and_update(self, api_failure_count: int) -> bool:
        """
        根据 API 失败计数检查并更新状态

        Args:
            api_failure_count: 当前 API 连续失败次数（来自 AlpacaClient）

        Returns:
            True 如果状态发生了变化
        """
        changed = False

        if self._state == DegradedState.NORMAL:
            if api_failure_count >= _DEGRADED_FAILURE_THRESHOLD:
                self._enter_degraded()
                changed = True

        elif self._state == DegradedState.DEGRADED:
            if api_failure_count == 0:
                self._enter_recovering()
                changed = True

        elif self._state == DegradedState.RECOVERING:
            if api_failure_count == 0:
                self._recovery_checks += 1
                if self._recovery_checks >= self._recovery_check_threshold:
                    self._exit_recovering()
                    changed = True
            else:
                # 恢复期间又失败了 → 回到降级
                logger.warning(f'恢复验证失败 (attempt {self._recovery_checks + 1})')
                self._enter_degraded()
                changed = True

        return changed

    def force_degraded(self, reason: str = 'manual'):
        """
        强制进入降级模式（手动或 trading_lock 触发）
        """
        if self._state != DegradedState.DEGRADED:
            self._state = DegradedState.DEGRADED
            self._entered_at = datetime.now(timezone.utc)
            self._reason = reason
            self._recovery_checks = 0
            logger.critical(f'强制降级模式: {reason}')

    def force_normal(self):
        """
        强制恢复正常模式
        """
        if self._state != DegradedState.NORMAL:
            self._state = DegradedState.NORMAL
            self._entered_at = None
            self._recovered_at = datetime.now(timezone.utc)
            self._reason = ''
            self._recovery_checks = 0
            logger.info('强制恢复正常模式')

    # ─── 内部方法 ────────────────────────────────────

    def _enter_degraded(self):
        """进入降级模式"""
        self._state = DegradedState.DEGRADED
        self._entered_at = datetime.now(timezone.utc)
        self._reason = f'API 连续 {_DEGRADED_FAILURE_THRESHOLD} 次失败'
        self._recovery_checks = 0
        logger.critical(f'⚠️ 进入降级模式: {self._reason}')
        logger.critical('   规则: 禁止新仓位/加仓，允许止损退出/减仓')
        # Log to audit_log for heartbeat detection
        try:
            from eagle_eye.storage.db import db
            import json
            db.execute(
                "INSERT INTO audit_log (event_type, severity, source, details) VALUES (?,?,?,?)",
                ('degraded_mode', 'WARNING', 'degraded_mode',
                 json.dumps({'active': True, 'reason': self._reason, 'entered_at': self._entered_at.isoformat()}))
            )
            db.commit()
        except Exception:
            pass
        # V7.1.1: Immediate notification via spool
        try:
            from eagle_eye.ops.notification import on_degraded_enter
            on_degraded_enter(self._reason)
        except Exception:
            pass

    def _enter_recovering(self):
        """进入恢复验证"""
        self._state = DegradedState.RECOVERING
        self._reason = 'API 恢复，验证中...'
        self._recovery_checks = 0
        logger.info(f'🔄 进入恢复验证模式 (需 {self._recovery_check_threshold} 次连续成功)')

    def _exit_recovering(self):
        """退出恢复验证 → 正常模式"""
        self._state = DegradedState.NORMAL
        self._recovered_at = datetime.now(timezone.utc)
        self._reason = ''
        logger.info(f'✅ 恢复正常模式 (经过 {self._recovery_check_threshold} 次验证)')
        # Log recovery to audit_log
        try:
            from eagle_eye.storage.db import db
            import json
            db.execute(
                "INSERT INTO audit_log (event_type, severity, source, details) VALUES (?,?,?,?)",
                ('degraded_mode', 'INFO', 'degraded_mode',
                 json.dumps({'active': False, 'recovered_at': self._recovered_at.isoformat()}))
            )
            db.commit()
        except Exception:
            pass
        # V7.1.1: Immediate notification
        try:
            from eagle_eye.ops.notification import on_degraded_exit
            on_degraded_exit()
        except Exception:
            pass

    # ─── 状态摘要 ────────────────────────────────────

    def status_summary(self) -> dict:
        """返回降级模式状态摘要"""
        return {
            'state': self._state.name,
            'is_degraded': self.is_degraded(),
            'is_recovering': self.is_recovering(),
            'entered_at': self._entered_at.isoformat() if self._entered_at else None,
            'reason': self._reason or 'N/A',
            'recovery_checks': self._recovery_checks,
            'rules': {
                'can_open_positions': self.can_open_position('*'),
                'can_add_positions': self.can_add_position('*'),
                'can_exit_positions': True,
                'can_reduce_positions': True,
            },
        }


# ─── 全局单例 ───────────────────────────────────────
degraded_mode = DegradedMode()
