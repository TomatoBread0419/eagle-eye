# A 股自动化交易平台调研 (2026-06-10)

## 核心结论

A 股实盘量化交易**全都需要 Windows 桌面客户端**，没有类似 Alpaca 的开放 REST API。

## 券商系平台

| 平台 | 背景 | 门槛 | Termux 可用 |
|------|------|------|:---:|
| QMT | 迅投+各券商 | 5-50万资金 | ❌ Windows |
| PTrade | 恒生电子 | 50万+ | ❌ Windows |
| 华泰 MATIC | 华泰证券 | 需华泰开户 | ❌ Windows |
| 国信 TradeStation | 国信证券 | 需国信开户 | ❌ Windows |

## 第三方量化平台

| 平台 | API | 实盘 | Termux 可用 |
|------|-----|------|:---:|
| 掘金量化 (MyQuant) | REST+SDK | ✅ 对接券商 | ⚠️ 初始需电脑 |
| 聚宽 (JoinQuant) | Python SDK | ✅ 对接券商 | ⚠️ 初始需电脑 |
| 米筐 (RiceQuant) | Python SDK | ✅ 对接券商 | ⚠️ 初始需电脑 |
| 果仁网 | Web | ✅ | ✅ 浏览器 |
| 万矿 (WindQuant) | Python | ✅ | ❌ 桌面 |

## 数据 API（Termux 可用）

| 平台 | 说明 | Termux |
|------|------|:---:|
| Tushare | 免费 A 股数据，积分制 | ✅ pip install |
| AKShare | 开源免费，数据全 | ✅ pip install |
| 东方财富 Choice | 付费，数据最全 | ❌ 桌面 |
| 同花顺 iFinD | 付费，机构级 | ❌ 桌面 |

## 推荐架构：QMT 云服务器 + Termux Agent

```
小米Pad5 (Termux)          云Windows服务器（~¥30-50/月）
┌─────────────────┐       ┌──────────────────┐
│ Hermes Agent    │ HTTP  │  QMT + xtquant   │
│ 策略/信号生成    │──────→│  Flask 桥接       │
│ 数据采集        │       │  券商下单          │
└─────────────────┘       └──────────────────┘
```

### 部署步骤
1. 阿里云/腾讯云买 Windows 轻量应用服务器（2核2G，¥30-50/月）
2. 远程桌面（Microsoft Remote Desktop）连接
3. 安装 QMT 客户端 + Python + Flask 桥接代码
4. Termux Agent 通过 HTTP 调用桥接接口

### 成本对比
| 方案 | 月费 | 稳定性 |
|------|------|--------|
| 自己开 Windows 电脑 | ¥40-80 电费 | 断电/断网风险 |
| 云 Windows 服务器 | ¥30-50 | 99.9% 在线 |

### 推荐券商（QMT 门槛低）
- 国金证券
- 华鑫证券
- 国盛证券

## 注意事项
- 证监会对程序化交易有报备要求，个人散户目前管得松但趋势收紧
- QMT 是 x86 程序，不能在 WoA (Windows on ARM) 上正常运行
- 刷 WoA 会失去 Android/Termux，不建议
