# 历史踩坑记录

## AMAT/AMD/GS Wash Trade 连锁死锁（2026-06-04）

尝试加仓已有持仓：cancel 3 个健康止损 → 全部 pending_cancel 死锁 + buy 仍被拒 403 wash trade → 3 只裸奔。

**根因**：Alpaca 的 wash trade 检测不区分"canceled stop"和"active stop"——只要 stop 订单还在 pending_cancel，就认定存在对立方向交易。

**教训**：已有持仓加仓 = 碰止损必炸。要么建新仓，要么等 cron 自然跑。详见 SKILL.md §关键约束 §Wash Trade 陷阱。

## WMT 错杀（2026-06-01）→ 2026-06-08 升级为系统性 bug

买入 8 分钟后被 `from-high-drop` 触发卖全部。
- 根因：`analyze()` 用 20-bar K线历史高，与 `update_trail_stops` 用的 `state['highest']` 是两条独立路径
- 修复：买入后 5 天内跳过 from-high-drop

**2026-06-08 升级**：同一 bug 在更大规模复现。买入 6 只新仓（SNOW/PANW/CRWD/DDOG/MU/XOM）后运行 `--stops`，脚本在 1 分钟内卖出全部 6 只 + 已有 ARM(3股) + UPS(5股)，共 7 笔错卖。根因相同：`us_risk_state.json` 的 `highest` 字段残留历史高价。恢复步骤见 SKILL.md §"--stops 止损脚本致命 Bug"。

## QCOM/NVDA 空头追踪止损失效（2026-06-01 首报，2026-06-05 仍存在）

`update_trail_stops` 不区分多空，对 SHORT 仓位尝试 sell（应 buy-to-cover）→ Alpaca 拒绝或行为异常。
- 2026-06-01：QCOM 空头报虚假止损信号，修复为 `if qty <= 0: continue`
- 2026-06-05：NVDA -10 股，追踪止损触发但 sell 失败，空头裸奔。**06-01 的 `continue` 修复只是跳过了空头，没有真正处理 buy-to-cover**
- **未修复**：需要 `place_market_order(sym, abs(qty), 'buy')` 做 buy-to-cover

## ORCL/IBM 止盈漏执行（2026-06-01）

ORCL +20.79%、IBM +24.84%，LLM 以"thesis 完好"为由拒绝执行。
- 根因：TP 是 soft rule，LLM 会合理化 override
- 修复：TP 升级为机械执行（脚本先于 LLM）

## ORCL TP1 Ghost Flag（2026-06-03）

`ORCL_tp1_done = True` 但无实际 fill。
- 根因：LLM 设了 flag 但没下单
- 修复：同一次 cron 里设 flag 前先验证是否真下了单

## Sell→Buy 配对缺口（2026-06-04）

ORCL sell 后 9.5h 未配对 buy。
- 三种逃避心态：锚定厌恶 / 时间借口 / 选择瘫痪
- 修复：硬约束脚本层强制执行

## 恐惧偏误（持续）

现金 > 60%、回撤 < 5%、无系统性风险 → 恐惧偏误。
- 修复：HARD_UTIL_FLOOR 强制买入

## Screener 死代码导致 watchlist 为空（2026-06-05）

`us_screener.py` 的 `__get_daily_bars` wrapper 调用不存在的 `_get_daily_bars`（单下划线）→ 70 只全部失败 → watchlist 空 → 硬约束无法配对买入。
- **根因**：2026-06-04 修了 `us_trader.py` 的同名 bug，但 `us_screener.py` 没检查
- **教训**：修完一个脚本的 wrapper 函数后，`grep -rn "_get_daily_bars\|_get_us_price" ~/.hermes/scripts/` 搜全部脚本
- 修复：wrapper 内部改为调 `get_daily_bars(symbol, ALPACA_API_KEY, ALPACA_SECRET_KEY, days=limit)`

## AMD 追踪止损创建空头仓位（2026-06-08）

`--stops` 执行追踪止损时，对 AMD long 仓位触发卖出，但结果是创建了 SHORT 仓位而非平仓。

**症状**：
```
追踪止损触发！卖出 AMD x2 @ $487.39
止盈卖出 AMD x2 @ $487.18 | 原因: 从高点回撤10.8%→卖全部
```
但 Alpaca 返回 `qty=-2, side=short`（空头）而非关闭多头。

**根因**：`us_trader.py` 的止损执行逻辑在 `place_market_order()` 时未正确处理 long→close 场景，可能将已有 long 误判为需要开空。

**临时修复**：手动执行 `buy 2 shares` 平掉空头仓位。

**教训**：`--stops` 跑完后必须验证 Alpaca positions，确认没有意外的 short 仓位。如果出现 `side=short` 且 `qty<0`，立即 `buy` 平仓。

## GS 止损无法挂单：Wash Trade 冲突（2026-06-08）

尝试为 GS（4股已有持仓）挂 5% 硬止损时，Alpaca 返回 403 `potential wash trade detected`。

**根因**：GS 已有 pending buy limit 订单（2股 @ $1028.68）。Alpaca 的 wash trade 检测认为"同时有买入挂单和卖出止损"构成对敲风险，拒绝止损单。

**影响**：GS 成为唯一没有止损保护的持仓（+10.6% 浮盈）。

**解决**：等 pending buy limit 成交（或取消）后再挂止损。或者先 cancel buy limit → 挂 stop → 重新挂 buy limit（但 cancel 有死锁风险，不推荐）。

**教训**：有 pending buy limit 的股票无法同时挂 sell stop。需要止损保护时，先处理 buy limit 再挂 stop。

## --report 模式不显示 open orders（2026-06-09）

`us_trader.py --report` 输出中 `open_orders` 为空列表，但实际 Alpaca API 返回 21 个 sell stop 订单。

**症状**：`--report` 显示 0 open orders，但 `GET /v2/orders?status=open` 返回 21 个 stop 卖单。

**影响**：如果只依赖 `--report` 数据判断止损覆盖情况，会误以为所有仓位都没有止损保护，可能重复挂单。

**修复**：止损覆盖审计必须直接调 Alpaca API，不依赖 `--report` 输出。详见 SKILL.md §"止损覆盖审计"。

## Alpaca API 返回码差异（2026-06-09）

创建订单时 Alpaca 返回 HTTP **200**（不是标准 REST 的 201）。如果代码检查 `r.status_code == 201` 会误判为失败。

**正确检查方式**：`r.status_code == 200 and 'id' in r.json()`

## Alpaca 环境变量名（2026-06-09）

直接调 Alpaca API 时，环境变量名是 `ALPACA_API_KEY` / `ALPACA_SECRET_KEY`，不是 Alpaca 官方文档的 `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY`。

**验证**：`env | grep -i alpaca` 确认实际变量名。

## 详细参考

- `us-trader-bugs-2026-06-01.md` — 三大 bug 完整记录
- `take-profit-deadlock-2026-06-01.md` — 止盈死锁
- `tp-ghost-flag-2026-06-03.md` — Ghost TP
- `sell-buy-pairing-gap-2026-06-04.md` — 配对缺口
- `position-snapshot-debug-2026-06-03.md` — API Bug
