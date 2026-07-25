#!/usr/bin/env python3
"""Stop coverage audit for cron job."""
import os, requests, json
from datetime import datetime, timedelta

env = dict(line.strip().split("=", 1) for line in open(os.path.expanduser("~/.hermes/.env")) if "=" in line and not line.startswith("#"))
base = env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
headers = {"APCA-API-KEY-ID": env.get("ALPACA_API_KEY",""), "APCA-API-SECRET-KEY": env.get("ALPACA_SECRET_KEY","")}

# 1. Positions
r = requests.get(f"{base}/v2/positions", headers=headers, timeout=30)
positions = r.json()
print(f"  Positions: {len(positions)}")
for p in positions:
    print(f"    {p['symbol']}: {p['qty']}sh @${float(p['avg_entry_price']):.2f}")

# 2. Open orders
r = requests.get(f"{base}/v2/orders?status=open", headers=headers, timeout=30)
orders = r.json()
print(f"\n  Open orders: {len(orders)}")
stop_syms = set(); sell_syms = set()
for o in orders:
    otype = o.get("type","?"); side = o.get("side","?"); sym = o.get("symbol","?")
    if otype == "stop" and side == "sell": stop_syms.add(sym)
    if side == "sell" and otype != "stop": sell_syms.add(sym)
    print(f"    {sym} {side} {otype} qty={o['qty']} status={o.get('status','?')}")

# 3. Coverage audit
pos_syms = {p["symbol"] for p in positions}
no_stop = pos_syms - stop_syms
no_protect = no_stop - sell_syms
print(f"\n  Coverage audit:")
print(f"    With stop: {len(stop_syms)}/{len(positions)} {sorted(stop_syms)}")
print(f"    No stop: {len(no_stop)} {sorted(no_stop) if no_stop else 'ALL COVERED'}")
print(f"    Non-stop sell: {len(sell_syms)} {sorted(sell_syms) if sell_syms else 'none'}")
print(f"    Unprotected: {len(no_protect)} {sorted(no_protect) if no_protect else 'ALL COVERED'}")

# 4. ARM recent stops
days_7 = (datetime.now() - timedelta(days=7)).isoformat()
r = requests.get(f"{base}/v2/orders?symbols=ARM&status=filled&limit=25&after={days_7}", headers=headers, timeout=30)
arm_orders = r.json()
arm_stops = [o for o in arm_orders if o.get("type")=="stop" and o.get("side")=="sell"]
print(f"\n  ARM stop loss last 7d: {len(arm_stops)} fills")
for o in arm_stops:
    print(f"    {o.get('filled_at','?')} qty={o['qty']} @${o.get('filled_avg_price','?')}")
