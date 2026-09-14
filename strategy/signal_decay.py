#!/usr/bin/env python3
"""
strategy/signal_decay.py — 信号衰减检测 (V7.1 Phase 4)
检查所有持仓的买入理由是否仍然成立，每2h自动运行。
输出: cfg.data_dir / 'signal_decay.json'

检测维度:
  🔴 RSI > 75     → 过热 (warning)
  🔴 MACD 死叉    → 趋势反转 (critical)
  🔴 价格 < MA50  → 中期趋势破坏 (critical)
  🟡 价格 < MA20  → 短期走弱 (warning)
  🟢 盈利 >25%    → 建议缩紧止盈线 (watch)
"""

import json
from datetime import datetime, timezone, timedelta

from eagle_eye.core.config import cfg
from eagle_eye.core.logger import get_logger
from eagle_eye.broker.alpaca_client import get_alpaca_client
from eagle_eye.strategy.indicator_engine import calc_rsi, calc_sma, calc_macd

logger = get_logger('strategy.decay')


def get_holdings():
    """从 Alpaca 获取当前持仓，返回统一格式"""
    try:
        client = get_alpaca_client()
        positions = client.get_positions()
        if not positions:
            print('  ⚠️ 持仓获取失败: 无数据')
            return []
        return [{
            'symbol': p['symbol'],
            'qty': float(p['qty']),
            'avg_entry': float(p['avg_entry_price']),
            'current': float(p['current_price']),
            'market_value': float(p['market_value']),
            'pnl_pct': float(p['unrealized_plpc']) * 100,
        } for p in positions]
    except Exception as e:
        print(f'  ⚠️ 持仓获取失败: {e}')
        return []


def check_decay(pos):
    """检查单只持仓的信号衰减"""
    sym = pos['symbol']
    try:
        client = get_alpaca_client()
        bars = client.get_bars(sym, days=85, limit=70)
        if not bars or len(bars) < 20:
            return {'symbol': sym, 'error': '数据不足'}

        closes = [b['c'] for b in bars]
        current = closes[-1]
        rsi14 = calc_rsi(closes, 14)
        ma20 = calc_sma(closes, 20)
        ma50 = calc_sma(closes, 50) if len(closes) >= 50 else None
        macd_line, signal_line, histogram, crossover = calc_macd(closes)

        signals = []

        # RSI 过热
        if rsi14 is not None and rsi14 > 75:
            signals.append({
                'type': 'warning',
                'code': 'RSI_OVERHEAT',
                'message': f'RSI={rsi14} 过热，做好止盈准备',
                'rsi': rsi14,
            })

        # MACD 死叉
        if crossover == 'death':
            signals.append({
                'type': 'critical',
                'code': 'MACD_DEATH_CROSS',
                'message': 'MACD死叉，趋势可能反转',
            })

        # 破 MA50
        if ma50 and current < ma50:
            signals.append({
                'type': 'critical',
                'code': 'BELOW_MA50',
                'message': f'跌破MA50(${ma50:.2f})，中期趋势破坏',
                'ma50': round(ma50, 2),
            })

        # 破 MA20
        if ma20 and current < ma20:
            signals.append({
                'type': 'warning',
                'code': 'BELOW_MA20',
                'message': f'跌破MA20(${ma20:.2f})，短期走弱',
                'ma20': round(ma20, 2),
            })

        # 大幅盈利
        if pos['pnl_pct'] > 25:
            signals.append({
                'type': 'watch',
                'code': 'LARGE_PROFIT',
                'message': f'浮盈+{pos["pnl_pct"]:.0f}%，建议缩紧止盈线',
            })

        # 整体衰减等级
        has_critical = any(s['type'] == 'critical' for s in signals)
        has_warning = any(s['type'] == 'warning' for s in signals)

        if has_critical:
            decay_level = 'CRITICAL'
        elif has_warning:
            decay_level = 'WARNING'
        elif any(s['type'] == 'watch' for s in signals):
            decay_level = 'WATCH'
        else:
            decay_level = 'CLEAN'

        return {
            'symbol': sym,
            'current': round(current, 2),
            'avg_entry': round(pos['avg_entry'], 2),
            'pnl_pct': round(pos['pnl_pct'], 1),
            'rsi14': rsi14,
            'ma20': round(ma20, 2) if ma20 else None,
            'ma50': round(ma50, 2) if ma50 else None,
            'macd_crossover': crossover,
            'decay_level': decay_level,
            'signals': signals,
        }

    except Exception as e:
        return {'symbol': sym, 'error': str(e)}


def main():
    now = datetime.now(timezone(timedelta(hours=8)))

    print(f'🔬 信号衰减检测 | {now.strftime("%Y-%m-%d %H:%M")}')

    # 1. 获取持仓
    holdings = get_holdings()
    if not holdings:
        print('  ℹ️ 当前无持仓')
        result = {'timestamp': now.isoformat(), 'holdings': 0, 'checks': [], 'alerts': []}
        output_path = cfg.data_dir / 'signal_decay.json'
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        return

    print(f'  检查 {len(holdings)} 只持仓...')

    # 2. 逐一检查
    checks = []
    for i, pos in enumerate(holdings):
        r = check_decay(pos)
        checks.append(r)
        if (i + 1) % 10 == 0:
            print(f'  [{i + 1}/{len(holdings)}]')

    # 3. 汇总
    criticals = [c for c in checks if c.get('decay_level') == 'CRITICAL']
    warnings = [c for c in checks if c.get('decay_level') == 'WARNING']
    watches = [c for c in checks if c.get('decay_level') == 'WATCH']
    cleans = [c for c in checks if c.get('decay_level') == 'CLEAN']
    errors = [c for c in checks if 'error' in c]

    result = {
        'timestamp': now.isoformat(),
        'holdings': len(holdings),
        'summary': {
            'critical': len(criticals),
            'warning': len(warnings),
            'watch': len(watches),
            'clean': len(cleans),
            'error': len(errors),
        },
        'alerts': [],
        'checks': checks,
    }

    # 构建告警列表
    for c in checks:
        for s in c.get('signals', []):
            alert = {
                'symbol': c['symbol'],
                'level': s['type'],
                'code': s['code'],
                'message': s['message'],
            }
            if s['type'] == 'critical':
                result['alerts'].insert(0, alert)  # 置顶
            else:
                result['alerts'].append(alert)

    output_path = cfg.data_dir / 'signal_decay.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)

    # 可读输出
    print(f'\n{"="*45}')
    print(f'📊 信号衰减 | 🔴{len(criticals)} 🟡{len(warnings)} 🔵{len(watches)} 🟢{len(cleans)}')

    if criticals:
        print(f'\n🔴 需要立即关注:')
        for c in criticals:
            print(f'  {c["symbol"]:6s} ${c["current"]:>8.2f} PnL {c["pnl_pct"]:+.1f}%')
            for s in c.get('signals', []):
                print(f'    → {s["message"]}')

    if warnings:
        print(f'\n🟡 需要关注:')
        for c in warnings:
            print(f'  {c["symbol"]:6s} ${c["current"]:>8.2f} PnL {c["pnl_pct"]:+.1f}%')
            for s in c.get('signals', []):
                print(f'    → {s["message"]}')

    if watches:
        print(f'\n🔵 仅观察:')
        for c in watches[:5]:
            print(f'  {c["symbol"]:6s} {c["signals"][0]["message"] if c.get("signals") else ""}')

    if not criticals and not warnings:
        print('\n✅ 所有持仓买入理由仍成立，无衰减信号。')

    print(f'\n✅ 已保存: {output_path}')


if __name__ == '__main__':
    main()
