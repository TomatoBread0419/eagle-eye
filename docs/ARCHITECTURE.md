# 🦅 Eagle Eye V7.1 LTS — 完整架构文档

> 自动生成于 2026-07-21 | 基于 Termux/Android 24h 运行环境扫描
>
> 📌 2026-07-21 修复: `us_screener.py` 从 `.bak` 备份恢复 (多模型判断 2:1，语法验证通过)

## 一、系统总览

Eagle Eye 是一套运行在 Android/Termux 上的**美股智能交易系统**，采用双轨架构：
- **GARP 执行器**（每 20 分钟）— 基于估值筛选自动调仓
- **AI 决策器**（每 4 小时）— 基于 LLM（mimo-v2.5-pro）的 MoA 决策聚合
- **事件驱动链**（每 2 小时）— 新闻扫描→信号评估→执行

技术栈：Python 3.14 + SQLite + Alpaca Paper Trading API + Hermes Agent Cron

---

## 二、完整文件树状图

```
~/
├── .env → ~/eagle_eye/.env                    # 符号链接，全局配置入口
│
├── eagle_eye/                                  # 📦 Python 包（可编辑安装，git: HTTPS）
│   ├── setup.py                                # pip install -e . 安装配置
│   ├── main.py                                 # 系统入口
│   ├── __init__.py                             # 包标识 v7.1
│   │
│   ├── core/                                   # 🔧 基础设施层
│   │   ├── config.py                           #   加载 .env，暴露 SimpleNamespace 配置 Bean
│   │   ├── http.py                             #   HTTP 客户端（代理/重试/超时）
│   │   ├── cache.py                            #   内存缓存
│   │   ├── logger.py                           #   结构化日志
│   │   └── runtime.py                          #   运行时上下文
│   │
│   ├── broker/                                 # 🏦 券商接口层
│   │   └── alpaca_client.py                    #   Alpaca API 封装（Paper Trading）
│   │
│   ├── strategy/                               # 📊 策略引擎层
│   │   ├── screener.py                         #   股票筛选器（动态池）
│   │   ├── indicator_engine.py                 #   技术指标计算
│   │   ├── signal_decay.py                     #   信号衰减检测
│   │   ├── market_breadth.py                   #   市场宽度分析
│   │   └── market_env.py                       #   市场环境判断（牛/熊/震荡）
│   │
│   ├── portfolio/                              # 💰 组合管理层
│   │   ├── portfolio_manager.py                #   持仓管理主模块
│   │   ├── allocation_engine.py                #   仓位分配引擎
│   │   └── kelly_engine.py                     #   动态凯利公式仓位计算
│   │
│   ├── execution/                              # ⚡ 订单执行层
│   │   ├── trade_executor.py                   #   交易执行器
│   │   ├── order_manager.py                    #   订单生命周期管理
│   │   ├── order_state_machine.py              #   订单状态机
│   │   ├── order_intent.py                     #   订单意图（买入/卖出/替换）
│   │   ├── position_manager.py                 #   持仓快照与同步
│   │   ├── stop_loss_manager.py                #   止损管理
│   │   ├── take_profit_manager.py              #   止盈管理
│   │   └── candidate_tracker.py                #   候选股票追踪
│   │
│   ├── risk/                                   # 🛡️ 风控层
│   │   ├── policy_validator.py                 #   策略合规校验
│   │   ├── degraded_mode.py                    #   降级模式（网络/API 异常）
│   │   └── trading_lock.py                     #   交易锁（防止并发冲突）
│   │
│   ├── storage/                                # 💾 持久化层
│   │   ├── db.py                               #   SQLite 连接管理
│   │   ├── models.py                           #   ORM 模型定义
│   │   ├── migrate.py                          #   数据库迁移
│   │   ├── repositories.py                     #   Repository 工厂
│   │   └── repos/                              #   各领域 Repository
│   │       ├── positions.py                    #     持仓数据
│   │       ├── history.py                      #     交易历史
│   │       ├── market.py                       #     市场数据
│   │       ├── watchlist.py                    #     观察列表
│   │       ├── pending.py                      #     待处理订单
│   │       ├── calibrated.py                   #     校准参数
│   │       └── system.py                       #     系统状态
│   │
│   ├── ops/                                    # 🔨 运维层
│   │   ├── constitution.py                     #   系统宪章（硬约束定义）
│   │   ├── audit_engine.py                     #   合规审计引擎
│   │   ├── health_check.py                     #   健康检查
│   │   ├── emergency_stop.py                   #   紧急停止机制
│   │   ├── notification.py                     #   通知推送（微信/Telegram）
│   │   ├── watchdog.py                         #   看门狗（进程存活检测）
│   │   ├── scheduler.py                        #   任务调度器
│   │   ├── shadow_mode.py                      #   影子模式（只算不执行）
│   │   └── behavior_fingerprint.py             #   行为指纹（防漂移）
│   │
│   ├── ai/                                     # 🤖 AI 模块（预留，当前由 MoA 外部驱动）
│   ├── events/                                 # 📰 事件模块（预留，当前由 stock_trader/tools/ 驱动）
│   ├── monitoring/                             # 📈 监控模块（预留）
│   ├── scheduler/                              # ⏰ 调度模块（预留）
│   │
│   ├── tools/                                  # 🔨 工具脚本
│   │   └── pool_builder.py                     #   动态池构建器 ← 权威版本
│   │
│   ├── logs/                                   # 📝 运行日志
│   │   └── eagle_eye.log
│   │
│   ├── docs/                                   # 📚 文档
│   │   ├── architecture.md                     #   架构设计文档
│   │   ├── workflow-design.md                  #   工作流设计
│   │   ├── event-driven-plan.md                #   事件驱动计划
│   │   ├── prompt-engineering.md               #   Prompt 工程
│   │   ├── docker-setup.md                     #   Docker 部署（未使用）
│   │   ├── prompts/                            #   Prompt 模板
│   │   │   ├── system-prompt.md                #     系统 Prompt
│   │   │   └── daily-scan.md                   #     每日扫描 Prompt
│   │   └── examples/                           #   使用示例
│   │
│   ├── .env                                    # 🔐 环境变量（Alpaca 密钥、代理、参数）
│   ├── .env.backup / .env.bak / .env.example
│   ├── CHANGELOG.md
│   ├── EXECUTION_LAYER_REVIEW.md
│   ├── EXECUTION_REFACTOR_PLAN.md
│   └── README.md
│
├── stock_trader/                               # 🏗️ 运行时目录（非 git 仓库，纯数据/脚本目录）
│   ├── config.py                               #   运行时配置
│   ├── trading.py                              #   高阶交易逻辑（买卖配对、止损替换）
│   ├── market_data.py                          #   市场数据获取（yfinance / 东方财富）
│   ├── indicators.py                           #   技术指标计算（独立副本）
│   │
│   ├── v7_scan.py                              #   V7 扫描入口 → 调用 eagle_eye.strategy
│   ├── v7_portfolio.py                         #   V7 组合入口 → 调用 eagle_eye.portfolio
│   ├── moa_decision.py                         #   🧠 MoA 决策聚合器（多模型投票）
│   ├── scan_market_events.py                   #   市场事件扫描（Google News RSS + 搜狗微信）
│   ├── run_google_searches.py                  #   Google 搜索封装
│   ├── cn_auto_trader.py                       #   A 股自动交易（东方财富数据源）
│   ├── sync_positions.py                       #   持仓同步（Alpaca ↔ 本地）
│   ├── pool_builder.py                         #   动态池构建器 ← 运行时副本
│   ├── update_market_data.py                   #   市场数据更新
│   ├── make_json.py                            #   JSON 数据格式化
│   ├── proxy_patch.py                          #   代理补丁（中国网络）
│   ├── audit_stops.py                          #   止损审计
│   ├── verify_hard_constraints.py              #   硬约束验证
│   │
│   ├── cron_audit.py                           #   Cron 审计任务
│   ├── cron_portfolio.py                       #   Cron 组合任务
│   │
│   ├── tools/                                  # 🔧 事件驱动工具链
│   │   ├── event_news_fetcher.py               #   新闻抓取（Google News + 搜狗微信）
│   │   ├── event_executor.py                   #   事件信号执行
│   │   ├── event_exit_checker.py               #   事件退出检查
│   │   └── event_review.py                     #   事件回顾与归档
│   │
│   ├── skills/                                 # 🎓 Hermes 技能系统（仓库内副本）
│   │   ├── stock-trading-system/               #   主技能：美股交易系统
│   │   │   ├── SKILL.md
│   │   │   ├── references/ (90+ 文件)          #     历史决策、架构文档、经验教训
│   │   │   ├── scripts/                        #     辅助脚本
│   │   │   ├── src/                            #     源码快照（config, indicators, etc.）
│   │   │   └── templates/                      #     模板（dashboard, eagle-eye CLI）
│   │   ├── eagle-eye-v6-refactor/              #   V6 重构方案
│   │   ├── market-event-monitor/               #   事件监控技能
│   │   └── cn-stock-auto-trader/               #   A 股交易技能
│   │
│   ├── docs/                                   # 📚 运行时文档
│   │   ├── SYSTEM_INVENTORY.md                 #   系统清单
│   │   ├── DEPENDENCY_MAP.md                   #   依赖图
│   │   ├── CORE_TRADING_CHAIN.md               #   核心交易链
│   │   ├── FAILOVER_PLAN.md                    #   故障转移计划
│   │   └── ... (其他治理文档)
│   │
│   ├── audit/                                  # 📋 审计报告
│   │   ├── V7.1_LTS_AUDIT.md
│   │   ├── SYSTEM_FINAL_GOVERNANCE_REPORT.md
│   │   └── ... (审计文档)
│   │
│   ├── notifications/                          # 🔔 通知队列
│   │   └── spool/{critical,warnings,processed}/
│   │
│   ├── reports/                                # 📊 报告输出
│   ├── logs/                                   # 📝 运行日志
│   ├── cache/                                  # 💾 缓存
│   ├── backups/                                # 💾 备份
│   ├── archives/                               # 📦 归档（旧版扫描脚本）
│   │
│   ├── eagle_eye.db                            #   SQLite 数据库（运行时数据）
│   ├── .env                                    #   环境变量（独立副本，非符号链接源）
│   └── .gitignore
│
└── .hermes/                                    # ⚙️ Hermes Agent 集成层
    ├── scripts/                                #   CLI 入口与 Cron 脚本
    │   ├── eagle-eye                           #   🎯 主 CLI 分发器（Python）
    │   │                                     #     子命令: report/scan/portfolio/execute/
    │   │                                     #     calibrate/audit/status/moa/constitution
    │   ├── eagle_heartbeat.py                  #   💓 心跳监控（微信 SLA 检测）
    │   ├── us_report.py                        #   美股日报生成器
    │   ├── us_screener.py                      #   股票扫描器（从 .bak 恢复）
│   ├── us_screener.py.bak                  #   扫描器备份（恢复源）
    │   ├── us_portfolio.py                     #   持仓分析
    │   ├── us_trader.py                        #   交易执行（轻量版）
    │   ├── us_trader_v6.py                     #   交易执行（V6 完整版，71KB）
    │   ├── us_common.py                        #   公共工具函数
    │   ├── us_kelly.py                         #   凯利仓位计算
    │   ├── us_signal_decay.py                  #   信号衰减检测
    │   ├── calibrator.py                       #   参数自校准（每周六）
    │   ├── compliance_audit.py                 #   合规审计
    │   ├── contract_validator.py               #   合约验证
    │   ├── review_package.py                   #   审计报告打包
    │   ├── cn_auto_trader.py                   #   A 股自动交易（副本）
    │   ├── cn_risk_state.json                  #   A 股风控状态
    │   ├── cn_signal_latest.json               #   A 股最新信号
    │   ├── cron_watchdog.py                    #   Cron 看门狗
    │   ├── cron_add_two.py                     #   Cron 辅助
    │   └── event_review_cron.sh                #   事件回顾 Cron 脚本
    │
    ├── cron/                                   #   Cron 任务定义与输出
    │   ├── a638e8d39d5d/                       #   AI 决策 cron（每 4h）
    │   ├── b735145148c4/                       #   日报 cron
    │   └── 79f6bcc55cc9/                       #   其他 cron
    │
    └── skills/                                 #   全局技能（跨仓库共享）
```

