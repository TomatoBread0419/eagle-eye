"""
execution/position_manager.py — 持仓状态管理 + 技术分析 (V7.1 Phase 3)

从 us_trader.py 提取，所有 Alpaca API 通信通过 AlpacaClient。
逻辑与原始完全相同，无任何计算、阈值或策略改动。
"""

import json
import os
import time
from typing import Optional, Dict, Any, List

from eagle_eye.core.config import cfg
from eagle_eye.core.logger import get_logger
from eagle_eye.core.http import http_get
from eagle_eye.broker.alpaca_client import get_alpaca_client

from eagle_eye.strategy.indicator_engine import (
    calc_rsi, calc_sma, calc_boll, calc_volatility,
    calc_volume_metrics, calc_macd, calc_atr,
    get_volatility_stop_pct,
)

logger = get_logger('execution.position')

# Alpaca market data URL and headers
DATA_URL = cfg.alpaca_data_url
HEADERS = cfg.alpaca_headers

# 风控参数（从 us_trader.py 原样复制）
TP_RSI_SELL = 80            # RSI > 80 卖 50%（基准）
TP_DRAWDOWN_PCT = 0.08      # 从20根K线最高点回落 >8% 卖全部

# ======================== 状态文件管理 ========================

def load_state() -> dict:
    """读取风险状态文件"""
    state_file = cfg.data_dir / 'us_risk_state.json'
    try:
        with open(state_file) as f:
            return json.load(f)
    except:
        return {'peak_equity': 0, 'positions': {}, 'paused_drawdown': False, 'report_date': ''}


def save_state(state: dict) -> None:
    """保存风险状态文件"""
    state_file = cfg.data_dir / 'us_risk_state.json'
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2, default=str)


def get_highest(sym: str, state: dict) -> float:
    """获取某标的的最高价记录"""
    return state.get('positions', {}).get(sym, {}).get('highest', 0)


def set_highest(sym: str, price: float, state: dict, cost: Optional[float] = None) -> None:
    """更新某标的的最高价记录

    v4.6 修复：entry_cost 变化 → 直接重置 highest（新仓位）
    之前用 abs(price - stored_cost)/stored_cost > 0.30 启发式，
    相近成本开新仓时无法检测，旧 highest 毒化追踪止损
    """
    if 'positions' not in state:
        state['positions'] = {}
    if sym not in state['positions']:
        state['positions'][sym] = {'highest': 0, 'trail_trigger': 0, 'entry_cost': cost or 0}
    pos = state['positions'][sym]
    if cost and pos.get('entry_cost', 0) > 0:
        stored_cost = pos.get('entry_cost', 0)
        if stored_cost != cost:
            pos['highest'] = max(price, cost)
            pos['entry_cost'] = cost
            pos['trail_trigger'] = 0
            return
    if price > pos['highest']:
        pos['highest'] = price
    if cost:
        pos['entry_cost'] = cost


def get_trail_stop(sym: str, state: dict, cost_basis: float, vol_20d: Optional[float] = None) -> float:
    """计算追踪止损价（波动率分档）

    参数:
        vol_20d: 20日年化波动率（百分比），None 时使用默认 8%
    """
    stop_pct = get_volatility_stop_pct(vol_20d)
    pos = state.get('positions', {}).get(sym, {})
    highest = pos.get('highest', cost_basis)
    trail_stop = highest * (1 - stop_pct)
    # 最低不低于初始止损
    init_stop = cost_basis * (1 - stop_pct)
    return max(trail_stop, init_stop)


# ======================== 板块映射 ========================

SECTOR_MAP = {
    'NVDA': '🌟半导体', 'AMD': '🌟半导体', 'AMAT': '🌟半导体', 'INTC': '🌟半导体', 'TSM': '🌟半导体',
    'AVGO': '🌟半导体', 'MU': '🌟半导体', 'TXN': '🌟半导体', 'QCOM': '🌟半导体', 'ARM': '🌟半导体',
    'AAPL': '🍎消费科技', 'MSFT': '🍎消费科技', 'GOOGL': '🍎消费科技', 'META': '🍎消费科技',
    'KO': '🍎消费', 'PEP': '🍎消费', 'WMT': '🍎消费', 'COST': '🍎消费', 'SBUX': '🍎消费',
    'JPM': '💰金融', 'BAC': '💰金融', 'GS': '💰金融', 'C': '💰金融', 'MS': '💰金融', 'BLK': '💰金融', 'V': '💰金融', 'MA': '💰金融',
    'CAT': '🏭工业', 'BA': '🏭工业', 'GE': '🏭工业', 'HON': '🏭工业',
    'XOM': '⚡能源', 'CVX': '⚡能源',
    'LLY': '💊医药', 'PFE': '💊医药', 'JNJ': '💊医药', 'UNH': '💊医药',
    'TSLA': '⚠️新能源',
}


