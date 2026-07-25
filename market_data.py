# ========================
# 行情数据模块
# 数据源：新浪 Finance（A股/美股）/ 东方财富（备用）
# Termux/Android: 使用 urllib.request 而非 requests
#   - 东方财富  2026-05-20 起持续 502 Bad Gateway（nginx 宕机）
#   - 新浪财经  始终稳定，作为主力数据源
#   - 美股：     Alpaca IEX 日K 作为主力（feed=iex），避过东财不稳定性
# ========================

import json
import time
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional

SINA_URL = "https://hq.sinajs.cn/list={}"
EM_STOCK_URL = "https://push2.eastmoney.com/api/qt/stock/get"
EM_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

HEADERS_SINA = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.sina.com.cn/",
}
HEADERS_EM = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.eastmoney.com/",
}
# 东方财富 502 全局开关（2026-05-20 起宕机）
EM_DISABLED = True

# ─── 通用 HTTP helpers ──────────────────────────────────────

def _http_get(url: str, headers: dict, timeout: int = 8) -> Optional[bytes]:
    """GET 请求，返回原始字节"""
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read()
    except Exception as e:
        return None

def _http_get_json(url: str, headers: dict, timeout: int = 8) -> Optional[dict]:
    """GET 请求，返回解析后的 JSON"""
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return None

# ─── 新浪行情 ────────────────────────────────────────────────

def get_quote_sina(symbol: str) -> Optional[dict]:
    """
    通过新浪获取股票实时行情（支持A股和美股）
    A股 symbol: sh600519, sz000858
    美股 symbol: usAAPL, usTSLA
    """
    s = symbol.strip()
    s_upper = s.upper()
    if s_upper.startswith("SH") or s_upper.startswith("SZ"):
        code = s  # 保持小写：sh600519
    elif s_upper.startswith("US"):
        code = s.lower()
    elif s_upper.startswith("1.") or s_upper.startswith("0."):
        code = ("sh" if s_upper.startswith("1.") else "sz") + s.split(".")[1]
    elif "." in s_upper:
        parts = s_upper.split(".")
        mkt = {"HK": "hk", "US": "us"}.get(parts[0], parts[0].lower())
        code = mkt + parts[1]
    else:
        code = "sh" + s.upper()

    url = SINA_URL.format(code)
    try:
        raw = _http_get(url, HEADERS_SINA, timeout=8)
        if not raw:
            return None
        text = raw.decode("GBK", errors="replace")

        m = re.search(r'hq_str_\w+="([^"]+)"', text)
        if not m:
            return None
        fields = m.group(1).split(",")
        if len(fields) < 10:
            return None

        name = fields[0]

        if code.startswith("us"):
            price = float(fields[1])
            change = float(fields[2])
            pct = float(fields[3].replace("%", ""))
            prev_close = round(price - change, 4)
            return {
                "symbol": code[2:].upper(),
                "name": name,
                "price": price,
                "prev_close": prev_close,
                "change": change,
                "change_pct": pct,
                "open": float(fields[4]) if fields[4] else None,
                "high": float(fields[5]) if fields[5] else None,
                "low": float(fields[6]) if fields[6] else None,
                "volume": fields[7],
                "timestamp": datetime.now(timezone.utc),
            }
        else:
            open_price = float(fields[1]) if fields[1] else 0
            prev_close = float(fields[2]) if fields[2] else 0
            price = float(fields[3]) if fields[3] else 0
            high = float(fields[4]) if fields[4] else 0
            low = float(fields[5]) if fields[5] else 0
            change = round(price - prev_close, 2)
            pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
            return {
                "symbol": code[2:].upper(),
                "name": name,
                "price": price,
                "prev_close": prev_close,
                "change": change,
                "change_pct": pct,
                "open": open_price,
                "high": high,
                "low": low,
                "volume": fields[8] if len(fields) > 8 else None,
                "timestamp": datetime.now(timezone.utc),
            }
    except Exception as e:
        print(f"[行情] 获取 {symbol} 失败: {e}")
        return None


