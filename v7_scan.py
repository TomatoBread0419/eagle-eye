#!/usr/bin/env python3
"""V7 native screener entry point — drop-in replacement for us_screener.py"""
import os, sys
os.chdir(os.path.expanduser('~/stock_trader'))
# Ensure ~ is on PYTHONPATH
home = os.path.expanduser('~')
if home not in sys.path:
    sys.path.insert(0, home)
from eagle_eye.strategy.screener import run_scan
run_scan(mode='normal')
