#!/usr/bin/env python3
"""
契约验证器 v1 (2026-06-18)
验证鹰眼系统各模块之间的数据契约。
任何模块输出格式变化都会在这里被捕获。

用法: python3 contract_validator.py [--fix]
"""
import json, os, sys
from datetime import datetime

SRC_DIR = os.path.expanduser('~/stock_trader')

# ========== 契约定义 ==========
# 每个契约定义: 文件路径 + 必须存在的字段 + 字段类型

CONTRACTS = {
    'trade_history.json': {
        'path': f'{SRC_DIR}/trade_history.json',
        'required_top_level': ['kelly'],
        'optional_top_level': ['timestamp', 'period_days', 'total_orders',
                               'filled_orders', 'matched_trades'],
        'kelly_item': {
            'required': ['win_rate', 'odds_ratio'],
            'optional': ['total_trades', 'wins', 'losses', 'avg_win_pct',
                         'avg_loss_pct', 'kelly_full_pct'],
        },
    },
    'market_env.json': {
        'path': f'{SRC_DIR}/market_env.json',
        'required_top_level': ['timestamp', 'macro', 'breadth'],
        'macro_item': {
            'required': [],
            'optional': ['regime', 'vix', 'dxy', 'yield_10y', 'yield_2y',
                         'spread_10y2y', 'fomc'],
        },
        'breadth_item': {
            'required': [],
            'optional': ['health', 'pct_above_ma50', 'pct_above_ma200',
                         'advancers', 'decliners', 'ad_ratio'],
        },
    },
    'calibrated_params.json': {
        'path': f'{SRC_DIR}/calibrated_params.json',
        'required_top_level': ['_meta', 'kelly', 'stop_loss', 'score_weights'],
        'kelly_item': {
            'required': ['sigmoid_k', 'sigmoid_midpoint', 'target_alloc'],
            'optional': ['atr_to_odds_slope', 'atr_to_odds_intercept',
                         'max_pct_large_cap', 'max_pct_small_cap',
                         'actual_win_rate', 'sample_size', 'calibration_quality'],
        },
        'stop_loss_item': {
            'required': ['tier_vol_20', 'tier_vol_35', 'tier_vol_50', 'tier_vol_max'],
            'optional': ['false_stop_rate', 'adjustment', 'sample_size'],
        },
    },
    'us_watchlist.json': {
        'path': f'{SRC_DIR}/us_watchlist.json',
        'required_top_level': ['timestamp', 'buy_candidates'],
        'optional_top_level': ['kelly_allocations', 'total_scanned', 'success',
                               'critical_alerts'],
    },
    'signal_decay.json': {
        'path': f'{SRC_DIR}/signal_decay.json',
        'required_top_level': [],
        'optional_top_level': ['alerts', 'timestamp'],
    },
    'us_risk_state.json': {
        'path': f'{SRC_DIR}/us_risk_state.json',
        'required_top_level': [],
        'optional_top_level': ['positions', 'peak_equity', 'paused_drawdown'],
    },
    'compliance_report.json': {
        'path': f'{SRC_DIR}/compliance_report.json',
        'required_top_level': ['timestamp', 'total', 'compliant', 'details'],
    },
    'us_pending_replacements.json': {
        'path': f'{SRC_DIR}/us_pending_replacements.json',
        'required_top_level': [],
        'optional_top_level': ['pending'],
        'optional': True,  # 首次卖出前不存在是正常的
        'pending_item': {
            'required': ['symbol', 'reason', 'timestamp'],
            'optional': ['qty', 'price', 'replace_by'],
        },
    },
}


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        return {'_parse_error': str(e)}


def validate_contract(name, contract):
    """验证单个契约"""
    path = contract['path']
    data = load_json(path)
    
    result = {
        'name': name,
        'path': path,
        'exists': data is not None,
        'errors': [],
        'warnings': [],
    }
    
    if data is None:
        if contract.get('optional'):
            result['errors'] = []  # 可选文件不存在不算错误
            result['warnings'].append('文件不存在(可选,首次使用前正常)')
        else:
            result['errors'].append('文件不存在')
        return result
    
    if '_parse_error' in data:
        result['errors'].append(f'JSON解析失败: {data["_parse_error"]}')
        return result
    
    if not isinstance(data, dict):
        result['errors'].append(f'顶层不是dict，是{type(data).__name__}')
        return result
    
    # 检查必须存在的顶层字段
    for field in contract.get('required_top_level', []):
        if field not in data:
            result['errors'].append(f'缺少必须字段: {field}')
    
    # 检查trades数组项
    if 'trades_item' in contract:
        trades = data.get('matched_trades', data.get('trades', []))
        if isinstance(trades, list) and len(trades) > 0:
            sample = trades[0]
            for req in contract['trades_item'].get('required', []):
                if req not in sample:
                    result['errors'].append(f'trades[0]缺少必须字段: {req}')
        elif not isinstance(trades, list):
            result['errors'].append(f'trades不是list，是{type(trades).__name__}')
    
    # 检查kelly对象
    if 'kelly_item' in contract:
        kelly = data.get('kelly', data)
        if isinstance(kelly, dict):
            for req in contract['kelly_item'].get('required', []):
                if req not in kelly:
                    result['warnings'].append(f'kelly缺少推荐字段: {req}')
    
    # 检查pending数组项
    if 'pending_item' in contract and 'pending' in data:
        pending = data['pending']
        if isinstance(pending, list) and len(pending) > 0:
            sample = pending[0]
            for req in contract['pending_item'].get('required', []):
                if req not in sample:
                    result['errors'].append(f'pending[0]缺少必须字段: {req}')
    
    return result


def validate_all():
    """验证所有契约"""
    print(f'🔍 契约验证 | {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print(f'{"="*60}')
    
    results = []
    total_errors = 0
    total_warnings = 0
    
    for name, contract in CONTRACTS.items():
        r = validate_contract(name, contract)
        results.append(r)
        total_errors += len(r['errors'])
        total_warnings += len(r['warnings'])
        
        if r['errors']:
            icon = '❌'
        elif r['warnings']:
            icon = '⚠️'
        elif not r['exists']:
            icon = '⬜'
        else:
            icon = '✅'
        
        status = f'{len(r["errors"])}错误 {len(r["warnings"])}警告' if r['errors'] or r['warnings'] else 'OK'
        if not r['exists']:
            status = '不存在(首次运行前正常)'
        
        print(f'  {icon} {name}: {status}')
        for e in r['errors']:
            print(f'      ❌ {e}')
        for w in r['warnings']:
            print(f'      ⚠️ {w}')
    
    print(f'\n{"="*60}')
    print(f'总计: {total_errors} 错误, {total_warnings} 警告')
    
    if total_errors == 0:
        print(f'✅ 所有契约验证通过')
    else:
        print(f'❌ 有契约违反，需要修复上游模块')
    
    return results, total_errors


if __name__ == '__main__':
    results, errors = validate_all()
    sys.exit(1 if errors > 0 else 0)
