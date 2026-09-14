# 🦅 Eagle Eye

> 多智能体驱动的美股交易辅助系统 · S&P 500 动态池 · 7×24 Termux 运行

Eagle Eye 通过多个 AI Agent 协作完成 **扫描 → 决策 → 风控 → 执行 → 审计** 全闭环。
使用提示词工程定义 Agent 行为，非硬编码策略。
当前接入 Alpaca 模拟盘，Android Termux 上 7×24 小时运行。

---

## 📌 系统状态（v7.2.0 · 2026-07-20）

| 模块 | 状态 | 说明 |
|------|------|------|
| 动态池 | ✅ | S&P 500 筛选 + 手动标的 → 327 只，每周六自动更新 |
| 市场扫描 | ✅ | 多维度 GARP 评分（动量/估值/质量/催化/资金流） |
| AI 决策 | ✅ | 每 4 小时，AI 自主判断模式/仓位 |
| 凯利仓位 | ✅ | 动态半凯利，结合置信度+波动率 |
| 风控系统 | ✅ | 宪法规则：单只 ≤18%、板块 ≤30%、总暴露 ≤90% |
| 交易执行 | ✅ | 纯代码执行器，每 20 分钟检查待执行订单 |
| 审计日志 | ✅ | SQLite 持久化，完整决策链路记录 |
| 行为指纹 | ✅ | 每日系统指标检测日报 |
| 微信推送 | ✅ | 实时交易信号 + 状态报告 |
| 配置中心 | ✅ | V2 分层 Bean，单一 .env 来源 |
| HTTP 层 | ✅ | requests + curl 子进程回退（Termux SSL 兼容） |
| 参数校准 | ✅ | 每周六从实际交易数据校准凯利/止损参数 |
| 市场事件 | ✅ | 每 2 小时扫描新闻/事件驱动信号 |

**🚧 开发中** — 审计可视化面板 / 风险分析 Agent / Web 控制台

---

## ⚡ 核心能力

- **动态池** — 从 S&P 500 出发，按流动性/成交额自动筛选 200-300 只，保留手动标的
- **提示词驱动** — 行为由提示词定义，迭代周期从周缩短到小时
- **风控即代码** — 宪法规则约束，API 连续失败自动降级（仅允许止损退出）
- **凯利仓位** — 动态半凯利，结合校准参数自适应
- **配置中心** — `cfg.alpaca.api_key`、`cfg.risk.max_single`、`cfg.pool.target_max` 分层管理
- **HTTP 韧性** — requests + curl 子进程回退，解决 Termux SSL 握手问题
- **结构化通信** — 模块间通过 JSON Schema 契约，松耦合可插拔

---

## 🏗️ 系统架构

```
┌──────────────────────────────────────────────────────┐
│                    数据采集层                          │
│  S&P 500 成分 → pool_builder.py → scan_universe.json  │
│  Alpaca Bars + 价格/成交量                            │
├──────────────────────────────────────────────────────┤
│                    策略分析层                          │
│  indicator_engine → screener (GARP 5维评分)            │
│  market_env (VIX/DXY/利差) → signal_decay             │
│  kelly_engine (半凯利) → allocation_engine             │
├──────────────────────────────────────────────────────┤
│                    决策执行层                          │
│  AI 决策 Agent (每4h) → order_manager                 │
│  trade_executor (每20min) → position_manager           │
│  stop_loss_manager (动态追踪)                         │
├──────────────────────────────────────────────────────┤
│                    风控审计层                          │
│  drawdown_guard → compliance_audit                    │
│  behavior_fingerprint → SQLite 审计日志               │
├──────────────────────────────────────────────────────┤
│                    基础设施层                          │
│  Config V2 (7 Bean 分层) → alpaca_client              │
│  http.py (requests + curl 降级) → SQLite storage      │
│  Hermes cron 调度 → 微信 iLink 推送                   │
└──────────────────────────────────────────────────────┘
```

---

## 🎬 运行示例

```bash
# 系统状态
$ python main.py status
平台: Android Termux  |  市场状态: OPEN
权益: $100,000  |  仓位: 30%  |  持仓: 15 只

# 动态池更新
$ python tools/pool_builder.py
✅ 动态池更新完成
   S&P 500: 300 只  |  总池: 327 只  |  耗时: 119s

# 扫描器输出
$ python main.py scan
Top 候选: PANW 72.3 — AI 网络安全 + 估值合理
          SNOW 68.1 — 数据云复苏，机构增持
```

---

## 📁 项目结构

```
eagle_eye/
├── core/                    # 基础设施
│   ├── config.py            # Config V2 分层配置管理器
│   ├── http.py              # HTTP 客户端（requests + curl 降级）
│   ├── logger.py            # 结构化日志
│   └── cache.py             # 缓存层
├── broker/
│   └── alpaca_client.py     # Alpaca API 适配器（唯一入口）
├── strategy/                # 策略层
│   ├── screener.py          # GARP 动量扫描器
│   ├── indicator_engine.py  # 技术指标计算
│   ├── market_env.py        # 宏观环境采集
│   └── signal_decay.py      # 信号衰减检测
├── portfolio/               # 仓位管理
│   ├── kelly_engine.py      # 凯利仓位计算
│   └── portfolio_manager.py # 投资组合管理
├── execution/               # 执行层
│   ├── trade_executor.py    # 交易执行器
│   ├── order_manager.py     # 订单管理
│   └── stop_loss_manager.py # 止损管理
├── ops/                     # 运维
│   ├── watchdog.py          # 系统看门狗
│   └── behavior_fingerprint.py  # 行为指纹
├── storage/                 # 持久化
│   ├── db.py                # SQLite 数据库
│   └── migrate.py           # 数据库迁移
└── tools/                   # 工具
    └── pool_builder.py      # 动态池粗筛（S&P 500 → 300 只）
```

---

## ⚙️ 配置中心（V2 分层结构）

所有配置从单一 `.env` 文件加载，按逻辑分组：

```python
from eagle_eye.core.config import cfg

cfg.alpaca.api_key         # Alpaca 凭证
cfg.risk.max_single        # 单只最大仓位 0.20
cfg.pool.target_max        # 动态池上限 300
cfg.http.max_retries       # HTTP 最大重试 3
cfg.proxy.enabled          # 代理开关
cfg.notify.telegram_bot_token  # 通知凭证
```

优先级：`.env 文件 > 环境变量 > 默认值`

---

## 📋 更新日志

见 [CHANGELOG.md](CHANGELOG.md)

---

## 📄 许可证

MIT License
