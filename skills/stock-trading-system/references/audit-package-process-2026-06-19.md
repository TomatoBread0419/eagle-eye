# Eagle Eye Audit Package — 生成流程

**生成时间**: 2026-06-19
**用户要求**: "禁止省略任何项目。禁止自行筛选文件。禁止输出摘要代替原始内容。禁止执行任何修复。只允许收集与打包。"

## 触发条件

用户说"生成审计包"或类似指令。

## 12个Section

| # | Section | 文件名 | 数据源 |
|:--:|---------|--------|--------|
| 1 | System Architecture | architecture_report.md | 模块清单 + 数据库 + Cron |
| 2 | Strategy Files (原始) | strategy_files/ | SKILL.md + 权重 + 校准参数 + 合规报告 + 推送策略 |
| 3 | Cron Inventory | cron_inventory.md | cronjob list |
| 4 | Portfolio Snapshot | portfolio_snapshot.md | Alpaca API |
| 5 | Candidate Universe | candidate_universe.md | watchlist + screener_log |
| 6 | Policy Validator | policy_validator_report.md | Gate 0-3 计算 |
| 7 | Candidate Tracker | candidate_tracker.md | screener_log |
| 8 | Risk Audit | risk_audit.md | Alpaca orders + risk_state |
| 9 | Execution History (72h) | execution_history.md | cron logs + gateway logs |
| 10 | Incident Report (72h) | incident_report.md | cron errors + system events |
| 11 | Database Inventory | database_inventory.md | SQLite .tables + .schema |
| 12 | Module Inventory | module_inventory.md | find + wc -l |

## 额外输出

- `EXECUTIVE_SUMMARY.md` — 回答10个核心问题
- `AUDIT_INDEX.md` — 所有文件索引
- `*_raw.json` — 原始数据快照（portfolio/watchlist/scan_log/signal_decay/risk_state/market_env/calibrated_params/trade_history/cron/database/modules/execution_history）

## 打包

```
eagle_eye_audit_package_YYYY-MM-DD/
├── AUDIT_INDEX.md
├── EXECUTIVE_SUMMARY.md
├── 12个 markdown 报告
├── strategy_files/ (7个原始文件)
└── 12个 raw JSON 数据文件
```

打包为 `eagle_eye_audit_package_YYYY-MM-DD.zip`

## 执行流程

1. 创建目录 `~/eagle_eye_audit_package_YYYY-MM-DD/`
2. 并行收集原始数据（Alpaca API + JSON文件 + SQLite + Cron）
3. 收集策略文件（SKILL.md + 权重 + 校准 + 合规 + 推送策略）
4. 生成12个markdown报告 + EXECUTIVE_SUMMARY + AUDIT_INDEX
5. 打包zip
6. 发送给用户

## 禁止行为

- ❌ 自动修复
- ❌ 自动重启
- ❌ 自动优化
- ❌ 自动重构
- ❌ 自动新增模块/通知/字段
- ❌ 省略项目
- ❌ 摘要代替原始内容

## 脚本

- `~/.hermes/scripts/review_package.py` — 日报生成（Section 1-8）
- `~/.hermes/scripts/generate_audit_reports.py` — 审计报告生成（从raw JSON生成markdown）
