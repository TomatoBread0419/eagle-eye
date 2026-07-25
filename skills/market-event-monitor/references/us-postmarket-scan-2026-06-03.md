# 美股盘后扫描 — 2026-06-03 工作流

## 触发

cron 任务在 BJT 06:00 工作日自动运行（≈ ET 18:00 昨晚）。覆盖时段：美股盘后/盘前财报密集段（美东 16:00-20:00）→ 简报送达后用户 07:00-09:00 开盘前可读。

## 数据源

### 1. Yahoo Finance 8 API（无 key）
- **日线收盘**：`/v8/finance/chart/{sym}?interval=1d&range=5d` → 拿 `meta.regularMarketPrice` + `meta.chartPreviousClose`
- **盘后/盘前 tick**：`/v8/finance/chart/{sym}?interval=1m&range=1d&includePrePost=true` → `meta.regularMarketPrice` 是当日已结算收盘，最后几笔 1m close 是 AH/PM 实时价

### 2. Google News RSS（无 key）
- `news.google.com/rss/search?q={keyword}&hl=en-US&gl=US&ceid=US:en`
- 必须用 `en-US` 才能拿到英文盘后/盘前分析（用 `zh-CN` 只会返回国内财经站噪音）

## 必查维度（4 段 ≤500 字）

| 段 | 搜索词模板 | 输出 |
|---|---|---|
| 昨晚收盘 | `US stock market close {M月D日} 2026 SPX NDX DJI` + `VIX close today` | 三大指数 + VIX 涨跌幅 |
| 盘后财报 | `after hours earnings today` + 具体 TICK 业绩词 | Top 3 异动：超预期/不及/指引上下修 |
| 评级调整 | `analyst rating upgrade downgrade today` + `{TICK} {bank} downgrade` | 升/降目标价 |
| 盘后要闻 | `after market news today` + 板块热点词 | M&A / 监管 / 高管 |

## 关键坑点（2026-06-03 实测）

### 坑 A：Yahoo 1m timestamp 是 UTC，BJT 早晨拿到的"最新 tick"实际是昨晚 AH

cron 跑在 BJT 07:30 = UTC 23:30 = ET 19:30。此时 `?interval=1m&range=1d` 返回的"最后几笔 1m"时间是 UTC 23:30 = BJT 07:30，**但这只代表数据已经流向 Yahoo 的时间，不分盘前盘后**。要确认"这是盘后还是盘前"必须：

- 算 ET：`BJT - 13h = ET` → BJT 07:30 = ET 18:30（昨晚盘后期，AH 16:00-20:00 ET）
- 看 `meta.regularMarketPrice` 字段：若已经被当日新收盘刷新，则是盘后；否则是盘前

错误判断会得到相反结论。例如今天把 AH 误判为 PM，结果会读成"早盘低开"，实际是"昨夜盘后回吐"。

### 坑 B：`regularMarketPrice` vs `chartPreviousClose` 不要混用

- `chartPreviousClose`：range 内"再前一日"的官方收盘。range=5d 时它是 4 天前的值，不是 1 天前
- `regularMarketPrice`：最新已结算交易日收盘
- 计算 ±1d 涨跌幅用 `regularMarketPrice` 做基点；算 5d 趋势用 `chartPreviousClose` 做基点

坑 C：Yahoo Finance 个别 ticker 返回 404（实测 `ZI` ZoomInfo 不可用）
备用：CNBC / Investing.com / MarketBeat 直接搜 ticker

## 持仓评估

跑完后必须读 `~/stock_trader/us_risk_state.json` 交叉：
- `positions[*].highest` + 当前价 → 是否触发 Tier-1 (+20%) / Tier-2 (+35%) 止盈
- `trade_log` 最新 entry → 昨日是否新开仓，距硬止损距离
- 现金占比 + 浮盈浮亏 → 总体风险敞口

报告里要给一张持仓小表（关键 5-7 仓 + 触发状态 + 距止损 %），不要全文罗列 25 仓。

## 输出模板

```
🔔 美股盘后 | YYYY-MM-DD 06:00

🌙 [昨晚收盘]
• SPX / NDX / DJI：[点位 + %]
• VIX：[值]

📊 [盘后财报]
• 超预期：TICK1 +X%
• 不及预期：TICK2 -X%
• 指引上修：TICK3

🔄 [评级调整]
• TICK1 升 → 目标价 $X
• TICK2 降 → 目标价 $X

📰 [盘后要闻]
• [1-3 条 1 行]

⚠️ [持仓]
• TICK1 收 $X（距止损 Y%）

🔜 下次：09:00 早间速报
```

**强制规则**：
- 多源交叉验证（≥3 源：Yahoo 报价 + ≥2 路新闻）
- 事件双扫协议：发现重大财报/政策搜同日 ±3 天内其他事件
- 重大事件立即标 🔥
- 真信号才推，安静时段回「🔕 美股盘后扫描：今晨无重大事件」

## 与其他 cron 任务的关系

- 上游：`us-premarket` (BJT 16:00 隔夜覆盖)
- 下游：`hk-intraday` (BJT 09:30-16:00)
- 横向：与 `market-event-monitor` 主扫描合并输出时不冲突，盘后更聚焦单 ticker 财报/评级
