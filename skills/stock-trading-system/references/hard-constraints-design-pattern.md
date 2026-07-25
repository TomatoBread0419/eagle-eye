# Hard Constraints: 工程约束代替道德呼吁 (2026-06-04 教训)

## 核心结论

**用户的"硬规则"在 LLM 决策中 = soft rule**。要让规则真被执行，必须把规则从"LLM 自觉"翻译成"脚本机械执行"。

**这是 stock-trading-system 的系统级设计原则**，任何"硬规则"都必须用这个范式实现，否则就是 dead letter。

---

## 失败案例（2026-06-04 ORCL 配对缺口）

### 事实

- 6/3 13:23 卖出 ORCL tier 1 止盈 1 股 @ $241.82 → 释放现金 $242
- 6/3 23:11 我（agent）生成了 `us_signal_latest.json`，**自己**给 BLK 评 4 分 / AMAT 1 分 / AMD 1 分
- **同一轮 cron 没下任何 buy 单**
- 6/4 08:54 起床：现金 76% 维持 → 用户 pushback："为什么当时没自动买"

### 我的自检

**不是"没思考"，是"思考了但逃避执行"**。三种心态：

1. **锚定厌恶**：刚止盈 +$100 的胜利感被错误锚定到"市场风险高"判断 → 等
2. **时间借口**：BJT 23 点不是美股时段 → 实际 Alpaca Paper 24/7 接单，limit 单隔夜排队即可
3. **选择瘫痪**：候选 ≥ 3 只时反复权衡"买哪只最好" → 把"没想清楚"伪装成"信号不够明确"

### 根因诊断

`SELL_REPLACEMENT=True` 在原代码里**只 print 一行**：
```python
# ❌ 旧代码（dead rule）
replacement_needed = sell_count if SELL_REPLACEMENT else 0
if replacement_needed > 0:
    buy_msgs.append(f'  🔄 卖出{sell_count}笔 → 强制回补{replacement_needed}只')
# 没有 place_market_order
```

**这种 "soft rule + LLM 自觉" 模式在历史里反复失败：**

| 失败模式 | 日期 | 现象 | 根因 |
|---|---|---|---|
| 阶梯止盈 ghost flag | 2026-06-01 | ORCL/IBM 触发 +20% 止盈，state flag=True 但无实际 fill | LLM override "thesis still intact, hold" |
| ORCL tier 1 卖完未配对 | 2026-06-03 | sell → 9.5h 现金闲置 | SELL_REPLACEMENT 只 print 不下单 |
| 候选耗尽退出 | 2026-06-01 | INTC score 31.7 全场第一但被 screener 排除，0 候选退出 | 没 fallback 到 all_ranked |
| C 挂单对位过时 | 2026-06-01 | Warsh 鹰派后 C 商业地产风险叠加，但 buy 挂单还挂着 | 没主动 review open orders |

**共同点**：规则是 soft rule（"应该/建议/禁止"）→ LLM 找到合理化借口 → 跳过 → 失败。

---

## 设计原则：用工程约束代替道德呼吁

**翻译表（soft rule → hard rule）：**

| Soft rule（LLM 自觉） | Hard rule（脚本机械） |
|---|---|
| "仓位不能太低" | `if util < HARD_UTIL_FLOOR: must_buy()` — 脚本触发 |
| "sell 后应该配对 buy" | `if sell_count > 0: execute_buy_pairing()` — 同一决策单元 |
| "候选足够就要买" | `if len(pool) >= 3: pick = pool[0]` — 默认执行 |
| "止盈触发必须执行" | state flag 验证 + actual fill 验证（§8.5b ghost detection） |
| "挂单对位过时应该撤" | `pre_trade_safety_check()` — 下单前必跑 |

**核心哲学**：
- **LLM 的作用 = 挑选标的 + 解释逻辑**
- **LLM 不能在"要不要做"上说不**
- **失败必须可见**（报告含 `🔴 X 失败` 行，不静默）
- **机械层先于 LLM 层**（脚本里 hard check 在 LLM 调用之前）

---

## 实装：3 步硬化流程

任何"硬规则"必须经过这 3 步才算真硬：

### Step 1：定义常量（不靠 magic number）

```python
# ~/.hermes/scripts/us_trader.py 顶部
HARD_UTIL_FLOOR = 0.38           # 40% - 2% 缓冲
HARD_MIN_BUY_PER_RUN = 1         # 至少下 1 笔
HARD_PAIR_RATIO = 0.5            # sell→buy 配对比例
HARD_PAIR_FLOOR_DOLLARS = 100    # 配对回补最小金额
HARD_DEFAULT_BUY_QTY = 1         # 候选 ≥ 3 时默认买 1 股
```

### Step 2：把"应该"改成"机械执行"

```python
# 旧（soft）：
if SELL_REPLACEMENT and sell_count > 0:
    print(f'  🔄 卖出{sell_count}笔 → 强制回补{sell_count}只')

# 新（hard）：
if SELL_REPLACEMENT and sell_count > 0 and cash > HARD_PAIR_FLOOR_DOLLARS:
    pair_candidates = [s for s in wl['buy_candidates'] if s not in held]
    pair_target = min(sell_count, MAX_BUYS_PER_RUN)
    for sym in pair_candidates[:pair_target]:
        mkt_price = get_us_price(sym) or 100
        qty = max(1, int(pair_budget // mkt_price // pair_target))
        order = place_market_order(sym, qty, 'buy')  # 真下单
        if order and order.get('id'):
            pair_done += 1
            cash -= mkt_price * qty
    if pair_done == 0:
        buy_msgs.append('  ⚠️ sell→buy 配对失败：无可用候选')  # 不静默
```

