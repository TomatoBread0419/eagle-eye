#!/usr/bin/env bash
# pool_builder_runner.sh — 动态池粗筛 cron wrapper
set -euo pipefail
cd ~/stock_trader
LOGDIR=~/stock_trader/logs
mkdir -p "$LOGDIR"
LOG="$LOGDIR/pool_builder_$(date +%Y%m%d).log"
PYTHONPATH="C:/Users/23914" "C:/Users/23914/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe" pool_builder.py 2>&1 | tee -a "$LOG"
