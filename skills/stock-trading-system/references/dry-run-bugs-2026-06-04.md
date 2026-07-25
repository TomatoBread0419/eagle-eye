# 2026-06-04 硬约束 dry-run 暴露的 6 个 bug

## 触发

用户在 6/4 09:54 授权把"sell→buy 配对缺口"3 条规则升级为脚本层硬约束。我 patch 完 §15.8a 后**只做了静态检查 9/9**——没 dry-run 就以为 OK。

第一次 dry-run 立刻暴露 6 个 bug。

## Bug #1：§6b pair qty 无上限 → NVDA 171 股 $39k

**症状：** 报告里出现 `🔄 sell→buy 配对 NVDA x171 @ ~$228.39`——171 股 = $39,000 = 现金 50%。

**根因（原代码）：**
```python
pair_budget = min(cash * HARD_PAIR_RATIO, cash - 500)  # 现金 $78k * 0.5 = $39k
for sym in pair_candidates[:pair_target * 2]:
    ...
    qty = max(1, int(pair_budget // mkt_price // max(pair_target, 1)))
    # = max(1, int(39210 // 228.39 // 1)) = 171
```

**修复：**
```python
qty = max(1, int(pair_budget // mkt_price // max(pair_target, 1)))
qty = min(qty, int((cash * MAX_SINGLE_PCT_OF_CASH) // mkt_price))  # 现金 15%
qty = min(qty, MAX_PAIR_QTY_PER_SYMBOL)                            # 10 股
# 二次校验
if qty * mkt_price > cash * MAX_SINGLE_PCT_OF_CASH:
    qty = max(1, int((cash * MAX_SINGLE_PCT_OF_CASH) // mkt_price))
```

**教训：** 任何 `qty = ... // price` 都要套 3 层护栏（金额 % + 股数 max + 二次校验）。

## Bug #2：§6c add qty `int(held.qty * 0.5)` 也无上限

**症状：** 持仓 16 股 JPM 加仓 qty = 16 * 0.5 = 8 股 = $2,400（中等风险但仍超合理上限）。

**修复：** 加 `MAX_ADD_QTY_PER_SYMBOL = 3` + 金额护栏同 #1。

## Bug #3：6e 块 `total_bought_so_far < 1` 永远 False

**症状：** 6e 块在 dry-run 输出里**完全没出现**——既没 `🔧 硬约束 buy` 也没 `🔴 硬约束失败` 行。

**根因（原代码）：**
```python
total_bought_so_far = len([m for m in buy_msgs if '买入' in m or '加仓' in m or '配对' in m])
if can_buy and utilization < HARD_UTIL_FLOOR and total_bought_so_far < HARD_MIN_BUY_PER_RUN:
    # 6b 触发 → '配对' 在 m 里 → total_bought_so_far = 1 → 1 < 1 = False → 6e 跳过
```

**修复：**
```python
buy_count_6b6c = len([m for m in buy_msgs 
                       if ('配对 ' in m and '配对失败' not in m)  # 配对成功才计
                       or ('加仓 ' in m)])
```

**教训：** 想判断"是否真买成功"不能用关键字匹配。最好用 explicit flag:
```python
bought = []  # 真下单成功的 symbol 列表
# place_market_order 成功后
bought.append(sym)
# 6e 判断
if not bought and util < HARD_UTIL_FLOOR:
    ...
```

## Bug #4：`__get_daily_bars` 调死代码 `_get_daily_bars`

**症状：** dry-run 报 `NameError: name '_get_daily_bars' is not defined`。

**根因（pre-existing 死代码）：**
```python
# L230-232 原代码
def __get_daily_bars(symbol):
    """包装 us_common.get_daily_bars，注入 API keys"""
    return _get_daily_bars(symbol, config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)
# _get_daily_bars（单下划线）从未定义！
```

**为什么藏到现在：** 6b 段用 import 的 `get_us_price`（无 key）跑得通；6e 块 RSI 快检用 `__get_daily_bars` 但因 Bug #3 永远跳过；`get_bars()` 在 analyze() 内部也调了 `_get_daily_bars` 但平时也没人调 analyze()——所以死代码**从没被执行过**。

**修复：**
```python
from us_common import get_daily_bars as _us_common_daily_bars, get_us_price as _us_common_us_price

def __get_daily_bars(symbol):
    return _us_common_daily_bars(symbol, config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)
```

**教训：** "调了但函数从未定义"的死代码藏在 永远跑不到的代码路径里。**只有 dry-run 让死代码路径被触发**才会暴露。

