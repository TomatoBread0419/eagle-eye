# Termux mihomo 代理方案 (2026-06-10)

替代 Android 全局 VPN，在 Termux 内部运行 clash-meta 代理。
优势：不被 Android 杀后台、不耗系统 VPN 槽位、仅 Python 脚本走代理。

## 架构

```
mihomo (clash-meta) 后台进程
  ├── HTTP 代理: 127.0.0.1:7890
  └── SOCKS5:    127.0.0.1:7891
       ↓
proxy_patch.py → PySocks 自动 patch socket
       ↓
market_news.py / cron job → Google News RSS 走代理
Alpaca/微信/搜狗 → 直连不受影响
```

## 安装

```bash
# 1. 下载 mihomo (aarch64)
curl -L -o ~/tmp/mihomo.gz \
  https://github.com/MetaCubeX/mihomo/releases/download/v1.19.27/mihomo-linux-arm64-v1.19.27.gz
gunzip ~/tmp/mihomo.gz
mkdir -p ~/.local/bin
cp ~/tmp/mihomo ~/.local/bin/mihomo
chmod +x ~/.local/bin/mihomo

# 2. PySocks
pip install pysocks

# 3. 配置文件
~/.config/mihomo/config.yaml   # 编辑订阅链接
~/.hermes/scripts/proxy_start.py   # 管理脚本
~/.hermes/scripts/proxy_patch.py   # 自动补丁模块
```

## 配置

`~/.config/mihomo/config.yaml`:
```yaml
mixed-port: 7890
socks-port: 7891
allow-lan: false
bind-address: "127.0.0.1"
mode: rule
log-level: warning

proxy-providers:
  sub:
    type: http
    url: "YOUR_CLASH_SUBSCRIPTION_URL"
    interval: 3600
    path: ./providers/sub.yaml
    health-check:
      enable: true
      url: https://www.gstatic.com/generate_204
      interval: 600

proxy-groups:
  - name: PROXY
    type: url-test
    use: [sub]
    url: https://www.gstatic.com/generate_204
    interval: 300
    tolerance: 50

rules:
  - MATCH,PROXY
```

## 使用

```bash
python3 ~/.hermes/scripts/proxy_start.py start    # 启动
python3 ~/.hermes/scripts/proxy_start.py status   # 状态
python3 ~/.hermes/scripts/proxy_start.py test     # 测试Google连通性
python3 ~/.hermes/scripts/proxy_start.py stop     # 停止
```

## Python 集成

在需要翻墙的脚本顶部加一行：
```python
from proxy_patch import patch as _proxy_patch
_proxy_patch()  # mihomo不在运行则静默跳过
```

`market_news.py` 已集成，自动走代理访问 Google News RSS。

## 已知问题

- 订阅链接可能返回 504（服务器后端挂了），此时需从 Clash App 导出本地缓存配置
- mihomo 进程跟随 Termux session 生命周期，Termux 被杀则代理停止
- 建议配合 cron 健康检查自动重启
