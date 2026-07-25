# SYSTEM_INVENTORY.md — Eagle Eye Stock Trading System

Generated: 2026-06-19 03:00 BJT
Purpose: Complete read-only inventory of all system modules
Location: ~/stock_trader/docs/SYSTEM_INVENTORY.md

---

## 1. PYTHON SCRIPTS

### 1.1 Hermes Scripts (~/.hermes/scripts/) — 25 files

| # | Script | Lines | Size | Purpose | Internal Imports |
|---|--------|-------|------|---------|-----------------|
| 1 | calibrator.py | 402 | 13,348 | 参数自校准器 v1 — 从实际交易数据校准评分/止损/凯利参数，每周六运行 | json, os, math, datetime |
| 2 | cn_auto_trader.py | 543 | 20,819 | A股全自动交易系统 v1 — 特朗普访华概念股监控+虚拟模拟盘+双层风控 | sys, os, json, time, datetime, requests |
| 3 | compliance_audit.py | 254 | 8,336 | 规则合规审计器 v1 — 检查用户偏好是否有对应代码实现 | json, os, re, datetime |
| 4 | contract_validator.py | 212 | 7,404 | 契约验证器 v1 — 验证各模块间数据契约，捕获格式变化 | json, os, sys, datetime |
| 5 | cron_add_two.py | 197 | 5,984 | 一次性脚本 — 添加午间速报+美股盘后两个cron任务 | json, uuid, shutil, datetime |
| 6 | cron_watchdog.py | 73 | 2,285 | Cron交付监控Watchdog — 每2h检查核心cron交付到微信 | os, subprocess, sys, datetime |
| 7 | eagle_heartbeat.py | 433 | 14,619 | Eagle Eye心跳+WeChat SLA监控 — 每小时运行(no_agent) | os, sys, json, datetime, pathlib |
| 8 | generate_audit_reports.py | 199 | 11,050 | 从原始数据生成所有审计markdown报告 | json, os, datetime |
| 9 | macro_context.py | 224 | 7,489 | 宏观环境温度计 v5 — VIX/DXY/利差/FOMC→判断市场类型 | sys, os, json, datetime |
| 10 | market_breadth.py | 303 | 11,631 | 市场广度健康度扫描 v5 — 83标的+11板块ETF→市场健康度 | sys, os, json, time, datetime, **us_common** |
| 11 | market_env.py | 401 | 14,872 | 市场环境扫描合并版 v6 — macro_context+market_breadth单脚本 | sys, os, json, time, datetime, **us_common**, **config** |
| 12 | market_news.py | 135 | 4,517 | 多源市场新闻搜索 — Google RSS + 搜狗微信 fallback | urllib.request/parse, re, time |
| 13 | ops_notify_relay.py | 20 | 452 | 通知中继 — 每分钟cron(no_agent)，读spool→格式化→stdout | sys, os, **eagle_eye.ops.notification** |
| 14 | ops_scheduler_receipt.py | 111 | 3,029 | Scheduler Receipt — 关键任务完成通知，每5分钟运行 | sys, os, json, sqlite3, datetime |
| 15 | proxy_patch.py | 41 | 1,023 | 自动代理补丁 — 在脚本顶部import即可启用代理 | os, socket |
| 16 | proxy_start.py | 134 | 4,204 | Termux内代理管理 — 启动/停止mihomo代理 | subprocess, sys, os, time, signal, json |
| 17 | review_package.py | 359 | 14,905 | Eagle Eye Daily Review Package — 8段式原始数据报告 | sys, os, json, urllib.request, datetime |
| 18 | us_common.py | 329 | 11,908 | 美股交易系统共享模块 — us_trader/us_screener共用 | json, time, urllib.request, datetime |
| 19 | us_kelly.py | 264 | 8,779 | 凯利仓位计算器 v5 — Alpaca 90天订单→FIFO→凯利公式 | sys, os, json, ssl, datetime, collections |
| 20 | us_portfolio.py | 366 | 14,208 | 持仓分析器 — 输出持仓详情/板块分布/仓位缺口/风险标记 | sys, os, json, datetime, urllib, **config**, **us_common** |
| 21 | us_report.py | 416 | 18,366 | AI决策报告生成器 — 汇总所有数据源→结构化报告 | sys, os, json, subprocess, datetime |
| 22 | us_screener.py | 859 | 37,290 | GARP动量扫描器 v2 — 78只美股→动量排序→技术过滤→候选买入 | sys, os, json, time, urllib, datetime, **config**, **us_common** |
| 23 | us_signal_decay.py | 240 | 7,985 | 信号衰减检测 v5 — 检查持仓买入理由是否仍成立 | sys, os, json, datetime, **us_common** |
| 24 | us_trader.py | 72 | 3,214 | 美股交易系统V7.1 LTS薄入口 — CLI入口+向后兼容包装 | sys, os, **eagle_eye.execution.*** |
| 25 | us_trader_v6.py | 1,674 | 71,796 | 美股信号检查v2 — 移动止损/止盈/总账户风控/每日推送(遗留) | sys, os, json, time, urllib, **config**, **us_common** |

