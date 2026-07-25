# OWNER GOVERNANCE RULE v1.0

**Effective:** 2026-06-19
**Authority:** Owner
**Status:** ACTIVE — Immediately enforceable

---

## OBJECTIVE

Reduce Owner involvement to ≤ 5 minutes per day.

## PRINCIPLE

Owner is not a message relay between AI systems.
Hermes must become self-auditing.

## RULES

### Rule 1: ONE Daily Report

Name: **Eagle Eye Daily Review**

Contents (4 sections only):
1. **System Health** — uptime, cron status, API connectivity, proxy status
2. **Trade Summary** — executions today, P&L, position changes, pending orders
3. **Risk Summary** — drawdown, stop coverage, sector exposure, policy violations
4. **Action Required** — items needing owner decision (0 = system healthy, no action)

Delivery: WeChat, once per day.

### Rule 2: Silent Unless Action Required

WeChat notifications are ONLY permitted for:

| Trigger | Threshold |
|---------|-----------|
| EMERGENCY_STOP | Activated |
| SYSTEM_OFFLINE | > 2 hours |
| MISSED_AI_DECISION | ≥ 2 consecutive cycles |
| DRAWDOWN | > 12% |
| POLICY_VIOLATION | Any hard constraint breach |

**Everything else is silent.** All other cron output → local storage only.

### Rule 3: No Feature Development

Continue 14-day autonomous test.
Only: bug fix, reliability improvement, documentation.
Forbidden: new features, new modules, new integrations.

### Rule 4: Success Criteria

Owner interaction ≤ 5 minutes per day.

If owner interaction exceeds this limit, the system design has failed.

---

## CRON COMPLIANCE MATRIX

| Cron Job | Current Delivery | Required Delivery | Action |
|----------|:----------------:|:-----------------:|--------|
| Eagle Eye Daily Review (154d0c4e4f81) | weixin | **weixin** | COMPLIANT — only WeChat-allowed job |
| 美股AI决策 (a638e8d39d5d) | weixin | local | RECONFIGURE |
| 美股GARP扫描 (b735145148c4) | weixin | local | RECONFIGURE |
| 美股盘后扫描 (28139eb5e759) | weixin | local | RECONFIGURE |
| 持仓专题卡片 (ea3e2530b0b7) | weixin | local | RECONFIGURE |
| 凯利仓位计算 (0ca23f29fbde) | weixin | local | RECONFIGURE |
| Review Report (98dcdfc2aa4f) | weixin | — | One-shot, allow to complete |
| 市场事件监控 (d65b06eddcad) | local | local | COMPLIANT |
| 早间速报 (147cc7f5088a) | local | local | COMPLIANT |
| 午间速报 (d3f17ab4ca86) | local | local | COMPLIANT |
| 市场环境采集 (156e40a9c859) | local | local | COMPLIANT |
| 参数自校准 (1da0dc5f927c) | local | local | COMPLIANT |
| 规则合规审计 (8604888631f4) | local | local | COMPLIANT |
| All paused jobs | — | — | NO ACTION |

## WECHAT MESSAGE BUDGET

| Category | Max/Day | Notes |
|----------|:-------:|-------|
| Daily Review | 1 | Eagle Eye Daily Review only |
| Critical Alert | 0–3 | Only 5 triggers above |
| **Daily Total** | **≤ 4** | Down from previous cap of 8 |

---

## DEFINITIONS

**System Health:** Process alive status (gateway, proxy, scheduler), API reachability (Alpaca, DeepSeek), disk space, last successful cron run.

**Trade Summary:** Orders executed today (filled), P&L vs previous close, position count change, sector allocation shifts.

**Risk Summary:** Current drawdown %, stop coverage %, positions near stop, sector concentration, policy violation count.

**Action Required:** Items requiring owner decision. When system is operating normally within all constraints, this section reports "0 actions required" and owner does nothing.

---

*Protect Owner Capital. Protect Owner Attention.*
