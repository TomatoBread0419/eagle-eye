# 更新日志

## [v7.2.1] - 2026-08-01

### Type
Feature

### Summary
Eagle Eye v7.2.1 首个正式 Release（BL-001）。V7.2 动态池系统 + Config V2 分层 + HTTP curl 降级 + 事件驱动双轨，clean history 基线。

## v7.2.0 — 2026-07-20

### ✨ 新功能

- **动态池系统** — 从 S&P 500 出发，按流动性/成交额自动筛选 200-300 只标的，替代原 87 只硬编码 watchlist
  - 数据源：S&P 500 成分列表 + Alpaca Trading API
  - 筛选门槛：股价 ≥ $10、日均成交额 ≥ $5M
  - 保留手动标的（中概股、太空、量子计算等 15 只）
  - 每周六 05:30 自动更新（Hermes cron）
  - 24h 本地缓存 + curl 降级获取成分列表

- **Config V2 分层结构** — 7 个 SimpleNamespace Bean，单一 `.env` 来源
  - `cfg.alpaca` / `cfg.risk` / `cfg.pool` / `cfg.http` / `cfg.proxy` / `cfg.log` / `cfg.notify`
  - 向后兼容：`cfg.alpaca_api_key` 等旧属性仍可用
  - `__repr__` 脱敏：secret_key 不再暴露

### 🔧 改进

- **HTTP curl 降级** — 解决 Termux 上 Python requests SSL 握手失败问题
  - 所有 HTTP 方法（GET/POST/PATCH/DELETE）自动回退到 curl 子进程
  - 连接错误直接回退，不再无意义重试

- **BRK.B 点号兼容** — 扫描器正确处理 BRK.B、BF.B 等含点号符号

- **环境变量优先级修复** — `.env 文件 > 环境变量 > 默认值`
  - 解决 shell 残留旧 key 污染系统配置的问题

### 📁 新增文件

- `tools/pool_builder.py` — 动态池粗筛模块
- `CHANGELOG.md` — 本更新日志

### 📝 文档

- README 全面重写，更新为 V2 架构
- 修正「87 只候选池」为「327 只动态池」

---

## v7.1.1 — 2026-07-15

### 🔧 修复

- 修正校准参数未能传递到凯利仓位引擎的问题 — 之前 `calibrated_params.json` 未正确流入 Kelly 计算
- 修复 6c 标的存在止损单时仍然尝试买入导致的 Alpaca 403 wash-trade 拒绝
- 增加 just_sold 同轮次洗盘交易预防 — 卖出后禁止同标的立即买入

### 📝 文档

- 重构 README 为产品级主页布局，中文优先
- 新增 Demo 运行示例板块
- 删除架构说明中 MiniMax TTS（不属于交易系统）

## v7.1.0 — 2026-07-15

### ✨ 新功能

- 交易执行循环上线（每 20 分钟，纯代码不经 LLM）
- 规则合规审计（每周六）
- 参数自校准（每周六）
- 市场事件采集（每 2 小时）
- 行为指纹日报

### 🔧 改进

- 凯利仓位管理：读取 `calibrated_params.json`
- 微信推送频率优化：从 12 次/天降到 4 次/天

---

## v7.0.0 — 2026-07-01

### ✨ 新功能

- 多 Agent 协作架构（扫描 → 决策 → 风控 → 执行 → 审计）
- Alpaca Paper Trading API 集成
- 提示词工程体系（四层结构）
- 结构化通信（JSON Schema 契约）
- 降级保护（API 失败 → 仅止损退出）
- 微信 iLink 实时推送
