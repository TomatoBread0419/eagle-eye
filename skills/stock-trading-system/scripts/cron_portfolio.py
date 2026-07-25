#!/usr/bin/env python3
"""
Quick portfolio snapshot — bypasses us_trader.py's heavy api_get() retry loops.

Use when:
  - us_trader.py is timing out (Alpaca slow/unreachable)
  - You need a fast read-only snapshot for cron reporting
  - You want to check positions without running full signal computation

Does NOT:
  - Compute signals or make trading decisions
  - Place orders or modify stops
  - Update risk state files

Reads: APCA_API_KEY_ID / APCA_API_SECRET_KEY from ~/.hermes/.env
       Falls back to ~/stock_trader/config.py if env vars missing.

Usage:
  python3 ~/stock_trader/cron_portfolio.py
"""
import urllib.request, json, os, sys

# Load API keys
env_path = os.path.expanduser("~/.hermes/.env")
api_key = api_secret = None
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "APCA_API_KEY_ID" in line and "=" in line:
            api_key = line.split("=", 1)[1].strip()
        elif "APCA_API_SECRET_KEY" in line and "=" in line:
            api_secret = line.split("=", 1)[1].strip()

if not api_key or not api_secret:
    sys.path.insert(0, os.path.expanduser("~/stock_trader"))
    from config import ALPACA_API_KEY, ALPACA_SECRET_KEY
    api_key, api_secret = ALPACA_API_KEY, ALPACA_SECRET_KEY

headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret}

# Account
req = urllib.request.Request("https://paper-api.alpaca.markets/v2/account", headers=headers)
resp = urllib.request.urlopen(req, timeout=10)
acct = json.loads(resp.read())
equity = float(acct.get("equity", 0))
cash = float(acct.get("cash", 0))
bp = float(acct.get("buying_power", 0))
print(f"Equity: ${equity:,.0f} | Cash: ${cash:,.0f} | BP: ${bp:,.0f}")

# Positions
req = urllib.request.Request("https://paper-api.alpaca.markets/v2/positions", headers=headers)
resp = urllib.request.urlopen(req, timeout=15)
positions = json.loads(resp.read())
print(f"\n持仓 ({len(positions)} 只):")
for p in sorted(positions, key=lambda x: -float(x.get("market_value", 0))):
    sym = p["symbol"]
    qty = int(p["qty"])
    mkt = float(p["market_value"])
    pnl = float(p.get("unrealized_plpc", 0)) * 100
    cost = float(p.get("avg_entry_price", 0))
    cur = float(p.get("current_price", 0))
    print(f"  {sym:5s} {qty:>4}股  成本${cost:>8.2f}  现价${cur:>8.2f}  市值${mkt:>10,.0f}  盈亏{pnl:>+6.1f}%")

# Open orders
req = urllib.request.Request("https://paper-api.alpaca.markets/v2/orders?status=open&limit=50", headers=headers)
resp = urllib.request.urlopen(req, timeout=10)
orders = json.loads(resp.read())
print(f"\n挂单 ({len(orders)} 笔):")
for o in orders:
    sym = o["symbol"]
    side = o["side"]
    qty = o.get("qty", "?")
    otype = o.get("type", "?")
    status = o.get("status", "?")
    print(f"  {sym:5s} {side:5s} {qty}股 @{otype} status={status}")
