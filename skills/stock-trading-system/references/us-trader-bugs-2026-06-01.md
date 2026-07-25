# us_trader.py Script Bugs — 2026-06-01 22:38 Cron

## 摘要

22:38 BJT 这一轮 us_trader.py 跑出三个独立 bug（前两个是脚本逻辑错误，第三个是设计层面缺口）：

1. **WMT 错杀** — 刚买入 8 分钟就被 `from-high-drop 15.2%` 触发"卖全部"
2. **QCOM 空头误报** — `update_trail_stops` 不区分多空，对空头报"卖出失败"
3. **恐惧偏误检测无 fallback** — Cash 78% > 60% 已触发，但脚本只读 `us_watchlist.json` 候选，没 fallback 到 `all_ranked top5`（INTC top-ranked 不在 buy_candidates 里就漏了）

第三个由 cron agent 手动补了 INTC（10 股 @ $110.28），但治标不治本。下次 session 必须在 `us_trader.py` 里 patch。

---

## Bug #1: WMT 错杀（from-high-drop TP 应用于新鲜仓位）

### 症状
22:30 cron 刚买入 WMT 5 股 @ $114.82。22:38 同一轮 cron 触发卖出 5 股 @ $114.62，浮亏 -0.17%。

**卖出原因（脚本误判）**：
```
💰 止盈卖出 WMT x5 @ $114.62 | 原因: 从高点回撤15.2%→卖全部
```

### 根因
`analyze()` 函数（us_trader.py ~L353）计算 `recent_high_20 = max(highs[-20:])`，对刚买入 8 分钟的 WMT 来说，20-bar high 是几周前的 $135。从 $135 跌 15.2% → 触发"卖全部"。

但买入时的入场价 $114.82，距成本只跌 0.17%。**从 20-bar 历史高点回撤 ≠ 当前仓位回撤**。脚本把"行业回撤"误判成"个股回撤"。

### 影响
- 净亏 -$17（5 股 × $0.2）
- 错失 WMT 中长期持有机会
- 制造噪声：微信报告突然出现"WMT 卖全部"，用户得追问

### 修复方案（us_trader.py patch）
在 `analyze()` 函数的 `sell_reason` 逻辑里加持仓天数判断：

```python
# analyze() 加一个参数 days_held（或从 holdings 查 avg_entry_date）
if days_held < 5:  # 买入后 5 个 bar 内不触发 from-high-drop
    pass  # 跳过这一类 sell_reason
elif price < recent_high_20 * (1 - TP_DRAWDOWN_PCT):
    sell_reason = f'从高点回撤{drop_pct:.1f}%→卖全部'
```

或者更简单：买入时 `set_highest(sym, current, state)` 把 highest 设成当前价而不是 0，这样 trailing stop 起点就是入场价附近。

实际上 `update_trail_stops` 已经在 L392 调用了 `set_highest(sym, current, state)`，但只是覆盖到 `state['positions'][sym]['highest']`。analyze 用的 `recent_high_20` 是 20-bar K线 high，不是 state 里的 highest。**两个最高价计算路径不一致**是 bug 根因。

### 临时 workaround
cron agent 在卖出检查时，先 `set_highest(sym, cost, state)` 把 highest 设为成本价（覆盖之前的 20-bar high）。这样 from-high-drop 计算的 base 就是入场价。

---

## Bug #2: QCOM 空头误报（update_trail_stops 不区分多空）

### 症状
22:38 cron 跑出：
```
⚠️ QCOM 追踪止损触发但卖出失败
```

实际上 QCOM 是 -10 股 SHORT（不是多头）。脚本的 `update_trail_stops` 对所有 holdings 一视同仁地套用多头追踪止损逻辑。

### 根因
us_trader.py L384-412：
```python
for h in holdings:
    sym = h['symbol']
    qty = h['qty']   # ← 对空头，qty = -10
    cost = h['avg']
    current = h['current']
    ...
    if current <= soft_stop and current > init_stop:
        # 触发了
        ...
        order = place_market_order(sym, int(qty), 'sell')   # ← int(-10) = -10
        if order and order.get('id'):
            ...
        else:
            msgs.append(f'  ⚠️ {sym} 追踪止损触发但卖出失败')  # ← 噪声
```

对 QCOM SHORT：
- `qty = -10`
- `current = $235.62`（已上涨 → 浮亏方向）
- `soft_stop = highest * 0.95 = $249.4 * 0.95 = $236.93`（条件成立：current ≤ soft_stop）
- 调用 `place_market_order('QCOM', -10, 'sell')` → Alpaca 拒绝负 qty

### 实际风险
- 报告噪声：每轮都报"卖出失败"，用户看到以为有 bug
- **真正的风险**：如果 QCOM 继续涨触发 -5% 硬线（$245.16），§15 强制平空也会因同 bug 失败 → 风险扩大
- 但目前 P&L -0.28%，离 -5% 还远，**不紧急**

### 修复方案
us_trader.py L384 加一行：
```python
for h in holdings:
    sym = h['symbol']
    qty = h['qty']
    if qty <= 0:
        continue   # 空头走 §15 check_short_positions 专用路径
    ...
```

或者在 `update_trail_stops` 开头判断：
```python
def update_trail_stops(holdings, state, existing_stops):
    # 过滤掉空头
    long_holdings = [h for h in holdings if h['qty'] > 0]
    msgs = []
    for h in long_holdings:
        ...
```

### 临时 workaround
cron agent 在每轮 us_trader.py 跑完后，看 us_signal_latest.json 里的"⚠️ XXX 追踪止损触发但卖出失败"行，对 SHORT 持仓忽略即可。

