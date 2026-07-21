"""
execution/order_intent.py — OrderIntent 对象（V7.1 Phase 2.5）

交易流程：
  Decision（决策）
    ↓
  OrderIntent（订单意图）
    ↓
  Safety Check（安全检查）
    ↓
  Execution（执行）
    ↓
  Broker（券商）

OrderIntent 是决策层和执行层之间的契约对象。
它包含交易意图的完整信息，但不直接操作 API。

这是 Constitution 铁律 #3（永不执行未知订单）的执行层实现
——每个订单在到达 broker 之前必须经过 Safety Check。

用法：
    from eagle_eye.execution.order_intent import OrderIntent, OrderSide, OrderType
    intent = OrderIntent(
        symbol='AAPL',
        side=OrderSide.BUY,
        qty=10,
        order_type=OrderType.MARKET,
        time_in_force='day',
        reason='Portfolio allocation: target=12.8%',
        priority=1,
    )
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any


class OrderSide(Enum):
    """买卖方向"""
    BUY = 'buy'
    SELL = 'sell'


class OrderType(Enum):
    """订单类型"""
    MARKET = 'market'
    LIMIT = 'limit'
    STOP = 'stop'
    STOP_LIMIT = 'stop_limit'


class OrderIntentStatus(Enum):
    """订单意图状态（在到达 execution 前的状态）"""
    DRAFT = 'DRAFT'            # 刚创建，尚未验证
    VALIDATED = 'VALIDATED'    # 已通过业务规则验证
    SAFETY_CHECKED = 'SAFETY_CHECKED'  # 已通过安全检查（锁/降级/风控）
    READY = 'READY'            # 可以发送到 broker
    REJECTED = 'REJECTED'      # 被安全检查拒绝
    CANCELLED = 'CANCELLED'    # 执行前被取消


@dataclass
class OrderIntent:
    """
    订单意图 — 决策层和执行层之间的契约

    这个对象在进入执行层之前必须经过完整的安全检查。
    不包含任何交易逻辑——只是数据载体。
    """

    # ─── 必填字段 ────────────────────────────────────
    symbol: str                              # 标的符号（AAPL, NVDA 等）
    side: OrderSide                          # buy | sell
    qty: int                                 # 数量（整数）
    order_type: OrderType                    # 订单类型
    time_in_force: str                       # day | gtc | ioc

    # ─── 可选字段 ────────────────────────────────────
    limit_price: Optional[float] = None      # 限价（type=limit 时）
    stop_price: Optional[float] = None       # 止损价（type=stop 时）
    reason: str = ''                         # 决策理由（可解释性）
    priority: int = 0                        # 优先级（越高越先执行）
    client_order_id: Optional[str] = None    # 自定义订单 ID

    # ─── 元数据 ──────────────────────────────────────
    status: OrderIntentStatus = OrderIntentStatus.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    decision_source: str = ''                # 决策来源（scanner/portfolio/manual）
    sector: str = ''                         # 所属板块
    portfolio_weight_before: Optional[float] = None   # 交易前仓位权重
    portfolio_weight_after: Optional[float] = None    # 交易后仓位权重
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ─── 验证 ────────────────────────────────────────

    def validate(self) -> tuple[bool, Optional[str]]:
        """
        验证订单意图的基本合法性

        不涉及任何策略逻辑——只检查数据完整性。

        Returns:
            (is_valid, error_message)
        """
        if not self.symbol or not isinstance(self.symbol, str):
            return False, 'symbol 缺失或无效'
        if len(self.symbol) > 10:
            return False, f'symbol 过长: {self.symbol}'

        if self.qty <= 0:
            return False, f'qty 必须 > 0: {self.qty}'
        if self.qty != int(self.qty):
            return False, f'qty 必须是整数: {self.qty}'

        if self.side not in (OrderSide.BUY, OrderSide.SELL):
            return False, f'invalid side: {self.side}'

        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            return False, 'limit order 缺少 limit_price'
        if self.order_type == OrderType.STOP and self.stop_price is None:
            return False, 'stop order 缺少 stop_price'
        if self.order_type == OrderType.STOP_LIMIT and (
            self.stop_price is None or self.limit_price is None
        ):
            return False, 'stop_limit order 缺少 stop_price 或 limit_price'

        if self.time_in_force not in ('day', 'gtc', 'ioc', 'fok'):
            return False, f'invalid time_in_force: {self.time_in_force}'

        return True, None

    # ─── 状态转换 ────────────────────────────────────

    def mark_validated(self):
        """标记为已验证"""
        self.status = OrderIntentStatus.VALIDATED

    def mark_safety_checked(self):
        """标记为已通过安全检查"""
        self.status = OrderIntentStatus.SAFETY_CHECKED

    def mark_ready(self):
        """标记为可以执行"""
        self.status = OrderIntentStatus.READY

    def mark_rejected(self):
        """标记为被拒绝"""
        self.status = OrderIntentStatus.REJECTED

    def mark_cancelled(self):
        """标记为已取消"""
        self.status = OrderIntentStatus.CANCELLED

    # ─── 序列化 ──────────────────────────────────────

    def to_alpaca_payload(self) -> dict:
        """
        转换为 Alpaca API 下单 payload

        Returns:
            Alpaca /v2/orders POST 请求体
        """
        payload = {
            'symbol': self.symbol,
            'qty': str(self.qty),
            'side': self.side.value,
            'type': self.order_type.value,
            'time_in_force': self.time_in_force,
        }
        if self.limit_price is not None:
            payload['limit_price'] = str(self.limit_price)
        if self.stop_price is not None:
            payload['stop_price'] = str(self.stop_price)
        if self.client_order_id:
            payload['client_order_id'] = self.client_order_id
        return payload

    def to_dict(self) -> dict:
        """转换为字典"""
        d = asdict(self)
        d['side'] = self.side.value
        d['order_type'] = self.order_type.value
        d['status'] = self.status.value
        d['created_at'] = self.created_at.isoformat()
        return d

    def __repr__(self):
        price_info = ''
        if self.limit_price:
            price_info = f' @ ${self.limit_price:.2f}'
        if self.stop_price:
            price_info = f' stop=${self.stop_price:.2f}'
        return (
            f'OrderIntent({self.side.value} {self.symbol} x{self.qty} '
            f'{self.order_type.value}{price_info} | {self.status.value})'
        )
