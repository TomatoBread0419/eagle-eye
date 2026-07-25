#!/usr/bin/env python3
"""
🦅 Eagle Eye — 美股智能交易系统 v4 入口
用法: eagle-eye report|scan|portfolio|stops|execute|status|help
"""
import sys, os, subprocess

HOME = os.path.expanduser('~')
SCRIPTS = f'{HOME}/.hermes/scripts'
PYTHON = 'python3'

COMMANDS = {
    'report': f'{SCRIPTS}/us_report.py',
    'scan': f'{SCRIPTS}/us_screener.py',
    'portfolio': f'{SCRIPTS}/us_portfolio.py',
    'trader': f'{SCRIPTS}/us_trader.py',
}

def run_script(script, args=None):
    cmd = [PYTHON, script] + (args or [])
    return subprocess.run(cmd, capture_output=False, text=True, timeout=120).returncode

def show_status():
    print('🦅 Eagle Eye 系统状态')
    print('='*40)
    files = {
        '持仓分析器': f'{SCRIPTS}/us_portfolio.py',
        '扫描器 v2': f'{SCRIPTS}/us_screener.py',
        '执行器': f'{SCRIPTS}/us_trader.py',
        '决策报告': f'{SCRIPTS}/us_report.py',
        '共享模块': f'{SCRIPTS}/us_common.py',
        '新闻收集': f'{SCRIPTS}/market_news.py',
    }
    print('\n组件:')
    for name, path in files.items():
        exists = '✅' if os.path.exists(path) else '❌'
        print(f'  {exists} {name}: {os.path.basename(path)}')
    data_dir = f'{HOME}/stock_trader'
    data_files = {
        '持仓数据': f'{data_dir}/us_portfolio.json',
        '扫描结果': f'{data_dir}/us_watchlist.json',
        '市场事件': f'{data_dir}/market_events_latest.json',
        '风控状态': f'{data_dir}/us_risk_state.json',
    }
    print('\n数据:')
    for name, path in data_files.items():
        if os.path.exists(path):
            mtime = os.path.getmtime(path)
            from datetime import datetime
            age = datetime.now() - datetime.fromtimestamp(mtime)
            hours = age.total_seconds() / 3600
            age_str = f'{age.total_seconds()/60:.0f}分钟前' if hours < 1 else f'{hours:.1f}小时前'
            print(f'  ✅ {name}: 更新于 {age_str}')
        else:
            print(f'  ❌ {name}: 不存在')

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1].lower()
    if cmd in ('help', '--help', '-h'):
        print(__doc__)
    elif cmd == 'status':
        show_status()
    elif cmd == 'report':
        run_script(COMMANDS['report'])
    elif cmd == 'scan':
        run_script(COMMANDS['scan'])
    elif cmd == 'portfolio':
        run_script(COMMANDS['portfolio'])
    elif cmd == 'stops':
        run_script(COMMANDS['trader'], ['--stops'])
    elif cmd == 'execute':
        if len(sys.argv) < 3:
            orders = sys.stdin.read().strip()
            if orders:
                run_script(COMMANDS['trader'], ['--execute', orders])
            else:
                print('用法: eagle-eye execute \'{"orders": [...]}\'')
        else:
            run_script(COMMANDS['trader'], ['--execute', sys.argv[2]])
    else:
        print(f'未知命令: {cmd}')
        print(__doc__)
