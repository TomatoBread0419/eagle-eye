---
name: stock-trading-system
description: 美股自动交易系统 V7.1 LTS — 闭环自校准+动态凯利+合规审计+SQLite+模块化架构。AI全权自主执行，无需用户确认。Alpaca Paper Trading，Android/Termux 纯 Python。
version: 7.1.3
category: data-science
---

# 美股自动交易系统

## Owner 交互协议

AI 全权自主执行，不问确认。Owner 说以下指令时立即响应：
- **"停止" / "停"** → 立刻停下，不管当前任务是否完成
- **"收拾"** → 把当前阶段收干净，不新增任务
- **"继续"** → 不分析，直接执行下一步
- **"汇报"** → 只报告进度，不新增操作

## Git 身份配置（保留）

任何 git commit 前必须验证：
- `git config user.email` 等于 GitHub noreply 地址 `140422770+TomatoBread0419@users.noreply.github.com`
- 绝不替用户生成 SSH key 或公钥
- 绝不编造 git config 中的 user.name/user.email
- 推送永远用 SSH

## V7.1 宪法执行层

三条影子评分路径已全部堵死（AI 不可越过代码层修改）：

| 路径 | 前 | 后 | 宪法条款 |
|------|----|----|:--:|
| 事件→评分 | `score += bias` ±3 | 只读 alerts，不改分 | Article 11 |
| 校准器漂移 | 无限制自动调参 | 20% cap，超限拒写 | Article 13 |
| AI 权重 | 无边界自调 68 参数 | 设计基线锁，>20% 强制回退 | Article 12 |

## 速度优先铁律

- 参考模型讨论只做一轮；分歧直接由聚合器拍板
- 禁止"两个参考模型再分析一下"的二次讨论循环
- 一句结论 + 直接动手。不写计划，不做分析前置。

## 架构（闭环自校准）

```
┌──────── ① 宏观环境 ────────┐
│ market_env.py                │  VIX/DXY/10Y-2Y利差/FOMC
│ → market_env.json            │
└──────────────────────────────┘
           ↓
┌──────── ② 参数自校准 ──────┐
│ calibrator.py                │  90天交易数据
│ → calibrated_params.json     │  sigmoid参数/止损分档/板块加分
└──────────────────────────────┘
           ↓
┌──────── ③ 选股+评分 ───────┐
│ us_screener.py               │  13维度评分
│ kelly_position_sizes()       │  动态凯利(score→sigmoid→p)
│ → us_watchlist.json          │
└──────────────────────────────┘
           ↓
┌──────── ④ 执行+止损 ───────┐
│ us_trader.py (三模式)        │  --report / --execute / --stops
│ 止损分档(波动率)             │  7-10%
└──────────────────────────────┘
           ↓
┌──────── ⑤ 合规审计 ────────┐
│ compliance_audit.py          │  20条规则自动检查
│ → compliance_report.json     │
└──────────────────────────────┘
```

### 模块文件

```
~/.hermes/scripts/
├── us_report.py       # 汇总报告生成器（cron 调用，输出给 AI）
├── us_portfolio.py    # 持仓分析（板块分布/缺口/风险标记）
├── us_screener.py     # GARP 扫描器（87只+板块标签+动态凯利）
├── us_trader.py       # 交易执行（--report / --execute / --stops）
├── us_common.py       # 共享模块（指标计算、行情获取）
├── calibrator.py      # 参数自校准器（sigmoid/止损/板块加分）
├── compliance_audit.py # 合规审计（20条规则）
├── market_news.py     # 多源新闻搜索
├── proxy_patch.py     # SOCKS5 代理补丁
└── proxy_start.py     # 代理管理

~/stock_trader/
├── config.py
├── ai_weight_config.json    # AI可调评分权重
├── calibrated_params.json   # 校准后参数
├── compliance_report.json   # 合规审计报告
├── regime.json              # 市场状态
├── us_risk_state.json       # 止损/止盈状态
├── us_watchlist.json        # 扫描器输出
├── us_portfolio.json        # 持仓分析
├── market_events_latest.json # 市场叙事
└── us_signal_latest.json
```

### us_common.py 共享函数（import path: ~/eagle-eye-pack/scripts/us_common.py）