def get_quote_em(symbol: str) -> Optional[dict]:
    """
    东方财富 API 获取实时行情（A股/港股，支持盘前盘后）
    ⚠️ 2026-05-20 起东财全线 502，此函数直接返回 None
    """
    if EM_DISABLED:
        return None

    s = symbol.strip()
    s_upper = s.upper()

    if s_upper.startswith("1.") or s_upper.startswith("0."):
        secid = s
    elif s_upper.startswith("SH") or s_upper.startswith("SZ"):
        code = s_upper[2:]
        secid = ("1" if code.startswith("6") else "0") + "." + code
    elif s_upper.startswith("HK"):
        code = s_upper[2:]
        secid = "116." + code
    else:
        secid = "1." + s_upper

    url = (f"{EM_STOCK_URL}?secid={secid}"
           f"&fields=f43,f44,f45,f46,f47,f48,f57,f58,f60"
           f"&ut=fa5fd1943c7b386f172d6893dbfba10b&fltt=2&invt=2")
    try:
        data = _http_get_json(url, HEADERS_EM, timeout=8)
        if not data or data.get("rc") != 0:
            return None
        d = data.get("data", {})
        if not d:
            return None

        price = round(d.get("f43", 0) / 100, 2)
        prev = round(d.get("f60", 0) / 100, 2)
        change = round(price - prev, 2)
        pct = round(change / prev * 100, 2) if prev else 0

        def safe_price(v):
            if v is None or v == "-" or v == "":
                return None
            return round(float(v) / 100, 2)

        open_price = None
        if isinstance(d.get("f44"), (int, float)) and d.get("f44", 0) > 0:
            open_price = safe_price(d.get("f44"))

        return {
            "symbol": d.get("f57"),
            "name": d.get("f58"),
            "price": price,
            "prev_close": prev,
            "change": change,
            "change_pct": pct,
            "open": open_price,
            "high": safe_price(d.get("f45")),
            "low": safe_price(d.get("f46")),
            "volume": d.get("f47"),
            "amount": d.get("f48"),
            "timestamp": datetime.now(timezone.utc),
        }
    except Exception as e:
        print(f"[行情] 获取 {symbol} 失败: {e}")
        return None


def get_historical(symbol: str, period: str = "3mo", interval: str = "1d") -> Optional[list]:
    """
    获取历史K线（新浪财经）
    period: 3mo, 6mo, 1y, 2y
    interval: 1d (日K), 1w (周K)
    """
    s = symbol.strip()
    s_upper = s.upper()

    if s_upper.startswith("SH") or s_upper.startswith("SZ"):
        sym_sina = s_upper[:2].lower() + s_upper[2:]
    elif s_upper.startswith("1.") or s_upper.startswith("0."):
        parts = s.split(".")
        sym_sina = ("sh" if parts[0] == "1" else "sz") + parts[1]
    else:
        return None

    days_map = {"3mo": 60, "6mo": 120, "1y": 250, "2y": 500}
    datalen = days_map.get(period, 60)
    scale_map = {"1d": 240, "1w": 1024, "1m": 60}
    scale = scale_map.get(interval, 240)

    url = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           f"CN_MarketData.getKLineData?symbol={sym_sina}&scale={scale}&datalen={datalen}")
    headers = {
        "Referer": "https://finance.sina.com.cn/",
        "User-Agent": "Mozilla/5.0",
    }
    try:
        data = _http_get_json(url, headers, timeout=8)
        if not isinstance(data, list):
            return None
        candles = []
        for item in data:
            candles.append({
                "timestamp": datetime.strptime(item["day"], "%Y-%m-%d").replace(tzinfo=timezone.utc),
                "open": float(item["open"]),
                "close": float(item["close"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "volume": float(item["volume"]) if item.get("volume") else 0,
            })
        # 新浪返回的是最新在前，需要反转成时间正序
        candles.reverse()
        return candles
    except Exception as e:
        print(f"[行情] 获取 {symbol} 历史数据失败: {e}")
        return None


def get_batch_quotes(symbols: list) -> dict:
    """批量获取多只股票行情"""
    results = {}
    for sym in symbols:
        q = get_quote_em(sym)  # 快速短路（东财已禁用）
        if not q:
            q = get_quote_sina(sym)
        if q:
            results[sym.upper()] = q
        time.sleep(0.1)
    return results


if __name__ == "__main__":
    print("=== 行情测试 ===")
    q = get_quote_sina("sh600519")
    if q:
        print(f"贵州茅台: ¥{q['price']} ({q['change_pct']:+.2f}%)")

    q2 = get_quote_sina("usAAPL")
    if q2:
        print(f"AAPL: ${q2['price']} ({q2['change_pct']:+.2f}%)")

    candles = get_historical("sh600519", "3mo")
    if candles:
        print(f"K线: {len(candles)} 条，最新收盘 ¥{candles[-1]['close']}")
