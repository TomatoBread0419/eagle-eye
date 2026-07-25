#!/usr/bin/env python3
"""
规则合规审计器 v1 (2026-06-17)
自动检查用户偏好是否有对应代码实现。
解决"规则三层断裂"问题——规则在Memory/SKILL但不在代码中。

输出: compliance_report.json
"""
import json, os, re
from datetime import datetime

SRC_DIR = os.path.expanduser('~/stock_trader')
SCRIPTS_DIR = os.path.expanduser('~/.hermes/scripts')
OUTPUT = f'{SRC_DIR}/compliance_report.json'

# ========== 用户偏好清单 ==========
# 从Memory/SKILL.md提取的全部用户偏好
# 每条检查: 脚本中是否有对应的代码实现

USER_PREFERENCES = [
    {
        'id': 'P01',
        'name': '龙头回避',
        'description': '板块#1-2跳过，选#3-5轮动',
        'check_patterns': [r"sector_leader"],
        'files': ['us_screener.py'],
    },
    {
        'id': 'P02',
        'name': '7天止损黑名单',
        'description': '止损后7天不重买',
        'check_patterns': [r'recent_stops', r'stop.*blacklist'],
        'files': ['us_screener.py', 'us_trader.py'],
    },
    {
        'id': 'P03',
        'name': '财报≤5天不建仓',
        'description': '财报临近不建新仓',
        'check_patterns': [r'earnings_days', r'ed <= 5'],
        'files': ['us_screener.py'],
    },
    {
        'id': 'P04',
        'name': '动态凯利仓位',
        'description': '每只标的仓位根据score和ATR动态计算',
        'check_patterns': [r'kelly_position_sizes', r'kelly_pct', r'sigmoid'],
        'files': ['us_screener.py'],
    },
    {
        'id': 'P05',
        'name': '波动率分档止损',
        'description': '根据20日波动率分7-10%四档',
        'check_patterns': [r'get_volatility_stop_pct', r'tier_vol'],
        'files': ['us_common.py', 'us_trader.py'],
    },
    {
        'id': 'P06',
        'name': '回撤>12%停买',
        'description': '账户回撤超过12%暂停买入',
        'check_patterns': [r'DRAWDOWN_PAUSE.*0\.12', r'drawdown.*pause'],
        'files': ['us_trader.py'],
    },
    {
        'id': 'P07',
        'name': '回撤>20%减半仓',
        'description': '账户回撤超过20%强制减半',
        'check_patterns': [r'DRAWDOWN_CUT.*0\.20', r'drawdown.*cut'],
        'files': ['us_trader.py'],
    },
    {
        'id': 'P08',
        'name': '阶梯止盈 +20%/+35%',
        'description': '盈利20%卖1/3，35%再卖1/3',
        'check_patterns': [r'take_profit', r'TP.*20', r'TP.*35', r'execute_take_profit'],
        'files': ['us_trader.py'],
    },
    {
        'id': 'P09',
        'name': 'MACD金叉/死叉',
        'description': 'MACD信号加入评分',
        'check_patterns': [r'calc_macd', r'golden_cross', r'death_cross'],
        'files': ['us_screener.py', 'us_common.py'],
    },
    {
        'id': 'P10',
        'name': 'RS vs SPY相对强度',
        'description': '区分真涨和随大盘涨',
        'check_patterns': [r'spy_ret_1m', r'rs_1m', r'rs_vs_spy'],
        'files': ['us_screener.py'],
    },
    {
        'id': 'P11',
        'name': '成交量确认',
        'description': '放量上涨+3/缩量虚涨-3',
        'check_patterns': [r'calc_volume_metrics', r'bullish_confirmation', r'divergence_penalty'],
        'files': ['us_screener.py', 'us_common.py'],
    },
    {
        'id': 'P12',
        'name': '板块缺配加分',
        'description': '缺配板块的标的评分加权',
        'check_patterns': [r'sector_gap_scoring', r'sector_gaps'],
        'files': ['us_screener.py'],
    },
    {
        'id': 'P13',
        'name': '事件→板块映射',
        'description': '市场事件利好/利空映射到板块',
        'check_patterns': [r'read_event_alerts'],
        'files': ['us_screener.py'],
    },
    {
        'id': 'P14',
        'name': 'sell→buy配对',
        'description': '卖出后必须有对应的买入',
        'check_patterns': [r'log_sell_for_replacement', r'pending_replacement'],
        'files': ['us_trader.py'],
    },
    {
        'id': 'P15',
        'name': '止损后1h替代买入',
        'description': '止损触发后1小时内必须有替代',
        'check_patterns': [r'check_pending_replacements', r'replace_by'],
        'files': ['us_trader.py'],
    },
    {
        'id': 'P16',
        'name': 'FOMC日不做操作',
        'description': 'FOMC当天不做任何操作',
        'check_patterns': [r'fomc', r'FOMC'],
        'files': ['us_trader.py', 'market_env.py'],
    },
    {
        'id': 'P17',
        'name': '参数自校准',
        'description': '参数从实际交易数据中自动校准',
        'check_patterns': [r'calibrated_params', r'calibrator'],
        'files': ['us_screener.py', 'calibrator.py'],
    },
    {
        'id': 'P18',
        'name': '市场状态检测',
        'description': '自动检测trending/volatile/crisis/quiet',
        'check_patterns': [r'detect_regime', r'regime'],
        'files': ['calibrator.py'],
    },
    {
        'id': 'P19',
        'name': '30%仓位门槛→市价单',
        'description': '仓位低时用市价单不纠结',
        'check_patterns': [r'LOW_UTIL_FORCE_MARKET', r'force_market'],
        'files': ['us_trader.py'],
    },
    {
        'id': 'P20',
        'name': '板块龙头标👑不过度集中',
        'description': '保留的标的不全是板块龙头',
        'check_patterns': [r'sector_leader'],
        'files': ['us_screener.py'],
    },
]


