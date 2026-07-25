# us_trader.py --report 输出结构：stops 区段

`us_trader.py --report` 返回的 JSON 有两组平行持仓数据，分别在不同的顶层 key 下：

## holdings 区段（基础信息）

```json
{
  "holdings": [
    {
      "symbol": "ABBV",           // 股票代码
      "qty": 3,                   // 持仓股数
      "side": "long",             // 方向
      "avg": 228.68,              // 平均入场价
      "current": 224.81,          // 当前价
      "market": 674.44,           // 市值
      "pnl": -11.60,              // 浮动盈亏美元
      "pnl_pct": -1.69            // 浮动盈亏百分比
    }
  ]
}
```

**特点**：只有基础字段，不含止损/波动率信息。

## stops 区段（止损详情）← 这是止损距离读卡的数据源

```json
{
  "stops": [
    {
      "symbol": "ABBV",
      "cost": 228.68,             // 入场成本（与 avg 同）
      "current": 224.81,          // 当前价
      "highest": 227.23,          // 持仓期间最高价
      "vol_20d": 21.5,            // 20日年化波动率 (%)
      "stop_pct": 0.08,           // 波动率分档止损百分比
      "trail_stop": 210.39,       // 追踪止损价（动态上移）
      "init_stop": 210.39,        // 初始止损价
      "hard_stop": 210.39,        // 硬止损价（Alpaca stop order）
      "dist_to_stop": 0.0642      // 现价到止损的距离（小数，0.0642=6.42%）
    }
  ]
}
```

### 关键字段解释

| 字段 | 含义 | 使用场景 |
|------|------|---------|
| `trail_stop` | 追踪止损价，随最高价上移 | 计算有效距离的第一个触发点 |
| `hard_stop` | Alpaca 实际执行的 stop order 价格 | 止损覆盖审计 |
| `dist_to_stop` | (现价 - 有效止损) / 现价，小数 | 直接用于排名和过滤 |
| `stop_pct` | 波动率分档结果 0.07-0.10 | 风控参数，非直接使用 |
| `vol_20d` | 20日年化波动率百分比 | 判断波动率分档的原始数据 |

### 有效止损价选择规则

当同时存在 `trail_stop` 和 `hard_stop`：
1. 首先使用 `trail_stop`（它随最高价上移，最先触发）
2. 两者可能相等（新仓位尚未上涨）
3. `trail_stop` 总是 ≥ `init_stop`/`hard_stop`

### stops vs holdings：数量一致性

两个区段长度相同（每只持仓都有对应），但：
- `holdings` 只有 n+1 个字段：symbol/qty/side/avg/current/market/pnl/pnl_pct
- `stops` 有全部止损和波动率相关字段

## 其他顶层字段（补充）

```json
{
  "timestamp": "2026-06-11T10:10:29+00:00",
  "mode": "report",
  "account": { /* 账户概况：equity/cash/long_mv/short_mv/utilization/target_util/drawdown/can_buy */ },
  "analysis": [ /* 技术分析：price/rsi/ma5/ma20/boll/buy_score/macd_atr/vol_20d */ ],
  "holdings": [ /* 基础持仓 */ ],
  "stops": [ /* 止损完整数据 */ ],
  "event_signals": [],
  "negative_bias": [],
  "risk_flags": []
}
```

## 常见陷阱

1. **`--report` 不返回 open orders**（2026-06-09 已知 bug）。止损覆盖审计必须直接调 Alpaca API，不能依赖此输出。
2. **`dist_to_stop` 默认相对 trail_stop**，不是 hard_stop。列卡时如要显示"止损价"列应优先用 trail_stop。
3. **`dist_to_stop` 为小数**（0.0642 = 6.42%），不是百分比整数，乘以 100 后再格式化。
4. **超时风险**：全量输出可能在 90-150s 返回（含 Alpaca API 调用），`terminal()` 需设 `timeout=150`。
