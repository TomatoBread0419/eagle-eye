# 风控体系

## 双轨止损

| 层 | 实现 | 行为 |
|----|------|------|
| Layer 1（硬件） | Alpaca GTC stop @ cost×(1-pct) | 永不取消，永不移动。pct 由波动率分档：7-10% |
| Layer 2（软件） | Python 追踪止损 @ highest×(1-pct) | 每轮 cron 更新。pct 与 Layer 1 同档 |

## 阶梯止盈

| 触发 | 行动 | 备注 |
|------|------|------|
| PnL ≥ +20% | PATCH stop qty → 卖 1/3 | 先 PATCH，不 cancel |
| PnL ≥ +35% | 再卖 1/3 | 保留最后 1/3 跑趋势 |
| 从 20-bar 高回落 >8% | 卖最后 1/3 | 趋势反转 |
| RSI > 85 | 卖 50%（override） | 极端超买 |

## Alpaca Stop Order 死锁（重要）

- **永远不要 cancel stop order** → `pending_cancel` 卡死，锁住所有 shares
- 需要减 qty：用 `PATCH /v2/orders/{id} {"qty": N}`
- `pending_cancel` 只能等下一交易日开盘自动清理

### Wash Trade 陷阱（2026-06-04 新增）

**已有止损单的持仓不能直接加仓。** buy order + 已有 stop sell → `403: potential wash trade detected`。

即使 cancel 旧止损后再买，也会触发二重问题：
1. Cancel → pending_cancel 死锁（shares held_for_orders）
2. Buy 仍然被拒 403（pending_cancel 的 stop 仍被 wash trade 检测认定）

**唯一安全做法**：
- 建新仓（无旧止损）：直接下限价单 ✅
- 加仓已有持仓：不要碰止损，等 cron 自然处理或接受不加仓
- 如果旧止损在 `new` 状态：cancel → 立刻 buy → 立刻挂新止损（有风险）

## Ghost TP Flag

`us_risk_state.json` 中 `{sym}_tp1_done = True` 但无实际 fill：
1. 确认当前 PnL > TP 触发线
2. PATCH stop qty → market sell 1 share
3. 更新 state → 留 log

## 账户级风控

| 回撤 | 行动 |
|------|------|
| <12% | 正常交易 |
| 12-20% | 停买 |
| ≥20% | 强制卖出 50% |
| 恢复至 <8.4% | 自动恢复买入 |

## 硬约束（脚本层，LLM 不可覆盖）

- `HARD_UTIL_FLOOR = 0.38`
- `HARD_PAIR_RATIO = 0.5`
- sell→buy 同周期完成
- 候选 ≥3 → 取 pool[0]

## Short 仓位

| 浮亏 | 行动 |
|------|------|
| ≤-3% | 观察 |
| -3~-5% | 强制重审 thesis |
| ≥-5% | 强制市价平空 |

## 详细参考

- `take-profit-deadlock-2026-06-01.md` — stop 死锁完整事件
- `tp-ghost-flag-2026-06-03.md` — ghost TP 修复实录
- `sell-buy-pairing-gap-2026-06-04.md` — sell→buy 配对缺口
- `hard-constraints-design-pattern.md` — 硬约束设计
