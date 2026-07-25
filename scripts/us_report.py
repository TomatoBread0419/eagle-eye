#!/usr/bin/env python3
"""
us_report.py — AI 决策报告生成器
汇总所有数据源，生成结构化报告供 AI 做交易决策

支持 --update-weights 参数：在生成报告前更新评分权重
"""
import sys, os, json, subprocess
from datetime import datetime, timezone, timedelta

SRC_DIR = '$HOME/stock_trader'
SCRIPTS_DIR = '$HOME/.hermes/scripts'
os.chdir(SRC_DIR)

PORTFOLIO_FILE = f'{SRC_DIR}/us_portfolio.json'
WATCHLIST_FILE = f'{SRC_DIR}/us_watchlist.json'
EVENTS_FILE = f'{SRC_DIR}/market_events_latest.json'
STATE_FILE = f'{SRC_DIR}/us_risk_state.json'
MACRO_FILE = f'{SRC_DIR}/macro_context.json'
BREADTH_FILE = f'{SRC_DIR}/market_breadth.json'
ENV_FILE = f'{SRC_DIR}/market_env.json'  # v6: 合并宏观+广度
KELLY_FILE = f'{SRC_DIR}/trade_history.json'
DECAY_FILE = f'{SRC_DIR}/signal_decay.json'

SECTOR_NAMES = {
    'tech': '科技', 'ai': 'AI/云', 'consumer': '消费', 'finance': '金融',
    'pharma': '医药', 'industrial': '工业', 'telecom': '通讯',
    'energy': '能源', 'defense': '军工', 'resources': '资源', 'other': '其他',
}


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return None


def run_portfolio_analysis(mode='normal', target_util=None):
    """运行 us_portfolio.py 获取最新持仓分析"""
    args = ['python3', f'{SCRIPTS_DIR}/us_portfolio.py', '--mode', mode]
    if target_util:
        args.extend(['--target-util', str(target_util)])
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return load_json(PORTFOLIO_FILE)
    except:
        return load_json(PORTFOLIO_FILE)


