# Eagle Eye Daily Auto-Approval Policy

**Version:** 1.2 (Owner Override 2026-07-14)
**Effective:** 2026-06-18 (v1.1), Amended 2026-07-14
**Amends:** §§5, 6.1(new), 7, 8
**Scope:** All Eagle Eye V7.1 LTS automated trading operations
**Override:** This policy takes precedence over conflicting rules in Memory or SKILL.md

## Owner Override 2026-07-14 — Simulation Mode

Monthly Trade Guard / Position Guard / Daily Trade Guard 的卖出限频条款已暂停：
- **Monthly Trade Guard**（§5）— 暂停。无月度交易笔数上限。
- **Daily Trade Guard**（§5）— 暂停。无日交易笔数上限，止损豁免条款不再需要。
- **Position Guard**（§5）— 暂停软限制（15%）。硬限制（18%）保持有效。
- **Sector Guard**（§5）— 暂停。无板块上限，让系统暴露测试集中风险。

**以下条款保持有效（不可绕过的安全底线）：**
- **Cash Guard**（§5）— 现金 < 20% 停买。保持有效。
- **Drawdown Guard**（§5）— >12% 停买、>20% 减半。保持有效。
- **止损** — 波动率分档止损。保持有效。
- **阶梯止盈** — +20%/35%。保持有效。
- **Liquidation Constraint**（§3）— 暂停。模拟盘可全仓一日清。
- **Multi-Cycle Confirmation**（§6）— 暂停。模拟盘单次扫描即可入场。
- **Sell Discipline**（§2）— 暂停。模拟盘单指标可触发卖出。

**Owner 保留权利：恢复任何 Guard 无需通知系统。

---

## 1. Decision Pipeline (Mandatory Sequence)

```
Scan → Portfolio Impact Assessment → Trade Decision → Execution
```

**Prohibited:** Scan → Trade (skip portfolio impact) is forbidden in all modes.

Every trade decision must answer three questions before execution:
1. What does this do to sector balance?
2. What does this do to position concentration?
3. What does this do to cash utilization?

---

## 2. Sell Discipline — No Single-Indicator Exits

**A sell decision requires at least TWO of the following triggers:**

| Trigger | Threshold |
|---------|-----------|
| Signal Decay CRITICAL | MACD death cross + below MA50 |
| Stop Loss hit | Price ≤ hard stop |
| Take Profit tier | +20% (TP1) or +35% (TP2) |
| Sector over-concentration | Sector > 30% |
| Position over-size | Single position > 18% |
| Fundamental deterioration | Earnings miss / guidance cut / adverse event |

