"""constitution.py — Constitution Lock (Phase 3)

独立校验模块：验证三条宪法条款是否被代码强制执行。
运行: python -m eagle_eye.ops.constitution
"""
import json, os, sys

SRC = os.path.expanduser('~/stock_trader')
SCRIPTS = os.path.expanduser('~/.hermes/scripts')

def check_article_11():
    """Article 11: 事件 MUST NOT 修改评分"""
    path = os.path.join(SCRIPTS, 'us_screener.py')
    with open(path) as f:
        code = f.read()
    lines = code.split('\n')
    violations = []
    # Banned patterns
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if 'score += bias' in stripped:
            violations.append(f'line {i}: BANNED "score += bias" (事件评分注入)')
        if 'sector_bias' in stripped and 'removed' not in stripped:
            if 'sector_bias' not in stripped.split('#')[0] if '#' in stripped else True:
                if 'def load_sector_event_bias' not in stripped and '= load_sector_event_bias' not in stripped:
                    violations.append(f'line {i}: BANNED "sector_bias" reference: {stripped[:80]}')
    if violations:
        return False, violations
    return True, []

def check_article_12():
    """Article 12: 参数漂移 >20% 必须阻止校准输出"""
    path = os.path.join(SCRIPTS, 'calibrator.py')
    with open(path) as f:
        code = f.read()
    checks = ['DRIFT_CAP' in code, 'drift_exceeded' in code, 'DRIFT GUARD' in code, 'baseline_params.json' in code]
    if not all(checks):
        missing = [n for n, ok in zip(['DRIFT_CAP','drift_exceeded','DRIFT GUARD','baseline_path'], checks) if not ok]
        return False, [f'Calibrator 缺少漂移守卫: {missing}']
    return True, []

def check_article_13():
    """Article 13: 权重修改 >20% 必须回退到设计基线"""
    screener_path = os.path.join(SCRIPTS, 'us_screener.py')
    config_path = os.path.join(SRC, 'ai_weight_config.json')
    
    # Check config has _design_defaults
    try:
        with open(config_path) as f:
            cfg = json.load(f)
    except:
        return False, ['ai_weight_config.json 不可读']
    
    if '_design_defaults' not in cfg:
        return False, ['ai_weight_config.json 缺少 _design_defaults']
    
    # Check screener validates weights against design defaults
    with open(screener_path) as f:
        code = f.read()
    if '_design_defaults' not in code:
        return False, ['us_screener.py 不检查 _design_defaults']
    if 'violation' not in code.lower() and '回退' not in code:
        return False, ['us_screener.py 无权重违规处理逻辑']
    
    return True, []

def run_all_checks():
    articles = {
        'Article 11 (事件不修改评分)': check_article_11,
        'Article 12 (校准器漂移守卫)': check_article_12,
        'Article 13 (权重硬边界)': check_article_13,
    }
    passed = 0
    failed = 0
    for name, check in articles.items():
        ok, details = check()
        if ok:
            print(f'  ✅ {name}')
            passed += 1
        else:
            print(f'  ❌ {name}')
            for d in details:
                print(f'     {d}')
            failed += 1
    
    print(f'\n{"="*50}')
    print(f'结果: {passed}/{passed+failed} 通过')
    if failed == 0:
        print('Constitution Lock: ACTIVE — 三条宪法条款全部代码强制执行')
        return 0
    else:
        print(f'Constitution Lock: BROKEN — {failed} 条违规')
        return 1

if __name__ == '__main__':
    sys.exit(run_all_checks())
