# Auto-Approval Policy v1.1 — Summary

Full text: `~/stock_trader/auto_approval_policy.md`

## Core Principles

1. **Pipeline:** Scan → Portfolio Impact → Trade Decision → Execution (never skip)
2. **Sell discipline:** ≥2 triggers required. Single-indicator exits forbidden. Default: Reduce, not liquidate.
3. **No same-day liquidation:** Max reduction depends on position size (>10%→50%, 5-10%→66%, <5%→full). Stop loss execution exempt.
4. **Entry priority:** Fill gaps > reinforce active > open new > chase scores
5. **Hard constraints:** Position≤18%, Sector≤30%, ActiveSectors≥4(Min), Exposure≤90%
6. **Multi-cycle gate:** 2-3 consecutive scan cycles before full entry. Seed Position exemption (§6.1) for deadlock.
7. **Dashboard only:** No same-cycle trades. Actions Required = 0/1/2+. Only 5 categories counted.

## Active Sectors Thresholds

| Level | Count | Status |
|-------|-------|--------|
| Target | ≥6 | Green |
| Healthy | ≥5 | OK |
| Minimum | ≥4 | Baseline |
| Critical | <4 | Requires action |

## §6.1 Structural Exemption (Seed Position)

Activates when Active Sectors < 4. Allows ONE gap-sector candidate to enter as ≤5% placeholder.

Conditions (ALL must be true):
- Gap Sector (currently <3% allocation)
- RSI 40-70
- No contradictory signals
- Kelly ≤ 8%
- Initial position ≤ 5%

Seed = placeholder, not full build. Self-deactivates when Active Sectors ≥ 4.

## Actions Required — 5 Categories Only

| Category | Examples |
|----------|---------|
| Safety | Naked position, emergency stop triggered |
| Exposure | Active Sectors < 4, position > 18%, sector > 30% |
| Data | Scanner failure, API outage, stale data > 24h |
| Execution | Order stuck > 1 session, ghost orders |
| Portfolio(Critical) | Active Sectors < 4 |

NOT counted: Observation, Scheduled Review, Sector Gaps, In-Progress trades.

## Dashboard Required Sections

1. Portfolio Snapshot
2. Position Heatmap
3. Sector Map (with Active Sectors level)
4. Constraint Monitor
5. Stop Coverage
6. Seed Position Eligibility (§6.1)
7. §6.1 Reasoning Chain (if triggered)
8. Entry Candidates (§6 gate)
9. In Progress
10. Actions Required

Template: `templates/dashboard-v1.1.md`
