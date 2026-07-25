#!/usr/bin/env python3
"""V7 native portfolio analyzer — drop-in replacement for us_portfolio.py"""
import os, sys
os.chdir(os.path.expanduser('~/stock_trader'))
home = os.path.expanduser('~')
if home not in sys.path:
    sys.path.insert(0, home)
from eagle_eye.portfolio.portfolio_manager import analyze_portfolio, print_report
result = analyze_portfolio(target_util=0.85, mode='aggressive')
print_report(result)