def get_sector(sym: str) -> str:
    """获取标的所属板块"""
    return SECTOR_MAP.get(sym, '其他')


# ======================== 市场数据获取（通过 AlpacaClient）========================

def __get_daily_bars(symbol: str) -> list:
    """获取日K线数据（通过 AlpacaClient）"""
    client = get_alpaca_client()
    return client.get_bars(symbol, days=100)


def __get_us_price(symbol: str) -> Optional[float]:
    """获取最新成交价（通过 AlpacaClient）"""
    client = get_alpaca_client()
    return client.get_last_price(symbol)


def __get_volatility(symbol: str) -> Optional[float]:
    """获取某只股票的 20 日年化波动率（用于波动率分档止损）"""
    bars = __get_daily_bars(symbol)
    if not bars or len(bars) < 21:
        return None
    closes = [b['c'] for b in bars]
    return calc_volatility(closes, 20)


# ======================== K线获取 ========================

def get_bars(symbol: str, limit: int = 30) -> Optional[list]:
    """优先小时K线，不足时回退到日K（免费层小时K仅4条，日K稳定60+）"""
    # 先试小时K（直接用 urllib，市场数据非交易 API）
    url = f'{DATA_URL}/{symbol}/bars?timeframe=1Hour&limit={limit}'
    for attempt in range(2):
        try:
            sc, body = http_get(url, headers=HEADERS, timeout=15)
            if sc == 200:
                bars = json.loads(body).get('bars')
                if bars is not None and len(bars) >= 20:
                    return bars
                break
        except Exception:
            if attempt < 1:
                time.sleep(3)
            else:
                break
    # 回退：日K线（免费层可靠）
    return __get_daily_bars(symbol)


# ======================== 技术分析 ========================

def analyze(symbol: str) -> Optional[dict]:
    """返回分析结果，包含卖出信号"""
    bars = get_bars(symbol)
    if not bars:
        return None

    closes = [b['c'] for b in bars]
    highs = [b['h'] for b in bars]
    price = closes[-1]
    prev = closes[-2] if len(closes) > 1 else price
    chg = (price - prev) / prev * 100

    rsi14 = calc_rsi(closes, 14)
    lower, mid, upper = calc_boll(closes, 20)
    ma5 = calc_sma(closes, 5)
    ma20 = calc_sma(closes, 20)

    # 买入信号
    buy_score = 0
    buy_reasons = []
    if rsi14 and rsi14 < 35:
        buy_score += 2
        buy_reasons.append(f'RSI超卖({rsi14})')
    if lower and price < lower:
        buy_score += 2
        buy_reasons.append('触及布林下轨')
    if ma5 and ma20:
        if price > ma5 and ma5 > ma20:
            buy_score += 1
            buy_reasons.append('均线多头')

    # v4.3: 成交量确认
    volumes = [b.get('v', 0) for b in bars] if bars and 'v' in bars[0] else []
    if volumes and sum(volumes) > 0:
        vm = calc_volume_metrics(volumes, closes)
        if vm:
            conf = vm.get('confirmation', 'neutral')
            if conf == 'bullish':
                buy_score += 2
                buy_reasons.append('放量上涨确认')
            elif conf == 'divergence':
                buy_score -= 2
                buy_reasons.append('缩量虚涨预警')
            elif conf == 'bearish':
                buy_score -= 1
                buy_reasons.append('放量下跌警示')

    # 卖出/止盈信号
    sell_reason = None
    # v4.7 修复: 用收盘价算回撤，不用日内最高价（虚假回撤 bug）
    # 日内最高价可大幅偏离收盘价 → "回撤15.9%"实际回撤<1%
    recent_high_20 = max(closes[-20:]) if len(closes) >= 20 else max(closes)
    tp_rsi = TP_RSI_SELL

    if rsi14 and rsi14 > tp_rsi:
        sell_reason = f'RSI超买极端({rsi14}/{tp_rsi})→卖50%'
    elif price < recent_high_20 * (1 - TP_DRAWDOWN_PCT):
        drop_pct = (recent_high_20 - price) / recent_high_20 * 100
        sell_reason = f'从高点回撤{drop_pct:.1f}%→卖全部'

    trend = '上涨' if ma5 and ma20 and ma5 > ma20 else ('下跌' if ma5 and ma20 and ma5 < ma20 else '震荡')

    # v4.2: 顺手算波动率（已有 closes，零额外 API 成本）
    vol_20d = calc_volatility(closes, 20)

    # v4.4: MACD + ATR
    macd_line, signal_line, histogram, crossover = calc_macd(closes)
    if crossover == 'golden':
        buy_score += 3
        buy_reasons.append('MACD金叉')
    elif crossover == 'death':
        buy_score -= 2
        buy_reasons.append('MACD死叉')
    elif histogram and histogram > 0:
        buy_score += 1

    highs_bars = [b.get('h', b.get('c', 0)) for b in bars]
    lows_bars = [b.get('l', b.get('c', 0)) for b in bars]
    atr = calc_atr(highs_bars, lows_bars, closes)

    return {
        'symbol': symbol, 'price': price, 'change_pct': round(chg, 2),
        'rsi': rsi14, 'ma5': ma5, 'ma20': ma20,
        'boll_lower': lower, 'boll_mid': mid, 'boll_upper': upper,
        'trend': trend, 'buy_score': buy_score, 'buy_reasons': buy_reasons,
        'sell_reason': sell_reason, 'recent_high': recent_high_20,
        'bars_count': len(closes), 'vol_20d': vol_20d,
        'macd_histogram': histogram, 'macd_crossover': crossover,
        'atr': atr, 'atr_pct': round(atr / price * 100, 1) if atr and price else None,
    }

