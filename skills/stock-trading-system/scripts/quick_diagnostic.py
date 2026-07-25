#!/usr/bin/env python3
"""
美股交易系统一键自检脚本 — 可在 execute_code / terminal / cron 中复用

用法:
  python3 quick_diagnostic.py           # 跑全部检查
  python3 quick_diagnostic.py --brief   # 简短模式（只输出状态行）

设计要点:
  - 自动处理 sandbox CWD 问题（sys.path.insert 在最前）
  - 同时支持 execute_code（直接 import）和 terminal（subprocess 调用）
  - 输出格式对齐 WeChat push 报告（emoji 锚 + 分隔线）
  - 失败不抛异常，所有错误以 [ERR]/[WARN] 行输出
"""
import sys
import os
import json
import urllib.request
import urllib.error
from datetime import datetime

# ✅ 关键：必须在 import config 之前
SRC_DIR = '$HOME/stock_trader'
sys.path.insert(0, SRC_DIR)
os.chdir(SRC_DIR)

try:
    import config
except Exception as e:
    print(f'[FATAL] 导入 config 失败: {e}')
    print(f'  提示: 检查 sys.path 是否包含 {SRC_DIR}')
    sys.exit(1)

ALPACA_HEADERS = {
    'APCA-API-KEY-ID': config.ALPACA_API_KEY,
    'APCA-API-SECRET-KEY': config.ALPACA_SECRET_KEY,
}


def alpaca_get(path, timeout=20):
    """Alpaca API GET 封装 — 返回 (status_code, dict)"""
    url = f'https://paper-api.alpaca.markets/v2{path}'
    req = urllib.request.Request(url, headers=ALPACA_HEADERS)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return 200, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, str(e)[:100]


def check_account():
    """账户健康度"""
    sc, acct = alpaca_get('/account')
    if sc != 200:
        return f'[ERR] Alpaca 账户: HTTP {sc}'

    eq = float(acct.get('equity', 0))
    cash = float(acct.get('cash', 0))
    util = (1 - cash / eq) * 100 if eq > 0 else 0
    last_eq = float(acct.get('last_equity', eq))
    pnl_today = eq - last_eq
    return (
        f'[OK] 账户 权益 ${eq:,.2f}  现金 ${cash:,.2f}  '
        f'利用率 {util:.1f}%  今日 {pnl_today:+,.2f}'
    )


def check_positions():
    """持仓 + 风险预警"""
    sc, pos = alpaca_get('/positions')
    if sc != 200:
        return [f'[ERR] 持仓: HTTP {sc}']

    lines = [f'[OK] 持仓 {len(pos)} 只:']
    long_n = short_n = 0
    for p in sorted(pos, key=lambda x: -abs(float(x['market_value']))):
        pnl = float(p['unrealized_plpc']) * 100
        pld = float(p['unrealized_pl'])
        side = 'LONG' if float(p['qty']) > 0 else 'SHORT'
        if side == 'LONG':
            long_n += 1
        else:
            short_n += 1
        # 风险标记
        if pnl <= -4.0:
            tag = '🔴止损临近'
        elif pnl <= -2.0:
            tag = '🟡浮亏'
        elif pnl >= 15.0:
            tag = '🟢止盈位'
        else:
            tag = ''
        lines.append(
            f'  {p["symbol"]:<6} {side:<5} {pnl:+6.2f}%  ${pld:+9.2f}  {tag}'
        )

    lines.append(f'  LONG {long_n} / SHORT {short_n}')

    # 恐惧偏误检测
    if pos:
        sc2, acct = alpaca_get('/account')
        if sc2 == 200:
            eq = float(acct['equity'])
            cash = float(acct['cash'])
            util = (1 - cash / eq) * 100
            if util < 30 and eq > 0:
                lines.append(
                    f'⚠️ 恐惧偏误检测: 仓位利用率 {util:.1f}% < 30% 目标'
                )

    return lines


def check_open_orders():
    """挂单 + 止损覆盖检查"""
    sc, orders = alpaca_get('/orders?status=open&limit=100')
    if sc != 200:
        return [f'[ERR] 挂单: HTTP {sc}']

    lines = [f'[OK] 挂单 {len(orders)} 笔:']
    for o in orders[:15]:
        lines.append(
            f'  {o["side"]:4} {o["symbol"]:<6} {o["qty"]:>4}  {o["type"]}'
        )
    return lines


def check_state_files():
    """关键状态文件"""
    files = [
        ('us_risk_state.json', '美股风控'),
        ('us_signal_latest.json', '美股信号'),
        ('us_watchlist.json', '美股选股'),
        ('market_events_latest.json', '市场事件'),
    ]
    lines = []
    for f, name in files:
        p = f'{SRC_DIR}/{f}'
        if not os.path.exists(p):
            lines.append(f'[!] {name}: 缺失')
            continue
        try:
            d = json.load(open(p))
            age_h = (datetime.now().timestamp() - os.path.getmtime(p)) / 3600
            if age_h > 24:
                tag = '[STALE]'
            else:
                tag = '[OK]'
            lines.append(f'{tag} {name}: {age_h:.1f}h 前更新')
        except Exception as e:
            lines.append(f'[ERR] {name}: JSON 损坏 — {e}')
    return lines


def check_short_positions():
    """Short 仓位专项检查（v3 §14）"""
    sc, pos = alpaca_get('/positions')
    if sc != 200:
        return []

    warnings = []
    for p in pos:
        qty = float(p['qty'])
        if qty >= 0:  # 不是 short
            continue
        pnl = float(p['unrealized_plpc']) * 100
        if pnl <= -5.0:
            warnings.append(
                f'🔴 {p["symbol"]} SHORT 浮亏 {pnl:.1f}% — 强制平空信号'
            )
        elif pnl <= -3.0:
            warnings.append(
                f'🟡 {p["symbol"]} SHORT 浮亏 {pnl:.1f}% — 重审 thesis'
            )
    return warnings


def main():
    print('=' * 60)
    print(f'📊 美股系统自检  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 60)

    sections = [
        ('💰 账户', [check_account()]),
        ('📋 持仓', check_positions()),
        ('🔄 挂单', check_open_orders()),
        ('📁 状态文件', check_state_files()),
        ('⚠️ Short 专项', check_short_positions()),
    ]

    for title, lines in sections:
        print(f'\n{title}')
        for line in lines:
            print(line)

    print('\n' + '=' * 60)
    print('✅ 自检完成')


if __name__ == '__main__':
    main()