```python
# 技术指标
calc_rsi(prices, period=14)      # RSI
calc_sma(prices, period)          # SMA
calc_boll(prices, period=20)      # 布林带
calc_macd(prices)                 # MACD（线/信号/柱/交叉）
calc_atr(highs, lows, closes)     # ATR
calc_volatility(prices, period)   # 20日年化波动率

# 风险指标
get_volatility_stop_pct(vol_20d)  # 波动率分档止损 7-10%
calc_volume_metrics(vol, closes)  # 量价分析
calc_correlation(ret_a, ret_b)    # 持仓相关性

# 数据获取
get_daily_bars(sym, key, secret)  # Alpaca 日K线
get_us_price(sym, key, secret)    # 实时报价
url_get(url, headers, timeout)    # HTTP GET 带重试
get_yf_metrics(symbol)            # yfinance 基本面（优雅降级）
```

## 13维度评分公式（全部权重/阈值来自 ai_weight_config.json）

```
基础分 = ret_1m × 0.4 + ret_3m × 0.25 + ret_short × 0.15

RSI 罚分:
  正常: RSI > 75 → -10 | 防御: RSI > 65 → -10 | RSI > 85 → -20

均线加分: ma_uptrend +3, ma_cross +2

波动率因子（20日年化）:
  <20% → +3 | <30% → +1 | >50% → -3 | >40% → -1

MACD 因子:
  金叉 → +3 | 死叉 → -2 | 零轴上方 → +1

成交量因子（量价配合）:
  📈放量上涨 → +3 | ⚠️缩量虚涨 → -3 | 📉放量下跌 → -2

RS vs SPY 相对强度:
  RS_1m > 5% → +2 | RS_1m > 2% → +1 | RS_1m < -5% → -2

yfinance 基本面（优雅降级）:
  Beta >2.0 → -2 | Beta >1.5 → -1 | Beta <0.5 → +1
  Forward PE >50 → -2 | 10≤PE≤25 → +2 | 25<PE≤35 → +1
  股息率 >2% → +1

市场事件→板块映射:
  利好板块: +1~3 | 利空板块: -1~-3

防御模式板块加分:
  telecom/defense +5 | energy +4 | pharma +3
  consumer +2 | resources +1 | finance/industrial 0
  tech -2 | ai -3 | space -3

板块缺配加分（读 us_portfolio.json）:
  缺口>3% → +5 | 缺口>2% → +3 | 缺口>1% → +2
```

### 13维度完整分析矩阵

| # | 维度 | 数据源 | 成本 |
|:--:|------|------|:--:|
| 1 | 价格动量 (1月/3月/5日) | Alpaca IEX | API |
| 2 | RSI (14) | 纯计算 | 零 |
| 3 | 布林带 (20) | 纯计算 | 零 |
| 4 | 均线 (MA5/20/50) | 纯计算 | 零 |
| 5 | 波动率 (20日年化) | 纯计算 | 零 |
| 6 | MACD 金叉死叉 | 纯计算 | 零 |
| 7 | ATR 真实波幅 | 纯计算 | 零 |
| 8 | 成交量/量价关系 | Alpaca bars | 附带 |
| 9 | RS vs SPY | Alpaca SPY | 1次API |
| 10 | yfinance 基本面 | Yahoo | 限流中 |
| 11 | 板块内排名 | 扫描器汇总 | 零 |
| 12 | 市场事件→板块 | market_events | 零 |
| 13 | 板块缺口 | portfolio | 零 |

### 板块分布 + 防御加分

| 板块 | 标的数 | 防御加分 | 示例 |
|------|:---:|:---:|------|
| tech | 23 | -2 | AAPL, MSFT, NVDA, COHR, LSCC |
| ai | 12 | -3 | ARM, PLTR, SNOW, CRWD |
| consumer | 10 | +2 | WMT, COST, MCD |
| finance | 9 | 0 | JPM, GS, BLK |
| pharma | 8 | +3 | LLY, UNH, ABBV |
| industrial | 7 | 0 | CAT, BA, GE |
| energy | 3 | +4 | XOM, CVX, COP |
| defense | 3 | +5 | LMT, RTX, NOC |
| resources | 2 | +1 | FCX, NEM |
| space | 7 | -3 | RKLB, RDW, ASTS, LUNR, PL, BKSY, GSAT |
| telecom | 2 | +5 | T, VZ |

## 凯利仓位数学

凯利公式（全凯利）：`f* = (b × p - q) / b`
- b = 赔率（平均盈利/平均亏损）
- p = 胜率
- q = 1 - p

