#!/usr/bin/env python3
"""moa_decision.py — P4: MoA 决策链胶水代码
读扫描器/持仓/事件 → 输出结构化决策 JSON + 可读报告
"""
import json, os, sys
from datetime import datetime, timezone, timedelta

SRC = os.path.expanduser('~/stock_trader')
TZ = timezone(timedelta(hours=8))

def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}

def main():
    watchlist = load(f'{SRC}/us_watchlist.json')
    portfolio = load(f'{SRC}/us_portfolio.json')
    events = load(f'{SRC}/market_events_latest.json')

    # ── 扫描器候选 ──
    ranked = watchlist.get('all_ranked', [])
    buy = watchlist.get('buy_candidates', [])
    alerts = watchlist.get('critical_alerts', [])

    # ── 持仓 ──
    positions = portfolio.get('positions', [])
    sector_alloc = portfolio.get('sector_allocation', {})
    sector_gaps = portfolio.get('sector_gaps', {})
    risk_flags = portfolio.get('risk_flags', [])
    account = portfolio.get('account', {})

    # ── 决策输出 ──
    decision = {
        'timestamp': datetime.now(TZ).isoformat(),
        'phase': 'P4-MoA-decision-chain',
        'constitution': '3/3 ACTIVE',
        'account': {
            'equity': float(account.get('equity', 0)),
            'utilization': float(account.get('utilization', 0)),
            'target_util': float(account.get('target_util', 0)),
            'gap_dollars': float(account.get('gap_dollars', 0)),
            'drawdown': float(account.get('drawdown', 0)),
        },
        'positions': {
            'count': len(positions),
            'held': [{'symbol': p['symbol'], 'sector': p['sector'], 
                      'plpc': p.get('unrealized_plpc'), 'weight': p.get('weight'),
                      'stop_distance': p.get('distance_to_stop'),
                      'status': p.get('status')} for p in positions],
        },
        'scanner': {
            'top10': ranked[:10],
            'buy_candidates': buy[:10],
            'critical_alerts': alerts,
        },
        'sector': {
            'allocation': sector_alloc,
            'gaps': sector_gaps,
        },
        'risk_flags': risk_flags,
        'events_summary': events.get('market_narrative', 'unknown') if events else 'no data',
    }

    # 保存
    with open(f'{SRC}/moa_decision_report.json', 'w') as f:
        json.dump(decision, f, indent=2, ensure_ascii=False)
    print(f'✅ MoA 决策报告 → {SRC}/moa_decision_report.json')

    # 可读摘要
    print(f'账户: ${float(account.get("equity",0)):,.2f} | 仓位 {float(account.get("utilization",0))*100:.1f}% | 回撤 {float(account.get("drawdown",0))*100:.1f}%')
    print(f'扫描器: {len(ranked)} 只排名 | {len(buy)} 候选 | {len(alerts)} 警报')
    print(f'持仓: {len(positions)} 只 | {len(risk_flags)} 风险')
    if sector_gaps:
        gaps = [f'{s}({float(g.get("gap_dollars",0)):,.0f})' for s,g in sector_gaps.items()]
        print(f'板块缺口: {", ".join(gaps)}')

    return decision

if __name__ == '__main__':
    main()