**Subtotal: 25 scripts, ~7,165 lines**

### 1.2 Stock Trader Scripts (~/stock_trader/) — 12 files (top-level only, excluding archives/backups)

| # | Script | Lines | Size | Purpose | Internal Imports |
|---|--------|-------|------|---------|-----------------|
| 1 | audit_stops.py | 58 | 2,876 | 止损覆盖审计 | os, json, requests, datetime |
| 2 | cn_auto_trader.py | 544 | 20,845 | A股自动交易(A股版) — 特朗普概念股监控+模拟盘 | sys, os, json, time, datetime, urllib |
| 3 | config.py | 30 | 1,331 | 配置文件 — API密钥和系统参数 | os |
| 4 | cron_audit.py | 45 | 2,197 | Stop coverage审计(cron版) | os, requests, json, datetime |
| 5 | cron_portfolio.py | 59 | 2,349 | Quick portfolio snapshot for cron reporting | urllib, json, os, sys |
| 6 | indicators.py | 223 | 6,552 | 技术指标&交易信号模块 — 纯Python实现 | statistics, typing |
| 7 | market_data.py | 277 | 9,836 | 行情数据模块 — 新浪Finance/东方财富(备用) | json, time, re, urllib, datetime, typing |
| 8 | run_google_searches.py | 141 | 4,810 | Google News RSS搜索 — 6组搜索词 | sys, json, urllib, ssl, time, re, **proxy_patch** |
| 9 | scan_market_events.py | 515 | 21,395 | 全板块市场事件扫描 — 英文(Google RSS)+中文(搜狗微信+华尔街见闻) | json, os, re, sys, time, urllib, datetime |
| 10 | trading.py | 225 | 8,415 | 交易执行模块 — Alpaca API对接(支持Paper Trading) | json, time, urllib, datetime, typing |
| 11 | update_market_data.py | 150 | 4,877 | 重建JSON — 从qt.gtimg.cn获取市场数据 | json, os, sys, re, urllib |
| 12 | verify_hard_constraints.py | 131 | 5,572 | 硬约束验证 — 独立检查us_trader.py是否执行3条硬约束 | sys, os, re, json, datetime, urllib, **config** |

**Subtotal: 12 scripts, ~2,398 lines**

### 1.3 Eagle Eye Package (~/eagle_eye/) — 49 modules (V7.1 LTS modular architecture)

