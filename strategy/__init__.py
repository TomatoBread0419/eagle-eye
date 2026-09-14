"""
strategy/ — 策略层 (V7.1 Phase 4)

Self-contained market strategy modules.
No sys.path dependencies. No us_common imports.
All Alpaca communication through broker/.

Modules:
  indicator_engine.py  — Pure-math technical indicators (RSI, MACD, ATR, etc.)
  market_env.py        — Macro context + market breadth scanner (merged)
  market_breadth.py    — Market breadth health scanner
  signal_decay.py      — Signal decay detection for positions
"""

from eagle_eye.strategy.indicator_engine import (
    calc_rsi, calc_sma, calc_boll, calc_macd, calc_atr,
    calc_volume_metrics, calc_volatility, get_volatility_stop_pct,
    calc_correlation, get_yf_metrics,
)
from eagle_eye.strategy.market_env import (
    get_vix, get_dxy, get_10y_yield, get_2y_yield,
    get_fomc_calendar, interpret_macro, interpret_breadth,
)
from eagle_eye.strategy.market_breadth import main as scan_breadth
from eagle_eye.strategy.signal_decay import main as scan_signal_decay
from eagle_eye.strategy.screener import run_scan

__all__ = [
    'calc_rsi', 'calc_sma', 'calc_boll', 'calc_macd', 'calc_atr',
    'calc_volume_metrics', 'calc_volatility', 'get_volatility_stop_pct',
    'calc_correlation', 'get_yf_metrics',
    'get_vix', 'get_dxy', 'get_10y_yield', 'get_2y_yield',
    'get_fomc_calendar', 'interpret_macro', 'interpret_breadth',
    'scan_breadth', 'check_decay', 'scan_signal_decay',
]