**Single indicators that do NOT alone justify a sell:**
- RSI > 75 alone
- Single-day score drop
- Sector rank slippage (e.g., #3 → #5)
- "Looks weak" / gut feel

When only one trigger fires, the default action is **Reduce (sell 1/3 to 1/2)**, not liquidate.

---

## 3. Liquidation Constraint — No Same-Day Full Clear

**Any single position must not go from full size to zero in one trading day.**

| Current Size | Max Same-Day Reduction |
|-------------|----------------------|
| > 10% of portfolio | Max 50% |
| 5-10% of portfolio | Max 66% |
| < 5% of portfolio | Full exit allowed |

**Exception:** Stop loss execution (Alpaca stop order filled) bypasses this constraint — it is mechanical, not discretionary.

**If a position needs full exit:** Split across 2-3 trading days. Day 1: reduce by allowed %. Day 2: evaluate again, sell remainder if still warranted.

---

## 4. Entry Priority — Sector Balance First

**Order of capital deployment:**

1. **Fill sector gaps** — Target sectors currently below minimum allocation
   - Priority: sectors at 0% get first capital
2. **Reinforce active sectors** — Sectors already held but below target weight
3. **Open new opportunities** — High-score candidates in sectors not currently held (expand Active Sectors count)
4. **Chase high-score individuals** — Only when all above are satisfied

**Minimum sector allocation:** 3% per active sector
**New sector entry:** Requires 2+ scan cycles of sector-level strength before committing

---

## 5. Hard Portfolio Constraints (Non-Negotiable)

| Constraint | Limit | Enforcement |
|-----------|-------|-------------|
| Largest single position | ≤ 18% | Pre-trade check, reject if exceeded |
| Largest sector weight | ≤ 30% | Pre-trade check, reject if exceeded |
| Active sectors (≥3% each) | ≥ 6 target / ≥ 5 healthy / ≥ 4 minimum / < 4 critical | Prioritize gap-filling entries |
| Total exposure (utilization) | ≤ 90% | Cash buffer ≥ 10% |
| Single trade size | ≤ 15% of equity | Position sizing cap |

**Current status (2026-06-18):**
- Largest position: MU 11.5% ✅
- Largest sector: tech 23.3% ✅ (under 30%)
| Active sectors: 3 ❌ CRITICAL (tech, ai, finance — need ≥1 more for Minimum)
- Total exposure: 47.4% ✅

The Active Sectors gap is the most urgent constraint to address.

---

## 6. Entry Gate — Multi-Cycle Confirmation

**A candidate must appear in the buy list for 2-3 consecutive scan cycles before entry is allowed.**

| Cycle Count | Action |
|------------|--------|
| 1st appearance | Flag as WATCH. No entry. |
| 2nd appearance (consecutive) | Eligible for entry if all other gates pass |
| 3rd appearance (consecutive) | Priority entry candidate |

**Rationale:** Prevents chasing single-day momentum spikes. True strength persists across cycles.

**Scan cycles:** Each `us_screener.py` run = 1 cycle. Cron runs daily at 08:00 BJT; manual runs also count.

**Implementation:** Maintain a `candidate_tracker` that records each symbol's consecutive appearances. Reset to 0 if a symbol drops out for one cycle.

### 6.1 Structural Exemption — Seed Position for Gap Sectors

**Purpose:** When Active Sectors are below Minimum (4), the multi-cycle gate creates a deadlock — candidates cannot enter, so sectors cannot be filled, so Active Sectors never increase. This exemption breaks the deadlock without opening a general fast track.

**A Gap Sector candidate may enter as a Seed Position when ALL of the following are true:**

| Condition | Requirement |
|-----------|------------|
| Gap Sector | Candidate belongs to a sector currently ≥ 0% or below 3% allocation |
| Active Sectors | Active Sectors < Minimum (4) — exemption is void above Minimum |
| RSI | 40 ≤ RSI ≤ 70 (no extremes) |
| No contradictory signals | No death cross + volume spike combo; no death cross alone with RSI < 45 |
| Kelly | Kelly allocation ≤ 8% |
| Initial Position | ≤ 5% of portfolio (Seed Position size) |

**Seed Position semantics:**
- A Seed Position is a **placeholder**, not a full position build.
- It counts toward Active Sectors (moves a sector from 0% to ≥ 3%).
- It may be expanded to full Kelly allocation only after passing the standard multi-cycle gate (§6).
- If the candidate drops out of the buy list on the next scan, the Seed Position is not automatically sold — it remains as a sector placeholder unless it triggers a sell discipline (§2).
- Seed Positions are marked in the Dashboard with `🌱` prefix.

**Once Active Sectors ≥ Minimum (4), this exemption self-deactivates.** All further entries must pass the standard multi-cycle gate (§6).

---

## 7. Daily Output — Dashboard Only

**Every automated cycle produces exactly one Dashboard with these sections:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🦅 Eagle Eye Daily Dashboard
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PORTFOLIO SNAPSHOT
  Equity / Cash / Utilization / Drawdown

POSITION HEATMAP (all holdings)
  Symbol | Size% | Sector | PnL% | RSI | Signal | Status

SECTOR MAP
  Sector | Weight | Target | Gap | Active Holdings

CONSTRAINT MONITOR
  Max Position: X% (limit 18%)
  Max Sector: X% (limit 30%)
  Active Sectors: N (need ≥6)
  Exposure: X% (limit 90%)

STOP COVERAGE
  Protected N/N | Naked: [list if any]

ACTIONS REQUIRED: [0 / 1 / 2+]

  Only the following categories count toward Actions Required:

    Safety     — Stop coverage gap, naked position, emergency stop triggered
    Exposure   — Active Sectors < 4 (Critical), position > 18%, sector > 30%
    Data       — Scanner failure, API outage, data file stale > 24h
    Execution  — Order stuck > 1 session, ghost orders affecting capacity
    Portfolio  — Active Sectors Critical (< 4). NOT: sector gaps, observation, scheduled review.

  The following do NOT count as Actions Required:
    - Observation items (e.g., "RSI elevated, monitor")
    - Scheduled reviews (e.g., "rebalance next week")
    - Sector gaps (long-term optimization, not daily mandate)
    - Trades already In Progress (e.g., JPM reduction with open orders)

  When 0: "No intervention needed. System operating within policy."
  When 1: List the single action with rationale.
  When 2+: List each action with priority ranking.
```

**No trade orders are placed in the same cycle as the Dashboard.** The Dashboard is informational. Actions are recommendations for the next cycle.

---

## 8. Owner Intervention Threshold

| Actions Required | Owner Action |
|-----------------|-------------|
| 0 | Do nothing. System is self-managing. |
| 1 | Review within 24h. Non-urgent. |
| 2+ | Review within same trading session. System may have a gap. |

**Sector gaps are long-term optimization targets, not daily mandatory trades.** They are tracked in the Dashboard but do not generate Actions Required unless they cause Active Sectors to fall below Critical (< 4).

**Trades in progress** (orders already submitted, pending execution) are tracked as status items, not new action items. They graduate to Execution actions only if stuck > 1 session.

**Owner override:** Owner may always issue a direct trade instruction that bypasses this policy. Such instructions are executed immediately and logged with `source=owner_override`.

---

## 9. Policy Review

This policy is reviewed and may be amended:
- After any significant drawdown event (>5% single-day)
- Monthly (first trading day of each month)
- On owner request

Amendments require owner approval.

---

*End of Policy*
