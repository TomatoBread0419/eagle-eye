"""
proxy_patch.py -- 自动代理补丁
在需要翻墙的脚本顶部加一行即可:
    from proxy_patch import patch  # noqa

自动检测 mihomo 是否在运行，在则通过 SOCKS5 走代理。
不影响 Alpaca/Yahoo Finance 等直连服务。
"""
import os
import socket

SOCKS_HOST = '127.0.0.1'
SOCKS_PORT = 7891
PID_FILE = os.path.expanduser('~/.mihomo.pid')

_patched = False

def _is_proxy_running():
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return True
    except:
        return False

def patch(force=False):
    """给 socket 打 SOCKS5 补丁，mihomo 不在运行则跳过"""
    global _patched
    if _patched:
        return
    if not force and not _is_proxy_running():
        return

    try:
        import socks
        socks.set_default_proxy(socks.SOCKS5, SOCKS_HOST, SOCKS_PORT)
        socket.socket = socks.socksocket
        _patched = True
    except ImportError:
        pass  # pysocks 未安装，静默跳过
