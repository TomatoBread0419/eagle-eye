"""
execution/order_state_machine.py — 订单状态机（V7.1 Phase 2.5）

订单生命周期状态：
  PENDING     — 已创建，等待验证
  VALIDATING  — 正在验证（业务规则 + 风控 + 降级模式）
  APPROVED    — 已通过所有检查，等待提交到 broker
  SUBMITTED   — 已发送到 Alpaca，等待成交
  FILLED      — 已成交
  COMPLETED   — 已完成（结算确认）
  FAILED      — 失败（被拒绝/API 错误/超时）
  CANCELLED   — 已取消

状态转换规则：
  PENDING → VALIDATING → APPROVED → SUBMITTED → FILLED → COMPLETED
                          ↓                       ↓
                       REJECTED                 FAILED
  PENDING → CANCELLED（执行前取消）

每个状态转换都记录时间戳和原因，确保完全可追溯。

这是 Constitution 铁律 #3（永不执行未知订单）和
铁律 #10（始终创建审计日志）的执行层实现。

用法：
    from eagle_eye.execution.order_state_machine import OrderStateMachine, OrderState
    oms = OrderStateMachine()
    order = oms.create_order(intent)
    oms.transition(order.id, OrderState.VALIDATING)
    if oms.can_transition(order.id, OrderState.APPROVED):
        oms.transition(order.id, OrderState.APPROVED)
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, List, Any

from eagle_eye.core.logger import get_logger
from eagle_eye.execution.order_intent import OrderIntent

logger = get_logger('execution.oms')


# ════════════════════════════════════════════════════
# 状态定义
# ════════════════════════════════════════════════════

class OrderState(Enum):
    """订单状态"""
    PENDING = 'PENDING'            # 已创建，等待验证
    VALIDATING = 'VALIDATING'      # 正在验证中
    APPROVED = 'APPROVED'          # 已通过所有检查
    SUBMITTED = 'SUBMITTED'        # 已提交到 Alpaca
    FILLED = 'FILLED'              # 已成交
    COMPLETED = 'COMPLETED'        # 已完成（结算确认）
    FAILED = 'FAILED'              # 失败
    CANCELLED = 'CANCELLED'        # 已取消


# ════════════════════════════════════════════════════
# 合法状态转换表
# ════════════════════════════════════════════════════

_ALLOWED_TRANSITIONS: Dict[OrderState, List[OrderState]] = {
    OrderState.PENDING: [
        OrderState.VALIDATING,
        OrderState.CANCELLED,  # 可在验证前取消
    ],
    OrderState.VALIDATING: [
        OrderState.APPROVED,
        OrderState.FAILED,     # 验证失败
        OrderState.CANCELLED,  # 验证中取消
    ],
    OrderState.APPROVED: [
        OrderState.SUBMITTED,
        OrderState.CANCELLED,  # 提交前取消
    ],
    OrderState.SUBMITTED: [
        OrderState.FILLED,
        OrderState.FAILED,     # 提交失败/被拒
    ],
    OrderState.FILLED: [
        OrderState.COMPLETED,
    ],
    OrderState.COMPLETED: [],  # 终态
    OrderState.FAILED: [],     # 终态
    OrderState.CANCELLED: [],  # 终态
}

# 终态集合
_TERMINAL_STATES = {OrderState.COMPLETED, OrderState.FAILED, OrderState.CANCELLED}


# ════════════════════════════════════════════════════
# 订单记录
# ════════════════════════════════════════════════════

class OrderRecord:
    """
    单个订单的完整生命周期记录

    包含：
    - 原始 OrderIntent
    - 当前状态
    - 状态转换历史（审计日志）
    - Alpaca 订单 ID（提交后）
    """

    def __init__(self, intent: OrderIntent):
        self.id: str = str(uuid.uuid4())[:12]  # 短 ID
        self.intent: OrderIntent = intent
        self.state: OrderState = OrderState.PENDING
        self.alpaca_order_id: Optional[str] = None
        self.alpaca_order_data: Optional[dict] = None
        self.transitions: List[dict] = []  # 转换历史
        self.created_at: datetime = datetime.now(timezone.utc)
        self.updated_at: datetime = self.created_at
        self.error_message: Optional[str] = None

        # 记录初始状态
        self._record_transition(None, OrderState.PENDING, '订单创建')

    def _record_transition(self, from_state: Optional[OrderState],
                           to_state: OrderState, reason: str = ''):
        """记录一次状态转换"""
        entry = {
            'from': from_state.value if from_state else None,
            'to': to_state.value,
            'reason': reason,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
        self.transitions.append(entry)
        self.updated_at = datetime.now(timezone.utc)
        self.state = to_state

    def is_terminal(self) -> bool:
        """是否处于终态"""
        return self.state in _TERMINAL_STATES

    def is_success(self) -> bool:
        """是否成功完成"""
        return self.state == OrderState.COMPLETED

    def can_transition_to(self, target: OrderState) -> bool:
        """是否可以转换到目标状态"""
        allowed = _ALLOWED_TRANSITIONS.get(self.state, [])
        return target in allowed and not self.is_terminal()

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'symbol': self.intent.symbol,
            'side': self.intent.side.value,
            'qty': self.intent.qty,
            'order_type': self.intent.order_type.value,
            'state': self.state.value,
            'is_terminal': self.is_terminal(),
            'alpaca_order_id': self.alpaca_order_id,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'transitions': self.transitions,
            'reason': self.intent.reason,
        }


# ════════════════════════════════════════════════════
# 状态机
# ════════════════════════════════════════════════════

class OrderStateMachine:
    """
    订单状态机

    管理所有订单的生命周期。
    每次状态转换都记录时间戳和原因，确保完全可追溯。
    """

    def __init__(self):
        self._orders: Dict[str, OrderRecord] = {}

    # ─── 订单创建 ────────────────────────────────────

    def create_order(self, intent: OrderIntent) -> OrderRecord:
        """
        从 OrderIntent 创建订单记录

        Args:
            intent: 已验证的订单意图

        Returns:
            新创建的 OrderRecord
        """
        record = OrderRecord(intent)
        self._orders[record.id] = record
        logger.debug(
            f'创建订单 {record.id}: {intent.side.value} {intent.symbol} '
            f'x{intent.qty} {intent.order_type.value}'
        )
        return record

    # ─── 状态转换 ────────────────────────────────────

    def can_transition(self, order_id: str, target: OrderState) -> bool:
        """
        检查订单是否可以转换到目标状态

        Args:
            order_id: 订单 ID
            target: 目标状态

        Returns:
            True 如果允许转换
        """
        record = self._orders.get(order_id)
        if not record:
            logger.error(f'订单不存在: {order_id}')
            return False
        return record.can_transition_to(target)

    def transition(self, order_id: str, target: OrderState,
                   reason: str = '', **kwargs) -> OrderRecord:
        """
        执行状态转换

        Args:
            order_id: 订单 ID
            target: 目标状态
            reason: 转换原因
            **kwargs: 附加数据（如 alpaca_order_id, error_message 等）

        Returns:
            更新后的 OrderRecord

        Raises:
            ValueError: 如果转换不合法
        """
        record = self._orders.get(order_id)
        if not record:
            raise ValueError(f'订单不存在: {order_id}')

        if not self.can_transition(order_id, target):
            msg = (
                f'非法状态转换: {record.state.value} → {target.value} '
                f'(订单 {order_id}: {record.intent.symbol})'
            )
            logger.error(msg)
            raise ValueError(msg)

        old_state = record.state
        record._record_transition(old_state, target, reason)

        # 更新附加字段
        if 'alpaca_order_id' in kwargs:
            record.alpaca_order_id = kwargs['alpaca_order_id']
        if 'alpaca_order_data' in kwargs:
            record.alpaca_order_data = kwargs['alpaca_order_data']
        if 'error_message' in kwargs:
            record.error_message = kwargs['error_message']

        log_level = 'WARNING' if target in (OrderState.FAILED, OrderState.CANCELLED) else 'INFO'
        getattr(logger, log_level.lower())(
            f'状态转换 {order_id}: {old_state.value} → {target.value} '
            f'({record.intent.symbol} {record.intent.side.value} x{record.intent.qty})'
            + (f' | {reason}' if reason else '')
        )

        return record

    # ─── 批量操作 ────────────────────────────────────

    def transition_all(self, target: OrderState, reason: str = '') -> int:
        """
        将所有未完成的订单批量转换到目标状态

        Args:
            target: 目标状态
            reason: 转换原因

        Returns:
            成功转换的订单数
        """
        count = 0
        for record in list(self._orders.values()):
            if not record.is_terminal() and record.can_transition_to(target):
                try:
                    self.transition(record.id, target, reason)
                    count += 1
                except ValueError:
                    pass
        return count

    def cancel_all_pending(self, reason: str = '批量取消') -> int:
        """
        取消所有未完成的订单

        Args:
            reason: 取消原因

        Returns:
            成功取消的订单数
        """
        count = 0
        for record in list(self._orders.values()):
            if not record.is_terminal():
                if record.can_transition_to(OrderState.CANCELLED):
                    try:
                        self.transition(record.id, OrderState.CANCELLED, reason)
                        count += 1
                    except ValueError:
                        pass
        return count

    # ─── 查询 ────────────────────────────────────────

    def get_order(self, order_id: str) -> Optional[OrderRecord]:
        """获取单个订单"""
        return self._orders.get(order_id)

    def get_orders_by_state(self, state: OrderState) -> List[OrderRecord]:
        """获取指定状态的所有订单"""
        return [r for r in self._orders.values() if r.state == state]

    def get_pending_orders(self) -> List[OrderRecord]:
        """获取所有未完成的订单"""
        return [r for r in self._orders.values() if not r.is_terminal()]

    def get_orders_by_symbol(self, symbol: str) -> List[OrderRecord]:
        """获取指定标的的所有订单"""
        return [r for r in self._orders.values() if r.intent.symbol == symbol]

    def get_active_buys(self) -> List[OrderRecord]:
        """获取所有未完成的买单"""
        return [
            r for r in self._orders.values()
            if not r.is_terminal() and r.intent.side.value == 'buy'
        ]

    def get_active_sells(self) -> List[OrderRecord]:
        """获取所有未完成的卖单"""
        return [
            r for r in self._orders.values()
            if not r.is_terminal() and r.intent.side.value == 'sell'
        ]

    # ─── 统计 ────────────────────────────────────────

    def stats(self) -> dict:
        """订单统计"""
        total = len(self._orders)
        by_state = {}
        for record in self._orders.values():
            state_name = record.state.value
            by_state[state_name] = by_state.get(state_name, 0) + 1

        terminal = sum(1 for r in self._orders.values() if r.is_terminal())
        success = sum(1 for r in self._orders.values() if r.is_success())

        return {
            'total': total,
            'by_state': by_state,
            'terminal': terminal,
            'success': success,
            'failure': by_state.get(OrderState.FAILED.value, 0),
            'cancelled': by_state.get(OrderState.CANCELLED.value, 0),
            'pending_count': total - terminal,
        }

    # ─── 清理 ────────────────────────────────────────

    def prune_completed(self, keep_hours: int = 24):
        """
        清理已完成/失败/取消的订单（保留最近 N 小时）

        Args:
            keep_hours: 保留多少小时内的终态订单
        """
        cutoff = datetime.now(timezone.utc)
        to_remove = []
        for order_id, record in self._orders.items():
            if record.is_terminal():
                age_hours = (datetime.now(timezone.utc) - record.updated_at).total_seconds() / 3600
                if age_hours > keep_hours:
                    to_remove.append(order_id)

        for order_id in to_remove:
            del self._orders[order_id]

        if to_remove:
            logger.debug(f'清理了 {len(to_remove)} 个旧订单（保留 {keep_hours}h）')


# ─── 全局单例 ───────────────────────────────────────
_order_state_machine: Optional[OrderStateMachine] = None


def get_order_state_machine() -> OrderStateMachine:
    """获取 OrderStateMachine 单例"""
    global _order_state_machine
    if _order_state_machine is None:
        _order_state_machine = OrderStateMachine()
    return _order_state_machine