---

## 三、数据流与执行流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    Eagle Eye 数据流                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ 数据源    │───▶│ 扫描器    │───▶│ 筛选器    │───▶│ 信号衰减  │  │
│  │ Alpaca   │    │ v7_scan  │    │ screener │    │ decay    │  │
│  │ yfinance │    │ events   │    │ breadth  │    │          │  │
│  │ 东方财富  │    │          │    │          │    │          │  │
│  └──────────┘    └──────────┘    └──────────┘    └────┬─────┘  │
│                                                       │         │
│                                                       ▼         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    决策层（双轨并行）                       │   │
│  │  ┌─────────────────┐      ┌─────────────────────────┐   │   │
│  │  │ GARP 执行器      │      │ MoA AI 决策器            │   │   │
│  │  │ 每 20min         │      │ 每 4h (mimo-v2.5-pro)   │   │   │
│  │  │ 估值驱动         │      │ 多模型投票               │   │   │
│  │  └────────┬────────┘      └───────────┬─────────────┘   │   │
│  └───────────┼───────────────────────────┼─────────────────┘   │
│              │                           │                      │
│              ▼                           ▼                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    风控层                                  │   │
│  │  policy_validator → trading_lock → degraded_mode         │   │
│  │  constitution (硬约束) → emergency_stop                   │   │
│  └──────────────────────────┬───────────────────────────────┘   │
│                             │                                   │
│                             ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    执行层                                  │   │
│  │  trade_executor → order_manager → alpaca_client          │   │
│  │  stop_loss_manager / take_profit_manager                 │   │
│  └──────────────────────────┬───────────────────────────────┘   │
│                             │                                   │
│                             ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    持久化 + 反馈                           │   │
│  │  SQLite (eagle_eye.db) → position_manager → sync        │   │
│  │  calibrator (参数自校准) → behavior_fingerprint (防漂移)  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    推送层                                  │   │
│  │  notification → 微信/Telegram → 用户                       │   │
│  │  eagle_heartbeat (SLA 监控)                               │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四、CLI 命令映射

