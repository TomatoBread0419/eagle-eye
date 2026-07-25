# A-Share Automated Trading from Termux (2026-06-10)

## Core Constraint

**A股券商没有开放 REST API。** 所有实盘量化通道都绑定在 Windows 桌面客户端上，不像 Alpaca 一个 HTTP 请求就能下单。这是国内监管和券商架构决定的。

## What Works on Termux

| Platform | Type | Works? | Notes |
|----------|------|:---:|-------|
| AKShare | Data API | ✅ | Pure Python, pip install, free |
| Tushare | Data API | ✅ | Pure Python, credits system |
| 聚宽 SDK (jqdatasdk) | Cloud quant | ⚠️ | SDK runs on Termux, but initial broker binding needs desktop |
| 掘金 SDK (MyQuant) | Cloud quant | ⚠️ | Same as above |
| QMT | Broker client | ❌ | Windows desktop only |
| PTrade | Broker client | ❌ | Windows desktop only |
| 万矿 (WindQuant) | Quant platform | ❌ | Desktop required |

## Viable Architecture: Cloud Windows + QMT + HTTP Bridge

```
小米Pad5 (Termux)              Cloud Windows Server (¥30-50/月)
┌─────────────────┐           ┌──────────────────┐
│ Hermes Agent    │   HTTP    │  QMT + xtquant   │
│ 策略/信号生成    │──────────→│  Flask 桥接服务   │
│ 数据采集(AKShare)│           │  券商下单执行     │
└─────────────────┘           └──────────────────┘
```

### Cloud Server Options
- 阿里云 Windows 轻量应用服务器: ~30-50 RMB/月
- 腾讯云 Windows 轻量应用服务器: ~30-50 RMB/月
- 华为云: ~30-50 RMB/月

### Setup Steps (one-time, ~1 hour)
1. Buy cloud Windows server (2核2G minimum)
2. RDP into it (Microsoft Remote Desktop app on phone)
3. Download + install QMT client
4. Install Python + Flask/FastAPI bridge service
5. Configure Hermes Agent to call the bridge API

### QMT Broker Options (lowest barrier to entry)
- 国金证券 (Jinniu)
- 华鑫证券
- 国盛证券
- 门槛: 一般5-50万资金，部分券商0门槛

## Cost Comparison: Physical PC vs Cloud

| | Physical Windows PC | Cloud Server |
|--|-------------------|-------------|
| Monthly cost | 40-80 RMB electricity | 30-50 RMB |
| Uptime | Risk of power/network outage | 99.9% SLA |
| Maintenance | Self-managed | Managed |

## Regulatory Note

证监会对程序化交易有报备要求。个人散户目前管得松，但趋势是收紧。模拟盘测试策略没问题，实盘注意合规。

## Alternative: Don't Trade A-Shares via API

If the complexity is too high, consider:
- Use AKShare/Tushare for research only
- Manual execution via broker app
- Focus automation effort on US stocks (Alpaca) where API is open