**执行规则：半凯利**（实际仓位 = f* / 2）

**计算来源**：90天 Alpaca 订单历史 → FIFO 配对买卖 → us_kelly.py
- 实测(2026-06-14): 胜率46% / 赔率2.37 / 半凯利11.6%/笔
- cron: 每周六 05:30（数字短期稳定，不需每天算）

**仓位约束**：1%-25% 范围（半凯利计算结果在此范围内）

**sigmoid 转化（score→p）**: score 通过 sigmoid 映射到 0-1 概率值，参数由 calibrator.py 每周自动校准。

## 风控参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 总仓位 | 85% | 给回撤12%停买留10%缓冲 |
| 单只占比 | 灵活 | AI 根据波动率/板块判断 |
| 追踪止损 | 7-10% | **波动率分档**：<20%→7%, 20-35%→8%, 35-50%→9%, >50%→10% |
| 硬止损 | 7-10% | Alpaca stop order，同档（不调整、不取消） |
| 阶梯止盈 TP1 | +20% | 卖 1/3 |
| 阶梯止盈 TP2 | +35% | 再卖 1/3 |
| 账户回撤 | >12% | 停买 |
| 账户回撤 | >20% | 减半仓 |

## 模式系统（AI 决策）

| 模式 | 仓位目标 | RSI门槛 | 板块偏好 |
|------|:---:|:---:|------|
| aggressive | 50-70% | 75 | tech/ai 偏重 |
| normal | 40-50% | 75 | 均衡 |
| cautious | 35-40% | 70 | 防御板块加分 |
| defensive | 30-35% | 65 | 高波动过滤 |

AI 根据事件对持仓的实际影响（不是关键词匹配）判断模式。

## 动态扫描池机制

扫描池由 `scan_universe.json` 单一配置文件驱动（不再是代码硬编码）。AI 可以：

1. **优先执行新闻驱动买入**：发现赛道受益股（SpaceX供应链/散热/战略金属等），直接在池外买入
2. **无合适标的 → 扩展池子**：将标的追加到 `scan_universe.json` 的 `dynamic_additions` 字段，下轮扫描自动纳入打分
3. **机制**：AI 决策周期中，先判断「今天有什么新闻/事件可以买的」→ 有就直接买 → 没有再从池子打分选

动态添加格式（terminal 或 write_file 操作）：
```json
{\"dynamic_additions\": [[\"SYM\", \"sector\"], ...]}
```

## 关键约束

### 守卫栈优先级（2026-07-14 发现）

| 层 | 位置 | 修改方法 | 覆盖顺序 |
|---|------|----------|----------|
| 1 (最高) | cron job prompt | `cronjob(action='update')` | AI 每个决策周期优先读 |
| 2 | SKILL.md 正文 | `skill_manage(action='patch')` | skill 加载时注入 |
| 3 | 参考文档 (`references/`) | 直接编辑 | AI 可选引用 |
| 4 | 策略文档 (OWNER_MANDATE 等) | 直接编辑 | 静态背景 |

**⚠️ 血训**：改了层3/4/2但没改层1 → 下一轮 cron 仍然执行旧约束。AI 决策输入流是 system + skill(层2) + cron prompt(层1)。层1覆盖层2。

### 操作规则摘要

1. **止损后 1 小时内必须有替代买入**（不是等 1 天）
2. **高波动股票买少一点(1-2股)，但要买，不空仓**
3. **仓位 <30% 时：市价单为主，不纠结价格**
4. **禁止 cancel stop order** → PATCH 减量代替
5. **休市时不要 PATCH stop order qty** → replacement 链挂起锁死持仓
6. **TP 卖出前必须 PATCH stop qty 减少** → 再 market sell（wash trade 保护）
7. **买入前必须检查候选股 RSI** → RSI>80 时预期 50% 会被机械卖出
8. **反复止损股禁止 7 天内重新买入**
9. **开盘检查必须审核所有 pending 订单**（取消窗口 BJT 21:10-21:25）
10. **已有持仓加仓 = Wash Trade** → 必须先处理 stop order
11. **幽灵止损单（0持仓仍有stop挂单）= 不处理**（除非 0 pos + market open）
12. **每次 cron 必须做止损覆盖审计**：检查每只持仓是否有活止损

