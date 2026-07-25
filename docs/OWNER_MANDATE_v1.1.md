# EAGLE EYE OWNER MANDATE v1.2 (Owner Override 2026-07-14)

Priority: CRITICAL

Effective: Immediately — supersedes v1.1 for paper trading

## Owner Directive 2026-07-14

> **模拟盘模式：全自主运行，不确认，不限交易频率。**
> 所有错误都可以犯——模拟盘就是用来撞墙的。
>
> 月度交易限制 (Monthly Trade Guard) **已移除**。
> 回撤守卫 (>12% 停买、>20% 减半仓) 和现金守卫 (>20% 暂停) 保持有效。
>
> 本次 override 不影响实盘阶段的恢复条款。

Purpose:

Simulate aggressive autonomous trading. Paper account, no real capital at risk.

Primary priority order (simulation mode):

Return > Learning > Risk Control > Simplicity

---

# 1. Immediate Freeze

Freeze all feature development for 14 days.

Allowed:

* bug fixes
* reliability improvements
* recovery improvements
* documentation

Forbidden:

* new agents
* new dashboards
* new reports
* new AI modules
* new scoring systems
* new ranking systems
* new notifications
* new sector models

---

# 2. Produce Documents First

Within 24 hours generate:

1. SYSTEM_INVENTORY.md

2. SIMPLIFICATION_PLAN.md

3. DEPENDENCY_MAP.md

4. FAILOVER_PLAN.md

5. 14_DAY_AUTONOMY_TEST_PLAN.md

Do NOT implement before documents are completed.

---

# 3. Simplification Target

Reduce system complexity by at least 30%.

Targets:

Modules: <40

Cron Jobs: <10

Notifications: Essential Only

Rule:

If removal does not increase portfolio risk, remove it.

Identify duplicate:

* monitoring
* reporting
* logging
* explanation layers
* vanity dashboards
* non-actionable alerts

---

# 4. AI Authority Reduction

AI is Recommendation Engine only.

Architecture:

AI Recommendation

↓

Policy Validator

↓

Hard Guards

↓

OMS

↓

Broker

AI cannot:

* bypass guards
* override guards
* self-authorize trades
* modify policies

---

# 5. Hard Guards

Cash Guard:

Minimum cash = 20%

If cash <20%:

BUY_DISABLED

---

Position Guard:

Soft Limit = 15%

Hard Limit = 18%

18% cannot be exceeded.

---

Sector Guard:

Maximum = 25%

No exceptions.

---

Daily Trade Guard:

Normal = 4 trades/day

Emergency stop-loss = exempt

---

Monthly Trade Guard:

Maximum = 25 trades/month【已暂停 — Owner Override 2026-07-14】

After limit:

【已暂停】BUY_DISABLED

---

Drawdown Guard:

> 12%:

Pause new buys

> 20%:

Reduce exposure

---

# 6. Notification Reduction

Keep only:

1. Trade Executed

2. Risk Alert

3. Daily Summary

Everything else must be reviewed.

Rule:

If notification requires no action, remove it.

---

# 7. Hidden Dependency Audit

Produce DEPENDENCY_MAP.md

Map:

Market Data

↓

Scanner

↓

AI

↓

Policy

↓

OMS

↓

Broker

Label each component:

V6 or V7

Document:

* execution owner
* hidden dependencies
* failure impact

---

# 8. Single Point Of Failure Elimination

Produce FAILOVER_PLAN.md

Answer:

What happens if:

* phone dies
* reboot
* termux crashes
* storage corruption
* network outage
* power outage

Target:

Owner absent for 14 days.

System remains safe.

---

# 9. 14-Day Autonomous Test

Success criteria:

No manual intervention.

No dashboard login.

No manual restart.

No emergency action.

System must:

* avoid duplicate orders
* avoid missed orders
* avoid runaway trading
* maintain all guards

Success metric:

0 critical incidents in 14 days.

---

Final Rule:

When uncertain:

Choose:

Simpler

Safer

Lower Frequency

More Stable

Never optimize for complexity.

Never trade to satisfy metrics.

Protect Owner Capital.
