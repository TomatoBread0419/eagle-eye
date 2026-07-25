# Termux Mihomo 代理方案（Google News RSS 翻墙）

## 背景

Android VPN App 容易被系统杀后台 → Google News RSS 不可用 → 英文市场新闻断供。
解决方案：在 Termux 内跑 mihomo（clash-meta），只给 Python 脚本走代理，不占用系统 VPN 槽。

## 架构

```
mihomo (15MB Go binary)
  ↓ SOCKS5:127.0.0.1:7891
PySocks patch Python socket
  ↓
market_news.py / Google News RSS 走代理
Alpaca/微信/其他直连不受影响
```

## 安装（一次性）

```bash
# 1. 下载 mihomo
cd ~/tmp
curl -L -o mihomo.gz \
  "https://github.com/MetaCubeX/mihomo/releases/download/v1.19.27/mihomo-linux-arm64-v1.19.27.gz"
gunzip mihomo.gz
mkdir -p ~/.local/bin
cp mihomo ~/.local/bin/mihomo
chmod +x ~/.local/bin/mihomo
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

# 2. 安装 PySocks
pip install pysocks

# 3. 配置文件已生成在 ~/.config/mihomo/config.yaml
#    编辑它，填入 clash 订阅链接
```

## 使用

```bash
# 启动（从订阅链接拉取节点）
python3 ~/.hermes/scripts/proxy_start.py start

# 测试 Google 连通性
python3 ~/.hermes/scripts/proxy_start.py test

# 查看状态
python3 ~/.hermes/scripts/proxy_start.py status

# 停止
python3 ~/.hermes/scripts/proxy_start.py stop
```

## 自动集成

`market_news.py` 已内置代理检测——mihomo 运行时自动通过 SOCKS5 访问 Google News，未运行时直连（回退到搜狗微信）。

原理：
```python
from proxy_patch import patch
patch()  # 检测 ~/.mihomo.pid → 存在则打 SOCKS5 补丁
```

## 关键路径

| 文件 | 作用 |
|------|------|
| `~/.local/bin/mihomo` | clash-meta 二进制 |
| `~/.config/mihomo/config.yaml` | 代理配置（含订阅链接） |
| `~/.hermes/scripts/proxy_start.py` | 启动/停止/测试脚本 |
| `~/.hermes/scripts/proxy_patch.py` | Python socket 自动补丁模块 |
| `~/.mihomo.pid` | 运行时 PID 文件（用于检测） |
| `~/.mihomo.log` | 运行日志 |

## 端口

| 端口 | 协议 | 用途 |
|:---:|------|------|
| 7890 | HTTP | 通用 HTTP 代理 |
| 7891 | SOCKS5 | Python urllib 走此端口 |
| 9090 | REST API | clash 控制面板（仅本地） |

## 订阅故障排查

### 症状：mihomo 运行但 Google 不通

1. 检查订阅是否拉取成功：
   ```bash
   grep 'sub pull error' ~/.mihomo.log | tail -5
   ```
   - `504 Gateway Time-out` → 订阅源后端挂了，不是你的网络问题
   - `i/o timeout` → DNS/网络不通，检查 sitecustomize.py 是否生效

2. 检查 mihomo 是否有可用节点：
   ```bash
   curl -s http://127.0.0.1:9090/proxies | python3 -m json.tool | grep -A3 '"PROXY"'
   ```
   如果代理组为空 → 订阅没拉下来 → 节点为空 → 所有流量走 DIRECT → Google 超时

3. **订阅源 YOUR_VPN_SERVER_IP 后端挂掉的情况（2026-06-10 实测）**：
   - 直连返回 504 → 国内能访问但后端挂了
   - 走代理也 504 → 不是墙的问题，是服务器自己宕了
   - 解决方案：等恢复，或换 Shadowrocket 订阅链接
   - mihomo 也支持 Shadowrocket 格式：修改 `config.yaml` 中 `proxy-providers.sub.url` 为 Shadowrocket 订阅链接即可，类型保持 `http`

### 存活验证

无 Android VPN 时全链路测试通过（2026-06-10）：
- ✅ wallstreetcn 直连
- ✅ 搜狗微信 直连
- ✅ Alpaca API 直连
- ⚠️ Google News RSS — 依赖 mihomo 订阅正常拉取
