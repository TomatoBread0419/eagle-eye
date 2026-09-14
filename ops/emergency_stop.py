"""
ops/emergency_stop.py — 紧急停止 (V7.1 RC1)

Global kill switch. When activated:
  ❌ Block: new positions, adding to positions
  ✅ Allow: stop-loss exits, risk reduction

Triggered by:
  - Owner (manual CLI)
  - Watchdog CRITICAL alerts
  - Health Check UNHEALTHY status
  - Manual CLI flag

States: NORMAL → EMERGENCY
Once in EMERGENCY, requires manual reset to return to NORMAL.
Integrated with trading_lock — automatic lock propagation.

Usage:
    from eagle_eye.ops.emergency_stop import emergency_stop
    emergency_stop.activate('Watchdog detected API failure spike')
    if emergency_stop.active:
        # block all buys, allow exits only

Constitution: Capital preservation #1. Observer until triggered, then enforcer.
"""

import os
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Optional, List

from eagle_eye.core.logger import get_logger

logger = get_logger('ops.estop')


class EstopState(Enum):
    """紧急停止状态"""
    NORMAL = auto()        # 正常运行
    EMERGENCY = auto()     # 紧急停止
    RECOVERING = auto()    # 恢复验证中（未使用，保留）


class EmergencyStop:
    """
    紧急停止管理器

    Singleton. Global kill switch.
    When active, blocks all new positions and additions.
    Always allows exits and risk reduction.
    """

    def __init__(self):
        self._state = EstopState.NORMAL
        self._activated_at: Optional[datetime] = None
        self._activated_by: str = ''
        self._reason: str = ''
        self._trigger_source: str = ''

    # ─── 状态查询 ────────────────────────────────────

    @property
    def active(self) -> bool:
        """紧急停止是否激活"""
        return self._state == EstopState.EMERGENCY

    @property
    def state(self) -> EstopState:
        """当前状态"""
        return self._state

    @property
    def activated_at(self) -> Optional[datetime]:
        """紧急停止激活时间"""
        return self._activated_at

    @property
    def activated_by(self) -> str:
        """谁激活的"""
        return self._activated_by

    @property
    def reason(self) -> str:
        """激活原因"""
        return self._reason

    @property
    def trigger_source(self) -> str:
        """触发来源"""
        return self._trigger_source

    def is_normal(self) -> bool:
        """是否正常运行"""
        return self._state == EstopState.NORMAL

    # ─── 操作权限 ────────────────────────────────────

    def can_open_position(self, symbol: str) -> bool:
        """是否允许新建仓位"""
        if self._state == EstopState.NORMAL:
            return True
        logger.warning(f'🛑 紧急停止: 拒绝新仓位 {symbol}')
        return False

    def can_add_position(self, symbol: str) -> bool:
        """是否允许加仓"""
        if self._state == EstopState.NORMAL:
            return True
        logger.warning(f'🛑 紧急停止: 拒绝加仓 {symbol}')
        return False

    def can_exit_position(self, symbol: str) -> bool:
        """是否允许退出 — 始终允许"""
        return True

    def can_reduce_position(self, symbol: str) -> bool:
        """是否允许减仓 — 始终允许"""
        return True

    def can_modify_stops(self) -> bool:
        """是否允许修改止损 — 始终允许（保护资本）"""
        return True

    # ─── 激活 / 重置 ─────────────────────────────────

    def activate(self, reason: str = 'manual',
                 source: str = 'owner',
                 triggered_by: str = 'unknown') -> bool:
        """
        激活紧急停止

        Args:
            reason: 激活原因（人类可读）
            source: 触发来源 (owner/watchdog/health_check/manual)
            triggered_by: 具体触发者标识

        Returns:
            True 如果成功激活
        """
        if self._state == EstopState.EMERGENCY:
            logger.warning(f'🛑 紧急停止已激活，忽略重复请求: {reason}')
            return False

        self._state = EstopState.EMERGENCY
        self._activated_at = datetime.now(timezone.utc)
        self._reason = reason
        self._trigger_source = source
        self._activated_by = triggered_by

        # 同步到 trading_lock
        self._propagate_to_lock()

        # 记录到 audit_log
        self._log_estop_event('ACTIVATED', reason, source)

        logger.critical(f'🛑🛑🛑 紧急停止激活 🛑🛑🛑')
        logger.critical(f'   原因: {reason}')
        logger.critical(f'   触发: {source} ({triggered_by})')
        logger.critical(f'   规则: 禁止新仓位/加仓，允许止损/减仓')
        logger.critical(f'   时间: {self._activated_at.isoformat()}')

        return True

    def reset(self, reason: str = 'manual override') -> bool:
        """
        重置紧急停止（恢复 NORMAL）

        要求手动重置 — 不会自动恢复。

        Args:
            reason: 重置原因

        Returns:
            True 如果成功重置
        """
        if self._state == EstopState.NORMAL:
            logger.info('紧急停止未激活，无需重置')
            return False

        was_active_since = self._activated_at
        was_reason = self._reason

        self._state = EstopState.NORMAL
        self._activated_at = None
        self._reason = ''
        self._trigger_source = ''
        self._activated_by = ''

        # 同步到 trading_lock
        self._propagate_to_lock()

        # 记录
        self._log_estop_event('RESET', reason, 'manual')

        duration = ''
        if was_active_since:
            delta = datetime.now(timezone.utc) - was_active_since
            hours = delta.total_seconds() / 3600
            duration = f' (持续 {hours:.1f}h)'

        logger.critical(f'✅ 紧急停止已重置{duration}')
        logger.critical(f'   原因: {reason}')
        logger.critical(f'   之前停止原因: {was_reason}')

        return True

    # ─── 自动触发（来自 watchdog / health_check） ────

    def check_watchdog_trigger(self, watchdog_result: dict):
        """
        检查 watchdog 扫描结果，自动触发紧急停止

        Args:
            watchdog_result: full_watchdog_scan() 的返回结果
        """
        if watchdog_result.get('status') == 'CRITICAL':
            crit_alerts = [a for a in watchdog_result.get('alerts', [])
                          if a.get('severity') == 'CRITICAL']
            reasons = '; '.join(a.get('message', '')[:100] for a in crit_alerts[:3])
            self.activate(
                reason=f'Watchdog CRITICAL ({len(crit_alerts)} alerts): {reasons}',
                source='watchdog',
                triggered_by='auto',
            )

    def check_health_trigger(self, health_result: dict):
        """
        检查健康报告，自动触发紧急停止

        Args:
            health_result: full_health_report() 的返回结果
        """
        if health_result.get('overall') == 'UNHEALTHY':
            failures = []
            for check in ['database', 'api', 'data_freshness', 'system']:
                if not health_result.get(check, {}).get('healthy', True):
                    failures.append(check)
            self.activate(
                reason=f'Health Check UNHEALTHY: {", ".join(failures)}',
                source='health_check',
                triggered_by='auto',
            )

    # ─── 状态摘要 ────────────────────────────────────

    def status_summary(self) -> dict:
        """紧急停止状态摘要"""
        return {
            'state': self._state.name,
            'active': self.active,
            'activated_at': self._activated_at.isoformat() if self._activated_at else None,
            'activated_by': self._activated_by,
            'reason': self._reason or 'N/A',
            'trigger_source': self._trigger_source,
            'rules': {
                'can_open_positions': not self.active,
                'can_add_positions': not self.active,
                'can_exit_positions': True,
                'can_reduce_positions': True,
                'can_modify_stops': True,
            },
        }

    # ─── 内部方法 ────────────────────────────────────

    def _propagate_to_lock(self):
        """同步状态到 trading_lock"""
        try:
            from eagle_eye.risk.trading_lock import trading_lock
            if self.active:
                trading_lock.lock(
                    f'紧急停止: {self._reason[:80]}'
                )
            else:
                trading_lock.unlock()
        except ImportError:
            pass  # trading_lock 不可用

    def _log_estop_event(self, event: str, reason: str, source: str):
        """记录紧急停止事件到审计日志"""
        try:
            from eagle_eye.ops.audit_engine import log_event
            log_event(
                event_type='EMERGENCY_STOP',
                severity='CRITICAL' if event == 'ACTIVATED' else 'INFO',
                source=f'emergency_stop.{event}',
                details={
                    'event': event,
                    'reason': reason,
                    'source': source,
                    'state': self._state.name,
                },
            )
        except ImportError:
            pass


# ─── 全局单例 ───────────────────────────────────────
emergency_stop = EmergencyStop()


# ─── CLI ────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='V7.1 紧急停止')
    parser.add_argument('action', choices=['activate', 'reset', 'status'],
                       help='操作')
    parser.add_argument('--reason', type=str, default='manual CLI',
                       help='原因')
    args = parser.parse_args()

    if args.action == 'activate':
        emergency_stop.activate(reason=args.reason, source='manual_cli',
                                triggered_by='owner')
        print('🛑 紧急停止已激活')
    elif args.action == 'reset':
        emergency_stop.reset(reason=args.reason)
        print('✅ 紧急停止已重置')
    elif args.action == 'status':
        import json
        print(json.dumps(emergency_stop.status_summary(),
                        indent=2, ensure_ascii=False))