`eagle-eye` CLI（`~/.hermes/scripts/eagle-eye`）子命令到实际脚本的映射：

| 子命令 | 说明 | 目标脚本 |
|--------|------|----------|
| `report` | 生成决策报告 | `~/.hermes/scripts/us_report.py` |
| `scan` | 运行扫描器 | `~/.hermes/scripts/us_screener.py` ⚠️ 缺失 |
| `portfolio` | 持仓分析 | `~/.hermes/scripts/us_portfolio.py` |
| `trader` | 执行交易 | `~/.hermes/scripts/us_trader.py` |
| `calibrate` | 参数自校准 | `~/.hermes/scripts/calibrator.py` |
| `audit` | 合规审计 | `~/.hermes/scripts/compliance_audit.py` |
| `moa` | MoA 决策 | `~/stock_trader/moa_decision.py` |
| `constitution` | 系统宪章 | `~/eagle_eye/ops/constitution.py` |
| `execute` | 执行订单 (stdin JSON) | 内置处理 |

---

## 五、关键路径映射与已知问题

### 5.1 双目录结构

| 属性 | ~/eagle_eye/ | ~/stock_trader/ |
|------|-------------|-----------------|
| Git 远程 | HTTPS（唯一） | 无（非 git 仓库） |
| 角色 | 可安装 Python 包 | 运行时目录 |
| .env | 源文件（被 symlink 指向） | 独立副本 |
| pool_builder.py | 权威版本 (tools/) | 运行时副本 |