| Subpackage | Module | Lines | Purpose |
|------------|--------|-------|---------|
| **broker/** | alpaca_client.py | 373 | Alpaca broker API client |
| **core/** | __init__.py | 32 | Core package init |
| | cache.py | 237 | Caching layer |
| | config.py | 296 | System configuration |
| | http.py | 321 | HTTP client utilities |
| | logger.py | 137 | Logging infrastructure |
| | runtime.py | 205 | Runtime state management |
| **execution/** | __init__.py | 58 | Execution package init |
| | candidate_tracker.py | 137 | Candidate position tracking |
| | order_intent.py | 198 | Order intent definitions |
| | order_manager.py | 236 | Order lifecycle management |
| | order_state_machine.py | 404 | Order state machine |
| | position_manager.py | 314 | Position management |
| | stop_loss_manager.py | 346 | Stop-loss execution |
| | take_profit_manager.py | 133 | Take-profit execution |
| | trade_executor.py | 583 | Main trade execution engine |
| **ops/** | __init__.py | 74 | Ops package init |
| | audit_engine.py | 260 | Audit engine |
| | behavior_fingerprint.py | 376 | Behavioral fingerprinting |
| | emergency_stop.py | 323 | Emergency stop mechanism |
| | health_check.py | 260 | System health checks |
| | notification.py | 302 | Notification system |
| | scheduler.py | 322 | Task scheduler |
| | shadow_mode.py | 217 | Shadow/observation mode |
| | watchdog.py | 243 | System watchdog |
| **portfolio/** | __init__.py | 27 | Portfolio package init |
| | allocation_engine.py | 123 | Allocation engine |
| | kelly_engine.py | 293 | Kelly criterion engine |
| | portfolio_manager.py | 379 | Portfolio management |
| **risk/** | __init__.py | 31 | Risk package init |
| | degraded_mode.py | 289 | Degraded mode handling |
| | policy_validator.py | 328 | Policy validation |
| | trading_lock.py | 277 | Trading lock mechanism |
| **storage/** | __init__.py | 26 | Storage package init |
| | db.py | 164 | SQLite database layer |
| | migrate.py | 340 | Data migration scripts |
| | models.py | 287 | Data models |
| | repositories.py | 30 | Repository interfaces |
| | repos/*.py | (6 files) | Per-entity repositories |
| **strategy/** | __init__.py | 34 | Strategy package init |
| | indicator_engine.py | 257 | Technical indicator engine |
| | market_breadth.py | 301 | Market breadth analysis |
| | market_env.py | 407 | Market environment analysis |
| | signal_decay.py | 234 | Signal decay detection |
| | main.py | 209 | CLI entry point |

**Subtotal: 49 modules, 10,433 lines**

---

## 2. CONFIGURATION FILES (~/stock_trader/*.json)

No YAML/TOML/INI config files found. No ~/stock_trader/config/ directory.
All configuration is JSON-based.

| # | File | Size (bytes) | Last Modified | Purpose |
|---|------|-------------|---------------|---------|
| 1 | ai_weight_config.json | 4,174 | 2026-06-15 23:17 | AI评分权重配置 |
| 2 | behavior_fingerprint.json | 1,620 | 2026-06-18 13:29 | 行为指纹数据 |
| 3 | calibrated_params.json | 1,591 | 2026-06-18 02:30 | 校准参数(评分/止损/凯利) |
| 4 | cn_risk_state.bak.json | 122 | 2026-05-14 13:37 | A股风控状态备份 |
| 5 | cn_risk_state.json | 122 | 2026-05-15 10:30 | A股风控状态 |
| 6 | cn_signal_latest.json | 243 | 2026-05-15 10:30 | A股最新信号 |
| 7 | compliance_report.json | 4,685 | 2026-06-18 02:24 | 合规审计报告 |
| 8 | earnings_cache.json | 36 | 2026-06-18 08:00 | 财报缓存 |
| 9 | macro_context.json | 267 | 2026-06-18 20:32 | 宏观环境数据 |
| 10 | market_breadth.json | 3,044 | 2026-06-18 20:32 | 市场广度数据 |
| 11 | market_env.json | 3,798 | 2026-06-18 20:32 | 市场环境综合数据 |
| 12 | market_events_latest.json | 11,596 | 2026-06-19 02:14 | 最新市场事件 |
| 13 | market_scan_raw_latest.json | 2,695 | 2026-06-04 22:10 | 市场扫描原始数据 |
| 14 | signal_decay.json | 2,400 | 2026-06-18 21:05 | 信号衰减检测结果 |
| 15 | trade_history.json | 1,941 | 2026-06-16 10:09 | 交易历史(凯利用) |
| 16 | us_bars_history.json | 26,523 | 2026-05-08 05:10 | K线历史数据 |
| 17 | us_pending_replacements.json | 237 | 2026-06-18 04:13 | 待替换持仓 |
| 18 | us_portfolio.json | 5,266 | 2026-06-19 02:20 | 当前持仓快照 |
| 19 | us_recent_stops.json | 109 | 2026-06-19 02:23 | 近期止损记录 |
| 20 | us_risk_state.json | 7,414 | 2026-06-19 02:23 | 美股风控状态 |
| 21 | us_screener_log.json | 64,549 | 2026-06-18 14:48 | 扫描器日志 |
| 22 | us_signal_latest.json | 11,241 | 2026-06-08 09:42 | 最新交易信号 |
| 23 | us_watchlist.json | 5,671 | 2026-06-18 14:48 | 关注列表 |

**Subtotal: 23 JSON config files, ~158,800 bytes total**

Additional JSON data dirs:
- backup_json_20260618_100945/ — 15 backup JSONs (2026-06-18 snapshot)
- scan_work/ — 8 work-in-progress scan JSONs
- cache/smoke_test.json — 2 bytes
- notifications/spool/processed/ — 4 processed notification JSONs

---

## 3. CRON JOBS (~/.hermes/cron/jobs.json) — 16 jobs

| # | Job ID | Name | Schedule | Enabled | Deliver | Script/Skill | Model | Completed |
|---|--------|------|----------|---------|---------|-------------|-------|-----------|
| 1 | a638e8d39d5d | 美股AI决策 | `10 21-5 * * 1-5` (每小时交易时段) | ✅ YES | weixin | us_report.py | deepseek-v4-flash | 280 |
| 2 | b735145148c4 | 美股GARP扫描 | `0 8 * * 1-5` (工作日08:00) | ✅ YES | weixin | us_screener.py | deepseek-v4-flash | 31 |
| 3 | d65b06eddcad | 市场事件监控 | `0 */2 * * 1-5` (每2小时) | ✅ YES | local | skill:market-event-monitor | deepseek-v4-flash | 199 |
| 4 | 147cc7f5088a | 早间速报 | `0 9 * * 1-5` (工作日09:00) | ✅ YES | local | skill:market-event-monitor | deepseek-v4-flash | 13 |
| 5 | d2378848e547 | 港股盘中事件监控 | `30 9-15 * * 1-5` (每小时) | ❌ PAUSED | weixin | (prompt-based) | mimo-v2.5 | 12 |
| 6 | d3f17ab4ca86 | 午间速报 | `0 12 * * 1-5` (工作日12:00) | ✅ YES | local | skill:market-event-monitor | deepseek-v4-flash | 13 |
| 7 | 28139eb5e759 | 美股盘后扫描 | `0 6 * * 1-5` (工作日06:00) | ✅ YES | weixin | skill:market-event-monitor | deepseek-v4-flash | 13 |
| 8 | ea3e2530b0b7 | 持仓专题卡片 | `30 9 * * 1-5` (工作日09:30) | ✅ YES | weixin | skill:stock-trading-system | deepseek-v4-flash | 13 |
| 9 | 5bbde6a44f31 | Cron交付监控 | `*/5 * * * *` (每5分钟) | ❌ PAUSED | weixin | cron_watchdog.py | (no_agent) | 61 |
| 10 | 31bbb6eeb546 | 信号衰减检测 | `0 21,23,1,3 * * 1-5` (每2h交易时段) | ❌ PAUSED | weixin | skill:stock-trading-system | deepseek-v4-flash | 11 |
| 11 | 0ca23f29fbde | 凯利仓位计算 | `30 5 * * 6` (周六05:30) | ✅ YES | weixin | skill:stock-trading-system | deepseek-v4-flash | 1 |
| 12 | 156e40a9c859 | 市场环境采集 | `30 20 * * 1-5` (工作日20:30) | ✅ YES | local | skill:stock-trading-system | deepseek-v4-flash | 4 |
| 13 | 1da0dc5f927c | 参数自校准 | `0 6 * * 6` (周六06:00) | ✅ YES | local | skill:stock-trading-system | (default) | 0 |
| 14 | 8604888631f4 | 规则合规审计 | `10 6 * * 6` (周六06:10) | ✅ YES | local | (prompt-based) | (default) | 0 |
| 15 | 8bce957367ec | Eagle Eye Heartbeat | `0 6,9,15,21 * * *` (4x/day) | ❌ PAUSED | weixin | eagle_heartbeat.py | (no_agent) | 1 |
| 16 | f185a347cd9f | Ops Notification Relay | `* * * * *` (每分钟) | ❌ PAUSED | weixin | ops_notify_relay.py | (no_agent) | 37 |
| 17 | 8290d4140d57 | Scheduler Receipt | `*/5 * * * *` (每5分钟) | ❌ PAUSED | weixin | ops_scheduler_receipt.py | (no_agent) | 7 |
| 18 | 98dcdfc2aa4f | Review Report — 2026-06-18 | once at 2026-06-19 09:30 | ✅ YES | weixin | skill:stock-trading-system | deepseek-v4-flash | 0 |
| 19 | 154d0c4e4f81 | Eagle Eye 日报 | `0 8 * * *` (每日08:00) | ✅ YES | weixin | review_package.py | deepseek-v4-flash | 0 |

**Subtotal: 19 unique jobs** (18 recurring + 1 one-shot)
- Enabled: 12 | Paused: 7
- Deliver via weixin: 13 | Deliver local: 6
- Uses stock-trading-system skill: 8
- Uses market-event-monitor skill: 4

---

## 4. STOCK-TRADING RELATED SKILLS (~/.hermes/skills/)

| # | Skill Path | Name | Version | Lines | Size | Description |
|---|-----------|------|---------|-------|------|-------------|
| 1 | data-science/stock-trading-system/ | stock-trading-system | 7.1.1 | 1,720 | 96,910 | 美股自动交易系统 V7.1 LTS — 闭环自校准+动态凯利+合规审计+SQLite+模块化架构 |
| 2 | data-science/eagle-eye-v6-refactor/ | eagle-eye-v6-refactor | 6.0.0 | 89 | 3,920 | 鹰眼v6重构方案 — 从开环(132死参数)升级为闭环(参数自校准)，状态: IMPLEMENTED |
| 3 | data-science/market-event-monitor/ | market-event-monitor | — | 298 | 26,459 | 多源市场事件监控 — 半导体/金融/地缘/贸易/原材料，Google RSS+搜狗微信双源交叉验证 |

**Subtotal: 3 skills**
- Reference documents in stock-trading-system/: 26 files (audit reports, architecture docs, guardrails, learnings)
- Reference documents in market-event-monitor/: 5 files (monitoring workflows, proxy setup, diagnostics)
- Reference documents in eagle-eye-v6-refactor/: 1 file (production audit)

---

## 5. TOTAL MODULE COUNT

| Category | Count |
|----------|-------|
| Hermes scripts (~/.hermes/scripts/) | 25 |
| Stock trader scripts (~/stock_trader/*.py) | 12 |
| Eagle Eye package modules (~/eagle_eye/) | 49 |
| JSON config files (~/stock_trader/*.json) | 23 |
| Cron jobs (recurring + one-shot) | 19 (18 recurring + 1 one-shot) |
| Stock-trading related skills | 3 |
| **TOTAL** | **131** |

### Additional Notes

- **No config/ directory** exists in ~/stock_trader/. All config is flat JSON.
- **No YAML/TOML/INI** files found anywhere in the project.
- **Archives**: ~/stock_trader/archives/ contains ~37 legacy .py scripts (event_scripts/, market_scripts/, scan_scripts/, misc/) — not counted in active inventory.
- **Backups**: ~/stock_trader/backups/ contains 1 legacy .py + 1 JSON backup.
- **Markdown docs**: 27 .md files across logs/, reports/, audit/, docs/, cron/output/.
- **Notification spool**: 4 processed notification JSONs in ~/stock_trader/notifications/spool/processed/.
- **Scan work**: 8 intermediate scan JSONs in ~/stock_trader/scan_work/.
- **Internal dependency graph**:
  - us_common.py is imported by: market_breadth.py, market_env.py, us_portfolio.py, us_screener.py, us_signal_decay.py, us_trader_v6.py
  - config.py (stock_trader) is imported by: market_env.py, us_portfolio.py, us_screener.py, us_trader_v6.py, verify_hard_constraints.py
  - eagle_eye package is imported by: us_trader.py, ops_notify_relay.py
  - proxy_patch.py is imported by: run_google_searches.py

---

*End of SYSTEM_INVENTORY.md*
