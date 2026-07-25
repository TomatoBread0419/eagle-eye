# Cron Script Debugging: Output Buffering & Timeout

## Output Buffering (Python → no TTY → silent)

**Symptom:** Script runs (process alive) but produces **zero output**, even after 60s.

**Root cause:** Python's stdout is **line-buffered** when connected to a TTY (interactive terminal), but **fully buffered** (typically 8KB) when connected to a pipe — which is what cron does. No output appears until the buffer fills or the script exits.

**Note:** `print(..., flush=True)` only flushes THAT print call. If earlier prints (headers, initial progress lines) don't use `flush=True`, they're stuck in the buffer until enough data is accumulated.

**Fixes (most reliable first):**

```bash
# Option 1: -u flag (unbuffered binary stdout/stderr) — ALWAYS WORKS
python3 -u script.py

# Option 2: PYTHONUNBUFFERED=1 env var — same effect
PYTHONUNBUFFERED=1 python3 script.py

# Option 3: In-code: call sys.stdout.reconfigure(line_buffering=True) at the top
import sys
sys.stdout.reconfigure(line_buffering=True)
```

**For cron scripts specifically:**
- Hermes cron framework does NOT inject `-u` for you
- Even `flush=True` on every print is unreliable (initial/middle lines before first flush=True can be buffered)
- **Rule of thumb:** Always debug cron script failures by running with `-u` first

## Script Timeout

**Default:** 120s (hardcoded in `cron/scheduler.py:_DEFAULT_SCRIPT_TIMEOUT`)

**Config path:** `cron.script_timeout_seconds` in `~/.hermes/config.yaml`

**Resolution chain:** `_SCRIPT_TIMEOUT` module constant → `HERMES_CRON_SCRIPT_TIMEOUT` env var → `config.yaml` `cron.script_timeout_seconds` → default 120s

**When timeout fires:** The script process is killed, and the cron system returns `"Script timed out after {N}s: {path}"`. Note: `last_run_at` / `last_status` in cron state may NOT update after a timeout — the job appears as if it never ran.

**Verification:**
```bash
# Check if timeout was hit
grep "timeout\|timed out" ~/.hermes/logs/agent.log | tail -5
```

**For stock screener:** 57 stocks × 2 API calls × ~1s each + 0.15s sleep ≈ 150s minimum. Safe setting: 300s.
