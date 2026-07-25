# Take-Profit 阶梯执行死锁事件 — 2026-06-01

## 摘要

执行阶梯止盈 1/3 (ORCL 卖 3 股 / IBM 卖 1 股) 时，Alpaca Paper Trading 引擎
把已发出的 GTC stop-loss 订单卡在 `pending_cancel` 状态，导致：
- ❌ DELETE cancel → 42210000 "order pending cancel" (重复请求被拒)
- ❌ PATCH 改 qty → 42210000 "cannot replace order in pending_cancel status"
- ❌ reduce_only=true market sell → 40310000 `held_for_orders=10`
- ❌ 普通 market sell → 40310000 `held_for_orders=10`

所有"绕路"都被 Alpaca 锁死。

## 时间线

| 时间 (CST) | 事件 |
|---|---|
| 11:55 | 撤 ORCL 10 股 stop (`57d21d03`) → pending_cancel |
| 11:55 | 撤 IBM 5 股 stop (`6ca74ece`) → pending_cancel |
| 11:55+15s | 等状态变更，仍 pending_cancel |
| 11:55+45s | 重发 DELETE → 42210000 |
| 11:56+0s | PATCH qty 10→7 / 5→4 → 42210000 cannot replace |
| 11:56+30s | reduce_only=true market sell → 40310000 held_for_orders=10 |
| 11:57 | 决定不再试，记录阻塞日志，等下一交易日清理 |

## 错误响应原文

```json
// 撤单（第二次）
{"code": 42210000, "message": "order pending cancel"}

// PATCH 改 qty
{"code": 42210000, "message": "cannot replace order in pending_cancel status"}

// 普通卖单
{"available": "0", "code": 40310000, "existing_qty": "10",
 "held_for_orders": "10",
 "message": "insufficient qty available for order (requested: 3, available: 0)",
 "related_orders": ["57d21d03-f957-412e-9fc3-bef25e5521fd"], "symbol": "ORCL"}

// reduce_only=true 卖单 — 一样的错误
{"available": "0", "code": 40310000, "existing_qty": "10",
 "held_for_orders": "10",
 "message": "insufficient qty available for order (requested: 3, available: 0)",
 "related_orders": ["57d21d03-..."], "symbol": "ORCL"}
```

## 教训

1. **永远不要撤 stop 单** — 既然 Alpaca 不可靠，stop 单一旦发出就别动
2. **需要做部分止盈时，要么等到 stop 单自然 expire（盘后/到期），要么绕过 stop 重新计算仓位**
3. **新加的 stop 用 PATCH 改 qty 的方法不可行**（pending_cancel 状态 PATCH 也被拒）
4. **唯一的"绕路"是 reduce_only=true** — 但 Alpaca 仍把 stop 单算作持仓锁定
5. **GTC stop 在 Alpaca Paper 几乎不可改** — 要么下新单（锁住更多股）要么等过期

## 设计建议

下次要实现"分批止盈 + 移动止损"，**不要用 stop 锁全仓**。两种方案：

### 方案 A：止损分单制（推荐）
建仓时把 stop 分成 N 份小单：
- 1/3 在 cost * 0.95（先到期先触发 1/3）
- 1/3 在 cost * 0.93
- 1/3 在 cost * 0.90
分批自然减仓，不需要撤销任何单

### 方案 B：纯软件跟踪
完全不用 stop 单。脚本每分钟检查 trailing stop，触发就市价卖。
- 风险：脚本挂了就没保护
- 优势：没有死锁
- 折中：软件 + 单一 GTC stop 在 cost * 0.85（远低于正常 trailing，作为兜底）

## 状态（2026-06-01 11:57）

- ORCL 10 股 +20.79% 浮盈 $1,917 — 仍受 $182.14 stop 保护
- IBM 5 股 +24.84% 浮盈 $1,267 — 仍受 $240.78 stop 保护
- stop 单 status: pending_cancel（卡死，等收盘清理）
- us_risk_state.json 已写入阶梯止盈规则（level 1: 20% → 1/3）

## 下次复检

北京时间 2026-06-02 06:00 cron 触发时自动检查：
1. 查 ORCL/IBM stop 单是否仍是 pending_cancel
2. 如果已 cancel → 立即卖 1/3，重建剩余仓位 stop
3. 如果仍卡 → 写日志警告，等美东 6/1 收盘（北京时间 6/2 04:00）后清理
