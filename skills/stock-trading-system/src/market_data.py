# ========================
# 行情数据模块
# 数据源：新浪 Finance（A股/美股）/ 东方财富（备用）
# ========================

import requests
import time
import re
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


def get_quote_sina(symbol: str) -> Optional[dict]:
    """
    通过新浪获取股票实时行情（支持A股和美股）
    A股 symbol: sh600519, sz000858
    美股 symbol: usAAPL, usTSLA
    """
    # 统一格式（保持原始大小写，新浪接口区分大小写）
    s = symbol.strip()
    s_upper = s.upper()
    if s_upper.startswith("SH") or s_upper.startswith("SZ"):
        code = s  # 保持小写：sh600519
    elif s_upper.startswith("US"):
        code = s.lower()  # usAAPL → usaapl
    elif s_upper.startswith("1.") or s_upper.startswith("0."):
        # 东方财富格式转新浪
        code = ("sh" if s_upper.startswith("1.") else "sz") + s.split(".")[1]
    elif "." in s_upper:
        parts = s_upper.split(".")
        mkt = {"HK": "hk", "US": "us"}.get(parts[0], parts[0].lower())
        code = mkt + parts[1]
    else:
        # 假设 A股 上交所
        code = "sh" + s.upper()

    url = SINA_URL.format(code)
    try:
        resp = requests.get(url, headers=HEADERS_SINA, timeout=8)
        text = resp.content.decode("GBK", errors="replace")

        # 解析: var hq_str_XXXX="..."
        m = re.search(r'hq_str_\w+="([^"]+)"', text)
        if not m:
            return None
        fields = m.group(1).split(",")
        if len(fields) < 10:
            return None

        name = fields[0]

        if code.startswith("us"):
            # 美股格式: 名称,现价,涨跌,涨跌幅,开票价,最高,最低,成交量,时间,...
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
            # A股格式: 名称,今开,昨收,现价,最高,最低,...
            name = fields[0]
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
    symbol: 1.600519（上交所）, 0.000001（深交所）, 116.000001（港股）
    """
    # 转换格式
    s = symbol.strip()
    s_upper = s.upper()

    if s_upper.startswith("1.") or s_upper.startswith("0."):
        # 已经是 EM 格式
        secid = s
    elif s_upper.startswith("SH") or s_upper.startswith("SZ"):
        code = s_upper[2:]
        secid = ("1" if code.startswith("6") else "0") + "." + code
    elif s_upper.startswith("HK"):
        code = s_upper[2:]
        secid = "116." + code
    else:
        # 假设上交所
        secid = "1." + s_upper

    params = {
        "secid": secid,
        "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fltt": 2,
        "invt": 2,
    }
    try:
        resp = requests.get(EM_STOCK_URL, params=params, headers=HEADERS_EM, timeout=8)
        data = resp.json()
        if data.get("rc") != 0:
            return None
        d = data.get("data", {})
        if not d:
            return None

        price = round(d.get("f43", 0) / 100, 2)
        prev = round(d.get("f60", 0) / 100, 2)
        change = round(price - prev, 2)
        pct = round(change / prev * 100, 2) if prev else 0

        # 盘前/竞价时段 f44/f45/f46 可能为 -
        def safe_price(v):
            if v is None or v == "-" or v == "":
                return None
            return round(float(v) / 100, 2)
        if isinstance(d.get("f44"), (int, float)) and d.get("f44", 0) > 0:
            open_price = safe_price(d.get("f44"))
        else:
            open_price = None

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
    period: 3mo, 6mo, 1y, 2y (转换为请求天数)
    interval: 1d (日K), 1w (周K)
    """
    # 转换标format
    s = symbol.strip()
    s_upper = s.upper()

    if s_upper.startswith("SH") or s_upper.startswith("SZ"):
        code = s_upper[2:]  # 取数字部分
        sym_sina = s_upper[:2].lower() + code
    elif s_upper.startswith("1.") or s_upper.startswith("0."):
        parts = s.split(".")
        sym_sina = ("sh" if parts[0] == "1" else "sz") + parts[1]
    else:
        return None

    # period -> datalen
    days_map = {"3mo": 60, "6mo": 120, "1y": 250, "2y": 500}
    datalen = days_map.get(period, 60)

    # interval -> scale
    scale_map = {"1d": 240, "1w": 1024, "1m": 60}
    scale = scale_map.get(interval, 240)

    url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    params = {
        "symbol": sym_sina,
        "scale": scale,
        "datalen": datalen,
    }
    headers = {
        "Referer": "https://finance.sina.com.cn/",
        "User-Agent": "Mozilla/5.0",
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=8)
        data = resp.json()
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
        q = get_quote_em(sym)
        if not q:
            q = get_quote_sina(sym)
        if q:
            results[sym.upper()] = q
        time.sleep(0.1)
    return results


if __name__ == "__main__":
    print("=== 行情测试 ===")
    # A股测试
    q = get_quote_sina("sh600519")
    if q:
        print(f"贵州茅台: ¥{q['price']} ({q['change_pct']:+.2f}%)")

    # 美股测试
    q2 = get_quote_sina("usAAPL")
    if q2:
        print(f"AAPL: ${q2['price']} ({q2['change_pct']:+.2f}%)")

    # 历史K线
    candles = get_historical("sh600519", "3mo")
    if candles:
        print(f"K线: {len(candles)} 条，最新收盘 ¥{candles[-1]['close']}")
