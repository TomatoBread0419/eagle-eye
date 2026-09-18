#!/usr/bin/env bash
set -euo pipefail
cd ~/stock_trader
python3 "C:/Users/23914/.hermes/scripts/post_incident_observation.py" eod 2>&1
