# Cron Job Miss RCA Methodology

**Date:** 2026-06-19
**Context:** AI_DECISION job (a638e8d39d5d) missed 5 consecutive runs (21:10/22:10/23:10/00:10/01:10) while scheduler appeared alive.

## RCA Template — 4 Questions

When cron jobs miss scheduled runs, answer these 4 questions with evidence:

### Q1: Did the scheduler attempt to dispatch?

Check:
- `gateway.log` — last timestamped line before gap vs first after
- `errors.log` — same gap analysis
- `~/.hermes/cron/output/{job_id}/` — output file timestamps
- `jobs.json` → `last_run_at` vs expected schedule

Output: per-timeslot dispatched? yes/no

### Q2: If not dispatched, why?

Classification (pick one):
- A = scheduler loop didn't run (gateway process dead)
- B = scheduler loop ran but skipped job (grace window exceeded)
- C = dispatch succeeded but session not created
- D = session created but task didn't start
- E = task started but exited abnormally

Evidence required for each.

### Q3: Verify resource pressure hypothesis

Check for:
- OOM (`logcat | grep -i oom`)
- fork/spawn failed (grep logs)
- timeout errors
- resource unavailable

If no evidence: "correlation only, not proven causation"

### Q4: Catch-up behavior

Check scheduler source code (`cron/jobs.py` → `_compute_grace_seconds()`):
- Grace = min(period/2, 7200s), MIN_GRACE=120s
- Hourly job → 30min grace
- If missed > grace → fast-forward (skip), not catch-up
- `next_run_at` jumps to next future occurrence

## Evidence Sources

| Source | Path | What it shows |
|--------|------|---------------|
| gateway.log | `~/.hermes/logs/gateway.log` | Process lifecycle, adapter connections |
| errors.log | `~/.hermes/logs/errors.log` | Warnings/errors with timestamps |
| jobs.json | `~/.hermes/cron/jobs.json` | Per-job state (next_run_at, last_run_at) |
| cron output | `~/.hermes/cron/output/{job_id}/` | Execution output files |
| logcat | `logcat -d -t "MM-DD HH:MM:SS.000"` | Android-level process events |
| scheduler source | `~/.hermes/hermes-agent/cron/scheduler.py` | tick() logic, grace window |
| jobs source | `~/.hermes/hermes-agent/cron/jobs.py` | get_due_jobs(), advance_next_run() |

## Key Source Code Locations

- `scheduler.py` line 1857: `tick()` — main loop, acquires file lock, gets due jobs
- `scheduler.py` line 1901: `advance_next_run()` — called BEFORE execution (at-most-once)
- `jobs.py` line 344: `_compute_grace_seconds()` — grace = min(period/2, 7200)
- `jobs.py` line 993: `get_due_jobs()` — filters by next_run_at <= now
- `jobs.py` line 1005: `_get_due_jobs_locked()` — fast-forward logic for stale jobs
- `gateway/run.py` line 18794: `_start_cron_ticker()` — background thread, 60s interval

## Real Case: 2026-06-19 Gateway Death

**Root cause:** Android OS killed Termux process (APP_SCOUT_HANG at 01:38:36).
Gateway died ~21:06, restarted at 01:43:44 by user.
No OOM/fork/timeout evidence — silent OS-level kill.
5 missed runs exceeded 30min grace → all fast-forwarded to 02:10.

**Key insight:** `next_run_at` advancing while no output files exist = gateway was dead (not scheduler stuck). If scheduler were stuck, `next_run_at` would freeze.
