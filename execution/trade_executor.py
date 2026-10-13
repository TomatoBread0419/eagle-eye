"""
execution/trade_executor.py — 交易编排器 (V7.1 Phase 3)

Orchestrator. All business logic in sub-modules.
Constitution #2 (Risk Engine), #3 (Order Safety), #12 (Capital Preservation).
"""

import sys, os, json, time
from datetime import datetime, timezone, timedelta

from eagle_eye.risk.trading_lock import trading_lock
from eagle_eye.risk.degraded_mode import degraded_mode
from eagle_eye.execution.order_intent import OrderIntent, OrderSide, OrderType
from eagle_eye.execution.order_state_machine import OrderState, get_order_state_machine

from eagle_eye.execution.position_manager import (
    load_state, save_state, get_highest, set_highest,
    get_trail_stop, get_sector, get_bars, analyze,
    tech_snapshot, __get_daily_bars, __get_us_price,
)
from eagle_eye.execution.order_manager import (
    get_portfolio, get_holdings, get_open_stop_orders,
    get_open_buy_orders, place_market_order, place_stop_order,
    place_limit_order,
    cancel_order, log_sell_for_replacement, check_pending_replacements,
    clear_pending_replacement,
)
from eagle_eye.execution.stop_loss_manager import (
    set_replacement_logger, update_trail_stops,
    stop_coverage_audit, detect_ghost_stops, update_stop_blacklist,
)
from eagle_eye.execution.take_profit_manager import (
    set_replacement_logger as set_tp_repl, execute_take_profit,
)
from eagle_eye.core.config import cfg
from eagle_eye.core.logger import get_logger

logger = get_logger('execution')
set_replacement_logger(log_sell_for_replacement); set_tp_repl(log_sell_for_replacement)

# Governor Stage 0 (record-only): shadow 审计重定向到隔离台账。
# setdefault — harness/外部同名环境变量可覆盖；不设 SHADOW_MODE，零阻断。
os.environ.setdefault('SHADOW_AUDIT_FILE', 'D:/Hermes/audit_live/governor_stage0/shadow_decisions.jsonl')

# ═══ Paths & risk params (unchanged from V6) ═══
DATA_DIR = str(cfg.data_dir)
WATCHLIST_FILE, EVENTS_FILE = f'{DATA_DIR}/us_watchlist.json', f'{DATA_DIR}/market_events_latest.json'
DRAWDOWN_PAUSE = 0.12; DRAWDOWN_CUT = 0.20; TP_DRAWDOWN_PCT = 0.08; MIN_POSITION_UTIL = 0.40
LOW_UTIL_FORCE_MARKET = 0.30; FORCE_BUY_SCORE = 1; NORMAL_BUY_SCORE = 2
MAX_BUYS_PER_RUN = 4; SELL_REPLACEMENT = True
HARD_UTIL_FLOOR = 0.38; HARD_PAIR_RATIO = 0.5; HARD_DEFAULT_BUY_QTY = 1
HARD_PAIR_FLOOR_DOLLARS = 100; HARD_UTIL_FLOOR_BUY_DOLLARS = 500
MAX_SINGLE_PCT_OF_CASH = 0.15; MAX_PAIR_QTY_PER_SYMBOL = 10; MAX_ADD_QTY_PER_SYMBOL = 3


# ════════════════════════════════════════════════════
# Event signals (reads market_events_latest.json)
# ════════════════════════════════════════════════════

def load_event_buy_signals():
    signals = []
    if not os.path.exists(EVENTS_FILE): return signals
    try: data = json.load(open(EVENTS_FILE))
    except: return signals
    for opp in data.get('buy_opportunities', []):
        ticker = opp.get('ticker', '')
        price = opp.get('price', 0)
        reason = opp.get('catalyst', opp.get('opportunity', ''))
        priority_raw = opp.get('priority', '')
        if any(kw in priority_raw for kw in ['最高','🔥🔥🔥']) or priority_raw.strip().lower() in ('critical','highest'):
            priority = 'critical'
        elif '🔥🔥' in priority_raw or priority_raw.strip().lower() == 'high':
            priority = 'high'
        elif '🔥' in priority_raw: priority = 'watch'
        else: priority = 'watch'
        if ticker and ticker not in ('TBD','?'):
            for sym in ticker.split('/'):
                sym = sym.strip()
                if sym and len(sym) <= 5: signals.append((sym, price, reason, priority))
    return signals

