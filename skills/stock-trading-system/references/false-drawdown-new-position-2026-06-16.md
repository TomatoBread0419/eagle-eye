# 新建仓位虚假回撤卖出 — QCOM 案例（2026-06-16）

## 时间线

| 时间 (BJT) | 事件 |
|---|---|
| 22:10 | AI 决策：买入 QCOM 20股、CRWD 5股 |
| 22:12 | `us_trader.py --execute` → QCOM buy 20 @ $229.61 ✅ |
| 22:13 | `us_trader.py --stops` 运行 |
| 22:13 | --stops 输出：`💰 止盈卖出 QCOM x20 @ $229.26 \| 原因: 从高点回撤8.7%→卖全部` |
| 22:13 | QCOM market sell 20 股立即成交 |
| 22:14 | AI 检测到非预期卖出 → 检查 open orders → 确认虚假触发 |
| 22:14 | 重新买入 QCOM 20 股 |
| 22:15 | 修复 risk_state: QCOM.highest = 229.61 |
| 22:15 | 止损覆盖审计 → QCOM stop @ $205.65 重新挂上 ✅ |

## 根因分析

### 数据流

```
us_trader.py --execute
  → 下单 QCOM buy 20 @ $229.61 (market)
  → us_risk_state.json 写入 QCOM.entry_cost = 229.61
  → QCOM.highest 未更新 (仍然 = 249.40 来自旧数据)

us_trader.py --stops
  → 读取 risk_state.QCOM.highest = 249.40
  → 读取 risk_state.QCOM.entry_cost = 229.61
  → 计算回撤: (249.40 - 229.26) / 249.40 = 8.1% → 超过止盈回撤阈值
  → 输出: "止盈卖出 QCOM x20 @ $229.26 | 从高点回撤8.7%→卖全部"
```

### 为何 v4.1 30% 阈值启发式没触发

v4.1 的代码比较的是 `current_price` 与 `stored_cost`：
- QCOM: `abs(232.04 - 229.61) / 229.61 = 1.06%` → ❌ 远低于30%

**正确检测应该比较 highest vs entry_cost，不是 current_price vs stored_cost。**

### 为何 v4.7 closes[-20:] 修复也没用

v4.7 从 `max(highs[-20:])` 改为 `max(closes[-20:])`。但 QCOM 20 日前的收盘价也在 $249 左右，最高点仍然是 $249.40。

## 涉及的系统组件

| 组件 | 影响 |
|---|---|
| `us_risk_state.json` | QCOM.highest 被旧数据毒化 |
| `us_trader.py` | --stops 没有区分"持仓期内最高"和"20日数据最高" |
| `us_common.py` | `set_highest()` 的 30% 偏差阈值过于宽松 |

## 修复动作

### 短期（AI 每次执行 --execute 后手动做）
1. 买入后立即读 `us_risk_state.json`
2. 对新建仓：设置 `highest = entry_cost`
3. 写回文件

### 中期（脚本层面修复）
1. `set_highest()` 中：新建仓时直接 highest = entry_cost，不从 closes 推导
2. 或在 `stops_mode()` 入口处检测——若 highest > entry_cost * 1.05，重置

## 影响范围

| 指标 | 值 |
|---|---|
| QCOM 持有时间 | ~1 分钟 |
| 净亏损 | ~$7 (买 $229.61 → 卖 $229.26 → 再买 ~$232) |
| 额外 API 调用 | 3 次 Alpaca API |
| 是否能预防 | ✅ 如果在 --execute 后重置了 highest |
