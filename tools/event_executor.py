#!/usr/bin/env python3
"""Phase 2 — 事件驱动执行器
读取 events_analysis_queue.json 的 analyzed 推荐 → 下市价单 + 挂止损 → 记录 → 推微信"""
import json, os, sys, subprocess
from datetime import datetime, timezone, timedelta

HOME = os.path.expanduser('~')
STOCK_DIR = os.path.join(HOME, 'stock_trader')
EAGLE_DIR = os.path.join(HOME, 'eagle_eye')
BJT = timezone(timedelta(hours=8))
STOP_LOSS_PCT = 0.07
MIN_QTY = 5          # 最少买 5 股
MIN_NOTIONAL = 2500   # 最小下单金额 $2500

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

def main(dry_run=False):
    queue = load_json(os.path.join(STOCK_DIR, 'events_analysis_queue.json'))
    log = load_json(os.path.join(STOCK_DIR, 'events_log.json')) or {"version":"1.0","events":[]}

    if not queue or not queue.get('analyzed'):
        print("无待执行推荐"); return

    # 已执行过的 symbol 集合
    executed_syms = set()
    for e in log.get('events', []):
        if e.get('action') == 'executed':
            for sym in e.get('executed_syms', []):
                executed_syms.add(sym)

    from dotenv import load_dotenv; load_dotenv(override=True)
    from eagle_eye.broker.alpaca_client import get_alpaca_client
    from eagle_eye.execution.order_manager import place_market_order, place_stop_order, get_holdings, get_open_stop_orders, cancel_order

    c = get_alpaca_client()

    # 市场开盘检查
    if not c.is_market_open():
        print("⏸ 市场闭市，跳过执行")
        send_weixin("⏸ 事件执行器: 市场闭市，跳过")
        return

    acc = c.get_account()
    equity = float(acc['equity'])
    held = {p['symbol']: p for p in c.get_positions()}
    new_executions = []

    for event in queue['analyzed']:
        sector = event.get('sector', '?')
        direction = event.get('direction', '?')

        for rec in event.get('recommendations', []):
            sym = rec['symbol']
            action = rec['action']
            pct = rec['position']
            hold_days = rec.get('hold_days', 7)
            conf = rec['confidence']

            # 去重：已执行过
            if sym in executed_syms:
                print(f"  ⏭ {sym}: 已执行过，跳过")
                continue

            # SELL 逻辑：只卖已持仓的，无持仓跳过（不做空）
            if action == 'SELL':
                if sym in held:
                    qty = int(float(held[sym]['qty']))
                    price = c.get_last_price(sym)
                    if dry_run:
                        print(f"  🔄 [DRY] 卖出 {sym} x{qty} @ ${price:.2f}")
                    else:
                        order = place_market_order(sym, qty, 'sell', dedupe=False)
                        if order:
                            print(f"  ✅ 卖出 {sym} x{qty} @ ~${price:.2f}")
                            new_executions.append({'symbol':sym,'action':'SELL','qty':qty,'price':price,'reason':f'{sector} {direction}'})
                        else:
                            print(f"  ❌ 卖出 {sym} 失败")
                else:
                    print(f"  ⏭ {sym}: 无持仓，SELL 跳过")
                continue

            # BUY 逻辑
            if sym in held:
                print(f"  ⏭ {sym}: 已持有 {int(float(held[sym]['qty']))} 股（GARP），跳过")
                continue

            price = c.get_last_price(sym)
            if not price or price <= 0:
                print(f"  ❌ {sym}: 无报价，跳过")
                continue

            # 计算股数
            notional = equity * pct / 100.0
            qty = int(notional / price)

            if qty < MIN_QTY or notional < MIN_NOTIONAL:
                qty = max(MIN_QTY, int(MIN_NOTIONAL / price))
                actual_pct = qty * price / equity * 100
                if actual_pct > 5.0:
                    print(f"  ⏭ {sym}: 最小仓位 {actual_pct:.1f}% 超限 5%，跳过")
                    continue

            actual_pct = qty * price / equity * 100
            stop_price = round(price * (1 - STOP_LOSS_PCT), 2)

            if dry_run:
                print(f"  🔄 [DRY] 买 {sym} x{qty} @ ${price:.2f} | 仓位 {actual_pct:.1f}% | 止损 ${stop_price} | {sector}")
                new_executions.append({'symbol':sym,'action':'BUY','qty':qty,'price':price,'stop':stop_price,'position_pct':round(actual_pct,1),'hold_days':hold_days,'confidence':conf,'reason':f'{sector} {direction}'})
                continue

            # 下单
            order = place_market_order(sym, qty, 'buy')
            if not order:
                print(f"  ❌ 买单失败: {sym}")
                continue

            # 挂止损（先取消旧止损单，防 wash-trade 403）
            import time as _t
            existing_stops = get_open_stop_orders()
            if sym in existing_stops:
                cancel_order(existing_stops[sym]['id'])
                print(f"  🔄 {sym}: 取消旧止损 ${existing_stops[sym]['stop_price']}, 等待 2s")
                _t.sleep(2)
            stop = place_stop_order(sym, qty, stop_price)
            if not stop:
                print(f"  ⚠️ {sym}: 止损挂单失败，需手动补挂 ${stop_price}")

            print(f"  ✅ 买 {sym} x{qty} @ ~${price:.2f} | 仓位 {actual_pct:.1f}% | 止损 ${stop_price}")

            new_executions.append({
                'symbol': sym, 'action': 'BUY', 'qty': qty, 'price': price,
                'stop': stop_price, 'position_pct': round(actual_pct, 1),
                'hold_days': hold_days, 'confidence': conf,
                'reason': f'{sector} {direction}'
            })

            # 推微信
            emoji = '📈' if action == 'BUY' else '📉'
            send_weixin(
                f"🗺️ 事件交易 | {sector}\n"
                f"{emoji} {action} {sym} x{qty} @ ${price:.2f}\n"
                f"仓位: {actual_pct:.1f}%  置信度: {conf}%\n"
                f"持有窗口: {hold_days}天  止损: ${stop_price}"
            )

    # 记录到 events_log（仅 live 模式，dry-run 不落盘）
    if new_executions and not dry_run:
        log.setdefault('events', []).append({
            'action': 'executed',
            'executed_at': datetime.now(BJT).isoformat(),
            'mode': 'live',
            'executed_syms': [e['symbol'] for e in new_executions],
            'details': new_executions
        })
        save_json(os.path.join(STOCK_DIR, 'events_log.json'), log)

    # 更新队列：标记已分析的为已处理（仅 live 模式）
    if not dry_run:
        for event in queue['analyzed']:
            event['_executed'] = True
        save_json(os.path.join(STOCK_DIR, 'events_analysis_queue.json'), queue)

    total = len(new_executions)
    mode = "DRY-RUN" if dry_run else "LIVE"
    print(f"\n{'🔄' if dry_run else '✅'} [{mode}] 执行完成: {total} 笔")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='仅打印不下单')
    args = parser.parse_args()
    main(dry_run=args.dry_run)
