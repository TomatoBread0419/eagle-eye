"""
strategy/indicator_engine.py — 技术指标引擎 (V7.1 Phase 4)

All technical indicators extracted from us_common.py.
Pure math — no HTTP/API calls, no external dependencies except yfinance.

Usage:
    from eagle_eye.strategy.indicator_engine import calc_rsi, calc_macd, calc_volatility
"""


# ══════════════════════════════════════════════════
# 技术指标
# ══════════════════════════════════════════════════

def calc_rsi(prices, period=14):
    """RSI（纯 Python，无 numpy）"""
    if len(prices) < period + 1:
        return None
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0 for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def calc_sma(prices, period):
    """简单移动平均"""
    if len(prices) < period:
        return None
    return round(sum(prices[-period:]) / period, 2)


def calc_boll(prices, period=20, mult=2):
    """布林带 (lower, mid, upper)"""
    if len(prices) < period:
        return None, None, None
    last = prices[-period:]
    mean = sum(last) / period
    std = (sum((x - mean) ** 2 for x in last) / period) ** 0.5
    return round(mean - mult * std, 2), round(mean, 2), round(mean + mult * std, 2)


def calc_macd(prices, fast=12, slow=26, signal=9):
    """MACD: 返回 (macd_line, signal_line, histogram, crossover)
    
    crossover: 'golden' (金叉), 'death' (死叉), None
    """
    if len(prices) < slow + signal:
        return None, None, None, None
    
    def ema(data, period):
        k = 2 / (period + 1)
        result = [data[0]]
        for i in range(1, len(data)):
            result.append(data[i] * k + result[-1] * (1 - k))
        return result
    
    ema_fast = ema(prices, fast)
    ema_slow = ema(prices, slow)
    macd_line = round(ema_fast[-1] - ema_slow[-1], 4)
    
    # Signal line: EMA of FULL macd_series（v4.6 修复：之前只取最后 signal 个值，偏离标准）
    macd_series = [ema_fast[i] - ema_slow[i] for i in range(len(prices))]
    signal_ema = ema(macd_series, signal)
    signal_line = round(signal_ema[-1], 4)
    
    histogram = round(macd_line - signal_line, 4)
    
    # 金叉/死叉检测：比较昨天和今天
    prev_macd = macd_series[-2] if len(macd_series) >= 2 else None
    prev_signal_ema_series = ema(macd_series[-signal-1:-1], signal) if len(macd_series) > signal else []
    prev_signal = round(prev_signal_ema_series[-1], 4) if prev_signal_ema_series else None
    
    crossover = None
    if prev_macd is not None and prev_signal is not None:
        if prev_macd <= prev_signal and macd_line > signal_line:
            crossover = 'golden'
        elif prev_macd >= prev_signal and macd_line < signal_line:
            crossover = 'death'
    
    return macd_line, signal_line, histogram, crossover