### 安全阀（硬约束，AI 不可覆盖）

- 回撤 >12%：暂停买入
- 回撤 >20%：减半仓

**瞬态数据异常验证协议**：Alpaca 返回 0 positions + equity 暴跌时：
1. 重试 3 次，间隔 5s
2. 检查 portfolio history 是否显示数分钟前 equity 正常
3. 交叉验证本地状态文件
4. 检查是否有对应 sell fills
5. 确认永久性异常后才走恢复路径

### 开盘检查流程（BJT 21:00-22:00）

**优先级**：取消（有窗口限制）> 买入评估 > 止损管理

五步检查法：
0. 开盘前先紧急审查所有 sell market 订单，需要撤销的立即 DELETE
1. 列出所有挂单，区分 sell_market / buy_market / stop
2. 板块感知的卖单审核：检查每个 sell market 的股票是否在当前缺配板块
3. 买入订单验证：buy market 是否仍然合理
4. 模式对齐：所有操作应对齐当前模式
5. 执行：撤销不合理订单 → 补充新买入

### us_trader.py 三模式

```bash
python3 ~/.hermes/scripts/us_trader.py --report         # 只输出数据
python3 ~/.hermes/scripts/us_trader.py --execute '{...}' # AI 指令执行
python3 ~/.hermes/scripts/us_trader.py --stops           # 止损/止盈管理
```

### V7.1 P0 Guardrails（策略→代码硬守卫）

三层闸门（PASS/REJECT，不可绕过）：
- Gate 0: **Dashboard Gate** — `dashboard_{date}.md` 必须存在
- Gate 1: **Active Sectors** — 活跃板块 ≥4 或走 Seed Position 路径
- Gate 2: **Candidate Confirmation** — 候选需 ≥2 扫描周期（种子豁免）
- Gate 3: **Exposure Limits** — 按凯利公式计算（1%-25% per position），无硬性上限

Seed Position 要求（当 Active Sectors < 4 时）：
- `_seed: true` + `rsi: 40-70` + `sector: 英文名` + `reason` 字段
- Kelly ≤ 8%（可省略），仓位 ≤ 5%
- 种子豁免 §6 多周期确认

### Cash Paradox 规则

机械卖出（TP1/RSI 极端卖）释放大量现金时：
1. 净现金增 >$2K → 本轮必须补至少等额买入
2. TP1 和 RSI 极端卖不应叠加（同一标的满足一个即可）
3. 日终审计：utilization 比上轮低了 → 下轮优先补仓

## Cron 配置

| 名称 | 时间 | 模式 | 交付 |
|------|------|------|------|
| 美股 AI 决策 | 10 21-5 * * 1-5 | LLM | weixin+local |
| GARP 扫描 | 0 8 * * 1-5 | no_agent | local |
| 持仓专题卡片 | 30 9 * * 1-5 | LLM | local |
| 美股盘后扫描 | 0 6 * * 1-5 | LLM | local |
| 市场事件监控 | 0 */2 * * 1-5 | no_agent | local |
| 凯利仓位计算 | 30 5 * * 6 | LLM | local |
| 市场环境采集 | 30 20 * * 1-5 | LLM | local |
| 参数自校准 | 0 6 * * 6 | LLM | local |
| 合规审计 | 10 6 * * 6 | LLM | local |

**唯一推微信**: Eagle Eye Daily Review (0 8 * * *)、美股AI决策（21-5点盘中）

## 关键参考文件

- `references/p1-enforcement.md` — P1 宪法执行详情
- `references/v7.1-p0-guardrails.md` — P0 硬守卫文档
- `references/ai-tunable-weights-architecture.md` — AI可调权重
- `references/dual-layer-stop-philosophy.md` — 双层止损哲学
- `references/cron-wrapper-patterns.md` — 脚本路径限制
- `references/github-clean-migration.md` — Git 迁移记录
- `references/alpaca-stop-qty-increase-blocked-2026-06-23.md` — Wash Trade
- `references/space-sector-addition-2026-06-12.md` — 板块新增流程
- `references/v6-v7-integrated-seed-workflow-2026-06-24.md` — 种子路径
- `references/seed-position-execution-workflow.md` — 种子执行验证
- `references/v5.2-event-signal-fix.md` — 事件信号修复
- `references/skill-bloat-management.md` — SKILL.md 膨胀诊断与修复流程（MoA 环境）