def _check_preference(pref):
    """检查单条偏好是否有代码实现"""
    if pref.get('check_patterns') is None:
        return {
            'id': pref['id'],
            'name': pref['name'],
            'description': pref['description'],
            'status': '❌',
            'note': pref.get('note', '无代码实现'),
        }

    patterns = pref['check_patterns']
    for fname in pref.get('files', []):
        fpath = os.path.join(SCRIPTS_DIR, fname)
        try:
            with open(fpath) as f:
                content = f.read()
            for pattern in patterns:
                if re.search(pattern, content):
                    return {
                        'id': pref['id'],
                        'name': pref['name'],
                        'description': pref['description'],
                        'status': '✅',
                        'file': fname,
                        'matched_pattern': pattern,
                    }
        except FileNotFoundError:
            pass

    return {
        'id': pref['id'],
        'name': pref['name'],
        'description': pref['description'],
        'status': '⚠️',
        'note': f'模式未在 {", ".join(pref["files"])} 中找到',
    }


def audit_compliance():
    """运行合规审计"""
    print(f'🔍 规则合规审计 | {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print(f'{"="*60}')

    report = []
    for pref in USER_PREFERENCES:
        status = _check_preference(pref)
        report.append(status)

    compliant = sum(1 for r in report if r['status'] == '✅')
    partial = sum(1 for r in report if r['status'] == '⚠️')
    missing = sum(1 for r in report if r['status'] == '❌')

    result = {
        'timestamp': datetime.now().isoformat(),
        'total': len(report),
        'compliant': compliant,
        'partial': partial,
        'missing': missing,
        'compliance_rate': round(compliant / len(report) * 100, 1),
        'details': report,
    }

    # 输出
    for r in report:
        icon = r['status']
        note = r.get('note', r.get('file', ''))
        print(f'  {icon} {r["id"]}: {r["name"]} — {note}')

    print(f'\n{"="*60}')
    print(f'合规率: {compliant}/{len(report)} ({result["compliance_rate"]}%)')
    print(f'  ✅ 有代码实现: {compliant}')
    print(f'  ⚠️ 部分实现:   {partial}')
    print(f'  ❌ 无代码实现: {missing}')

    if missing > 0:
        print(f'\n❌ 以下规则需要写入代码:')
        for r in report:
            if r['status'] == '❌':
                print(f'  - {r["id"]}: {r["name"]} ({r["description"]})')

    # 保存
    with open(OUTPUT, 'w') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f'\n✅ 报告已保存 → {OUTPUT}')

    return result


if __name__ == '__main__':
    audit_compliance()
