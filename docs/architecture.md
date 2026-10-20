# 🦅 Eagle Eye 系统架构文档

> 模块化流水线美股交易辅助系统 · GARP 主线 + 事件驱动子系统 · Termux 7×24 运行
> 生成时间：2026-07-21

---

## 一、仓库代码（~/eagle_eye/）

```
eagle_eye/
├── README.md                    # 项目主页（V2 架构说明）
├── CHANGELOG.md                 # 更新日志（v7.0.0 → v7.2.0）
├── LICENSE                      # MIT
├── setup.py                     # Python 包定义（version 7.2.0）
├── .gitignore                   # 排除 .env / 交易状态 / 日志
│
├── core/                        # ── 基础设施层 ──
│   ├── config.py                # Config V2 分层 Bean（cfg.alpaca/risk/pool/http/proxy/log/notify）
│   ├── http.py                  # HTTP 客户端（requests + curl 子进程降级）
│   ├── logger.py                # 结构化日志
│   ├── cache.py                 # 缓存层
│   └── __init__.py
│
├── broker/                      # ── 券商接口层（唯一入口）──
│   ├── alpaca_client.py         # Alpaca API 适配器（下单/持仓/行情/时钟/降级计数）
│   └── __init__.py
│
├── strategy/                    # ── 策略层 ──
│   ├── screener.py              # GARP 动量扫描器（5 维评分，4 线程）
│   ├── indicator_engine.py      # 技术指标（波动率止损分档 7-10%）
│   ├── market_env.py            # 宏观环境采集（VIX/DXY/利差/FOMC）
│   ├── signal_decay.py          # 信号衰减检测（持仓买入理由复核）
│   └── __init__.py
│
├── execution/                   # ── 执行层 ──
│   ├── trade_executor.py        # GARP 交易执行循环（20 分钟一轮）
│   ├── order_manager.py         # 订单管理（市价/止损单，买入去重）
│   ├── stop_loss_manager.py     # 双层止损（硬件止损单 + 软件追踪）
│   ├── position_manager.py      # 仓位状态（us_risk_state.json 读写）
│   └── __init__.py
│
├── risk/                        # ── 风控层 ──
│   ├── trading_lock.py          # 交易锁（市场闭市/API 不健康/降级模式）
│   └── __init__.py
│
├── ops/                         # ── 运维层 ──
│   ├── drawdown_guard.py        # 回撤保护
│   ├── behavior_fingerprint.py  # 行为指纹日报
│   ├── scheduler.py             # 调度辅助
│   └── __init__.py
│
├── storage/                     # ── 持久化层 ──
│   ├── db.py                    # SQLite 审计日志
│   ├── migrate.py               # 数据库迁移
│   └── __init__.py
│
├── tools/
│   └── pool_builder.py          # 动态池粗筛（S&P 500 → 327 只）
│
└── docs/
    ├── event-driven-plan.md     # 事件驱动子系统计划书（三阶段）
    └── architecture.md          # 本文档
```

---

## 二、运行时数据（~/stock_trader/）

```
stock_trader/
├── .env                         # ⚠️ 单一配置来源（API Key，不入库）
├── credentials/
│   └── us_alpaca_paper.json     # Alpaca Paper 凭证
│
├── ── 动态池与扫描 ──
│   ├── scan_universe.json       # 动态池（327 只）
│   ├── us_watchlist.json        # 扫描结果 / 候选买入
│   └── calibrated_params.json   # 每周六校准的凯利/止损参数
│
├── ── 风控状态 ──
│   └── us_risk_state.json       # 持仓最高价/追踪止损/阶梯止盈状态
│
├── ── 事件驱动子系统 ──
│   ├── event_map.json           # 板块→股票映射库（7 板块 + style 标注）
│   ├── market_events_latest.json# 新闻采集输出（scan_market_events.py 生成）
│   ├── events_log.json          # 事件全量日志（检测/分析/执行/退出）
│   ├── events_analysis_queue.json # AI 分析结果存档
│   ├── scoreboard.json          # 风格分数板（geo/chain/policy）
│   ├── scan_market_events.py    # 新闻采集器（Google RSS + 搜狗微信 + 华尔街见闻）
│   └── tools/
│       ├── event_news_fetcher.py  # ①检测+②AI推理+校验层+推微信
│       ├── event_executor.py      # ③下单+止损+wash-trade 防护
│       ├── event_exit_checker.py  # ④退出检查+自动标记退出
│       └── event_review.py        # ⑤周末复盘+分数板更新
│
├── ── 遗留/其他 ──
│   ├── pool_builder/            # 动态池模块（早期版本，8 文件）
│   ├── nodes/                   # 旧节点脚本（config/core/position_check）
│   └── report_latest.json       # 最新报告快照
```

---

## 三、调度层（~/.hermes/scripts/）