def calc_atr(highs, lows, closes, period=14):
    """ATR 平均真实波幅（纯计算，零API成本）
    
    返回: ATR值（美元金额），或None
    """
    if len(closes) < period + 1:
        return None
    
    trs = []
    for i in range(1, len(closes)):
        h, l, pc = highs[i], lows[i], closes[i-1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    
    if len(trs) < period:
        return None
    
    atr = sum(trs[-period:]) / period
    return round(atr, 2)


def calc_volume_metrics(volumes, closes=None):
    """成交量分析：量比、量价关系、放量检测
    
    参数:
        volumes: 成交量序列（最近的在末尾）
        closes: 可选，收盘价序列（用于量价关系判断）
    
    返回: {
        'avg_vol_5d': float,      # 5日均量
        'avg_vol_20d': float,      # 20日均量
        'vol_ratio': float,        # 量比 = 5日均量 / 20日均量
        'vol_spike': bool,         # 最新日是否放量（>2x 20日均量）
        'vol_dry': bool,           # 是否缩量（<0.5x 20日均量）
        'price_up': bool|None,     # 价格是否上涨（需 closes 参数）
        'confirmation': str,       # 量价配合信号: 'bullish'/'bearish'/'divergence'/'neutral'
    }
    """
    if not volumes or len(volumes) < 20:
        return {}
    
    avg5 = sum(volumes[-5:]) / 5
    avg20 = sum(volumes[-20:]) / 20
    ratio = avg5 / avg20 if avg20 > 0 else 1.0
    latest_vol = volumes[-1]
    
    spike = latest_vol > avg20 * 2.0
    dry = latest_vol < avg20 * 0.5
    
    result = {
        'avg_vol_5d': round(avg5),
        'avg_vol_20d': round(avg20),
        'vol_ratio': round(ratio, 2),
        'vol_spike': spike,
        'vol_dry': dry,
        'price_up': None,
        'confirmation': 'neutral',
    }
    
    # 量价关系（需要价格数据）
    if closes and len(closes) >= 2:
        price_up = closes[-1] > closes[-2]
        result['price_up'] = price_up
        
        if price_up and ratio > 1.2:
            result['confirmation'] = 'bullish'   # 价涨量增 → 强势
        elif price_up and ratio < 0.8:
            result['confirmation'] = 'divergence'  # 价涨量缩 → 虚涨
        elif not price_up and ratio > 1.2:
            result['confirmation'] = 'bearish'    # 价跌量增 → 出货
        elif not price_up and ratio < 0.8:
            result['confirmation'] = 'neutral'    # 价跌量缩 → 正常回调
    
    return result


# ══════════════════════════════════════════════════
# 波动率 & 风险指标
# ══════════════════════════════════════════════════

def calc_volatility(prices, period=20):
    """20日年化波动率（日收益率标准差 × sqrt(252)）
    
    参数:
        prices: 价格序列（最近的在末尾）
        period: 计算窗口（默认20日）
    
    返回: 年化波动率百分比（如 35.2 表示 35.2%），或 None
    """
    if len(prices) < period + 1:
        return None
    returns = [(prices[i] / prices[i-1]) - 1 for i in range(-period, 0)]
    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
    daily_vol = variance ** 0.5
    annual_vol = daily_vol * (252 ** 0.5)
    return round(annual_vol * 100, 1)


def get_volatility_stop_pct(vol_20d):
    """波动率分档止损百分比（7-10%）
    
    波动率越高 → 止损越宽（给高波动股票更多呼吸空间，避免被噪音震出）
    波动率越低 → 止损越紧（稳定股票不需要宽止损）
    
    分档:
        <20%  → 7%（低波动，紧止损）
        20-35% → 8%（中波动）
        35-50% → 9%（高波动）
        >50%  → 10%（极高波动，超宽）
        未知   → 8%（默认）
    """
    if vol_20d is None:
        return 0.08
    if vol_20d < 20:
        return 0.07
    elif vol_20d < 35:
        return 0.08
    elif vol_20d < 50:
        return 0.09
    else:
        return 0.10


# ══════════════════════════════════════════════════
# yfinance 基本面数据（可选，网络不通时优雅降级）
# ══════════════════════════════════════════════════

def get_yf_metrics(symbol):
    """获取 yfinance 基本面指标（beta、forward PE、市值）
    
    如果 yfinance 未安装、网络不通、或被 Yahoo 限流，返回空 dict。
    注意：Yahoo Finance 对中国 IP 经常限流，此函数设计为优雅降级。
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        # 使用 fast_info 先试（轻量），失败再回退 info
        try:
            info = ticker.get_info()
        except Exception:
            return {}
        if not info or not isinstance(info, dict):
            return {}
        return {
            'beta': info.get('beta'),
            'forward_pe': info.get('forwardPE'),
            'trailing_pe': info.get('trailingPE'),
            'market_cap': info.get('marketCap'),
            'dividend_yield': info.get('dividendYield'),
        }
    except Exception:
        return {}


def calc_correlation(returns_a, returns_b):
    n = min(len(returns_a), len(returns_b))
    if n < 20:
        return None
    ra = returns_a[-n:]
    rb = returns_b[-n:]
    ma = sum(ra) / n
    mb = sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = (sum((r - ma) ** 2 for r in ra)) ** 0.5
    db = (sum((r - mb) ** 2 for r in rb)) ** 0.5
    if da == 0 or db == 0:
        return None
    return round(num / (da * db), 3)
