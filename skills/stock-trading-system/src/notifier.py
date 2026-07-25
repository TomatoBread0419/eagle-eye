# ========================
# 报警通知模块
# 支持 Bark / PushPlus / Telegram Bot
# ========================

import requests
from datetime import datetime, timezone
from typing import Optional

from config import BARK_KEY, PUSHPLUS_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _format_price(price):
    if price is None:
        return "N/A"
    return f"${price:.2f}"


def _format_change(change, pct):
    if change is None or pct is None:
        return ""
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.4f} ({sign}{pct:.2f}%)"


def notify_bark(title: str, body: str, group: str = "StockTrader") -> bool:
    """Bark iOS 推送"""
    if not BARK_KEY:
        return False
    url = f"https://api.day.app/{BARK_KEY}/{title}/{body}"
    try:
        resp = requests.get(url, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[通知] Bark 推送失败: {e}")
        return False


def notify_pushplus(title: str, content: str) -> bool:
    """PushPlus 微信推送"""
    if not PUSHPLUS_TOKEN:
        return False
    url = "http://www.pushplus.plus/send"
    data = {
        "token": PUSHPLUS_TOKEN,
        "title": title,
        "content": content,
        "template": "html",
    }
    try:
        resp = requests.post(url, json=data, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[通知] PushPlus 推送失败: {e}")
        return False


def notify_telegram(text: str) -> bool:
    """Telegram Bot 推送"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=data, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[通知] Telegram 推送失败: {e}")
        return False


def notify(title: str, body: str, level: str = "INFO") -> None:
    """
    统一通知接口，同时发送到所有已配置渠道
    level: INFO / BUY / SELL / ALERT
    """
    prefix = {"INFO": "📊", "BUY": "🟢 BUY", "SELL": "🔴 SELL", "ALERT": "⚠️ ALERT"}.get(level, "📊")
    msg = f"{prefix} [{_now()}]\n{body}"

    results = []
    if BARK_KEY:
        results.append(f"Bark: {notify_bark(title, msg)}")
    if PUSHPLUS_TOKEN:
        results.append(f"PushPlus: {notify_pushplus(title, msg)}")
    if TELEGRAM_BOT_TOKEN:
        results.append(f"Telegram: {notify_telegram(msg)}")

    # 打印到控制台
    print(f"[通知] {prefix} {title} - {body}")


# ---------- 业务层通知函数 ----------

def notify_price_alert(symbol: str, price: float, change_pct: float, threshold: float):
    """价格大幅波动报警"""
    body = f"{symbol} 价格 {_format_price(price)}，波动 {_format_change(price * change_pct / 100, change_pct)}，超过阈值 {threshold*100:.0f}%"
    notify(f"价格预警 {symbol}", body, "ALERT")


def notify_trade(side: str, symbol: str, qty: int, price: float, signal: str):
    """交易执行通知"""
    side_icon = "🟢 买入" if side.upper() == "BUY" else "🔴 卖出"
    body = f"{side_icon} {qty} 股 {symbol} @ {_format_price(price)}\n信号来源: {signal}"
    notify(f"交易执行 {symbol}", body, "BUY" if side.upper() == "BUY" else "SELL")


def notify_market_update(quotes: dict):
    """市场行情汇总推送"""
    lines = [f"[{_now()}] 市场行情\n"]
    for sym, q in quotes.items():
        price = q.get("price")
        pct = q.get("change_pct")
        lines.append(f"{sym}: {_format_price(price)} {_format_change(q.get('change'), pct)}")
    body = "\n".join(lines)
    notify("市场行情", body, "INFO")


def notify_error(context: str, detail: str):
    """错误通知"""
    notify(f"错误: {context}", detail, "ALERT")


if __name__ == "__main__":
    # 测试（仅打印）
    print("=== 通知模块测试 ===")
    notify("测试通知", "这是一条测试消息", "INFO")
