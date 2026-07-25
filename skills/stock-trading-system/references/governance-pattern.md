# Eagle Eye Governance Pattern

**Established:** 2026-06-18
**Scope:** How new constraints and rules are introduced into Eagle Eye.

## The Pattern

This session established a repeatable governance workflow:

```
1. POLICY DOCUMENT
   Owner defines constraints in auto_approval_policy.md
   → Clear rules, no implementation details

2. CODE GUARDS
   Developer implements hard enforcement
   → policy_validator.py (PASS/REJECT, no AI, no suggestions)

3. DRY RUN VALIDATION
   Mock broker, known inputs → expected outputs
   → 4/4 PASS gate before production

4. SINGLE CHOKE POINT
   Wire guards into the ONE execution path
   → execute_mode() is the only way orders reach Alpaca
   → Impossible to bypass
```

## Key Principles

- **Policy before code.** Don't implement constraints that haven't been written down and approved.
- **PASS/REJECT only.** Validators never generate trade suggestions. They say yes or no.
- **No AI in the guard path.** Policy enforcement is deterministic rule evaluation, never LLM judgment.
- **Single choke point.** All orders flow through `execute_mode()`. Guard it once, protect everything.
- **Mock first.** Dry run with fake broker before any real money moves.

## Anti-Patterns

- Writing policy in Memory/SKILL.md without code enforcement → "LLM self-discipline" fails
- Implementing constraints in multiple code paths → bypass risk
- Letting validators suggest alternatives → scope creep, policy drift
- Deploying without dry run → production surprises

## Files in Play

| File | Role |
|------|------|
| `auto_approval_policy.md` | Owner-defined constraints |
| `policy_validator.py` | Code-level PASS/REJECT gates |
| `candidate_tracker.py` | Multi-cycle scan history |
| `trade_executor.py::execute_mode()` | Single choke point |
| `notification.py` | Spool-based alert relay |
