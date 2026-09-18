#!/usr/bin/env bash
set -euo pipefail
cd ~/stock_trader
"C:/Users/23914/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe" tools/event_executor.py 2>&1