# ════════════════════════════════════════════════════
# Tech snapshot (from us_trader.py)
# ════════════════════════════════════════════════════

def tech_snapshot(symbols, max_show=10):
    """对一批股票做技术面快照。逻辑完全不变。"""
    snapshots = []
    alerts = []

    for sym in symbols[:max_show]:
        bars = get_bars(sym)
        if not bars or len(bars) < 20:
            continue
        closes = [b['c'] for b in bars]
        highs = [b['h'] for b in bars]
        price = closes[-1]
        rsi14 = calc_rsi(closes, 14)
        lower, mid, upper = calc_boll(closes, 20)
        ma5 = calc_sma(closes, 5)
        ma20 = calc_sma(closes, 20)

        trend = '→' if ma5 and ma20 and abs(ma5/ma20-1)<0.01 else \
                '↗' if ma5 and ma20 and ma5 > ma20 else \
                '↘' if ma5 and ma20 and ma5 < ma20 else '?'

        bb_pos = '上轨外' if upper and price > upper else \
                 '上半区' if mid and price > mid else \
                 '下半区' if mid and price >= lower else \
                 '下轨外' if lower and price < lower else '?'

        if len(highs) >= 20:
            high20 = max(highs[-20:])
            low20 = min([b['l'] for b in bars[-20:]])
            range20 = high20 - low20
            range_pos = (price - low20) / range20 * 100 if range20 > 0 else 50
        else:
            range_pos = 50

        snap = {'sym': sym, 'price': price, 'rsi': rsi14,
                'trend': trend, 'bb_pos': bb_pos, 'range_pos': range_pos}
        snapshots.append(snap)

        signal = None
        if rsi14 is not None:
            if rsi14 < 30:
                signal = f'🔥 {sym} RSI={rsi14} 超卖 → 可能反弹'
            elif rsi14 > 85:
                signal = f'⚠️ {sym} RSI={rsi14} 极度超买 → 警惕回调'
        if not signal and lower and price < lower:
            signal = f'💡 {sym} 跌破布林下轨 ${lower:.2f} → 统计反弹机会'
        elif not signal and upper and price > upper:
            signal = f'⚠️ {sym} 突破布林上轨 ${upper:.2f} → 可能回调'

        if signal:
            alerts.append(signal)
            snap['signal'] = signal

    return {'snapshots': snapshots, 'alerts': alerts}