## Bug #5：`get_sector(sym)` 函数未定义

**症状：** dry-run 跑到报告段报 `NameError: name 'get_sector' is not defined` at L957。

**根因（pre-existing）：** 报告段 L957 调 `get_sector(h['symbol'])` 但函数从未定义。Skill 里 `TRUMP_SECTOR_MAP` 在 markdown 文档里但没 import。

**修复：** 加 SECTOR_MAP dict + get_sector() 包装函数。

**教训：** 同 Bug #4 — 死代码藏在"dry-run 跑完才执行"的报告段。**没 dry-run 就发现不了**。

## Bug #6：dry-run 报 `现金 $X` 是 local var 不是真 Alpaca cash

**症状：** 真实 Alpaca 现金 $78,421.57（untruncated），但 dry-run 报告头写 `现金 $37,293.86`（被 §6b 算 NVDA 171 减下来的 local var）。

**根因：**
```python
# main() 开头
equity, cash = get_portfolio()  # 真实值
# §6b/6c/6e 段
cash -= price * qty  # 改的是 local var
# 报告段
print(f'现金 ${cash:,.2f}')  # 用的是 local，不是真 Alpaca
```

**症状细节：** 用户看到 dry-run 报 $37k 现金会以为真成交了，但实际 Alpaca cash 还是 $78k（limit 单 accepted 没扣款）。

**临时 workaround：** 报告加 `⚠️ cash 已扣除虚拟下单，真实以 Alpaca 为准`。

**终极修复（待办）：** 报告段重新 `equity, cash = get_portfolio()` 拉真值再 print。

**教训：** 任何 "side effect modifies local var used in report" 的模式都危险。Report 数据源必须 = 真 API 调用，不 = local var。

## 6 个 bug 之间的依赖关系

```
patch 完硬约束（§15.8a）
  ↓
dry-run 第一次
  ↓
触发 Bug #1（NVDA 171）→ 修复 → 触发出单被 dedupe 跳过 → 触发 Bug #3 永远跳过
  ↓
修 Bug #3
  ↓
触发 Bug #4（__get_daily_bars 死代码）→ 修复
  ↓
触发 Bug #5（get_sector 死代码）→ 修复
  ↓
dry-run 完整跑通
  ↓
6e 块成功挂 INTC 1 股 limit $118.75 ✅
```

**关键观察：** Bug #4 和 #5 都是 pre-existing 死代码，藏在"6e 块被修复后跑得到"的代码路径里。**修一个 bug 才能让下一个 bug 暴露**——这就是为什么"patch 后必须 dry-run 一次"是不可替代的。

## 配套修复

- `~/.hermes/scripts/us_trader.py` L100-106 加 4 个护栏常量
- `~/.hermes/scripts/us_trader.py` §6b 改 qty 计算加 3 层护栏
- `~/.hermes/scripts/us_trader.py` §6c 加同样护栏
- `~/.hermes/scripts/us_trader.py` §6e 改触发条件为 `buy_count_6b6c == 0` 精确匹配
- `~/.hermes/scripts/us_trader.py` §6e 6e 块加噪声单过滤 + 金额护栏
- `~/.hermes/scripts/us_trader.py` L230-242 重写 `__get_daily_bars`/`__get_us_price` 不调死代码
- `~/.hermes/scripts/us_trader.py` L63 删 `get_daily_bars`/`get_us_price` 直接 import（改走 `__get_*` 包装）
- `~/.hermes/scripts/us_trader.py` L243+ 加 SECTOR_MAP + get_sector()
- 备份：`stock_trader/backups/us_trader_20260604_hardutil_v2.py`

## 决策日志

- `stock_trader/logs/2026-06-04_hard_constraints_patch.md`（v1 patch 记录）
- `stock_trader/logs/2026-06-04_dry_run_bugs.md`（本 transcript 的精简版）

## Lesson（推广）

1. **静态检查 ≠ 端到端验证。** 9/9 静态断言通过，dry-run 立刻暴露 6 bug。
2. **死代码藏在永远跑不到的路径里。** 唯一办法是跑端到端。
3. **qty 计算没有护栏 = 灾难。** 现金 × 50% / 单股价 = 股数 — 必须三层护栏。
4. **触发条件用 explicit flag，不用关键字匹配。** 字符串包含判断会把"失败"算成"成功"。
5. **报告数据源 = 真 API，不 = local var。** local var 被 side effect 改过了，误导用户。
