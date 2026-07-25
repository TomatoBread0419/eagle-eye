import os, json, requests
from datetime import datetime

env_path = os.path.expanduser('~/.hermes/.env')
env = dict(line.strip().split('=', 1) for line in open(env_path) if '=' in line and not line.startswith('#'))

base = env.get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
headers = {
    'APCA-API-KEY-ID': env.get('ALPACA_API_KEY', ''),
    'APCA-API-SECRET-KEY': env.get('ALPACA_SECRET_KEY', '')
}

# 1. Open orders
orders = requests.get(f'{base}/v2/orders?status=open', headers=headers, timeout=30).json()
print('=== OPEN ORDERS ===')
for o in orders:
    extra = ''
    if o.get('stop_price'):
        extra = f' stop@{o["stop_price"]}'
    print(f"  {o['symbol']} {o['side']} {o['type']} qty={o['qty']} status={o['status']}{extra}")

# 2. Positions
positions = requests.get(f'{base}/v2/positions', headers=headers, timeout=30).json()
print(f'\n=== POSITIONS ({len(positions)}) ===')
for p in sorted(positions, key=lambda x: float(x['market_value']), reverse=True):
    print(f"  {p['symbol']} qty={p['qty']} avg=${float(p['avg_entry_price']):.2f} val=${float(p['market_value']):.0f} pl={float(p['unrealized_plpc'])*100:.1f}%")

# 3. Stop coverage audit
stop_syms = {o['symbol'] for o in orders if o.get('type') == 'stop' and o.get('side') == 'sell'}
sell_syms = {o['symbol'] for o in orders if o.get('type') != 'stop' and o.get('side') == 'sell'}
pos_syms = {p['symbol'] for p in positions}
covered = stop_syms | sell_syms
no_stop = sorted(pos_syms - covered)

print(f'\n=== STOP COVERAGE AUDIT ===')
print(f'  Stop orders: {len(stop_syms)} symbols: {sorted(stop_syms)}')
print(f'  Open sells: {len(sell_syms)} symbols: {sorted(sell_syms)}')
if no_stop:
    print(f'  ❌ NO STOP: {no_stop}')
else:
    print(f'  ✅ All {len(positions)} positions have stop or open-sell protection')

# 4. Check JPM sell market - is it a valid trade?
jpm_pos = [p for p in positions if p['symbol'] == 'JPM']
if jpm_pos:
    jpm = jpm_pos[0]
    jpm_stop = [o for o in orders if o['symbol'] == 'JPM' and o.get('type') == 'stop']
    jpm_sell = [o for o in orders if o['symbol'] == 'JPM' and o.get('type') != 'stop' and o['side'] == 'sell']
    print(f'\n=== JPM DETAIL ===')
    print(f'  Position: qty={jpm["qty"]} @ ${float(jpm["avg_entry_price"]):.2f}')
    print(f'  Stop order: {jpm_stop[0]["qty"] if jpm_stop else "NONE"}')
    print(f'  Sell market: {jpm_sell[0]["qty"] if jpm_sell else "NONE"}')
    print(f'  After sell: {int(jpm["qty"]) - (int(jpm_sell[0]["qty"]) if jpm_sell else 0)} remaining')
    print(f'  Stop covers: {int(jpm_stop[0]["qty"]) if jpm_stop else 0}')
    remaining = int(jpm['qty']) - (int(jpm_sell[0]['qty']) if jpm_sell else 0)
    stop_qty = int(jpm_stop[0]['qty']) if jpm_stop else 0
    match = remaining == stop_qty
    print(f'  After sell: {remaining} remaining, Stop covers: {stop_qty} → {"✅ Match" if match else "❌ Mismatch"}')