### 5.2 符号链接

```
~/.env → ~/eagle_eye/.env    # 全局配置入口
```

### 5.3 已知问题

1. ~~**`us_screener.py` 缺失**~~ — 已从 `.bak` 恢复 (2026-07-21)，`eagle-eye scan` 现在可用
2. **双 .env 文件** — `~/eagle_eye/.env` 是权威源，`~/stock_trader/.env` 是独立副本，可能不同步
3. **双 pool_builder.py** — `eagle_eye/tools/pool_builder.py` 是权威版本
4. **空模块** — `ai/`、`events/`、`monitoring/`、`scheduler/` 目录仅有 `__init__.py`，功能由外部脚本驱动
5. **pip 可编辑安装** — 包仅在 `~/.hermes/hermes-agent/venv/` 环境下可用

---

## 六、基础设施

### 6.1 运行环境
- **OS**: Android 13 (Termux)
- **Python**: 3.14 (via Hermes Agent venv)
- **数据库**: SQLite (eagle_eye.db)
- **券商**: Alpaca Paper Trading (模拟盘)
- **网络**: 中国（需代理访问 Alpaca/Google）

### 6.2 Cron 任务
- **AI 决策** (`a638e8d39d5d`): 每 4 小时，MoA 多模型决策
- **日报** (`b735145148c4`): 每日生成持仓报告
- **GARP 执行器** (`eaa04a4d262d`): 每 20 分钟估值调仓
- **事件驱动链**: market_events → fetcher → executor（每 2 小时）
- **心跳监控** (`eagle_heartbeat.py`): 每小时，微信 SLA 检测

