# OWNER GOVERNANCE RULE v1.0 — Cron & Notification Policy

**Effective:** 2026-06-19
**Authority:** Owner
**Supersedes:** Push Policy V3.0, V1.1, all earlier notification policies

---

## Principle

Owner is not a message relay between AI systems. Hermes must be self-auditing.

## Target

Owner interaction ≤ 5 minutes per day.

## ONE Daily Report: Eagle Eye Daily Review

Cron: `154d0c4e4f81` (08:00 daily, weixin)
Script: `review_package.py` → AI consolidates into 4 sections

| Section | Contents |
|---------|----------|
| System Health | Gateway, proxy, Alpaca API, disk, last cron run |
| Trade Summary | Positions, P&L, executions, candidates |
| Risk Summary | Drawdown, stop coverage, sector exposure, violations |
| Action Required | 0 = no owner action needed |

Format: ≤20 lines. No full holdings, no scanner raw data, no buy/sell suggestions.

## Silent Unless Action Required

WeChat notifications ONLY for:

| Trigger | Threshold |
|---------|-----------|
| EMERGENCY_STOP | Activated |
| SYSTEM_OFFLINE | > 2 hours |
| MISSED_AI_DECISION | ≥ 2 consecutive cycles |
| DRAWDOWN | > 12% |
| POLICY_VIOLATION | Any hard constraint breach |

Everything else → local storage only.

## WeChat Message Budget

| Category | Max/Day |
|----------|:-------:|
| Daily Review | 1 |
| Critical Alert | 0-3 |
| **Total** | **≤ 4** |

## Cron Delivery Assignment (2026-06-19)

| Job | Delivery | Notes |
|-----|:--------:|-------|
| Eagle Eye Daily Review | weixin | Only WeChat-allowed job |
| 美股AI决策 | local | Trades execute silently |
| GARP扫描 | local | |
| 盘后扫描 | local | |
| 持仓卡片 | local | |
| 凯利计算 | local | |
| 市场事件/速报/环境 | local | |
| 参数校准/合规审计 | local | |
| Heartbeat/Receipt/Relay | paused | Permanently off |

---

*Protect Owner Capital. Protect Owner Attention.*
