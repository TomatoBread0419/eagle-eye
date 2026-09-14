#!/usr/bin/env python3
"""
🦅 Eagle Eye V7.1 LTS — 美股智能交易系统

统一入口：
    python main.py status        # 系统状态
    python main.py report        # AI 决策报告
    python main.py scan          # 运行扫描器
    python main.py portfolio     # 持仓分析
    python main.py stops         # 止损/止盈管理
    python main.py execute       # 执行订单
    python main.py calibrate     # 参数自校准
    python main.py audit         # 规则合规审计
    python main.py health        # 健康检查
"""

import sys
import os
import argparse


def cmd_status():
    """系统状态总览"""
    from eagle_eye.core import cfg, runtime, get_logger

    logger = get_logger('main')
    info = runtime.system_info()

    print('🦅 Eagle Eye V7.1 LTS — 系统状态')
    print('=' * 50)
    print(f'  平台:     {info["platform"]}')
    print(f'  Python:   {info["python"]}')
    print(f'  根目录:   {info["root"]}')
    print(f'  数据目录: {info["data"]}')
    print(f'  日志目录: {info["log"]}')
    print(f'  市场状态: {info["market_status"]}')
    print(f'  北京时间: {info["time_bjt"]}')
    print(f'  美东时间: {info["time_et"]}')
    print()

    # 配置验证
    issues = cfg.validate()
    if issues:
        print('⚠️ 配置问题:')
        for issue in issues:
            print(f'  - {issue}')
    else:
        print('✅ 配置正常')

    # 数据目录检查
    print()
    print('📁 数据文件:')
    data_files = [
        ('ai_weight_config.json', '评分权重配置'),
        ('calibrated_params.json', '校准参数'),
        ('us_watchlist.json', '扫描器输出'),
        ('us_risk_state.json', '风控状态'),
        ('us_portfolio.json', '持仓分析'),
        ('trade_history.json', '交易历史'),
        ('signal_decay.json', '信号衰减'),
        ('market_env.json', '市场环境'),
    ]
    for filename, desc in data_files:
        path = cfg.data_dir / filename
        if path.exists():
            mtime = path.stat().st_mtime
            from datetime import datetime
            age = datetime.now().timestamp() - mtime
            if age < 3600:
                age_str = f'{age / 60:.0f}分钟前'
            elif age < 86400:
                age_str = f'{age / 3600:.1f}小时前'
            else:
                age_str = f'{age / 86400:.1f}天前'
            print(f'  ✅ {desc}: 更新于 {age_str}')
        else:
            print(f'  ❌ {desc}: 不存在')


def cmd_health():
    """健康检查"""
    from eagle_eye.core import cfg, runtime, get_logger

    logger = get_logger('health')
    print('🦅 Eagle Eye — 健康检查')
    print('=' * 50)

    checks = []

    # 1. 配置检查
    issues = cfg.validate()
    checks.append(('配置', len(issues) == 0, issues))

    # 2. 数据目录检查
    data_ok = cfg.data_dir.exists()
    checks.append(('数据目录', data_ok, [] if data_ok else [f'目录不存在: {cfg.data_dir}']))

    # 3. 日志目录检查
    log_ok = cfg.log_dir.exists()
    checks.append(('日志目录', log_ok, [] if log_ok else [f'目录不存在: {cfg.log_dir}']))

    # 4. API 连通性检查
    try:
        from eagle_eye.core import http_get
        code, _ = http_get(cfg.alpaca_base_url + '/v2/account', headers=cfg.alpaca_headers, retries=1)
        api_ok = code in (200, 401)  # 401=密钥错误但连通
        checks.append(('Alpaca API', api_ok, [] if api_ok else [f'HTTP {code}']))
    except Exception as e:
        checks.append(('Alpaca API', False, [str(e)]))

    # 输出结果
    all_ok = True
    for name, ok, issues in checks:
        status = '✅' if ok else '❌'
        print(f'  {status} {name}')
        if not ok:
            all_ok = False
        for issue in issues:
            print(f'      → {issue}')

    print()
    if all_ok:
        print('✅ 所有检查通过')
    else:
        print('⚠️ 部分检查失败，请修复后重试')


def cmd_v6_bridge(args):
    """
    V6 兼容桥接

    将命令转发到 V6 脚本，保持向后兼容。
    在 Phase 2-3 完成前，这是主要的运行方式。
    """
    import subprocess
    from eagle_eye.core import runtime

    v6_commands = {
        'report': 'us_report.py',
        'scan': 'us_screener.py',
        'portfolio': 'us_portfolio.py',
        'stops': 'us_trader.py --stops',
        'execute': 'us_trader.py --execute',
        'calibrate': 'calibrator.py',
        'audit': 'compliance_audit.py',
    }

    cmd = args.command
    if cmd not in v6_commands:
        print(f'未知命令: {cmd}')
        return 1

    script_args = v6_commands[cmd].split()
    script_path = runtime.script_path(script_args[0])

    if not script_path.exists():
        print(f'❌ 脚本不存在: {script_path}')
        return 1

    # 构建命令
    cmd_parts = [sys.executable, str(script_path)] + script_args[1:]

    # 传递额外参数
    if args.args:
        cmd_parts.extend(args.args)

    # 设置环境变量
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'

    print(f'🦅 V6 桥接: {" ".join(cmd_parts)}')
    result = subprocess.run(cmd_parts, env=env)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description='🦅 Eagle Eye V7.1 LTS — 美股智能交易系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('command', nargs='?', default='status',
                        choices=['status', 'health', 'report', 'scan', 'portfolio',
                                 'stops', 'execute', 'calibrate', 'audit'],
                        help='命令')
    parser.add_argument('args', nargs=argparse.REMAINDER,
                        help='传递给 V6 脚本的额外参数')

    args = parser.parse_args()

    # 确保目录存在
    from eagle_eye.core import cfg
    cfg.ensure_dirs()

    # 内置命令
    if args.command == 'status':
        cmd_status()
        return 0
    elif args.command == 'health':
        cmd_health()
        return 0
    else:
        # V6 桥接
        return cmd_v6_bridge(args)


if __name__ == '__main__':
    sys.exit(main() or 0)