### 6.3 外部依赖
- Alpaca API (交易 + 行情)
- yfinance (补充行情)
- 东方财富 (A 股数据)
- Google News RSS (事件扫描)
- 搜狗微信 (中文事件扫描)
- MiniMax T2A v2 (语音合成，用于保险自媒体)

---

## 七、模块职责速查

| 层级 | 模块 | 职责 |
|------|------|------|
| 核心 | `core/config` | 配置加载（.env → SimpleNamespace Bean） |
| 核心 | `core/http` | HTTP 客户端（代理/重试/超时） |
| 策略 | `strategy/screener` | 股票筛选（动态池） |
| 策略 | `strategy/indicator_engine` | 技术指标（RSI/MACD/布林带） |
| 策略 | `strategy/signal_decay` | 信号衰减检测 |
| 策略 | `strategy/market_env` | 市场环境判断 |
| 组合 | `portfolio/kelly_engine` | 动态凯利公式仓位 |
| 组合 | `portfolio/allocation_engine` | 仓位分配 |
| 执行 | `execution/trade_executor` | 交易执行 |
| 执行 | `execution/stop_loss_manager` | 止损管理 |
| 执行 | `execution/take_profit_manager` | 止盈管理 |
| 风控 | `risk/policy_validator` | 策略合规校验 |
| 风控 | `risk/degraded_mode` | 降级模式 |
| 存储 | `storage/db` | SQLite 连接 |
| 存储 | `storage/repos/*` | 各领域 Repository |
| 运维 | `ops/constitution` | 系统宪章（硬约束） |
| 运维 | `ops/audit_engine` | 合规审计 |
| 运维 | `ops/notification` | 通知推送 |
| 运维 | `ops/watchdog` | 看门狗 |
| 运维 | `ops/emergency_stop` | 紧急停止 |
| 工具 | `tools/pool_builder` | 动态池构建 |
| 运行时 | `moa_decision` | MoA 多模型决策聚合 |
| 运行时 | `scan_market_events` | 市场事件扫描 |
| 运行时 | `cn_auto_trader` | A 股自动交易 |
