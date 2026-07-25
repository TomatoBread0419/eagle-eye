#!/usr/bin/env python3
"""Phase 3 — 周末复盘脚本（每周六）
读取 events_log → 计算已实现/浮动 PnL → 更新 scoreboard.json → 推微信复盘报告"""
import json, os, sys, subprocess
from datetime import datetime, timezone, timedelta
from collections import defaultdict

HOME = os.path.expanduser('~')
STOCK_DIR = os.path.join(HOME, 'stock_trader')
BJT = timezone(timedelta(hours=8))

sys.path.insert(0, HOME)

def load_json(path):
    if not os.path.exists(path): return None
    with open(path) as f: return json.load(f)

def save_json(path, data):
    with open(path, 'w') as f: json.dump(data, f, ensure_ascii=False, indent=2)

def send_weixin(msg):
    try:
        subprocess.run(['hermes', 'send', '-t', 'weixin', msg],
                       capture_output=True, text=True, timeout=30)
    except: pass

def resolve_style(reason, event_map):
    """从 reason 字段（如 '地缘/台海 🔴 利空'）解析风格"""
    for sector, info in event_map.items():
        if sector in reason:
            return info.get('style', 'chain')
    return 'chain'

def calculate_pnl(trade, alpaca_positions):
    """计算单笔交易 PnL"""
    sym = trade['symbol']
    entry_price = trade['price']
    qty = trade['qty']

    # 优先用 Alpaca 实际数据（持仓还在）
    if sym in alpaca_positions:
        current = float(alpaca_positions[sym]['current_price'])
        pnl = (current - entry_price) * qty
        pnl_pct = (current - entry_price) / entry_price * 100
        status = 'open'
        return pnl, pnl_pct, status

    # 持仓不在 → 已退出（止损/止盈），用 stop 价格估算
    stop = trade.get('stop', 0)
    if stop > 0:
        pnl = (stop - entry_price) * qty
        pnl_pct = (stop - entry_price) / entry_price * 100
        status = 'closed_estimated'
        return pnl, pnl_pct, status

    return 0.0, 0.0, 'unknown'

def update_scoreboard(scoreboard, style, pnl, pnl_pct):
    """更新单风格分数"""
    s = scoreboard['styles'].get(style, scoreboard['styles']['chain'])
    s['trades'] += 1
    s['total_pnl'] = round(s['total_pnl'] + pnl, 2)

    if pnl > 0:
        s['wins'] += 1
        s['consecutive_wins'] += 1
        s['consecutive_losses'] = 0
        s['score'] += 5
    else:
        s['losses'] += 1
        s['consecutive_losses'] += 1
        s['consecutive_wins'] = 0
        s['score'] -= 10

    # 连续亏损暂停
    if s['consecutive_losses'] >= scoreboard.get('rules', {}).get('consecutive_loss_pause', 4):
        s['status'] = 'paused'
        s['score'] = max(s['score'], 0)

    # 最低分
    s['score'] = max(s['score'], 0)

def main():
    from dotenv import load_dotenv; load_dotenv(override=True)
    from eagle_eye.broker.alpaca_client import get_alpaca_client

    log_data = load_json(os.path.join(STOCK_DIR, 'events_log.json'))
    scoreboard = load_json(os.path.join(STOCK_DIR, 'scoreboard.json'))
    event_map = load_json(os.path.join(STOCK_DIR, 'event_map.json'))

    if not log_data or not scoreboard or not event_map:
        print("缺少必要文件"); return

    c = get_alpaca_client()
    alpaca_positions = {p['symbol']: p for p in c.get_positions()}

    # 按风格汇总 PnL
    style_pnl = defaultdict(lambda: {'pnl': 0.0, 'trades': 0, 'wins': 0})
    weekly_trades = []

    now = datetime.now(BJT)
    week_ago = now - timedelta(days=7)

    for e in log_data.get('events', []):
        if e.get('action') != 'executed':
            continue

        exec_at = e.get('executed_at', '')
        try:
            exec_dt = datetime.fromisoformat(exec_at.replace('+08:00', '')).replace(tzinfo=BJT)
        except:
            continue

        # 只统计最近一周
        if exec_dt < week_ago:
            continue

        for d in e.get('details', []):
            sym = d['symbol']
            reason = d.get('reason', '')
            style = resolve_style(reason, event_map)

            pnl, pnl_pct, status = calculate_pnl(d, alpaca_positions)

            style_pnl[style]['pnl'] += pnl
            style_pnl[style]['trades'] += 1
            if pnl > 0:
                style_pnl[style]['wins'] += 1

            weekly_trades.append({
                'symbol': sym,
                'style': style,
                'pnl': round(pnl, 2),
                'pnl_pct': round(pnl_pct, 1),
                'status': status,
                'entry': d['price'],
            })

            update_scoreboard(scoreboard, style, pnl, pnl_pct)

    # 保存 scoreboard
    scoreboard['updated_at'] = now.strftime('%Y-%m-%d')
    save_json(os.path.join(STOCK_DIR, 'scoreboard.json'), scoreboard)

    # 生成复盘报告
    lines = [f"📊 事件交易周报 | {now.strftime('%m-%d')}", ""]

    for style, info in sorted(style_pnl.items()):
        wins = info['wins']
        total = info['trades']
        pnl = info['pnl']
        emoji = '🟢' if pnl >= 0 else '🔴'
        win_rate = f"{wins/total*100:.0f}%" if total > 0 else "N/A"
        lines.append(f"  {emoji} {style}: {total}笔 | 胜率 {win_rate} | PnL ${pnl:+,.2f}")

    if weekly_trades:
        lines.append("")
        lines.append("本周明细:")
        for t in weekly_trades:
            emoji = '📈' if t['pnl'] >= 0 else '📉'
            lines.append(f"  {emoji} {t['symbol']}: ${t['pnl']:+.2f} ({t['pnl_pct']:+.1f}%) | {t['style']}")

    # 分数板摘要
    lines.append("")
    lines.append("风格分数:")
    for style, info in scoreboard['styles'].items():
        status_emoji = '✅' if info['status'] == 'active' else '⏸'
        lines.append(f"  {status_emoji} {style}: {info['score']}分 | 总PnL ${info['total_pnl']:+,.2f} | 胜率 {info['wins']}/{info['trades']}")

    report = '\n'.join(lines)
    print(report)
    send_weixin(report)
    print("\n✅ 周报已推微信")

if __name__ == '__main__':
    main()
