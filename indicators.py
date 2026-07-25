# ========================
# 技术指标 & 交易信号模块
# 纯 Python 实现，不依赖 ta-lib
# ========================

import statistics
from typing import Optional


def _ma(values: list, period: int) -> Optional[float]:
    """简单移动平均"""
    if len(values) < period:
        return None
    return round(sum(values[-period:]) / period, 4)


def _ema(values: list, period: int) -> Optional[float]:
    """指数移动平均"""
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for val in values[period:]:
        ema = val * k + ema * (1 - k)
    return round(ema, 4)


def _stddev(values: list, period: int) -> Optional[float]:
    """标准差"""
    if len(values) < period:
        return None
    return round(statistics.stdev(values[-period:]), 4)


def sma(candles: list, period: int = 20) -> Optional[float]:
    """SMA - 简单移动平均线"""
    closes = [c["close"] for c in candles if c.get("close") is not None]
    return _ma(closes, period)


def ema(candles: list, period: int = 20) -> Optional[float]:
    """EMA - 指数移动平均线"""
    closes = [c["close"] for c in candles if c.get("close") is not None]
    return _ema(closes, period)


def rsi(candles: list, period: int = 14) -> Optional[float]:
    """RSI - 相对强弱指数"""
    closes = [c["close"] for c in candles if c.get("close") is not None]
    if len(closes) < period + 1:
        return None

    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d for d in deltas[-period:] if d > 0]
    losses = [-d for d in deltas[-period:] if d < 0]

    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    rsi_val = 100 - (100 / (1 + rs))
    return round(rsi_val, 2)


def macd(candles: list, fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[dict]:
    """MACD - 指数平滑异同移动平均线"""
    closes = [c["close"] for c in candles if c.get("close") is not None]
    if len(closes) < slow + signal:
        return None

    # 计算快慢 EMA
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    if ema_fast is None or ema_slow is None:
        return None
    macd_val = round(ema_fast - ema_slow, 4)

    # 计算 MACD Histogram 的 EMA（用最近 N 个 histogram 值做 EMA）
    # 反推历史 MACD line
    k_fast = 2 / (fast + 1)
    k_slow = 2 / (slow + 1)
    k_sig = 2 / (signal + 1)

    # 构建完整 EMA series 用于算 signal line
    ema_f_series = [_ema(closes[:i+1], fast) for i in range(fast-1, len(closes))]
    ema_s_series = [_ema(closes[:i+1], slow) for i in range(slow-1, len(closes))]
    macd_series = [ema_f_series[i] - ema_s_series[i] for i in range(len(ema_s_series))]
    if len(macd_series) < signal:
        return None

    # Signal line = EMA of MACD line
    signal_val = _ema(macd_series, signal)
    histogram = round(macd_val - signal_val, 4) if signal_val else None

    return {
        "macd": macd_val,
        "signal": signal_val,
        "histogram": histogram,
    }


def bollinger_bands(candles: list, period: int = 20, num_std: float = 2.0) -> Optional[dict]:
    """布林带"""
    closes = [c["close"] for c in candles if c.get("close") is not None]
    if len(closes) < period:
        return None
    mid = _ma(closes, period)
    std = _stddev(closes, period)
    if std is None:
        return None
    return {
        "upper": round(mid + num_std * std, 4),
        "middle": mid,
        "lower": round(mid - num_std * std, 4),
    }


def atr(candles: list, period: int = 14) -> Optional[float]:
    """ATR - 平均真实波幅"""
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        high = candles[i].get("high")
        low = candles[i].get("low")
        prev_close = candles[i-1].get("close")
        if high is None or low is None or prev_close is None:
            continue
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    return round(sum(trs[-period:]) / period, 4)


def generate_signal(candles: list, rsi_oversold: int = 30, rsi_overbought: int = 70,
                    sma_short: int = 20, sma_long: int = 50) -> str:
    """
    基于技术指标生成交易信号
    返回: "BUY" / "SELL" / "HOLD"
    """
    if not candles or len(candles) < sma_long + 5:
        return "HOLD"

    rsi_val = rsi(candles)
    macd_val = macd(candles)
    sma_s = sma(candles, sma_short)
    sma_l = sma(candles, sma_long)
    bb = bollinger_bands(candles)
    current_price = candles[-1].get("close")

    if None in [rsi_val, macd_val, sma_s, sma_l, bb]:
        return "HOLD"

    signals = []

    # RSI 信号
    if rsi_val < rsi_oversold:
        signals.append("BUY")
    elif rsi_val > rsi_overbought:
        signals.append("SELL")

    # MACD 金叉/死叉
    if macd_val["histogram"] > 0:
        signals.append("BUY")
    elif macd_val["histogram"] < 0:
        signals.append("SELL")

    # 均线交叉信号
    if sma_s > sma_l:
        signals.append("BUY")
    elif sma_s < sma_l:
        signals.append("SELL")

    # 布林带信号
    if current_price < bb["lower"]:
        signals.append("BUY")
    elif current_price > bb["upper"]:
        signals.append("SELL")

    # 多数投票
    buy_count = signals.count("BUY")
    sell_count = signals.count("SELL")

    if buy_count > sell_count + 1:
        return "BUY"
    elif sell_count > buy_count + 1:
        return "SELL"
    return "HOLD"


def analyze(candles: list, symbol: str = "") -> dict:
    """综合技术分析"""
    result = {
        "symbol": symbol,
        "price": candles[-1].get("close") if candles else None,
        "sma_20": sma(candles, 20),
        "sma_50": sma(candles, 50),
        "ema_20": ema(candles, 20),
        "rsi": rsi(candles),
        "macd": macd(candles),
        "bollinger": bollinger_bands(candles),
        "atr": atr(candles),
        "signal": generate_signal(candles),
    }
    return result


if __name__ == "__main__":
    # 测试
    import market_data
    candles = market_data.get_historical("AAPL", period="3mo")
    if candles:
        a = analyze(candles, "AAPL")
        print(f"=== AAPL 技术分析 ===")
        for k, v in a.items():
            print(f"  {k}: {v}")