---

## Bug #3: Fear Bias 检测无 fallback（设计层面）

### 症状
22:38 cron 报告：
```
📊 仓位利用率 22%（目标≥40% cautious）⚠️严重不足
💤 BA 得分0未达1
💤 AAPL 得分0未达1
```

脚本判断"无 buy_candidates 通过" → 没买。但根据 §13.4 恐惧偏误检测规则：
- Cash/equity > 60% ✅（78% > 60%）
- Drawdown < 5% ✅（0.1% < 5%）
- 非 defensive 状态 ✅
- 距上次买入 ≥ 3 周期 ✅

**所有 4 条触发，应该强制买入**。但脚本只读 `us_watchlist.json` 的 `buy_candidates`，没有 fallback 到 `all_ranked top5`。

### 根因
us_trader.py L798-852：
```python
with open(WATCHLIST_FILE) as f:
    wl = json.load(f)
candidates = wl.get('buy_candidates', [])
held_syms = {h['symbol'] for h in holdings}
new_stocks = [s for s in candidates if s not in held_syms]
# ... 没有 fallback to all_ranked
```

`buy_candidates` 在 screener 跑时（5/29 8:08）已经过滤过 RSI < 70。INTC 当时 RSI 高，被排除。但今天 INTC RSI 31 = 完美买点。脚本不知道 RSI 已经变了。

### Cron Agent 的临时补救
本轮由 cron agent 手动：
1. 查 `us_watchlist.json` 的 `all_ranked` → INTC score 31.7 第一
2. 用 Alpaca IEX 实时拉 INTC K线 → RSI 31.1 ✅ < 70
3. 手动下 market buy 10 股 @ $110.28（amount = 1.1% 权益 = 试水）

### 修复方案
us_trader.py L800 之后加：
```python
# 恐惧偏误 fallback: 候选池耗尽时，从 all_ranked top 取非持仓
if fear_bias_triggered and not new_stocks:
    ranked = wl.get('all_ranked', [])
    fallback_candidates = [r['symbol'] for r in ranked[:10] if r['symbol'] not in held_syms][:3]
    new_stocks = fallback_candidates
    screener_msgs.append(f'  🔄 fear bias fallback: 从 all_ranked top 取 {new_stocks}')
```

其中 `fear_bias_triggered` 在 `check_position_utilization()` 里已经检测（need_buy=True），传给主函数。

---

## Bug #4: AMD 追踪止损创建空头仓位（2026-06-08）

### 症状
`--stops` 执行追踪止损时，对 AMD long 仓位触发卖出，但结果是创建了 SHORT 仓位而非平仓。

```
追踪止损触发！卖出 AMD x2 @ $487.39
止盈卖出 AMD x2 @ $487.18 | 原因: 从高点回撤10.8%→卖全部
```

但 Alpaca 返回 `qty=-2, side=short`（空头）而非关闭多头。

### 根因
`us_trader.py` 的止损执行逻辑在 `place_market_order()` 时未正确处理 long→close 场景。可能将已有 long 误判为需要开空，或 `side` 参数传递错误。

### 临时修复
手动执行 `buy 2 shares` 平掉空头仓位。

### 教训
`--stops` 跑完后必须验证 Alpaca positions，确认没有意外的 short 仓位。如果出现 `side=short` 且 `qty<0`，立即 `buy` 平仓。

---

## 时序总结（22:30 → 22:38）

| 时间 (BJT) | 事件 |
|---|---|
| 22:14 | 市场事件监控（d65b06eddcad）发现 Iran/Hormuz 危机 |
| 22:30 | us_trader.py 跑：IBM TP1 卖 2 + C/WMT 买入 + 无 stop（C/WMT 是新仓位） |
| 22:34 | cron 触发本轮（a638e8d39d5d）|
| 22:38 | 手动重跑 us_trader.py：BLK 追踪止损清仓 + IBM TP1 续卖 + WMT 被 bug 错杀 + C/WMT 硬止损挂单 + cron agent 手动补 INTC（§9.1a） |

## 23:10 下一轮 cron 必做
- [ ] INTC 补硬止损 $105（成本 $110.28 × 0.95）
- [ ] 验证 QCOM short 仍正常（P&L 应 < 5%）
- [ ] 关注 JPM（距止损 1%）
- [ ] 监控 Iran/WTI 后续

## 修复优先级

| Bug | 严重度 | 优先级 | 备注 |
|---|---|:---:|---|
| #1 WMT 错杀 | 中（噪声 + 错失机会） | P1 | 会持续在每个新买入触发的下行市场出现 |
| #2 QCOM 空头误报 | 低（仅噪声，但有隐藏风险） | P2 | 风险扩大到 -5% 强制平空时会暴露 |
| #3 Fear bias 无 fallback | 高（错过关键买点） | P1 | 当前正是 fear bias 状态，每天都在错过 |

**建议下次 session 第一件事**就是 patch 这三个 bug + 在 `references/cron-prompt-template.md` 加一行"运行时忽略 QCOM 误报"。

---

## 相关 skill 引用
- §8.5a LLM override TP 机械化（同性质问题：LLM 层的逻辑和脚本层的逻辑不一致）
- §9.1a Live RSI Override（这次 INTC 补仓就是按这个 pattern 手动做的）
- §13.4 恐惧偏误实时检测规则（脚本实现了触发条件但没实现自动 fallback 动作）
- §15 QCOM 强平预案（同 bug 会影响 §15 的 -5% 强制平空）
- §11.4 cron agent 自主决策权（本轮就是按这个原则手动补的 INTC）
