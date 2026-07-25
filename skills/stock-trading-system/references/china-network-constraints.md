# 中国网络环境约束（2026-06-08 确认）

## 连通性测试结果

在深圳 Termux 环境下测试（无 VPN）：

| 服务 | 端口 | 状态 | 延迟 |
|------|------|------|------|
| news.google.com | 443 | ❌ 超时 | 被墙 |
| weixin.sogou.com | 443 | ✅ OK | 0.1s |
| query1.finance.yahoo.com | 443 | ✅ OK | 0.3s |
| paper-api.alpaca.markets | 443 | ⚠️ DNS劫持 | 代理可用 |
| data.alpaca.markets | 443 | ⚠️ DNS劫持 | 代理可用 |

### Alpaca DNS 劫持详情（2026-06-08 发现）

运营商 DNS 返回 `198.18.0.x` 代理 IP。代理可以转发请求到真实 Alpaca，但增加延迟。

| IP | TLS | API响应 | 建议 |
|----|-----|---------|------|
| 198.18.0.24 | ✅ TLSv1.3 | ✅ 401/200 | 可用（需 timeout=30） |
| 198.18.0.25 | ❌ TLS失败 | - | 不可用 |
| 198.18.0.37 | ❌ TLS失败 | - | 不可用 |

**修复**：
1. 直接调用 Alpaca API 时使用 `timeout=30`（不是默认 15s）
2. 安装 `dns-hijack-fix` skill 的 `sitecustomize.py`，自动重解析到真实 IP
3. 临时：在 `/data/data/com.termux/files/usr/etc/hosts` 添加 Alpaca 真实 IP

## 影响

- **Google News RSS**：市场事件监控的主数据源不可用
- **Google 搜索**：部分搜索可能超时
- **其他美国服务**：Yahoo/Alpaca 等正常

## 解决方案

### 方案 A: 开 VPN（简单但有风险）
- 所有流量走 VPN → Google News 可用
- 风险：Alpaca 可能变慢，VPN 不稳定导致 cron 失败

### 方案 B: 分流 VPN（推荐）
- 只有 Google 走 VPN，Alpaca/雅虎/搜狗直连
- 需要配置 VPN 分流规则

### 方案 C: 改用国内数据源（最稳）
- 搜狗微信（已通）→ 主源
- 新浪财经 RSS（国内直连）
- 东方财富 RSS（国内直连）
- 财联社电报（国内直连）

## 建议

市场事件监控的 cron 应该：
1. 主源用搜狗微信（国内直连，0.1s）
2. 备源用 Yahoo Finance（国内直连，0.3s）
3. Google News 作为可选（需要 VPN）

## DNS 劫持

已通过 sitecustomize.py 修复（见 dns-hijack-fix skill）。
198.18.0.x 劫持 → 自动 Google DoH 重解析。
