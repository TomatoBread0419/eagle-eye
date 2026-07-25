#!/usr/bin/env python3
"""
verification_script_template.py — 硬化规则验证脚本模板

用法：
  1. 复制本文件为目标规则的 verify_xxx.py
  2. 在 STATIC_CHECKS 列表里定义 9 项静态检查
  3. 在 dynamic_check() 里定义实时账户/系统状态检查
  4. 跑：`python3 verify_xxx.py`

设计原则（2026-06-04 教训）：
  - 静态检查覆盖"代码层机械执行"的 8 个关键点
  - 动态检查用真实 API 数据验证当前是否触发硬约束
  - 输出统一格式：✅/❌/🔴/🟡/🟢 + 1-2 行 actionable 总结
  - 不静默：任何 ❌ 都要给出"如何修"

配套文档：references/hard-constraints-design-pattern.md
"""
import sys, os, json
from datetime import datetime, timezone, timedelta

# ── 路径配置 ──
SRC_DIR = '$HOME/stock_trader'
TARGET_SCRIPT = '/path/to/your/hardened_script.py'  # 改成实际目标
sys.path.insert(0, SRC_DIR)
os.chdir(SRC_DIR)

# ── 静态检查列表（9 项标准） ──
STATIC_CHECKS = [
    # Step 1: 常量定义
    {
        'name': '常量 HARD_X 已定义',
        'test': lambda c: 'HARD_X = ' in c,
        'fix': '在脚本顶部加 HARD_X = ...  定义阈值',
    },
    {
        'name': '常量 HARD_MIN_BUY_PER_RUN 已定义',
        'test': lambda c: 'HARD_MIN_BUY_PER_RUN = ' in c,
        'fix': '在脚本顶部加 HARD_MIN_BUY_PER_RUN = 1  至少下 1 笔',
    },
    # Step 2: 机械执行（非只 print）
    {
        'name': 'X 段真下 market buy（不是只 print）',
        'test': lambda c: "place_market_order(" in c and "buy_msgs.append(" in c and "X" in c,
        'fix': '把 print(...) 改成 place_market_order(...) + buy_msgs.append 报告',
    },
    # Step 3: 硬约束 fallback 块存在
    {
        'name': '硬约束块存在（注释标记）',
        'test': lambda c: '硬约束块' in c or 'HARD CONSTRAINT' in c,
        'fix': '在 §6e 或等效位置加硬约束 fallback 块',
    },
    # Fallback
    {
        'name': '硬约束块 fallback 到 all_ranked/主候选源',
        'test': lambda c: "'all_ranked'" in c or "fallback" in c.lower(),
        'fix': '硬约束块在主候选池空时必须有 fallback（不能直接退出）',
    },
    # 规则 3
    {
        'name': '候选 ≥ 3 → 默认选 pool[0]（不纠结）',
        'test': lambda c: 'pool = list(dict.fromkeys' in c or 'pool[0]' in c,
        'fix': '候选去重保序后直接 pool[0]，不允许"再想想"分支',
    },
    # 标识
    {
        'name': '硬约束块用 client_order_id 标识',
        'test': lambda c: 'client_order_id' in c and 'hardutil_' in c,
        'fix': "下硬约束单时加 client_order_id=f'hardutil_{ts}'  便于回溯",
    },
    # 不静默
    {
        'name': '硬约束块失败必报告（不静默）',
        'test': lambda c: '🔴 硬约束失败' in c or '硬约束失败' in c,
        'fix': '硬约束触发但失败时，必须报告 🔴 硬约束失败 + 原因',
    },
    # 通用：limit 单 + 现价 -1% 限价
    {
        'name': '硬约束 buy 用 limit 单（避免市价滑点）',
        'test': lambda c: "'type': 'limit'" in c or "limit_price" in c,
        'fix': "type='limit' + limit_price = current * 0.99 + time_in_force='day'",
    },
]


def run_static_checks(content):
    """跑所有静态检查，返回 (passed_count, total_count, failures[])"""
    passed = 0
    failures = []
    for check in STATIC_CHECKS:
        try:
            ok = check['test'](content)
        except Exception as e:
            ok = False
            failures.append((check['name'], f'测试异常: {e}'))
            continue
        if ok:
            passed += 1
        else:
            failures.append((check['name'], check['fix']))
    return passed, len(STATIC_CHECKS), failures


def dynamic_check():
    """
    子类覆盖：实时账户/系统状态检查
    返回: {
        'triggered': bool,   # 硬约束是否当前应触发
        'context': str,      # 1-2 行说明
        'expected_action': str,  # 预期系统做什么
    }
    """
    # ── 子类实装 ──
    # 例：拉 Alpaca 账户 + 计算 util
    # import config, urllib.request
    # req = urllib.request.Request('https://paper-api.alpaca.markets/v2/account', headers={...})
    # with urllib.request.urlopen(req, timeout=10) as r:
    #     acct = json.loads(r.read())
    # equity = float(acct['equity'])
    # cash = float(acct['cash'])
    # util = (equity - cash) / equity
    #
    # return {
    #     'triggered': util < 0.38,
    #     'context': f'util {util*100:.1f}% (cash ${cash:,.0f} / equity ${equity:,.0f})',
    #     'expected_action': 'us_trader.py §6e 块应自动下 1 笔 buy',
    # }
    return {
        'triggered': False,
        'context': '子类未实装 dynamic_check()',
        'expected_action': 'N/A',
    }


def main():
    print('═' * 60)
    print(f'🔧 硬约束验证 | {datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")} BJT')
    print(f'   目标脚本: {TARGET_SCRIPT}')
    print('═' * 60)

    # 1. 静态检查
    print('\n📋 第一部分：静态检查')
    try:
        content = open(TARGET_SCRIPT).read()
    except FileNotFoundError:
        print(f'  ❌ 找不到目标脚本: {TARGET_SCRIPT}')
        return
    passed, total, failures = run_static_checks(content)
    for name, fix in failures:
        print(f'  ❌ {name}')
        print(f'     └─ 修复: {fix}')
    for check in STATIC_CHECKS:
        if check['name'] not in [f[0] for f in failures]:
            print(f'  ✅ {check["name"]}')
    print(f'\n  静态检查: {passed}/{total} 通过')

    # 2. 动态检查
    print('\n💰 第二部分：动态检查（实时状态）')
    result = dynamic_check()
    if result['triggered']:
        print(f'  🔴 触发硬约束')
        print(f'     状态: {result["context"]}')
        print(f'     预期: {result["expected_action"]}')
    else:
        print(f'  ✅ 未触发: {result["context"]}')
        print(f'     ({result["expected_action"]})')

    # 3. 总结
    print('\n' + '═' * 60)
    if passed == total and result['triggered']:
        print('🟡 硬约束已就位 + 当前应触发。下一个 cron tick 将自动执行。')
    elif passed == total:
        print('✅ 所有静态检查通过。当前状态未触发硬约束。')
    elif passed >= total - 2:
        print(f'⚠️ 静态检查 {passed}/{total}。需补 {total - passed} 项才能完全硬化。')
    else:
        print(f'❌ 静态检查严重不足（{passed}/{total}）。需重做硬化流程。')
    print('═' * 60)


if __name__ == '__main__':
    main()
