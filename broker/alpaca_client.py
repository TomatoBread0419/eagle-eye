"""
broker/alpaca_client.py — Alpaca API 适配器（V7.1 Phase 2.5）

所有 Alpaca 通信必须通过此适配器。
策略模块不得直接调用 Alpaca API。

这是 Constitution 铁律 #3（永不执行未知订单）和
Memory Charter「AI 不能直接执行交易」的执行层实现。

用法：
    from eagle_eye.broker.alpaca_client import AlpacaClient
    client = AlpacaClient()
    positions = client.get_positions()
    order = client.place_order(symbol='AAPL', qty=1, side='buy', type='market', time_in_force='day')
"""

import json
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple

from eagle_eye.core.config import cfg
from eagle_eye.core.http import (
    alpaca_get, alpaca_post, alpaca_patch, alpaca_delete,
    http_get,
)
from eagle_eye.core.logger import get_logger

logger = get_logger('broker')


class AlpacaClient:
    """
    Alpaca Paper Trading API 适配器

    所有 Alpaca API 通信的唯一入口。
    不包含任何策略逻辑——只负责收发数据。
    """

    def __init__(self):
        self._base_url = cfg.alpaca_base_url
        self._data_url = cfg.alpaca_data_url
        self._headers = cfg.alpaca_headers
        self._api_failure_count = 0
        self._last_failure_time: Optional[datetime] = None

    # ─── 账户 ────────────────────────────────────────

    def get_account(self) -> Optional[dict]:
        """获取账户信息（权益、现金、购买力等）"""
        code, data = alpaca_get('/v2/account', timeout=30)
        if code == 200:
            self._reset_failures()
            return data
        self._record_failure()
        logger.error(f'获取账户信息失败: HTTP {code}')
        return None

    # ─── 持仓 ────────────────────────────────────────

    def get_positions(self) -> list:
        """获取所有持仓"""
        code, data = alpaca_get('/v2/positions', timeout=30)
        if code == 200:
            self._reset_failures()
            return data if isinstance(data, list) else []
        self._record_failure()
        logger.error(f'获取持仓列表失败: HTTP {code}')
        return []

    def get_position(self, symbol: str) -> Optional[dict]:
        """获取单只持仓"""
        code, data = alpaca_get(f'/v2/positions/{symbol}', timeout=30)
        if code == 200:
            self._reset_failures()
            return data
        if code == 404:
            self._reset_failures()
            return None
        self._record_failure()
        logger.error(f'获取持仓 {symbol} 失败: HTTP {code}')
        return None

    # ─── 订单 ────────────────────────────────────────

    def get_orders(self, status: str = 'open', limit: int = 100,
                   symbol: Optional[str] = None) -> list:
        """
        获取订单列表

        Args:
            status: open | closed | all
            limit: 最大返回数
            symbol: 可选，按标的过滤
        """
        path = f'/v2/orders?status={status}&limit={limit}'
        if symbol:
            path += f'&symbols={symbol}'
        code, data = alpaca_get(path, timeout=30)
        if code == 200:
            self._reset_failures()
            return data if isinstance(data, list) else []
        self._record_failure()
        logger.error(f'获取订单列表失败: HTTP {code}')
        return []

    def get_order(self, order_id: str) -> Optional[dict]:
        """获取单个订单"""
        code, data = alpaca_get(f'/v2/orders/{order_id}', timeout=30)
        if code == 200:
            self._reset_failures()
            return data
        self._record_failure()
        logger.error(f'获取订单 {order_id} 失败: HTTP {code}')
        return None

    def place_order(self,
                    symbol: str,
                    qty: int,
                    side: str,
                    type: str = 'market',
                    time_in_force: str = 'day',
                    limit_price: Optional[float] = None,
                    stop_price: Optional[float] = None,
                    client_order_id: Optional[str] = None) -> Optional[dict]:
        """
        下单

        Args:
            symbol: 标的符号
            qty: 数量
            side: buy | sell
            type: market | limit | stop | stop_limit
            time_in_force: day | gtc | ioc
            limit_price: 限价（type=limit 时必需）
            stop_price: 止损价（type=stop/stop_limit 时必需）
            client_order_id: 自定义订单 ID

        Returns:
            Alpaca 订单对象（含 id, status, filled_at 等），失败返回 None
        """
        order_payload = {
            'symbol': symbol,
            'qty': str(qty),
            'side': side,
            'type': type,
            'time_in_force': time_in_force,
        }
        if limit_price is not None:
            order_payload['limit_price'] = str(limit_price)
        if stop_price is not None:
            order_payload['stop_price'] = str(stop_price)
        if client_order_id:
            order_payload['client_order_id'] = client_order_id

        code, data = alpaca_post('/v2/orders', payload=order_payload, timeout=30)
        if code in (200, 201):
            self._reset_failures()
            logger.info(f'下单: {side} {symbol} x{qty} {type} → status={data.get("status")}')
            return data

        self._record_failure()
        logger.error(f'下单失败: {side} {symbol} x{qty} → HTTP {code} {data}')
        return None

    def cancel_order(self, order_id: str) -> bool:
        """
        取消订单

        注意 Alpaca 死锁规则：永远不要 cancel stop order。
        此方法仅用于取消 market/limit 订单。

        Args:
            order_id: 订单 ID

        Returns:
            True 如果成功（HTTP 204 或已取消），False 如果失败
        """
        code, data = alpaca_delete(f'/v2/orders/{order_id}', timeout=15)
        if code in (204, 200, 404):
            # 404 = 已取消或不存在，也算成功
            self._reset_failures()
            return True
        self._record_failure()
        logger.error(f'取消订单 {order_id} 失败: HTTP {code} {data}')
        return False

    def patch_order(self, order_id: str, patch_data: dict) -> Optional[dict]:
        """
        修改订单（PATCH）

        用于调整止损单数量等（遵守 Alpaca 死锁规则：PATCH 不 cancel）。

        Args:
            order_id: 订单 ID
            patch_data: 要修改的字段（如 {'qty': 3}）

        Returns:
            更新后的订单对象，失败返回 None
        """
        code, data = alpaca_patch(f'/v2/orders/{order_id}', payload=patch_data, timeout=15)
        if code == 200:
            self._reset_failures()
            return data
        self._record_failure()
        logger.error(f'修改订单 {order_id} 失败: HTTP {code} {data}')
        return None

    # ─── 市场数据 ────────────────────────────────────

    def get_bars(self, symbol: str, days: int = 100, limit: int = None) -> list:
        """
        获取日K线数据

        Args:
            symbol: 标的符号
            days: 获取多少天（与 limit 二选一）
            limit: 获取多少根（与 days 二选一）

        Returns:
            [{t, o, h, l, c, v, ...}, ...] 按时间升序
        """
        if limit is None:
            limit = min(days + 10, 500)  # 多取一些确保够

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=max(days, limit))
        start_str = start.strftime('%Y-%m-%d')
        end_str = end.strftime('%Y-%m-%d')

        url = (
            f'{self._data_url}/{symbol}/bars'
            f'?start={start_str}&end={end_str}'
            f'&timeframe=1Day&limit={limit}'
            f'&adjustment=raw&feed=iex&sort=asc'
        )

        code, body = http_get(url, headers=self._headers, timeout=30)
        if code == 200:
            self._reset_failures()
            try:
                data = json.loads(body)
                bars = data.get('bars', [])
                if bars:
                    return bars
            except json.JSONDecodeError:
                logger.warning(f'解析 {symbol} K线数据失败')

        self._record_failure()
        logger.error(f'获取 {symbol} K线失败: HTTP {code}')
        return []

    def get_last_price(self, symbol: str) -> Optional[float]:
        """获取最新成交价"""
        code, body = http_get(
            f'{self._data_url}/{symbol}/trades/latest',
            headers=self._headers,
            timeout=15
        )
        if code == 200:
            self._reset_failures()
            try:
                data = json.loads(body)
                trade = data.get('trade', {})
                price = trade.get('p')
                if price:
                    return price
            except (json.JSONDecodeError, KeyError):
                pass
        self._record_failure()
        return None

    def get_clock(self) -> Optional[dict]:
        """获取市场时钟（开/闭市状态）"""
        code, data = alpaca_get('/v2/clock', timeout=15)
        if code == 200:
            self._reset_failures()
            return data
        self._record_failure()
        logger.error(f'获取市场时钟失败: HTTP {code}')
        return None

    def is_market_open(self) -> Optional[bool]:
        """检查市场是否开盘"""
        clock = self.get_clock()
        if clock:
            return clock.get('is_open', False)
        return None

    # ─── 历史订单（止损黑名单用） ────────────────────

    def get_filled_stops(self, days: int = 7) -> list:
        """
        获取最近 N 天的已成交止损单

        用于防止反复止损后立即重买同一标的。

        Args:
            days: 回溯天数

        Returns:
            [{symbol, filled_at, ...}, ...]
        """
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        path = f'/v2/orders?status=closed&after={since}&direction=desc&limit=200'
        code, data = alpaca_get(path, timeout=30)
        if code == 200 and isinstance(data, list):
            self._reset_failures()
            stop_fills = [
                o for o in data
                if o.get('side') == 'sell'
                and o.get('type') == 'stop'
                and o.get('filled_at')
                and o.get('status') == 'filled'
            ]
            return stop_fills
        self._record_failure()
        return []

    # ─── 健康检查 ────────────────────────────────────

    @property
    def api_failure_count(self) -> int:
        """API 连续失败次数"""
        return self._api_failure_count

    @property
    def last_failure_time(self) -> Optional[datetime]:
        """最近一次 API 失败时间"""
        return self._last_failure_time

    def is_healthy(self) -> bool:
        """API 是否健康（能成功获取账户信息）"""
        acct = self.get_account()
        return acct is not None

    def _record_failure(self):
        """记录一次 API 失败"""
        self._api_failure_count += 1
        self._last_failure_time = datetime.now(timezone.utc)
        logger.warning(f'API 失败 #{self._api_failure_count}')

    def _reset_failures(self):
        """重置失败计数（一次成功调用后）"""
        if self._api_failure_count > 0:
            logger.info(f'API 恢复，已重置失败计数 (之前: {self._api_failure_count})')
            self._api_failure_count = 0
            self._last_failure_time = None

    def reset_failure_count(self):
        """手动重置失败计数（在 degraded mode 恢复时使用）"""
        self._api_failure_count = 0
        self._last_failure_time = None


# ─── 模块级单例 ─────────────────────────────────────
# 所有模块共享同一个 client 实例，失败计数统一

_client_instance: Optional[AlpacaClient] = None


def get_alpaca_client() -> AlpacaClient:
    """获取 AlpacaClient 单例"""
    global _client_instance
    if _client_instance is None:
        _client_instance = AlpacaClient()
    return _client_instance


def reset_client():
    """重置 client 单例（测试用）"""
    global _client_instance
    _client_instance = None
