#!/usr/bin/env python3
"""
硬约束验证脚本（2026-06-04 用户授权）
  独立检查 us_trader.py 是否真的在机械执行 3 条硬约束。
  可以随时手跑：`python3 verify_hard_constraints.py`
  不会下单，只读代码 + 当前账户状态做静态分析。
"""
import sys, os, re, json
from datetime import datetime, timezone, timedelta

SRC_DIR = '$HOME/stock_trader'
sys.path.insert(0, SRC_DIR)
os.chdir(SRC_DIR)

import urllib.request
import config

HEADERS = {
    'APCA-API-KEY-ID': config.ALPACA_API_KEY,
    'APCA-API-KEY-SECRET': config.ALPACA_SECRET_KEY,
    'APCA-API-SECRET-KEY': config.ALPACA_SECRET_KEY,
    'Content-Type': 'application/json',
}
TRADE_URL = 'https://paper-api.alpaca.markets/v2'

def api_get(path):
    req = urllib.request.Request(f'{TRADE_URL}{path}', headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except Exception as e:
        return 0, str(e)

def main():
    print('═' * 60)
    print('🔧 硬约束验证 | 2026-06-04 用户授权')
    print(f'   时间 {datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")} BJT')
    print('═' * 60)

    # ── 1. 静态代码检查 ──
    print('\n📋 第一部分：us_trader.py 静态检查')
    src_path = '$HOME/.hermes/scripts/us_trader.py'
    content = open(src_path).read()

    checks = [
        ('常量 HARD_UTIL_FLOOR 已定义', 'HARD_UTIL_FLOOR = 0.38' in content),
        ('常量 HARD_MIN_BUY_PER_RUN 已定义', 'HARD_MIN_BUY_PER_RUN = 1' in content),
        ('常量 HARD_PAIR_RATIO 已定义', 'HARD_PAIR_RATIO' in content),
        ('6b 段 sell→buy 真下 market buy（不是只 print）',
         'place_market_order(sym, qty, \'buy\')' in content and '配对' in content),
        ('6e 硬约束块存在（注释 "═══ 6e. 硬约束块"）',
         '6e. 硬约束块' in content),
        ('6e 块 fallback 到 all_ranked', "'all_ranked'" in content),
        ('6e 块候选 ≥ 3 → 默认选 pool[0]', 'pool = list(dict.fromkeys' in content),
        ('6e 块用 limit 单 + client_order_id 标识', "client_order_id': f'hardutil_" in content),
        ('6e 块失败必报告（不静默）', '🔴 硬约束失败' in content),
    ]
    for desc, ok in checks:
        print(f'  {"✅" if ok else "❌"} {desc}')

    # ── 2. 实时账户检查 ──
    print('\n💰 第二部分：当前账户状态 vs 硬约束')
    sc, acct = api_get('/account')
    if sc != 200:
        print(f'  ❌ Alpaca API 失败: {sc}')
        return
    equity = float(acct['equity'])  # type: ignore[index]
    cash = float(acct['cash'])  # type: ignore[index]
    util = (equity - cash) / equity
    util_pct = util * 100
    print(f'  权益: ${equity:,.2f}')
    print(f'  现金: ${cash:,.2f}')
    print(f'  持仓市值: ${equity - cash:,.2f}')
    print(f'  仓位利用率: {util_pct:.1f}%')
    print(f'  硬约束 HARD_UTIL_FLOOR: {38.0:.1f}%')
    if util_pct < 38.0:
        print(f'  🔴 触发硬约束：util {util_pct:.1f}% < 38.0%')
        print(f'     → 当次 cron 必须至少产生 1 笔 buy_order')
        print(f'     → us_trader.py §6e 块应自动执行')
    else:
        print(f'  ✅ 仓位 {util_pct:.1f}% ≥ 38%：本轮硬约束不触发')

    # ── 3. 持仓数 vs sell→buy 配对 ──
    print('\n📋 第三部分：当前持仓')
    sc, pos = api_get('/positions')
    if sc == 200:
        held = [p['symbol'] for p in pos]
        print(f'  持仓数: {len(held)} 只')
        for p in sorted(pos, key=lambda x: float(x['market_value']), reverse=True):
            mv = float(p['market_value'])
            pnl = float(p['unrealized_plpc']) * 100
            print(f'    {p["symbol"]:6s} {p["qty"]:>4s}股  ${mv:>9,.2f}  P/L {pnl:+.2f}%')
    else:
        print(f'  ❌ 持仓 API 失败: {sc}')

    # ── 4. us_watchlist.json 检查 ──
    print('\n📂 第四部分：us_watchlist.json 候选池')
    wl_path = f'{SRC_DIR}/us_watchlist.json'
    if os.path.exists(wl_path):
        wl = json.load(open(wl_path))
        age_h = (os.path.getmtime(wl_path) - 0) / 3600  # 简化
        mtime = datetime.fromtimestamp(os.path.getmtime(wl_path))
        age_h = (datetime.now().timestamp() - os.path.getmtime(wl_path)) / 3600
        print(f'  存在 (mtime {mtime.strftime("%m-%d %H:%M")}, age {age_h:.1f}h)')
        for key in ['buy_candidates', 'top10', 'all_ranked']:
            v = wl.get(key, [])
            print(f'  {key}: {len(v)} 个')
            if key == 'all_ranked' and v:
                # 展示 top 5
                for i, x in enumerate(v[:5]):
                    if isinstance(x, dict):
                        print(f'    #{i+1} {x.get("symbol","?")} score={x.get("score","?")}')
                    else:
                        print(f'    #{i+1} {x}')
    else:
        print(f'  ❌ 不存在（硬约束块会失败）')
        print(f'     先跑: python3 us_screener.py')

    # ── 5. 总结 ──
    print('\n' + '═' * 60)
    all_static = all(ok for _, ok in checks)
    if all_static and util_pct < 38.0:
        print('🟡 当前硬约束应触发。下一个 cron tick (北京 21:10+) 将自动 buy。')
    elif all_static:
        print('✅ 所有硬约束已就位。仓位 ≥ 38%，本轮不触发。')
    else:
        print('❌ 静态检查未通过，需 patch us_trader.py')
    print('═' * 60)

if __name__ == '__main__':
    main()
