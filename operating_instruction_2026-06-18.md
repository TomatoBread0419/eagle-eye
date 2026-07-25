# Eagle Eye Operating Instruction — 2026-06-18

**Issued:** 2026-06-18 15:10 BJT
**Effective:** 2026-06-18 21:10 BJT (next cron cycle)
**Policy:** Auto-Approval Policy v1.1
**Mode:** Full autonomous — zero owner intervention

---

## 1. No Manual Override

- Owner does not place orders.
- Owner does not pick candidates.
- Owner does not create exceptions.

System runs on its own authority under v1.1.

---

## 2. Pipeline Integrity

```
Scan → Portfolio Impact → Trade Decision → Execution
```

**Forbidden:** Dashboard → Manual Override → Trade

All trades originate from the automated pipeline only.

---

## 3. §6.1 Seed Position — Auto-Activation

The Structural Exemption is live. When Active Sectors < 4:

- System selects the candidate.
- System writes the full reasoning chain.
- System generates the OrderIntent.
- System executes.

**Reasoning chain required in Dashboard:**

```
§6.1 TRIGGER: Active Sectors = N (Critical < 4)
CANDIDATE:   SYM (sector)
WHY:         Gap Sector = X | RSI = Y | Kelly = Z% | No contradictory signals
WHY NOT:     [other qualified candidate] — [reason not selected]
INITIAL:     ≤5% Seed Position
RESULT:      Active Sectors → N+1
EXEMPTION:   [Active/Deactivated — if ≥4 reached]
```

---

## 4. Anti-KPI Gaming

Diversification is an **outcome**, not a goal.

- Do not trade to make a number green.
- Do not force a Seed Position if no candidate genuinely qualifies.
- The exemption exists to break deadlocks, not to manufacture diversification.

---

## 5. Review Report (Tomorrow)

A separate report answering only:

1. Did §6.1 trigger?
2. Was a Seed Position opened?
3. Active Sectors: X → Y?
4. Largest Sector: improved or unchanged?
5. Any policy violation?

---

## 6. Tonight's Cron

| Time (BJT) | Job | Action |
|-----------|-----|--------|
| 20:30 | 市场环境采集 | Data collection |
| 21:00 | 信号衰减检测 | Data collection |
| 21:10 | 美股AI决策 | **Full autonomous cycle** |

System proceeds without owner input.
