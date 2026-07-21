"""
risk/trading_lock.py — 交易锁（V7.1 Phase 2.5）

交易必须自动锁定，如果：
  - 数据库不健康（Database unhealthy）
  - API 不健康（API unhealthy）
  - 市场数据缺失（Market data missing）
  - 市场闭市（Market closed）

此锁不能被绕过。

这是 Constitution 铁律 #2（永不绕过风险引擎）和
Memory Charter「数据缺失时禁止交易」「系统不健康时禁止交易」的执行层实现。

用法：
    from eagle_eye.risk.trading_lock import trading_lock
    if trading_lock.is_locked():
        print(f'锁定原因: {trading_lock.reasons}')
    trading_lock.check(db_healthy=True, api_healthy=True, ...)
"""

from datetime import datetime, timezone
from enum import Enum, auto
from typing import List, Optional

from eagle_eye.core.logger import get_logger

logger = get_logger('risk.lock')


class LockReason(Enum):
    """锁定原因"""
    DATABASE_UNHEALTHY = auto()      # 数据库不可用
    API_UNHEALTHY = auto()           # Alpaca API 不可达
    MARKET_DATA_MISSING = auto()     # 市场数据缺失（VIX/SPY 等）
    MARKET_CLOSED = auto()           # 市场闭市（非交易时段/假日）
    DEGRADED_MODE = auto()           # 降级模式激活
    MANUAL_LOCK = auto()             # 手动锁定


