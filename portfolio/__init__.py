"""
portfolio/ — 投资组合管理层 (V7.1 Phase 5)

Architecture:
  Market Environment → Signal Engine → Portfolio Manager
  → Allocation Engine → Kelly Engine → Execution Layer

Kelly Engine is a PURE CALCULATOR — provides theoretical sizing values.
Portfolio Manager decides allocations — Kelly only informs, never controls.

Modules:
  kelly_engine.py       — Kelly criterion calculator (f* = p - q/b)
  allocation_engine.py   — Dynamic per-position sizing (score→sigmoid→p, ATR→b)
  portfolio_manager.py   — Holdings audit, sector gaps, risk flags, reporting
"""

from eagle_eye.portfolio.kelly_engine import calc_kelly, fifo_match, load_orders, kelly_main
from eagle_eye.portfolio.allocation_engine import kelly_position_sizes
from eagle_eye.portfolio.portfolio_manager import (
    analyze_portfolio, print_report, SECTOR_MAP, SECTOR_RECOMMENDATIONS,
)

__all__ = [
    'calc_kelly', 'fifo_match', 'load_orders', 'kelly_main',
    'kelly_position_sizes',
    'analyze_portfolio', 'print_report', 'SECTOR_MAP', 'SECTOR_RECOMMENDATIONS',
]