def generate_report(mode='normal', target_util=None):
    """生成完整的 AI 决策报告"""
    now = datetime.now(timezone(timedelta(hours=8)))

    # 1. 持仓分析
    portfolio = run_portfolio_analysis(mode=mode, target_util=target_util)
    if not portfolio:
        return "❌ 无法获取持仓数据"

    # 2. 扫描器候选
    watchlist = load_json(WATCHLIST_FILE)

    # 3. 市场事件
    events = load_json(EVENTS_FILE)

    # 4. 风控状态
    state = load_json(STATE_FILE) or {}

    # v4.7: 加载近期止损黑名单
    blacklist = load_json(f'{SRC_DIR}/us_recent_stops.json') or {}
    blacklist_syms = set(blacklist.get('blacklist', []))

    # v5.0: 加载宏观环境和市场广度 (v6: 优先读合并文件)
    env_data = load_json(ENV_FILE) or {}
    macro = env_data.get('macro', {}) or load_json(MACRO_FILE) or {}
    breadth = env_data.get('breadth', {}) or load_json(BREADTH_FILE) or {}
    kelly_data = load_json(KELLY_FILE) or {}
    decay_data = load_json(DECAY_FILE) or {}

    # ═══ 开始生成报告 ═══
    lines = []
    lines.append(f"=== 美股交易决策报告 | {now.strftime('%Y-%m-%d %H:%M')} BJT ===")
    lines.append("")

    # ─── 市场环境 ───
    lines.append("【市场环境】")
    if events:
        narrative = events.get('market_narrative', '?')
        sentiment = events.get('overall_sentiment', '')[:120]
        lines.append(f"叙事: {narrative} | 情绪: {sentiment}")

        # 关键事件
        buy_ops = events.get('buy_opportunities', [])
        if buy_ops:
            lines.append("关键事件:")
            for op in buy_ops[:3]:
                item = op.get('item', '?')
                priority = op.get('priority', '?')
                lines.append(f"  [{priority}] {item}")

        # 板块信号
        position_impact = events.get('position_impact', {})
        if isinstance(position_impact, dict):
            details = position_impact.get('details', [])
            if details:
                lines.append("板块信号:")
                for d in details[:5]:
                    lines.append(f"  {d}")
    else:
        lines.append("  无市场事件数据")
    lines.append("")

    # v5.0: 🌍 宏观环境
    lines.append("🌍 【宏观环境】")
    if macro:
        regime_str = macro.get('regime', '?')
        emoji = macro.get('regime_emoji', '⚪')
        lines.append(f"{emoji} 市场状态: {regime_str}")
        vix = macro.get('vix')
        if vix:
            vix_label = '自满' if vix < 15 else '正常' if vix < 25 else '恐慌' if vix < 35 else '极度恐慌'
            lines.append(f"VIX: {vix} [{vix_label}]")
        dxy = macro.get('dxy')
        if dxy:
            dxy_label = '弱美元' if dxy < 100 else '强美元' if dxy > 108 else '中性'
            lines.append(f"DXY: {dxy} [{dxy_label}]")
        spread = macro.get('spread_10y2y')
        if spread is not None:
            curve_label = '倒挂⚠️' if spread < 0 else '平坦' if spread < 0.5 else '正常'
            lines.append(f"10Y-2Y利差: {spread}% [{curve_label}]")
        fomc = macro.get('fomc', {})
        if fomc.get('next_meeting'):
            lines.append(f"下次FOMC: {fomc['next_meeting']} ({fomc['days_until']}天后)")
        warnings = macro.get('warnings', [])
        if warnings:
            for w in warnings:
                lines.append(f"  ⚠️ {w}")
        if regime_str == 'NORMAL':
            lines.append("→ ✅ 宏观健康 — 正常操作，可激进")
        elif regime_str == 'CAUTIOUS':
            lines.append("→ ⚠️ 宏观审慎 — 防御板块优先，缩紧止损")
        else:
            lines.append("→ 🔴 宏观危机 — 暂停买入，持有现金")
    else:
        lines.append("  ⚠️ 无宏观数据 — 运行 macro_context.py 采集")
    lines.append("")

    # v5.0: 📊 市场广度
    lines.append("📊 【市场广度】")
    if breadth:
        health = breadth.get('health', '?')
        label = breadth.get('health_label', health)
        lines.append(f"状态: {label} | %>MA50: {breadth.get('pct_above_ma50','?')}% | %>MA200: {breadth.get('pct_above_ma200','?')}%")
        lines.append(f"涨 {breadth.get('advancers','?')} / 跌 {breadth.get('decliners','?')} | 涨跌比: {breadth.get('ad_ratio','?')}")
        lines.append(f"52周新高: {breadth.get('new_highs','?')} | 新低: {breadth.get('new_lows','?')}")

        sector_ranking = breadth.get('sector_ranking', [])
        if sector_ranking:
            top3 = [f"{r['name']}({r['pct_above_ma200']:.0f}%)" for r in sector_ranking[:3]]
            bot3 = [f"{r['name']}({r['pct_above_ma200']:.0f}%)" for r in sector_ranking[-3:]]
            lines.append(f"板块 TOP3: {', '.join(top3)}")
            lines.append(f"板块 BOT3: {', '.join(bot3)}")

        etf_perf = breadth.get('etf_performance', [])
        if etf_perf:
            top = etf_perf[0]
            bot = etf_perf[-1] if len(etf_perf) > 1 else etf_perf[0]
            lines.append(f"月资金流: {top['symbol']}({top['name']}) {top['ret_1m']:+.1f}% → {bot['symbol']}({bot['name']}) {bot['ret_1m']:+.1f}%")
    else:
        lines.append("  ⚠️ 无广度数据 — 运行 market_breadth.py 采集")
    lines.append("")

    # v5.0: 🎲 凯利仓位参考
    lines.append("🎲 【凯利仓位参考】")
    if kelly_data:
        k = kelly_data.get('kelly', {})
        if k:
            lines.append(f"胜率: {k['win_rate']*100:.1f}% ({k['wins']}胜/{k['losses']}负)")
            lines.append(f"赔率: {k['odds_ratio']} | 平均盈/亏: +{k['avg_win_pct']}% / -{k['avg_loss_pct']}%")
            lines.append(f"凯利最优: {k['kelly_full_pct']}% | 推荐半凯利: {k['kelly_half_pct']}%")
            lines.append(f"→ {k['recommendation']}")
        else:
            lines.append("  ⚠️ 数据不足")
    else:
        lines.append("  ⚠️ 无交易历史 — 运行 us_kelly.py 采集")
    lines.append("")

    # v5.0: ⚠️ 信号衰减
    lines.append("⚠️ 【信号衰减检测】")
    if decay_data:
        summary = decay_data.get('summary', {})
        alerts = decay_data.get('alerts', [])
        lines.append(f"🔴{summary.get('critical',0)} 🟡{summary.get('warning',0)} 🔵{summary.get('watch',0)} 🟢{summary.get('clean',0)}")

        critical_alerts = [a for a in alerts if a.get('level') == 'critical']
        warning_alerts = [a for a in alerts if a.get('level') == 'warning']
        if critical_alerts:
            lines.append("🔴 关键衰减:")
            for a in critical_alerts[:5]:
                lines.append(f"  {a['symbol']}: {a['message']}")
        if warning_alerts:
            lines.append("🟡 预警衰减:")
            for a in warning_alerts[:5]:
                lines.append(f"  {a['symbol']}: {a['message']}")
    else:
        lines.append("  ⚠️ 无衰减数据 — 运行 us_signal_decay.py 采集")
    lines.append("")

    # ─── 账户状态 ───
    lines.append("【账户状态】")
    acct = portfolio.get('account', {})
    equity = acct.get('equity', 0)
    cash = acct.get('cash', 0)
    util = acct.get('utilization', 0)
    target = acct.get('target_util', 0)
    gap = acct.get('gap_dollars', 0)
    dd = acct.get('drawdown', 0)
    narrative = acct.get('market_narrative', '?')
    lines.append(f"Equity: ${equity:,.0f} | Cash: ${cash:,.0f}")
    lines.append(f"仓位: {util*100:.1f}% → 目标 {target*100:.0f}% ({narrative}) | 缺口: ${gap:,.0f}")
    lines.append(f"回撤: {dd*100:.1f}%")
    lines.append("")

    # v4.7: 近期止损黑名单
    if blacklist_syms:
        lines.append(f"⛔ 【近期止损黑名单】 ({len(blacklist_syms)}只，7天内被止损，禁止重新买入)")
        for s in sorted(blacklist_syms):
            lines.append(f"  ⛔ {s}")
        lines.append("")

    # ─── 持仓分析 ───
    positions = portfolio.get('positions', [])
    if positions:
        lines.append(f"【持仓分析】 ({len(positions)}只)")
        for p in positions:
            sym = p['symbol']
            arrow = '🟢' if p['unrealized_pl'] >= 0 else '🔴'
            status_tag = ''
            if sym in blacklist_syms:
                status_tag = ' ⛔近期止损'
            elif p.get('status') == 'approaching_stop':
                status_tag = ' ⚠️近止损'
            elif p.get('status') == 'near_tp1':
                status_tag = ' 💰近止盈'
            # v4.7: 止损距离（从 portfolio 数据取）
            dist_stop = p.get('distance_to_stop', 0)
            dist_str = f'🛡{dist_stop*100:.0f}%' if dist_stop > 0 else ''
            lines.append(f"  {arrow} {sym:6s} [{p['sector']:9s}] {p['qty']:.0f}股 "
                        f"${p['current_price']:<8.2f} pl={p['unrealized_plpc']:+.1%} "
                        f"w={p['weight']*100:.1f}% {dist_str}{status_tag}")
    lines.append("")

    # ─── 板块分布 ───
    sector_alloc = portfolio.get('sector_allocation', {})
    if sector_alloc:
        lines.append("【板块分布】")
        for s, alloc in sorted(sector_alloc.items(), key=lambda x: -x[1].get('weight', 0)):
            name = SECTOR_NAMES.get(s, s)
            lines.append(f"  {name:6s}: {alloc['count']}只 {alloc['weight']*100:.1f}% ${alloc['market_value']:,.0f}")
    lines.append("")

    # ─── 板块缺口 ───
    sector_gaps = portfolio.get('sector_gaps', {})
    if sector_gaps:
        lines.append("【板块缺口】")
        for s, gap_info in sector_gaps.items():
            name = SECTOR_NAMES.get(s, s)
            cur = gap_info.get('current_weight', 0)
            tgt = gap_info.get('target_weight', 0)
            gap_amt = gap_info.get('gap_dollars', 0)
            lines.append(f"  ❌ {name}: {cur*100:.1f}% → {tgt*100:.0f}% (缺口 ${gap_amt:,.0f})")
    lines.append("")

    # ─── v5.2: 事件警告（从扫描器 critical_alerts 读取） ───
    wl_critical = watchlist.get('critical_alerts', []) if watchlist else []
    if wl_critical:
        lines.append("【⚠️ 重大事件警告 — 决策前必须检查】")
        for alert in wl_critical:
            lines.append(f"  {alert}")
        lines.append("  → 以上事件必须在买入决策中考虑，可能需要降低仓位或跳过相关板块")
        lines.append("")

    # ─── 扫描器候选 ───
    if watchlist:
        lines.append("【扫描器候选 TOP10】")
        all_ranked = watchlist.get('all_ranked', [])
        held_syms = {p['symbol'] for p in positions}

        for i, item in enumerate(all_ranked[:10], 1):
            if isinstance(item, dict):
                sym = item.get('symbol', '?')
                score = item.get('score', 0)
                price = item.get('price', 0)
                sector = item.get('sector', '?')
            else:
                sym = item
                score = 0
                price = 0
                sector = '?'

            held_mark = ' ✅已持仓' if sym in held_syms else ''
            gap_mark = ''
            if sector in sector_gaps:
                gap_mark = ' 🎯缺配'
            name = SECTOR_NAMES.get(sector, sector)
            ed = item.get('earnings_days') if isinstance(item, dict) else None
            ed_mark = f' 📅{ed}天' if ed is not None and ed <= 14 else ''
            lines.append(f"  #{i} {sym:6s} [{name:6s}] ${price:<8.2f} 动量{score:+.0f}{held_mark}{gap_mark}{ed_mark}")

        # 缺配板块的候选
        gap_candidates = []
        for item in all_ranked:
            sym = item.get('symbol', '?') if isinstance(item, dict) else item
            sector = item.get('sector', '?') if isinstance(item, dict) else '?'
            if sector in sector_gaps and sym not in held_syms:
                gap_candidates.append(f"{sym}({SECTOR_NAMES.get(sector, sector)})")
        if gap_candidates:
            lines.append(f"  缺配板块候选: {', '.join(gap_candidates[:8])}")
    lines.append("")

    # ─── v6: 财报日预警（持仓+候选） ───
    earnings_map = watchlist.get('earnings_map', {}) if watchlist else {}
    if earnings_map:
        held_earnings = []
        for p in positions:
            sym = p['symbol']
            ed = earnings_map.get(sym)
            if ed is not None and ed <= 14:
                held_earnings.append(f"{sym}({ed}天)")
        if held_earnings:
            lines.append("【📅 持仓财报预警】")
            lines.append(f"  {', '.join(held_earnings)}")
            lines.append("  → 财报≤3天: 缩紧止损到5% | 财报当天: 不做操作")
            lines.append("")

    # ─── 风险标记 ───
    risk_flags = portfolio.get('risk_flags', [])
    if risk_flags:
        lines.append("【风险标记】")
        for flag in risk_flags:
            lines.append(f"  ⚠️ {flag}")
        lines.append("")

    # ─── 挂单状态 ───
    orders = portfolio.get('orders', {})
    if orders.get('pending_buys') or orders.get('pending_sells'):
        lines.append(f"【挂单】 {orders.get('pending_buys', 0)}笔买入 + {orders.get('pending_sells', 0)}笔卖出")
        for o in orders.get('details', [])[:8]:
            lines.append(f"  {o['symbol']} {o['side']} {o['type']} qty={o['qty']} status={o['status']}")
        lines.append("")

    # ─── AI 决策区 ───
    lines.append("【AI 决策区】")
    lines.append("请综合以上所有维度判断（宏观+广度+事件+板块缺口+扫描器）：")
    lines.append("1. 买什么？（从候选选，优先板块健康TOP3 + 缺配板块 #3-5 位）")
    lines.append("2. 买多少股？（波动率分档 + 板块集中度 + 账户风险）")
    lines.append("3. 加仓已有还是开新仓？（看板块健康状况，弱板块不宜加仓）")
    lines.append("4. 有没有需要卖出/减仓的？（健康BOT3板块的持仓 = 候选卖出）")
    lines.append("")
    lines.append("执行命令格式：")
    lines.append("  python3 ~/.hermes/scripts/us_trader.py --execute '{\"orders\": [{\"symbol\": \"LMT\", \"qty\": 3, \"side\": \"buy\"}]}'")

    return "\n".join(lines)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='AI 决策报告生成器')
    parser.add_argument('--mode', choices=['aggressive', 'normal', 'cautious', 'defensive'],
                       default='normal', help='决策模式 (默认 normal)')
    parser.add_argument('--target-util', type=float, default=None,
                       help='目标仓位利用率 (0.0-1.0, 默认 0.50)')
    parser.add_argument('--update-weights', type=str, default=None,
                       help='JSON字符串: 更新评分权重, 如: {"score_weights": {"ret_1m": 0.5}}')
    args = parser.parse_args()

    # 权重更新：先更新，再生成报告
    if args.update_weights:
        weight_file = os.path.join(SRC_DIR, 'ai_weight_config.json')
        try:
            updates = json.loads(args.update_weights)
            existing = {}
            try:
                with open(weight_file) as f:
                    existing = json.load(f)
            except:
                pass
            # 合并（递归更新）
            for section, values in updates.items():
                if section in existing and isinstance(existing[section], dict) and isinstance(values, dict):
                    existing[section].update(values)
                else:
                    existing[section] = values
            existing['_meta'] = {
                'version': existing.get('_meta', {}).get('version', 1),
                'description': 'AI可调评分权重 — 每日开盘前由AI根据市场环境调整',
                'last_updated': datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M'),
                'updated_by': 'hermes_agent'
            }
            with open(weight_file, 'w') as f:
                json.dump(existing, f, indent=2)
            print(f'✅ 权重已更新 ({len(updates)} 个分组)')
        except Exception as e:
            print(f'❌ 权重更新失败: {e}')

    report = generate_report(mode=args.mode, target_util=args.target_util)
    print(report)