class TradingLock:
    """
    交易锁——强制守卫，不可绕过

    单例——全局共享锁状态。
    每次交易前必须检查 is_locked()。
    如果 locked，无论什么原因都不能交易。
    """

    def __init__(self):
        self._locked = False
        self._reasons: list = []  # List[LockReason]
        self._details: dict = {}  # {LockReason: str}
        self._locked_at: Optional[datetime] = None
        self._last_check_at: Optional[datetime] = None

    # ─── 状态查询 ────────────────────────────────────

    @property
    def is_locked(self) -> bool:
        """是否锁定"""
        return self._locked

    @property
    def reasons(self) -> List[LockReason]:
        """当前锁定原因列表"""
        return list(self._reasons)

    @property
    def details(self) -> dict:
        """锁定详情"""
        return dict(self._details)

    @property
    def locked_at(self) -> Optional[datetime]:
        """锁定时间"""
        return self._locked_at

    def reason_names(self) -> List[str]:
        """锁定原因名称列表"""
        return [r.name for r in self._reasons]

    def reason_text(self) -> str:
        """锁定原因文本（用于日志/通知）"""
        if not self._locked:
            return '未锁定'
        lines = []
        for reason in self._reasons:
            detail = self._details.get(reason, reason.name)
            lines.append(f'  • {detail}')
        return '\n'.join(lines)

    # ─── 全面检查（主要入口） ────────────────────────

    def check(self,
              db_healthy: Optional[bool] = None,
              api_healthy: Optional[bool] = None,
              market_data_healthy: Optional[bool] = None,
              market_open: Optional[bool] = None,
              degraded_active: Optional[bool] = None) -> bool:
        """
        执行全面健康检查，自动更新锁状态

        传入各子系统的健康状态。None = 跳过该检查。

        Args:
            db_healthy: 数据库是否健康
            api_healthy: Alpaca API 是否健康
            market_data_healthy: 市场数据（VIX/SPY）是否可用
            market_open: 市场是否开盘
            degraded_active: 降级模式是否激活

        Returns:
            True 如果系统健康（未锁定），False 如果已锁定
        """
        self._last_check_at = datetime.now(timezone.utc)
        new_reasons = []
        new_details = {}

        if db_healthy is not None and not db_healthy:
            new_reasons.append(LockReason.DATABASE_UNHEALTHY)
            new_details[LockReason.DATABASE_UNHEALTHY] = '数据库连接异常或查询失败'

        if api_healthy is not None and not api_healthy:
            new_reasons.append(LockReason.API_UNHEALTHY)
            new_details[LockReason.API_UNHEALTHY] = 'Alpaca API 不可达（网络/认证/超时）'

        if market_data_healthy is not None and not market_data_healthy:
            new_reasons.append(LockReason.MARKET_DATA_MISSING)
            new_details[LockReason.MARKET_DATA_MISSING] = 'VIX/SPY 等关键市场数据缺失'

        if market_open is not None and not market_open:
            new_reasons.append(LockReason.MARKET_CLOSED)
            new_details[LockReason.MARKET_CLOSED] = '市场当前闭市（非交易时段或假日）'

        if degraded_active is not None and degraded_active:
            new_reasons.append(LockReason.DEGRADED_MODE)
            new_details[LockReason.DEGRADED_MODE] = '降级模式激活（API 连续失败）'

        # 更新锁状态
        was_locked = self._locked
        if new_reasons:
            if not self._locked:
                self._locked = True
                self._locked_at = datetime.now(timezone.utc)
                logger.warning(f'🔒 交易锁定: {[r.name for r in new_reasons]}')
            self._reasons = new_reasons
            self._details = new_details
        else:
            if self._locked:
                self._locked = False
                self._locked_at = None
                logger.info('🔓 交易解锁: 所有检查通过')
            self._reasons = []
            self._details = {}

        if was_locked != self._locked:
            self._log_state_change()

        return not self._locked

    # ─── 单项检查（便捷方法） ─────────────────────────

    def check_database(self, healthy: bool) -> bool:
        """检查数据库并更新锁"""
        if not healthy:
            return self._add_reason(LockReason.DATABASE_UNHEALTHY, '数据库不健康')
        return self._remove_reason(LockReason.DATABASE_UNHEALTHY)

    def check_api(self, healthy: bool) -> bool:
        """检查 API 并更新锁"""
        if not healthy:
            return self._add_reason(LockReason.API_UNHEALTHY, 'Alpaca API 不健康')
        return self._remove_reason(LockReason.API_UNHEALTHY)

    def check_market_data(self, healthy: bool) -> bool:
        """检查市场数据并更新锁"""
        if not healthy:
            return self._add_reason(LockReason.MARKET_DATA_MISSING, '关键市场数据缺失')
        return self._remove_reason(LockReason.MARKET_DATA_MISSING)

    def check_market_open(self, is_open: bool) -> bool:
        """检查市场状态并更新锁"""
        if not is_open:
            return self._add_reason(LockReason.MARKET_CLOSED, '市场闭市')
        return self._remove_reason(LockReason.MARKET_CLOSED)

    def check_degraded_mode(self, is_degraded: bool) -> bool:
        """检查降级模式并更新锁"""
        if is_degraded:
            return self._add_reason(LockReason.DEGRADED_MODE, '降级模式激活')
        return self._remove_reason(LockReason.DEGRADED_MODE)

    # ─── 手动控制 ────────────────────────────────────

    def lock(self, reason: str = '手动锁定'):
        """
        手动锁定（紧急情况）

        添加 MANUAL_LOCK 理由。此锁只能由 unlock() 或 check() 全绿清除。
        """
        self._add_reason(LockReason.MANUAL_LOCK, reason)
        logger.critical(f'🔒 手动锁定: {reason}')

    def unlock(self):
        """
        移除手动锁定

        注意：如果还有其他锁定原因，锁不会完全解开。
        """
        self._remove_reason(LockReason.MANUAL_LOCK)

    def force_unlock(self):
        """
        强制解锁（仅用于紧急恢复）

        ⚠️ 绕过所有安全检查，仅用于已知安全的恢复场景。
        """
        self._locked = False
        self._reasons = []
        self._details = {}
        self._locked_at = None
        logger.critical('⚠️ 强制解锁（所有安全检查已绕过）')

    # ─── 状态摘要 ────────────────────────────────────

    def status_summary(self) -> dict:
        """返回锁状态摘要"""
        return {
            'locked': self._locked,
            'reasons': [r.name for r in self._reasons],
            'details': {r.name: d for r, d in self._details.items()},
            'locked_at': self._locked_at.isoformat() if self._locked_at else None,
            'last_check_at': self._last_check_at.isoformat() if self._last_check_at else None,
        }

    # ─── 内部方法 ────────────────────────────────────

    def _add_reason(self, reason: LockReason, detail: str) -> bool:
        """添加锁定原因"""
        if reason not in self._reasons:
            self._reasons.append(reason)
        self._details[reason] = detail

        if not self._locked:
            self._locked = True
            self._locked_at = datetime.now(timezone.utc)
            logger.warning(f'🔒 交易锁定: {reason.name} — {detail}')

        return False  # 返回 False = 不健康

    def _remove_reason(self, reason: LockReason) -> bool:
        """移除锁定原因"""
        if reason in self._reasons:
            self._reasons.remove(reason)
            self._details.pop(reason, None)

        if not self._reasons:
            if self._locked:
                self._locked = False
                self._locked_at = None
                logger.info('🔓 交易解锁')

        return reason not in self._reasons  # True = 该检查已通过

    def _log_state_change(self):
        """记录状态变更"""
        if self._locked:
            logger.warning(
                f'交易锁已激活 | 原因: {", ".join(r.name for r in self._reasons)}'
            )
        else:
            logger.info('交易锁已解除 — 所有系统健康')


# ─── 全局单例 ───────────────────────────────────────
trading_lock = TradingLock()
