# ========================
# 交易执行模块
# 对接 Alpaca 券商 API（支持 Paper Trading）
# Termux/Android: 使用 urllib.request 而非 requests（避免 SSLEOFError）
# ========================

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional


def _request(method: str, url: str, headers: dict, body: Optional[dict] = None, timeout: int = 10) -> tuple:
    """统一的 HTTP 请求封装，基于 urllib.request"""
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='replace')
    except Exception as e:
        return 0, str(e)


class AlpacaTrader:
    """Alpaca 券商交易接口"""

    def __init__(self, api_key: str, secret_key: str, base_url: str = "https://paper-api.alpaca.markets"):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
            "Content-Type": "application/json",
        }

    # ---------- 账户 ----------

    def get_account(self) -> Optional[dict]:
        """获取账户信息"""
        status, body = _request("GET", f"{self.base_url}/v2/account", self.headers, timeout=10)
        if status == 200:
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return None
        print(f"[Alpaca] 获取账户失败({status}): {body[:200]}")
        return None

    # ---------- 持仓 ----------

    def get_positions(self) -> list:
        """获取当前所有持仓"""
        status, body = _request("GET", f"{self.base_url}/v2/positions", self.headers, timeout=10)
        if status == 200:
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return []
        if status == 404:
            return []
        print(f"[Alpaca] 获取持仓失败({status}): {body[:200]}")
        return []

    def get_position(self, symbol: str) -> Optional[dict]:
        """获取指定标的持仓"""
        status, body = _request("GET", f"{self.base_url}/v2/positions/{symbol}", self.headers, timeout=10)
        if status == 200:
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return None
        if status == 404:
            return None
        print(f"[Alpaca] 获取持仓 {symbol} 失败({status}): {body[:200]}")
        return None

    # ---------- 订单 ----------

    def list_orders(self, status: str = "all", limit: int = 50) -> list:
        """列出订单"""
        url = f"{self.base_url}/v2/orders?status={status}&limit={limit}"
        sc, body = _request("GET", url, self.headers, timeout=10)
        if sc == 200:
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return []
        print(f"[Alpaca] 列出订单失败({sc}): {body[:200]}")
        return []

    def get_order(self, order_id: str) -> Optional[dict]:
        """获取单个订单"""
        sc, body = _request("GET", f"{self.base_url}/v2/orders/{order_id}", self.headers, timeout=10)
        if sc == 200:
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return None
        print(f"[Alpaca] 获取订单失败({sc}): {body[:200]}")
        return None

    def submit_order(self, symbol: str, qty: int, side: str, order_type: str = "market",
                    time_in_force: str = "day", limit_price: float = None) -> Optional[dict]:
        """
        提交订单
        symbol: 股票代码
        qty: 数量
        side: "buy" 或 "sell"
        order_type: "market" / "limit"
        time_in_force: "day" / "gtc" / "opg" 等
        """
        payload = {
            "symbol": symbol.upper(),
            "qty": qty,
            "side": side.lower(),
            "type": order_type.lower(),
            "time_in_force": time_in_force.lower(),
        }
        if limit_price:
            payload["limit_price"] = limit_price

        sc, body = _request("POST", f"{self.base_url}/v2/orders", self.headers, body=payload, timeout=10)
        if sc in (200, 201):
            try:
                order = json.loads(body)
                print(f"[Alpaca] 订单已提交: {order.get('id')} {side.upper()} {qty} {symbol} @ {order.get('filled_avg_price') or order_type}")
                return order
            except json.JSONDecodeError:
                return None
        print(f"[Alpaca] 提交订单失败({sc}): {body[:200]}")
        return None

    def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        sc, body = _request("DELETE", f"{self.base_url}/v2/orders/{order_id}", self.headers, timeout=10)
        if sc == 204:
            print(f"[Alpaca] 订单已取消: {order_id}")
            return True
        print(f"[Alpaca] 取消订单失败({sc}): {body[:200]}")
        return False

    def cancel_all_orders(self) -> bool:
        """取消所有未成交订单"""
        sc, body = _request("DELETE", f"{self.base_url}/v2/orders", self.headers, timeout=10)
        if sc == 204:
            print(f"[Alpaca] 所有订单已取消")
            return True
        print(f"[Alpaca] 取消所有订单失败({sc}): {body[:200]}")
        return False

    # ---------- 便捷方法 ----------

    def market_buy(self, symbol: str, qty: int = 1) -> Optional[dict]:
        """市价买入"""
        return self.submit_order(symbol, qty, "buy", "market")

    def market_sell(self, symbol: str, qty: int = 1) -> Optional[dict]:
        """市价卖出"""
        return self.submit_order(symbol, qty, "sell", "market")

    def limit_buy(self, symbol: str, qty: int, price: float) -> Optional[dict]:
        """限价买入"""
        return self.submit_order(symbol, qty, "buy", "limit", limit_price=price)

    def limit_sell(self, symbol: str, qty: int, price: float) -> Optional[dict]:
        """限价卖出"""
        return self.submit_order(symbol, qty, "sell", "limit", limit_price=price)

    def close_position(self, symbol: str) -> Optional[dict]:
        """平掉指定标的的持仓（市价）"""
        sc, body = _request("DELETE", f"{self.base_url}/v2/positions/{symbol}", self.headers, timeout=10)
        if sc == 200:
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return None
        if sc == 404:
            return None
        print(f"[Alpaca] 平仓失败({sc}): {body[:200]}")
        return None

    def close_all_positions(self) -> bool:
        """清仓所有持仓"""
        sc, body = _request("DELETE", f"{self.base_url}/v2/positions", self.headers, timeout=10)
        if sc == 207:
            print(f"[Alpaca] 已清仓所有持仓")
            return True
        print(f"[Alpaca] 清仓失败({sc}): {body[:200]}")
        return False

    # ---------- 账户状态检查 ----------

    def get_buying_power(self) -> Optional[float]:
        """获取可用买入资金"""
        acc = self.get_account()
        if acc:
            return float(acc.get("buying_power", 0))
        return None

    def print_account(self):
        """打印账户概览"""
        acc = self.get_account()
        if not acc:
            return
        print("=== Alpaca 账户概览 ===")
        print(f"  账户ID:    {acc.get('id')}")
        print(f"  净值:      ${acc.get('portfolio_value')}")
        print(f"  现金:      ${acc.get('cash')}")
        print(f"  买入力:    ${acc.get('buying_power')}")
        print(f"  持仓市值:  ${acc.get('long_market_value')}")
        print(f"  当日盈亏:  ${acc.get('equity')} ({acc.get('last_equity')} base)")
        print(f"  状态:      {acc.get('status')}")


if __name__ == "__main__":
    import config
    trader = AlpacaTrader(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, config.ALPACA_BASE_URL)
    trader.print_account()
