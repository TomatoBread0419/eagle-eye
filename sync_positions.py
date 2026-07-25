#!/usr/bin/env python3
"""Read Alpaca real-time positions & account → overwrite us_portfolio.json."""
import requests, json, os, sys
from datetime import datetime, timezone

def _env(name):
    """Try both naming conventions."""
    for n in [name, name.replace("ALPACA_","APCA_")]:
        v = os.environ.get(n, "")
        if v: return v
    return ""

KEY    = _env("ALPACA_API_KEY")
SECRET = _env("ALPACA_SECRET_KEY")
BASE   = os.environ.get("ALPACA_BASE_URL","https://paper-api.alpaca.markets")

if not KEY or not SECRET:
    sys.exit("FATAL: Alpaca keys not found in environment")
    
auth = {"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SECRET}
now  = datetime.now(timezone.utc).isoformat()
port = {"positions":[], "total_market_value":0,
        "equity":0, "cash":0, "buying_power":0,
        "synced_at": now, "synced_from": BASE}

try:
    pos_raw = requests.get(f"{BASE}/v2/positions", headers=auth, timeout=10)
    acct_raw= requests.get(f"{BASE}/v2/account"  , headers=auth, timeout=10)
    pos_raw.raise_for_status()
    acct_raw.raise_for_status()
except Exception as e:
    sys.exit(f"Alpaca API error: {e}")

positions = pos_raw.json()
account   = acct_raw.json()

for p in positions:
    mv   = float(p["market_value"])
    pl   = float(p["unrealized_pl"])
    plpc = float(p["unrealized_plpc"]) * 100 if p.get("unrealized_plpc") else 0.0
    port["positions"].append({
        "symbol": p["symbol"], "qty": p["qty"],
        "market_value": round(mv,2), "unrealized_pl": round(pl,2),
        "unrealized_plpc": round(plpc,2),
        "avg_entry_price": float(p["avg_entry_price"]),
        "cost_basis": float(p["cost_basis"]),
        "side": p["side"], "asset_class": p.get("asset_class",""),
    })
    port["total_market_value"] += mv

port["equity"]       = round(float(account["equity"]),2)
port["cash"]         = round(float(account["cash"]),2)
port["buying_power"] = round(float(account["buying_power"]),2)
port["status"]       = account.get("status","UNKNOWN")
port["position_count"] = len(port["positions"])

path = os.path.expanduser("~/stock_trader/us_portfolio.json")
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path,"w",encoding="utf-8") as f:
    json.dump(port, f, indent=2, ensure_ascii=False)

# --- print report ---
print("=== ALPACA 实时仓位 ===")
for p in port["positions"]:
    print(f"  {p['symbol']:5s}  qty={p['qty']:>8s}  mkt=${p['market_value']:>10,.2f}  pl=${p['unrealized_pl']:>+8,.2f}  plpc={p['unrealized_plpc']:>+6.2f}%")
print(f"\n仓位数:   {port['position_count']}")
print(f"市值:     ${port['total_market_value']:,.2f}")
print(f"Equity:   ${port['equity']:,.2f}")
print(f"Cash:     ${port['cash']:,.2f}")
print(f"利用率:   {port['total_market_value']/max(port['equity'],1)*100:.1f}%")
print(f"Status:   {port['status']}")
print(f"快照时间: {port['synced_at']}")
print(f"\n已写入: {path}")
