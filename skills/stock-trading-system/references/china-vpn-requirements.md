# 中国网络环境与 VPN 需求

## Google News RSS 被墙

**症状**: `news.google.com` socket 连接超时，市场事件监控 cron 失败。

**根因**: 中国运营商 DNS 劫持 + Google 服务被墙。

**影响**: 
- 市场事件监控 (d65b06eddcad) 无法获取英文新闻
- 只能用搜狗微信（国内直连）作为 fallback

**解决方案**:
1. **开 VPN**（推荐）— 全局代理后 Google News 正常
2. **改用国内数据源** — 搜狗微信 + 新浪财经 + 东方财富
3. **分流 VPN** — 只有 Google 走 VPN，Alpaca 直连

**验证**:
```bash
python3 -c "
import socket
hosts = ['news.google.com', 'weixin.sogou.com', 'paper-api.alpaca.markets']
for h in hosts:
    try:
        ip = socket.getaddrinfo(h, 443)[0][4][0]
        flag = '⚠️ HIJACKED' if ip.startswith('198.18.') else '✅'
        print(f'{flag} {h}: {ip}')
    except: print(f'❌ {h}: 超时')
"
```

**注意**: VPN 断开时，事件扫描失败但 Alpaca 交易不受影响（Alpaca 国内直连）。

**⚠️ Cron 任务 VPN 要求（2026-06-08 确认）：**
- 市场事件监控 cron 依赖 Google News RSS
- VPN 不开时，cron 静默失败（不报错，只是没数据）
- **交易时段请保持 VPN 开着**，否则事件扫描会静默失败
- 如果 VPN 不稳定，考虑改用国内数据源（搜狗微信 + 新浪财经）

## Alpaca 连接状态

| 服务 | 国内直连 | 需要 VPN |
|------|:---:|:---:|
| paper-api.alpaca.markets | ✅ | ❌ |
| data.alpaca.markets | ✅ | ❌ |
| query1.finance.yahoo.com | ✅ | ❌ |
| weixin.sogou.com | ✅ | ❌ |
| news.google.com | ❌ | ✅ |
| finnhub.io | ❌ | ✅ |