def load_negative_bias_set():
    negative = set()
    if not os.path.exists(EVENTS_FILE): return negative
    try: data = json.load(open(EVENTS_FILE))
    except: return negative
    for sym, text in data.get('position_impact', {}).items():
        if isinstance(text, str) and text.lstrip().startswith('🔴'): negative.add(sym)
    return negative

def get_buy_threshold(utilization, event_signals, sym):
    t = FORCE_BUY_SCORE if utilization < MIN_POSITION_UTIL else NORMAL_BUY_SCORE
    for ss, _, _, priority in event_signals:
        if ss == sym and priority in ('critical','high'): t = max(0, t - 1); break
    return t


# ════════════════════════════════════════════════════
# Risk checks
# ════════════════════════════════════════════════════

def _log_audit_event(event_type, severity, details, symbol=None):
    """Write event to audit_log for real-time alerting (heartbeat reads this)."""
    try:
        from eagle_eye.storage.db import db as _db
        import json as _json
        _db.execute(
            'INSERT INTO audit_log (event_type, severity, source, symbol, details) VALUES (?,?,?,?,?)',
            (event_type, severity, 'trade_executor', symbol, _json.dumps(details, default=str))
        )
        _db.commit()
    except Exception:
        pass  # Non-blocking — audit logging must not impact trading


