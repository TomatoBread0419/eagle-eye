#!/usr/bin/env python3
"""Phase 3 — 事件退出检查器（每天盘前）
读取 events_log 的 executed 记录 → 对比 Alpaca 实际持仓 → 检查退出条件 → 推微信提醒
不自动卖出——只提醒，由用户或 Phase 2 执行器决策。"""
import json, os, sys, subprocess
from datetime import datetime, timezone, timedelta

HOME = os.path.expanduser('~')
STOCK_DIR = os.path.join(HOME, 'stock_trader')
BJT = timezone(timedelta(hours=8))
STOP_LOSS_PCT = 0.07
TAKE_PROFIT_PCT = 0.15

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

def get_active_event_positions(log_data):
    """从 events_log 提取活跃事件仓位（executed 但未 exited）"""
    active = {}  # symbol -> {executed_at, price, hold_days, reason, ...}
    exited_syms = set()

    for e in log_data.get('events', []):
        if e.get('action') == 'exited':
            for sym in e.get('exited_syms', []):
                exited_syms.add(sym)

    for e in log_data.get('events', []):
        if e.get('action') != 'executed':
            continue
        for d in e.get('details', []):
            sym = d.get('symbol', '')
            if sym not in exited_syms:
                active[sym] = {
                    'executed_at': e.get('executed_at', ''),
                    'entry_price': d.get('price', 0),
                    'hold_days': d.get('hold_days', 7),
                    'stop': d.get('stop', 0),
                    'reason': d.get('reason', ''),
                    'confidence': d.get('confidence', 0),
                }
    return active

def main():
    from dotenv import load_dotenv; load_dotenv(override=True)
    from eagle_eye.broker.alpaca_client import get_alpaca_client

    c = get_alpaca_client()
    log_data = load_json(os.path.join(STOCK_DIR, 'events_log.json'))
    if not log_data:
        print("events_log.json 不存在"); return

    active_positions = get_active_event_positions(log_data)
    if not active_positions:
        print("无活跃事件仓位"); return

    alpaca_positions = c.get_positions()
    held = {p['symbol']: p for p in alpaca_positions}

    alerts = []
    exited_this_run = []
    now = datetime.now(BJT)

    for sym, info in active_positions.items():
        entry = info['entry_price']
        hold_days = info['hold_days']
        exec_at = info['executed_at']

        # 仓位已不在 Alpaca → 仅在持有 >1 天后标记退出（防 API 延迟误判）
        if sym not in held:
            try:
                exec_dt_check = datetime.fromisoformat(info['executed_at'].replace('+08:00', ''))
                if (now - exec_dt_check).total_seconds() < 86400:
                    alerts.append(f"  ⏸ {sym}: 未在持仓中，但开仓不足24h，跳过退出标记")
                    continue
            except:
                pass
            alerts.append(f"  📤 {sym}: 已不在持仓，自动标记退出")
            # 写回 events_log
            log_data.setdefault('events', []).append({
                'action': 'exited',
                'symbol': sym,
                'exited_at': now.isoformat(),
                'exit_reason': 'position_not_found_in_alpaca',
                'entry_price': info['entry_price'],
                'hold_days': info['hold_days'],
                'reason': info['reason'],
            })
            exited_this_run.append(sym)
            continue

        # 用 Alpaca 实际持仓数据
        actual = held[sym]
        current = float(actual['current_price'])
        avg_entry = float(actual['avg_entry_price'])
        qty = int(float(actual['qty']))
        upl_pct = float(actual['unrealized_plpc']) * 100

        # 计算持有天数
        try:
            exec_dt = datetime.fromisoformat(exec_at.replace('+08:00', ''))
            days_held = (now - exec_dt).days
        except:
            days_held = 0

        emoji = '🟢' if upl_pct >= 0 else '🔴'

        # 退出条件检查
        if upl_pct <= -STOP_LOSS_PCT * 100:
            alerts.append(f"  🚨 {sym} 止损触发 {emoji} {upl_pct:+.1f}% | 止损线 -{STOP_LOSS_PCT*100:.0f}% | 建议立即卖出")
        elif upl_pct >= TAKE_PROFIT_PCT * 100:
            alerts.append(f"  💰 {sym} 止盈达标 {emoji} {upl_pct:+.1f}% | 止盈线 +{TAKE_PROFIT_PCT*100:.0f}% | 建议获利了结")
        elif days_held >= hold_days:
            alerts.append(f"  ⏰ {sym} 持有超期 {emoji} {upl_pct:+.1f}% | 已持有 {days_held}天 / 目标 {hold_days}天 | 建议评估是否退出")
        else:
            alerts.append(f"  ✅ {sym} 正常持有 {emoji} {upl_pct:+.1f}% | {days_held}/{hold_days}天 | 剩余 {hold_days - days_held}天")

    if exited_this_run:
        log_data['updated_at'] = now.isoformat()
        save_json(os.path.join(STOCK_DIR, 'events_log.json'), log_data)
        print(f"✅ 已标记 {len(exited_this_run)} 只退出: {exited_this_run}")

    if alerts:
        report = f"📊 事件仓位日报 | {now.strftime('%m-%d %H:%M')}\n\n" + '\n'.join(alerts)
        print(report)
        send_weixin(report)
        print("\n✅ 已推微信")
    else:
        print("无活跃仓位")

if __name__ == '__main__':
    main()