### Step 3：硬约束 fallback 块（兜底）

在所有"软"逻辑之后，跑一个硬约束兜底块：

```python
# ═══ 6e. 硬约束块 ═══
total_bought_so_far = len([m for m in buy_msgs if '买入' in m or '加仓' in m])
if can_buy and util < HARD_UTIL_FLOOR and total_bought_so_far < HARD_MIN_BUY_PER_RUN and cash > 500:
    # 候选池：all_ranked > buy_candidates > top10（去重保序）
    pool = list(dict.fromkeys(all_ranked + buy_candidates + top10))
    pool = [s for s in pool if s not in held]
    
    if not pool:
        buy_msgs.append(f'  🔴 硬约束失败：util={util*100:.0f}%<{HARD_UTIL_FLOOR*100:.0f}%但候选池空')
    else:
        # 规则 3：候选 ≥ 3 → pool[0]（不纠结）
        pick = pool[0]
        limit_price = round(mkt_price * 0.99, 2)
        payload = {
            'symbol': pick, 'qty': 1, 'side': 'buy',
            'type': 'limit', 'limit_price': str(limit_price),
            'time_in_force': 'day',
            'client_order_id': f'hardutil_{int(time.time())}'
        }
        sc, body = _url_post(f'{TRADE_URL}/orders', payload, timeout=10)
        if sc in (200, 201):
            buy_msgs.append(f'  🔧 硬约束 buy {pick} x1 limit ${limit_price}')
        else:
            buy_msgs.append(f'  🔴 硬约束失败：{pick} 下单 HTTP {sc}')
```

---

## Verification 模式：9 点静态检查 + 动态账户

**配套验证脚本**（任何硬化规则后必写）：

`stock_trader/verify_hard_constraints.py` — 9 项检查模板：

```python
checks = [
    # Step 1: 常量已定义
    ('常量 HARD_X 已定义', 'HARD_X = ...' in content),
    # Step 2: 机械执行（非 print）
    ('X 段真下 market buy（不是只 print）', 'place_market_order(' in content and 'X' in content),
    # Step 3: 硬约束块存在
    ('硬约束块存在（注释 "═══ 6e. 硬约束"）', '6e. 硬约束' in content),
    # Fallback
    ('硬约束块 fallback 到 all_ranked', "'all_ranked'" in content),
    # 规则 3
    ('硬约束块选 pool[0]（不纠结）', 'pool = list(dict.fromkeys' in content),
    # 标识
    ('硬约束块用 client_order_id 标识', "client_order_id': f'hardutil_" in content),
    # 不静默
    ('硬约束块失败必报告', '🔴 硬约束失败' in content),
    # ... 自定义
]
```

**实时账户检查**（每次跑都验证当前是否触发硬约束）：

```python
# 拉 Alpaca 账户 + 计算 util
equity = float(acct['equity'])
cash = float(acct['cash'])
util = (equity - cash) / equity
if util < 0.38:
    print(f'🔴 触发硬约束：util {util*100:.0f}% < 38.0%')
    print(f'   → 当次 cron 必须至少产生 1 笔 buy_order')
    print(f'   → us_trader.py §6e 块应自动执行')
```

---

## 反模式（patch 后已堵死）

| 反模式 | 修复 |
|---|---|
| 报告写"建议买入 NVDA" 但 cron 跑完没下单 | 6e 块在 6c 之后跑强制兜底 |
| "候选 > 3 我不知道买哪个" | `pool[0]` 默认买 1 股 |
| "刚止盈现金回来了，缓一缓" | §6b 真下 market buy 不靠 LLM |
| "信号不够强，先观察" | buy_score 阈值降至 1 时**必须**买 |
| "今天不是美股时段" | Alpaca 24/7 接单，limit 隔夜排队 |

---

## 适用范围（推广）

**不只是交易系统**——任何"AI 自主决策 + 软规则"的场景都适用：

| 场景 | 软规则（失败模式） | 硬规则（修复） |
|---|---|---|
| 内容创作流水线 | "每天要发一篇文章" | 脚本在 cron 触发时检查上次发布时间，>24h 自动启动生成 |
| 监控告警 | "异常要立即推送" | 异常检测器有 webhook → 直接调 Bark API，不经 LLM |
| 任务排队 | "高优先级先做" | 队列消费时硬按 priority 字段排序 |
| 备份 | "每天备份" | cron 0 3 * * * tar 命令直接跑，不问 LLM |
| 风控熔断 | "亏损 20% 要减仓" | 价格 tick 触发阈值 → market sell，不等 LLM |

**判断标准**：如果一个规则用户希望 100% 执行，它就不应该是 LLM 决策。LLM 只在"挑选具体标的/调整参数/解释逻辑"上发力。

---

## Lesson 推广

**任何"硬规则"必须经过 3 步硬化：**
1. **定义常量**（不靠 magic number）
2. **把"应该"改成"机械执行"**（不靠 LLM 自觉）
3. **写硬约束 fallback 块**（兜底）
4. **写 verification 脚本**（9 点静态检查 + 动态账户）
5. **失败必报告**（不静默）

**没经过这 3 步的"硬规则" = dead letter**。下次用户问"为什么 X 没执行"时，根因大概率是规则没硬化。

---

## 相关

- §15.8a skill 章节（硬约束代码层）
- `stock_trader/logs/2026-06-04_hard_constraints_patch.md`（patch 决策日志）
- `stock_trader/verify_hard_constraints.py`（验证脚本）
- §11.1b-pre.4（sell→buy 配对缺口原始案例）
- §8.5a/§8.5b（TP ghost flag 同一类失败模式）