def check_account_risk(equity, cash, state, holdings, sold_this_cycle=None):
    if sold_this_cycle is None: sold_this_cycle = {}
    peak = state.get('peak_equity', 0)
    if equity > peak: state['peak_equity'] = peak = equity
    dd = (peak - equity) / peak if peak > 0 else 0
    alerts = []; can_buy = True; cuts = []
    if dd >= DRAWDOWN_CUT:
        state['paused_drawdown'] = True; can_buy = False
        _log_audit_event('emergency_stop', 'CRITICAL', {'drawdown': round(dd*100, 1), 'threshold': '20%', 'action': '减半仓'})
        # V7.1.1: Immediate critical notification
        try:
            from eagle_eye.ops.notification import on_emergency_stop
            on_emergency_stop(f'Drawdown {dd*100:.1f}% > 20% — executing halving')
        except Exception:
            pass
        alerts.append(f'🚨 总回撤 {dd*100:.1f}% > 20%！执行减半仓')
        for h in holdings:
            qty = int(h['qty']) - sold_this_cycle.get(h['symbol'], 0)
            if qty > 0:
                # [execution_intent_type=risk_exit] 回撤>20% 强制减半仓 — Governor 不得阻断
                order = place_market_order(h['symbol'], max(1, qty // 2), 'sell', shadow_intent_type='risk_exit')
                if order:
                    sold_this_cycle[h['symbol']] = sold_this_cycle.get(h['symbol'], 0) + max(1, qty // 2)
                    cuts.append(f'  减仓 {h["symbol"]} x{max(1,qty//2)} @ ${h["current"]}')
    elif dd >= DRAWDOWN_PAUSE:
        state['paused_drawdown'] = True; can_buy = False
        alerts.append(f'⚠️ 总回撤 {dd*100:.1f}% > 12%，暂停买入')
    elif state.get('paused_drawdown') and dd < DRAWDOWN_PAUSE * 0.7:
        state['paused_drawdown'] = False
        alerts.append(f'✅ 回撤恢复至 {dd*100:.1f}%，解除风控暂停')
    return can_buy, alerts, cuts

def check_position_utilization(equity, cash, holdings, mode='normal', target_util_override=None):
    MM = {'aggressive':('active',0.55), 'normal':('neutral',0.50),
          'cautious':('cautious',0.40), 'defensive':('defensive',0.35)}
    ms, tu = MM.get(mode, ('cautious', MIN_POSITION_UTIL))
    if target_util_override is not None: tu = target_util_override
    sv = sum(h.get('market',0) for h in holdings)
    util = sv / equity if equity > 0 else 0
    if util < tu:
        return True, util, equity * tu - sv, ms, tu
    return False, util, 0, ms, tu


# ════════════════════════════════════════════════════
# V7.1 Safety wrapper
# ════════════════════════════════════════════════════

def v7_safety_check():
    from eagle_eye.broker.alpaca_client import get_alpaca_client
    client = get_alpaca_client()
    api_healthy = client.is_healthy()
    clock = client.get_clock()
    market_open = clock.get('is_open', False) if clock else None
    trading_lock.check(api_healthy=api_healthy, market_open=market_open,
                       degraded_active=degraded_mode.is_degraded())
    degraded_mode.check_and_update(client.api_failure_count)
    return {'trading_locked': trading_lock.is_locked,
            'lock_reasons': trading_lock.reason_names(),
            'degraded': degraded_mode.is_degraded(),
            'degraded_state': degraded_mode.state.name,
            'api_healthy': api_healthy, 'market_open': market_open,
            'api_failures': client.api_failure_count}

def _block_buys():
    return trading_lock.is_locked or degraded_mode.is_degraded()


# ════════════════════════════════════════════════════
# main() — full trading loop
# ════════════════════════════════════════════════════

def main(mode='normal'):
    now = datetime.now(timezone.utc); bj = now + timedelta(hours=8)
    ts = bj.strftime('%Y-%m-%d %H:%M')
    safety = v7_safety_check()
    if safety['trading_locked']:
        return print(f'🔒 交易锁定 | {ts}\n   原因: {", ".join(safety["lock_reasons"])}')

    state = load_state()
    acct, equity, cash = get_portfolio()
    if not acct: return print(f'❌ 美股信号检查 | {ts}\n无法连接Alpaca API，跳过本轮')

    holdings = get_holdings(); existing_stops = get_open_stop_orders()
    sold_this_cycle = {}  # P1-20260802: 本周期已卖数量，防同周期多卖出路径重复卖出
    can_buy, risk_alerts, cut_actions = check_account_risk(equity, cash, state, holdings, sold_this_cycle)
    for h in holdings: set_highest(h['symbol'], h['current'], state, cost=h['avg'])

    syms = [h['symbol'] for h in holdings]
    all_results = [r for sym in syms if (r := analyze(sym))]
    vol_map = {r['symbol']: r.get('vol_20d') for r in all_results if r.get('vol_20d') is not None}

    trail_msgs = update_trail_stops(holdings, state, existing_stops, vol_map=vol_map, sold_this_cycle=sold_this_cycle)
    tp_msgs = execute_take_profit(all_results, holdings, state, sold_this_cycle=sold_this_cycle)

    # Collect symbols just sold — prevent wash-trade in same run
    just_sold = set()
    for m in trail_msgs:
        if '追踪止损触发' in m:
            sym = m.split('卖出 ')[1].split(' ')[0] if '卖出 ' in m else ''
            if sym: just_sold.add(sym)
    for m in tp_msgs:
        if '止盈卖出' in m:
            sym = m.split('止盈卖出 ')[1].split(' ')[0] if '止盈卖出 ' in m else ''
            if sym: just_sold.add(sym)

    sell_count = len(tp_msgs) + len([m for m in trail_msgs if '追踪止损触发' in m])
    event_signals = load_event_buy_signals()
    need_buy, utilization, buy_gap, market_state, target_util = \
        check_position_utilization(equity, cash, holdings, mode=mode)

    buy_msgs = []; hold_syms = {h['symbol'] for h in holdings} | just_sold
    open_stop_syms = set()
    if can_buy and not _block_buys():
        # P1-20261013 wash-403 抑制: 买单一律避开在挂 sell-stop 标的。
        # 新鲜查询置于 trail/TP 之后（本周期一次, 非逐单 GET）: 避免用 L195 旧快照
        # 误拦本周期刚撤停的配对回买; 查询失败 → 空集 fail-open(行为同今日)。
        try:
            open_stop_syms = set(get_open_stop_orders().keys())
        except Exception:
            open_stop_syms = set()

        # 6a. Event-driven buys
        for ss, sp, reason, priority in event_signals:
            if ss in hold_syms: continue
            if priority == 'critical' and cash >= sp * 2:
                qty = max(2, min(5, int(cash * 0.05 // max(sp, 1))))
                if ss in open_stop_syms:
                    print(f'  ⏭ P1 skip buy {ss}: open sell-stop'); continue
                order = place_market_order(ss, qty, 'buy', shadow_intent_type='strategy_entry')
                if order and order.get('id'):
                    buy_msgs.append(f'  🔥 事件买入 {ss} x{qty} @ ~${sp:.2f} | {reason[:60]}')
                    cash -= sp * qty; hold_syms.add(ss)

        # 6b. sell→buy pair
        if SELL_REPLACEMENT and sell_count > 0 and cash > HARD_PAIR_FLOOR_DOLLARS:
            hold_syms = {h['symbol'] for h in holdings}
            try:
                wl = json.load(open(WATCHLIST_FILE))
                pool = [s for s in wl.get('buy_candidates', []) if s not in hold_syms]
                target = min(sell_count, MAX_BUYS_PER_RUN)
                done = 0; budget = min(cash * HARD_PAIR_RATIO, cash - 500)
                for sym in pool[:target * 2]:
                    if done >= target or budget < 200: break
                    mp = __get_us_price(sym) or 100
                    max_d = cash * MAX_SINGLE_PCT_OF_CASH
                    qty = max(1, int(budget // max(mp, 1) // max(target, 1)))
                    qty = min(qty, int(max_d // max(mp, 1)), MAX_PAIR_QTY_PER_SYMBOL)
                    if qty < 1: qty = 1
                    if qty * mp > cash * MAX_SINGLE_PCT_OF_CASH:
                        qty = max(1, min(int((cash * MAX_SINGLE_PCT_OF_CASH) // max(mp, 1)), MAX_PAIR_QTY_PER_SYMBOL))
                    if sym in open_stop_syms:
                        print(f'  ⏭ P1 skip buy {sym}: open sell-stop'); continue
                    order = place_market_order(sym, qty, 'buy', shadow_intent_type='strategy_entry')
                    if order and order.get('id'):
                        buy_msgs.append(f'  🔄 sell→buy 配对 {sym} x{qty} @ ~${mp:.2f}')
                        cash -= mp * qty; budget -= mp * qty; done += 1
                if done == 0: buy_msgs.append(f'  ⚠️ sell→buy 配对失败')
                elif done < sell_count: buy_msgs.append(f'  ⚠️ sell→buy 仅配对{done}/{sell_count}')
            except FileNotFoundError: buy_msgs.append(f'  ⚠️ 无 us_watchlist.json')

        # 6c. Add to existing
        for r in all_results:
            sym = r['symbol']
            if r['buy_score'] >= 3 and cash >= r['price'] * 2:
                held = next((h for h in holdings if h['symbol'] == sym), None)
                if held:
                    if sym in open_stop_syms:
                        print(f'  ⏭ P1 skip buy {sym}: open sell-stop'); continue
                    qty = max(1, min(3, int(held['qty'] * 0.5)))
                    max_d = cash * MAX_SINGLE_PCT_OF_CASH
                    qty = min(qty, int(max_d // max(r['price'], 1)), MAX_ADD_QTY_PER_SYMBOL)
                    if qty < 1: continue
                    order = place_market_order(sym, qty, 'buy', shadow_intent_type='strategy_entry')
                    if order and order.get('id'):
                        buy_msgs.append(f'  📗 加仓 {sym} x{qty} @ ${r["price"]:.2f} | 得分{r["buy_score"]}')
                        cash -= r['price'] * qty
        if need_buy: buy_msgs.append(f'  ⚡ 仓位仅{utilization*100:.0f}%，缺口${buy_gap:,.0f}')

        # 6e. Hard constraint
        bc = len([m for m in buy_msgs if ('配对 ' in m and '失败' not in m) or '加仓 ' in m])
        if can_buy and utilization < HARD_UTIL_FLOOR and bc == 0 and cash > HARD_UTIL_FLOOR_BUY_DOLLARS:
            from eagle_eye.strategy.indicator_engine import calc_rsi
            hard_done = False
            try:
                wl = json.load(open(WATCHLIST_FILE))
                hold_syms = {h['symbol'] for h in holdings}
                ranked = [x['symbol'] if isinstance(x, dict) else x for x in wl.get('all_ranked', [])]
                pool = list(dict.fromkeys(ranked + wl.get('buy_candidates', []) + wl.get('top10', [])))
                pool = [s for s in pool if s not in hold_syms and s not in get_open_buy_orders()]
                neg = load_negative_bias_set()
                if neg: pool = [s for s in pool if s not in neg]
                if not pool:
                    buy_msgs.append(f'  🔴 硬约束失败：候选池空')
                else:
                    for pick in pool[:3]:
                        if pick in open_stop_syms:
                            print(f'  ⏭ P1 skip buy {pick}: open sell-stop'); continue
                        live_rsi = None
                        try:
                            bars = __get_daily_bars(pick)
                            if bars and len(bars) >= 20: live_rsi = calc_rsi([b['c'] for b in bars], 14)
                        except: pass
                        mp = __get_us_price(pick) or 100
                        if live_rsi is not None and live_rsi > 75: continue
                        lp = round(mp * 0.99, 2); qty = HARD_DEFAULT_BUY_QTY
                        if lp * qty < 100: continue
                        if lp * qty > cash * MAX_SINGLE_PCT_OF_CASH:
                            qty = max(1, int((cash * MAX_SINGLE_PCT_OF_CASH) // max(lp, 1)))
                        if qty < 1: continue
                        # [execution_intent_type=strategy_entry] GARP 低利用率强制买入 (limit 保持原语义)
                        order = place_limit_order(pick, qty, 'buy', lp, dedupe=True,
                                                  client_order_id=f'hardutil_{int(time.time())}',
                                                  shadow_intent_type='strategy_entry')
                        if order and order.get('id'):
                            buy_msgs.append(f'  🔧 硬约束 buy {pick} x{qty} limit ${lp}')
                            hard_done = True; break
                    if not hard_done: buy_msgs.append(f'  🔴 硬约束失败')
            except FileNotFoundError: buy_msgs.append(f'  🔴 无 us_watchlist.json')
    else:
        buy_msgs.append(f'  {"🔒 V7.1 安全锁" if _block_buys() else "⏸ 风控暂停买入"}')

    # 6b. Screener buys
    screener_msgs = []
    if can_buy and not _block_buys():
        try:
            wl = json.load(open(WATCHLIST_FILE))
            hold_syms = {h['symbol'] for h in holdings}
            new_stocks = [s for s in wl.get('buy_candidates', []) if s not in hold_syms]
            if new_stocks:
                screener_msgs.append(f'  🔍 候选池: {", ".join(new_stocks[:8])}')
                mb = MAX_BUYS_PER_RUN * (2 if need_buy and utilization < 0.15 else 1)
                bought = len([m for m in buy_msgs if '买入' in m or '加仓' in m])
                for sym in new_stocks[:8]:
                    if bought >= mb or cash < 500: break
                    r = analyze(sym)
                    th = get_buy_threshold(utilization, event_signals, sym)
                    if r and r.get('buy_score', 0) >= th:
                        if sym in open_stop_syms:
                            print(f'  ⏭ P1 skip buy {sym}: open sell-stop'); continue
                        if r.get('rsi') and r['rsi'] >= 75:
                            screener_msgs.append(f'  ⏭ {sym} RSI{r["rsi"]}过热，跳过'); continue
                        mp = __get_us_price(sym) or r['price']
                        qty = max(2, min(5, int(cash * 0.05 // max(mp, 1)))) if need_buy else max(1, min(3, int(cash * 0.02 // max(mp, 1))))
                        if qty > 0:
                            order = place_market_order(sym, qty, 'buy', shadow_intent_type='strategy_entry')
                            if order and order.get('id'):
                                screener_msgs.append(f'  📗 买入 {sym} x{qty} @ ${mp:.2f} | 得分{r["buy_score"]}')
                                cash -= mp * qty; bought += 1
        except Exception as e: screener_msgs.append(f'  ⚠️ 扫描器错误: {e}')

    save_state(state)

    # ─── Report ───
    print(f'📊 美股风控报告 | {ts}\n{"="*50}')
    print(f'💰 权益 ${equity:,.2f}  |  现金 ${cash:,.2f}')
    pnl = equity - 100000; peak = state.get('peak_equity', equity)
    dd = (peak - equity) / peak * 100 if peak > 0 else 0
    print(f'  盈亏 {pnl:+,.2f} ({(equity/100000-1)*100:+.2f}%)  |  峰值 ${peak:,.0f}  |  回撤 {dd:.1f}%')
    print(f'  📊 仓位利用率 {utilization*100:.0f}%（目标≥{target_util*100:.0f}%）{"⚠️不足" if need_buy else "✅"}')
    if safety['degraded']: print(f'  ⚠️ V7.1 降级模式')
    print()
    if holdings:
        print(f'📋 持仓 ({len(holdings)}只)\n{"─"*50}')
        sh = {}
        for h in holdings:
            sec = get_sector(h['symbol']); d = sh.setdefault(sec, {'c':0,'v':0,'p':0})
            d['c']+=1; d['v']+=h['market']; d['p']+=h['pnl']
        print('  板块分布: ' + ', '.join(f"{k}{v['c']}只${v['v']:,.0f}" for k,v in sorted(sh.items())))
        print()
        for h in holdings:
            sym = h['symbol']; si = existing_stops.get(sym)
            spx = si['stop_price'] if si else get_trail_stop(sym, state, h['avg'])
            dist = (h['current'] - spx) / h['current'] * 100 if si else 0
            flag = ' 🛡' if si else ' ⚠️无止损'
            print(f'{"🟢" if h["pnl"]>=0 else "🔴"} {sym:6s} {h["qty"]:>3.0f}股  ${h["current"]:<8.2f}  浮盈{h["pnl_pct"]:+.2f}%  |  止损${spx:<.2f} 距现价{dist:.0f}%{flag}')
    else: print('🈳 空仓')
    for title, items in [('🚨 风控告警',risk_alerts),('🛡 止损更新',trail_msgs),
                          ('💰 止盈',tp_msgs),('✂️ 风控减仓',cut_actions),
                          ('📗 买入',buy_msgs),('🔍 扫描器',screener_msgs)]:
        if items: print(f'\n{title}'); [print(m) for m in items]
    print(f'\n{"="*50}\n✅ 本轮完成')
    # V7.1.1: Log executor success for heartbeat EXECUTOR_STALLED detection
    _log_audit_event('executor_success', 'INFO', {'holdings': len(holdings), 'utilization': round(utilization*100, 1)})
    state['report_date'] = bj.strftime('%Y-%m-%d'); save_state(state)


# ════════════════════════════════════════════════════
# report_mode / execute_mode / stops_mode
# ════════════════════════════════════════════════════

def report_mode(mode='normal', target_util=None):
    from eagle_eye.strategy.indicator_engine import get_volatility_stop_pct
    now = datetime.now(timezone.utc); bj = now + timedelta(hours=8)
    safety = v7_safety_check()
    state = load_state()
    acct, equity, cash = get_portfolio()
    if not acct: return print(json.dumps({'error': '无法连接Alpaca API'}))
    holdings = get_holdings();existing_stops = get_open_stop_orders()
    peak = state.get('peak_equity', 0)
    if equity > peak: state['peak_equity'] = equity; peak = equity
    dd = (peak - equity) / peak if peak > 0 else 0
    can_buy = dd < DRAWDOWN_PAUSE and not _block_buys()
    for h in holdings: set_highest(h['symbol'], h['current'], state, cost=h['avg'])
    all_results = [r for sym in [h['symbol'] for h in holdings] if (r := analyze(sym))]
    vol_map = {r['symbol']: r.get('vol_20d') for r in all_results if r.get('vol_20d') is not None}
    nb, util, gap, ms, tu = check_position_utilization(equity, cash, holdings, mode=mode, target_util_override=target_util)
    stops = [{'symbol': h['symbol'], 'cost': round(h['avg'],2), 'current': round(h['current'],2),
              'highest': round(get_highest(h['symbol'], state),2),
              'vol_20d': vol_map.get(h['symbol']),
              'stop_pct': round((sp := get_volatility_stop_pct(vol_map.get(h['symbol']))),3),
              'trail_stop': round((ts := max(get_highest(h['symbol'], state)*(1-sp), h['avg']*(1-sp))),2),
              'init_stop': round(h['avg']*(1-sp),2),
              'hard_stop': round(existing_stops.get(h['symbol'],{}).get('stop_price',0),2) if h['symbol'] in existing_stops else None,
              'dist_to_stop': round((h['current']-ts)/h['current'],4) if h['current']>0 else 0} for h in holdings]
    es = load_event_buy_signals(); neg = load_negative_bias_set()
    save_state(state)
    report = {'timestamp': bj.isoformat(), 'mode': 'report', 'v7_safety': safety,
              'account': {'equity': round(equity,2), 'cash': round(cash,2),
                          'long_mv': round(float(acct.get('long_market_value',0)),2),
                          'utilization': round(util,4), 'target_util': tu, 'market_state': ms,
                          'drawdown': round(dd,4), 'can_buy': can_buy, 'gap_dollars': round(gap,2)},
              'holdings': [{'symbol':h['symbol'],'qty':h['qty'],'avg':h['avg'],'current':h['current'],
                            'market':h['market'],'pnl':h['pnl'],'pnl_pct':h['pnl_pct']} for h in holdings],
              'analysis': all_results, 'stops': stops,
              'event_signals': [{'symbol':s[0],'price':s[1],'reason':s[2],'priority':s[3]} for s in es],
              'negative_bias': list(neg), 'risk_flags': []}
    if dd > 0.08: report['risk_flags'].append(f'回撤 {dd*100:.1f}% 接近 12% 暂停线')
    for h in holdings:
        if h['pnl_pct'] < -5: report['risk_flags'].append(f'{h["symbol"]} 浮亏 {h["pnl_pct"]:.1f}%')
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))


def execute_mode(orders_json):
    now = datetime.now(timezone.utc); bj = now + timedelta(hours=8)
    safety = v7_safety_check()

    # ═══ P0 Gate 0: Dashboard must exist ───
    from eagle_eye.risk.policy_validator import (
        check_dashboard_gate, validate_order_intent, quick_portfolio_snapshot,
        check_seed_eligibility, _get_candidate_scan_count,
    )
    dashboard_ok, dashboard_reason = check_dashboard_gate()
    if not dashboard_ok:
        return print(json.dumps({
            'error': 'Dashboard gate REJECTED',
            'reason': dashboard_reason,
            'policy': 'auto_approval_policy.md v1.1 §7',
        }, indent=2, ensure_ascii=False))

    try: data = json.loads(orders_json)
    except: return print(json.dumps({'error': 'JSON 解析失败'}))
    orders = data.get('orders', [])
    if not orders: return print(json.dumps({'error': '无订单'}))
    acct, equity, cash = get_portfolio()
    if not acct: return print(json.dumps({'error': '无法连接Alpaca API'}))
    state = load_state(); peak = state.get('peak_equity', 0)
    dd = (peak - equity) / peak if peak > 0 else 0
    if dd >= DRAWDOWN_PAUSE: return print(json.dumps({'error': f'回撤 {dd*100:.1f}% >= {DRAWDOWN_PAUSE*100:.0f}%'}))

    # ═══ P0: Build portfolio snapshot for policy validation ───
    pf_snapshot = quick_portfolio_snapshot()
    positions = get_holdings()
    util = sum(p.get('market',0) for p in positions) / equity if equity > 0 else 0
    fm = util < LOW_UTIL_FORCE_MARKET
    if fm:
        for o in orders:
            if o.get('side') == 'buy' and o.get('type') == 'limit':
                o['type'] = 'market'; o.pop('limit_price', None)
    pending = check_pending_replacements(); oms = get_order_state_machine()
    results = []

    # ═══ P0: Per-order policy validation ───
    for order in orders:
        sym = order.get('symbol',''); qty = int(order.get('qty',0))
        side = order.get('side','buy'); otype = order.get('type','market')
        lp = order.get('limit_price')
        if not sym or qty <= 0: results.append({'symbol':sym,'status':'skipped'}); continue
        if side == 'buy' and _block_buys(): results.append({'symbol':sym,'status':'skipped','reason':'V7.1安全锁'}); continue
        if side == 'buy' and not degraded_mode.can_open_position(sym): results.append({'symbol':sym,'status':'skipped','reason':'降级模式'}); continue

        # ═══ P0 Gate 1-3: Policy validation ───
        seed_intent = order.get('_seed', False)  # LLM marks seed intents
        pf_snapshot['_seed_intent'] = seed_intent
        pf_snapshot['symbol_info'] = {
            sym: {
                'rsi': order.get('rsi'),
                'kelly_pct': order.get('kelly_pct'),
                'signals': order.get('signals', {}),
            }
        }

        # Create intent for validation
        os_ = OrderSide.BUY if side == 'buy' else OrderSide.SELL
        ot = OrderType.LIMIT if otype == 'limit' else OrderType.MARKET
        intent = OrderIntent(
            symbol=sym, side=os_, qty=qty, order_type=ot,
            time_in_force='day', limit_price=lp,
            sector=order.get('sector', ''),
            reason=order.get('reason', ''),
        )

        v, e = intent.validate()
        if not v: results.append({'symbol':sym,'status':'rejected','reason':e}); continue

        pk_ok, pk_reason = validate_order_intent(intent, pf_snapshot)
        if not pk_ok:
            results.append({
                'symbol': sym, 'status': 'policy_rejected',
                'reason': pk_reason, 'policy': 'v1.1',
            })
            # Log violation
            try:
                from eagle_eye.storage.db import db as _db
                import json as _json
                _db.execute(
                    'INSERT INTO policy_violations (symbol, check_name, result, reason, portfolio_snapshot) VALUES (?,?,?,?,?)',
                    (sym, 'validate_order_intent', 'REJECT', pk_reason,
                     _json.dumps({k:v for k,v in pf_snapshot.items() if k != 'symbol_info'}, default=str))
                )
                _db.commit()
            except: pass
            continue

        intent.mark_validated(); intent.mark_safety_checked(); intent.mark_ready()
        rec = oms.create_order(intent)
        oms.transition(rec.id, OrderState.VALIDATING); oms.transition(rec.id, OrderState.APPROVED)
        mp = __get_us_price(sym) or 0
        if mp > 0 and side == 'buy':
            mq = int((cash * MAX_SINGLE_PCT_OF_CASH) // mp)
            if qty > mq: qty = max(1, mq)
            if qty * mp > cash * 0.5: oms.transition(rec.id, OrderState.FAILED); results.append({'symbol':sym,'status':'skipped'}); continue
        if otype == 'limit' and lp:
            # [execution_intent_type=strategy_entry] Step 0-B: redirect 到 order_manager.place_limit_order
            or_ = place_limit_order(sym, qty, side, float(lp), dedupe=True,
                                    shadow_intent_type='strategy_entry')
        else: or_ = place_market_order(sym, qty, side, dedupe=True,
                                       shadow_intent_type='strategy_entry')
        if or_ and or_.get('id'):
            oms.transition(rec.id, OrderState.SUBMITTED, alpaca_order_id=or_.get('id'))
            results.append({'symbol':sym,'status':'submitted','order_id':or_['id'],'qty':qty,'type':otype,
                           'policy_check': 'PASS', 'policy_reason': pk_reason})
            if side == 'buy' and mp > 0: cash -= qty * mp
        else: oms.transition(rec.id, OrderState.FAILED); results.append({'symbol':sym,'status':'failed'})

    print(json.dumps({'timestamp':bj.isoformat(), 'v7_safety':safety,
                      'equity':round(equity,2), 'cash_remaining':round(cash,2),
                      'utilization':round(util*100,1), 'force_market':fm,
                      'pending_replacements':pending, 'oms_stats':oms.stats(),
                      'policy_version': 'v1.1',
                      'dashboard_gate': dashboard_reason,
                      'executed': results}, indent=2, ensure_ascii=False))


def stops_mode():
    now = datetime.now(timezone.utc); bj = now + timedelta(hours=8); ts = bj.strftime('%Y-%m-%d %H:%M')
    safety = v7_safety_check(); update_stop_blacklist()
    state = load_state()
    acct, equity, cash = get_portfolio()
    if not acct: return print(f'❌ 止损管理 | {ts} | 无法连接Alpaca API')
    holdings = get_holdings(); existing_stops = get_open_stop_orders()
    for h in holdings: set_highest(h['symbol'], h['current'], state, cost=h['avg'])
    all_results = []
    for sym in [h['symbol'] for h in holdings]:
        r = analyze(sym)
        if r:
            if r.get('sell_reason') and '回撤' in r['sell_reason']:
                sh = get_highest(sym, state)
                if sh > 0 and (sh - r['price'])/sh*100 < TP_DRAWDOWN_PCT*100*0.5:
                    r['sell_reason'] = None; r['_suppressed_sell'] = f'状态校验: 实际回撤仅{(sh-r["price"])/sh*100:.1f}%'
            all_results.append(r)
    vol_map = {r['symbol']: r.get('vol_20d') for r in all_results if r.get('vol_20d') is not None}
    sold_this_cycle = {}  # P1-20260802: 本周期已卖数量，防同周期多卖出路径重复卖出
    trail_msgs = update_trail_stops(holdings, state, existing_stops, vol_map=vol_map, sold_this_cycle=sold_this_cycle)
    tp_msgs = execute_take_profit(all_results, holdings, state, sold_this_cycle=sold_this_cycle)
    cb, ra, ca = check_account_risk(equity, cash, state, holdings, sold_this_cycle)
    save_state(state)
    am = stop_coverage_audit(holdings, vol_map=vol_map)
    gm = detect_ghost_stops(holdings)
    suppressed = [r for r in all_results if r.get('_suppressed_sell')]
    if suppressed: print(f'🛡 止损/止盈管理 | {ts}\n  🛡 虚假信号抑制 ({len(suppressed)}):'); [print(f"    {r['_suppressed_sell']}") for r in suppressed]
    if gm: print(f'🛡 止损/止盈管理 | {ts}'); [print(m) for m in gm]
    if am: print(f'🛡 止损覆盖审计 | {ts} | 补挂 {len(am)}'); [print(m) for m in am]
    ms = trail_msgs + tp_msgs + [f'  {a}' for a in ca] + [f'  {a}' for a in ra]
    if ms: print(f'🛡 止损/止盈管理 | {ts}'); [print(m) for m in ms]
    elif not suppressed and not am and not gm: print(f'🛡 止损/止盈管理 | {ts} | 无触发')
    if safety['degraded']: print(f'  ⚠️ V7.1 降级模式生效中')


# ════════════════════════════════════════════════════
# CLI entry
# ════════════════════════════════════════════════════

def run_cli():
    import argparse
    p = argparse.ArgumentParser(description='美股交易系统 V7.1')
    p.add_argument('--report', action='store_true')
    p.add_argument('--mode', choices=['aggressive','normal','cautious','defensive'], default='normal')
    p.add_argument('--target-util', type=float, default=None)
    p.add_argument('--execute', type=str)
    p.add_argument('--stops', action='store_true')
    args = p.parse_args()
    if args.report: report_mode(mode=args.mode, target_util=args.target_util)
    elif args.execute: execute_mode(args.execute)
    elif args.stops: stops_mode()
    else: main(mode=args.mode)


if __name__ == '__main__':
    run_cli()