```
~/.hermes/scripts/
├── v7_scan_runner.py            # GARP 扫描 runner（工作日 08:00）
├── trade_executor_runner.py     # GARP 执行 runner（20 分钟一轮，21:00-05:00）
├── scan_events_runner.py/.sh    # 事件采集 runner（每 2h :00）
├── event_news_fetcher_cron.sh   # 事件 AI 分析 runner（每 2h :05）
├── event_executor_cron.sh       # 事件执行 runner（每 2h :10）
├── event_exit_checker_cron.sh   # 仓位日报 runner（工作日 08:30）
├── event_review_cron.sh         # 周末复盘 runner（周六 09:00）
├── pool_builder_runner.sh       # 动态池更新（周六 05:30）
└── gateway_watchdog.sh          # 网关看门狗（每 5 分钟）
```

---

## 四、Cron 调度总表

| # | 任务 | Schedule | 脚本 | 输出 |
|---|------|----------|------|------|
| 1 | GARP 扫描 | `0 8 * * 1-5` | v7_scan_runner.py | us_watchlist.json |
| 2 | GARP 交易执行 | `*/20 21-5 * * 1-5` | trade_executor_runner.py | Alpaca 订单 |
| 3 | 事件采集 | `0 */2 * * 1-5` | scan_events_runner.py | market_events_latest.json |
| 4 | 事件 AI 分析 | `5 */2 * * *` | event_news_fetcher_cron.sh | 分析报告 → 微信 |
| 5 | 事件执行 | `10 */2 * * 1-5` | event_executor_cron.sh | 事件订单 + 止损 |
| 6 | 仓位日报 | `30 8 * * 1-5` | event_exit_checker_cron.sh | 日报 → 微信 |
| 7 | 周末复盘 | `0 9 * * 6` | event_review_cron.sh | 周报 → 微信 + scoreboard |
| 8 | 动态池更新 | `30 5 * * 6` | pool_builder_runner.sh | scan_universe.json |
| 9 | 凯利仓位计算 | `30 5 * * 6` | us_kelly.py | calibrated_params.json |
| 10 | 参数自校准 | `0 6 * * 6` | calibrator.py | calibrated_params.json |
| 11 | 合规审计 | `10 6 * * 6` | compliance_audit.py | 审计报告 |
| 12 | 网关看门狗 | `*/5 * * * *` | gateway_watchdog.sh | 健康自检 |

---

## 五、数据流总图

```
                    ┌─────────────────────────────────┐
                    │          GARP 主线系统           │
                    └─────────────────────────────────┘
  S&P 500 ──→ pool_builder ──→ scan_universe.json (327只)
                                  │
                          screener (5维评分)
                                  │
                          AI 决策 (每4h)
                                  │
                          kelly_engine (半凯利)
                                  │
                    trading_lock 风控门 → trade_executor
                                  │
                          order_manager → Alpaca Paper
                                  │
                          stop_loss_manager (双层止损)

                    ┌─────────────────────────────────┐
                    │        事件驱动子系统 (30%)       │
                    └─────────────────────────────────┘
  RSS 新闻源 (Google/搜狗/华尔街见闻)
        │ ①每2h :00 采集
        ▼
  market_events_latest.json
        │ ②每2h :05 AI因果推理 + 校验层
        ▼
  events_log.json + 微信分析报告
        │ ③每2h :10 执行（GARP去重/wash-trade防护/分数板限仓）
        ▼
  Alpaca Paper 下单 + 止损单
        │ ④工作日08:30 退出检查（止损/止盈/超期）
        ▼
  仓位日报 → 微信
        │ ⑤周六09:00 复盘
        ▼
  scoreboard.json（geo/chain/policy 加分制）
  80+分→15%额度 | <30分→暂停 | 连续4亏→淘汰 | 满1月→复活

                    ┌─────────────────────────────────┐
                    │        共用基础设施              │
                    └─────────────────────────────────┘
  core/config.py (.env 单一来源)
  core/http.py (requests + curl 降级)
  broker/alpaca_client.py (唯一券商入口)
  risk/trading_lock.py (总风控门 — 两系统在此汇合)
  storage/db.py (SQLite 审计)
  微信 iLink 推送
```

---

## 六、安全约束汇总

| 约束 | GARP 主线 | 事件驱动 |
|------|----------|---------|
| 资金占比 | ~70% | ≤30% |
| 单只上限 | 18% | 5% |
| 板块/风格上限 | 30% | 10% |
| 总仓位上限 | 90% | — |
| 止损 | 波动率分档 7-10% | 固定 7% + Alpaca 硬止损单 |
| 持仓窗口 | 长期 | 3-21 天（hold_days） |
| 淘汰机制 | — | 连续 4 亏暂停 |
| 防重复 | 买入去重 | GARP 持仓去重 + 已执行去重 |
