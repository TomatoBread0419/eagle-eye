"""
ops/shadow_mode.py — 影子模式 (V7.1 RC1)

Paper trading safety net. When enabled:
  - OrderIntents are generated normally (full decision pipeline)
  - Orders are NEVER submitted to Alpaca
  - All simulated actions are logged to audit_engine + SQLite

This allows full system testing without real capital at risk.
Enables: strategy validation, behavior fingerprinting, regression testing.

Toggle: environment variable EAGLE_SHADOW_MODE=true or cfg.shadow_mode

Usage:
    from eagle_eye.ops.shadow_mode import shadow_mode
    if shadow_mode.enabled:
        shadow_mode.log_order(intent)  # log but DON'T submit
    else:
        broker.place_order(...)        # real execution

Constitution: Observer only. Never submits orders. Never modifies trading state.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

from eagle_eye.core.config import cfg
from eagle_eye.core.logger import get_logger

logger = get_logger('ops.shadow')


class ShadowMode:
    """
    影子模式管理器

    Singleton. When enabled, intercepts all order submissions.
    Never modifies trading state — only logs.
    """

    def __init__(self):
        self._enabled = self._detect_enabled()
        self._simulated_count: int = 0
        self._simulated_since: Optional[datetime] = None

    @property
    def enabled(self) -> bool:
        """是否启用影子模式"""
        return self._enabled

    @property
    def simulated_count(self) -> int:
        """已模拟的订单数"""
        return self._simulated_count

    @property
    def simulated_since(self) -> Optional[datetime]:
        """影子模式启用时间"""
        return self._simulated_since

    def enable(self, reason: str = 'manual'):
        """
        启用影子模式

        Args:
            reason: 启用原因
        """
        if not self._enabled:
            self._enabled = True
            self._simulated_since = datetime.now(timezone.utc)
            self._simulated_count = 0
            logger.critical(f'👻 影子模式启用: {reason}')
            self._log_shadow_event('ENABLED', reason=reason)

    def disable(self, reason: str = 'manual'):
        """
        禁用影子模式（恢复真实交易）

        Args:
            reason: 禁用原因
        """
        if self._enabled:
            total = self._simulated_count
            since = self._simulated_since
            self._enabled = False
            self._simulated_since = None
            logger.critical(
                f'✅ 影子模式禁用: {reason} '
                f'(期间模拟 {total} 笔订单'
                + (f', {self._format_duration(since)}' if since else '')
                + ')'
            )
            self._log_shadow_event('DISABLED', reason=reason)

    def log_order(self, intent) -> dict:
        """
        记录一笔影子订单（不提交到 Alpaca）

        Args:
            intent: OrderIntent 对象

        Returns:
            {'simulated': True, 'intent_id': ..., 'details': ...}
        """
        self._simulated_count += 1

        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'simulated': True,
            'symbol': intent.symbol,
            'side': intent.side.value,
            'qty': intent.qty,
            'order_type': intent.order_type.value,
            'limit_price': intent.limit_price,
            'stop_price': intent.stop_price,
            'time_in_force': intent.time_in_force,
            'reason': intent.reason,
            'decision_source': intent.decision_source,
            'sector': intent.sector,
            'status': 'SIMULATED',
            'would_have_been': 'submitted_to_alpaca',
        }

        # Log to audit engine
        self._log_shadow_event(
            'ORDER_SIMULATED',
            symbol=intent.symbol,
            details=entry,
        )

        logger.info(
            f'👻 [SHADOW #{self._simulated_count}] '
            f'{intent.side.value} {intent.symbol} x{intent.qty} '
            f'{intent.order_type.value}'
            + (f' @ ${intent.limit_price:.2f}' if intent.limit_price else '')
            + (f' | {intent.reason[:60]}' if intent.reason else '')
        )

        return entry

    def log_batch(self, intents: list) -> list:
        """
        记录一批影子订单

        Args:
            intents: OrderIntent 列表

        Returns:
            [entry, ...]
        """
        return [self.log_order(i) for i in intents]

    def status_summary(self) -> dict:
        """影子模式状态摘要"""
        return {
            'enabled': self._enabled,
            'simulated_count': self._simulated_count,
            'simulated_since': (
                self._simulated_since.isoformat()
                if self._simulated_since else None
            ),
            'mode': 'SHADOW' if self._enabled else 'LIVE',
        }

    # ─── 内部方法 ────────────────────────────────────

    @staticmethod
    def _detect_enabled() -> bool:
        """检测是否应启用影子模式"""
        # 1. 环境变量
        if os.environ.get('EAGLE_SHADOW_MODE', '').lower() in ('true', '1', 'yes'):
            return True
        # 2. 配置文件
        try:
            if cfg.get('EAGLE_SHADOW_MODE', '').lower() in ('true', '1', 'yes'):
                return True
        except Exception:
            pass
        # 3. 默认：禁用
        return False

    def _log_shadow_event(self, event: str, symbol: str = None,
                          reason: str = '', details: dict = None):
        """记录影子模式事件到审计日志"""
        try:
            from eagle_eye.ops.audit_engine import log_event
            log_event(
                event_type='SHADOW_MODE',
                severity='INFO',
                source=f'shadow_mode.{event}',
                symbol=symbol,
                details={
                    'shadow_event': event,
                    'reason': reason,
                    'simulated_count': self._simulated_count,
                    **(details or {}),
                },
            )
        except ImportError:
            pass  # audit_engine not available — log only

    @staticmethod
    def _format_duration(since: datetime) -> str:
        """格式化持续时间"""
        delta = datetime.now(timezone.utc) - since
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f'{delta.total_seconds() / 60:.0f}min'
        elif hours < 24:
            return f'{hours:.1f}h'
        return f'{hours / 24:.1f}d'


# ─── 全局单例 ───────────────────────────────────────
shadow_mode = ShadowMode()
