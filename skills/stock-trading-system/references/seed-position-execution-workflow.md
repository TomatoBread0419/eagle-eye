# Seed Position 执行工作流（实操指南）

## 触发条件

`us_trader.py --execute` 返回：
```
REJECTED: Active Sectors=3 < Minimum(4). Check §6.1 Seed Position eligibility.
```

**含义**：组合中活跃板块（≥3%配置）不足 4 个。所有非种子买入被拦截。

## Step 0: 盘点可用的 Gap Sector 候选

`us_watchlist.json` 有两个不同的字段：

| 字段 | 类型 | 内容 |
|------|------|------|
| `buy_candidates` | `list[str]` | 仅符号，如 `["AMD", "AMAT", ...]` |
| `all_ranked` | `list[dict]` | 每条含 `symbol`, `score`, `price`, `sector`, `earnings_days` |

**实操**：读 `all_ranked` 按 sector 过滤，找出 gap sector 的候选：

```python
import json
w = json.load(open('~/stock_trader/us_watchlist.json'))
ar = w.get('all_ranked', [])
from collections import Counter
sectors = Counter(item['sector'] for item in ar)
print(dict(sectors))
```

从板块列表和当前持仓分布，找到配置 < 3% 的板块（gap sectors）。在 `all_ranked` 中过滤出这些板块的候选，按 score 排序。

**2026-06-23 实例**：Active Sectors=3（tech 24.4%, ai 11.8%, finance 11.4%），gap sectors 包括 pharma(1.9%), consumer(0%), energy(0%), resources(0%), industrial(0%)。`all_ranked` 中可用候选：FCX(resources, score=25.0), CAT(industrial, score=26.6), GE(industrial, score=24.3)。UNH(pharma) 因 wash trade 不可用。

## Step 1: 验证 RSI 40-70

种子仓位要求 RSI 必须在 40-70 区间。用 `us_common` 实时计算：

```python
import sys, os
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
sys.path.insert(0, os.path.expanduser('~/stock_trader'))
from us_common import get_daily_bars, calc_rsi, calc_volatility

env = dict(line.strip().split('=',1) for line in open(os.path.expanduser('~/.hermes/.env')) if '=' in line and not line.startswith('#'))
key = env['ALPACA_API_KEY']; secret = env['ALPACA_SECRET_KEY']
bars = get_daily_bars('FCX', key, secret, days=45)
closes = [b['c'] for b in bars]
rsi = calc_rsi(closes, 14)
vol = calc_volatility(closes, 20)
print(f'RSI={rsi:.1f} vol={vol:.0f}%')
```

**2026-06-23 实测**：FCX RSI=55.0 ✅, GE RSI=68.0 ✅, CAT RSI=72.4 ❌（70 以上不合格）

## Step 2: 检查矛盾信号

Seed Position 要求 **无矛盾信号**：
- death cross + volume spike → 排除
- death cross + RSI < 45 → 排除

```python
from us_common import calc_macd
macd_line, signal_line, hist, crossover = calc_macd(closes)
```

FCX RSI=55.0 在区间中央，无矛盾信号风险。

## Step 3: 提交种子订单

订单 JSON 必须包含 `_seed: true`, `rsi`, `sector`（英文名）三个字段：

```json
{
  "symbol": "FCX",
  "qty": 75,
  "side": "buy",
  "_seed": true,
  "rsi": 55.0,
  "sector": "resources",
  "reason": "Fill resources gap (0%), event bias +3"
}
```

**数量计算**：seed 仓位 ≤ 5% of equity
- 5% × $105,455 = $5,273
- FCX at $69.69 → 75 股 × $69.69 = $5,227 ✅

**期望输出（PASS 路径）**：
```
policy_check: "PASS"
policy_reason: "PASS | | Active Sectors=3<4 | Seed Position — exempt from §6 multi-cycle gate"
status: "submitted"
```

## Step 4: 验证成交

```python
import time, requests
time.sleep(3)
orders = requests.get(f'{base}/v2/orders?status=all&symbols=FCX&limit=5', headers=headers).json()
for o in orders:
    print(f"filled={o['filled_qty']}/{o['qty']} status={o['status']} avg={o.get('filled_avg_price','N/A')}")
```

## Step 5: 挂硬止损

波动率分档：FCX vol=57% → >50% 档 → 10% 止损：

```python
from us_common import get_volatility_stop_pct
stop_pct = get_volatility_stop_pct(57)  # 0.10
stop_price = round(69.65 * (1 - 0.10), 2)  # $62.69
```

通过 Alpaca API 直接挂 stop（--execute 不适用于刚成交的标的）：

```python
r = requests.post(f'{base}/v2/orders', headers=headers, json={
    'symbol': 'FCX', 'qty': '75', 'side': 'sell',
    'type': 'stop', 'stop_price': '62.69', 'time_in_force': 'gtc'
})
```

## Step 6: 修复 risk_state（关键！防虚假回撤）

新建仓必须设置 `highest = entry_cost`。否则下轮 `--stops` 会用 20日历史收盘最高价计算回撤，导致刚买的股票被立即误卖出：

```python
import json, os
state = json.load(open(os.path.expanduser('~/stock_trader/us_risk_state.json')))
state['positions']['FCX'] = {'highest': 69.65, 'entry_cost': 69.65}
json.dump(state, open(os.path.expanduser('~/stock_trader/us_risk_state.json'), 'w'), indent=2)
```

## Step 7: 运行止损管理

```bash
python3 ~/.hermes/scripts/us_trader.py --stops
```

验证：新仓位的硬止损和追踪止损均显示在输出中。

## Step 8: 止损覆盖审计

```python
positions = requests.get(f'{base}/v2/positions', headers=headers).json()
orders = requests.get(f'{base}/v2/orders?status=open', headers=headers).json()
held = {p['symbol'] for p in positions if int(float(p['qty'])) > 0}
stops = {o['symbol'] for o in orders if o['type'] == 'stop' and o['side'] == 'sell'}
unprotected = held - stops
print(f'Unprotected: {sorted(unprotected) if unprotected else "ALL PROTECTED ✅"}')
```

期望：`ALL PROTECTED ✅`（8/8 覆盖）。

## 执行后效果

种子买入成功后：
- **新 sector 从 0% → ~5%**，成为活跃板块
- **Active Sectors 从 3→4**，后续买入不再需种子路径
- **仓位利用率提升**（如 49.5% → 54.5%）

## 已知陷阱

1. **Wash trade 堵死加仓**：若 gap sector 的唯一候选已有持仓且设了 stop（如 UNH/pharma 有 stop order），无法通过种子路径加仓。必须换标的或等 stop 触发。
2. **all_ranked 只有 20 条**：不是全量扫描池，gap sector 候选可能不在排名前 20。需时跑完整扫描器输出获取。
3. **RSI 计算需 14+ 根日K线**：新上市标的可能不足，用 `len(bars) >= 15` 检查。
4. **止损挂单后 risk_state 修复必须在 --stops 之前**：否则 --stops 读到 old highest 误判回撤。
