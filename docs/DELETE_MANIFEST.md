# DELETE_MANIFEST.md — Eagle Eye Stock Trading System

**Generated:** 2026-06-19
**Source:** SIMPLIFICATION_PLAN.md + SYSTEM_INVENTORY.md
**Purpose:** Exhaustive list of every item proposed for removal, with risk assessment
**Owner Rule:** "If this component disappears, can Owner lose money?" — YES = NEVER DELETE
**System Context:** US stock trading via Alpaca paper trading on Android/Termux

---

## SECTION 1: SCRIPTS TO REMOVE (20 items)

### 1.1 Legacy V5 Scripts → ARCHIVE

| # | Name | Type | Location | Why Remove | Risk | Rollback | Owner Rule |
|---|------|------|----------|------------|------|----------|------------|
| 1 | macro_context.py | script | ~/.hermes/scripts/ | V5 fully merged into market_env.py V6. Only read as fallback by us_report.py which already prefers market_env.json. Fallback path removable after 1 week validation. | LOW | YES | SAFE — V6 produces identical output |
| 2 | market_breadth.py | script | ~/.hermes/scripts/ | V5 fully merged into market_env.py V6. market_breadth.json deprecated per DEPENDENCY_MAP. | LOW | YES | SAFE — V6 is superset |
| 3 | us_trader_v6.py | script | ~/.hermes/scripts/ | V7.1 LTS active via us_trader.py → eagle_eye/execution/trade_executor.py. V6 has no active callers (1,674 lines, monolithic). | LOW | YES | SAFE — V7 OMS is production-tested |
| 4 | cn_auto_trader.py | script | ~/.hermes/scripts/ | CN/HK market not in active US trading pipeline. Owner Mandate focuses on US positions. No cron jobs reference it. | LOW | YES | SAFE — CN market, orthogonal to US system |
| 5 | cn_auto_trader.py | script | ~/stock_trader/ | Exact duplicate of hermes version. Both locations contain same script (544 vs 543 lines). | NONE | YES | SAFE — Delete copy, archive original |
| 6 | cron_add_two.py | script | ~/.hermes/scripts/ | One-time script to add 2 cron jobs. Already executed (2026-06-18). Purpose fulfilled. | NONE | YES | SAFE — Already executed, no ongoing function |

### 1.2 Duplicate/Overlapping Scripts → MERGE or ARCHIVE

| # | Name | Type | Location | Why Remove | Risk | Rollback | Owner Rule |
|---|------|------|----------|------------|------|----------|------------|
| 7 | us_common.py | script | ~/.hermes/scripts/ | eagle_eye/core/http.py + eagle_eye/broker/alpaca_client.py provide same functionality in V7. Only us_screener.py still uses it. **PREREQUISITE: Migrate us_screener imports BEFORE archiving.** | MEDIUM | YES | SAFE after migration — us_screener.py must be migrated to eagle_eye HTTP first. If removed prematurely, GARP scanner breaks → no watchlist → degraded AI decisions. |
| 8 | generate_audit_reports.py | script | ~/.hermes/scripts/ | eagle_eye/ops/audit_engine.py provides programmatic audit. Markdown reports are human-readable copies of data already in JSONs. No automated consumer. | LOW | YES | SAFE — Audit data remains in JSONs; reports are convenience, not guards |
| 9 | cron_audit.py | script | ~/stock_trader/ | Duplicate of audit_stops.py (58 lines). Both check same Alpaca stops. Merge into single script or fold into audit_engine.py. | NONE | YES | SAFE — Simple duplicate elimination |
| 10 | cron_portfolio.py | script | ~/stock_trader/ | us_portfolio.py (366 lines) already generates full portfolio snapshot. This is a 59-line stripped-down duplicate. | LOW | YES | SAFE — us_portfolio.py is superset |
| 11 | verify_hard_constraints.py | script | ~/stock_trader/ | eagle_eye/risk/policy_validator.py enforces same constraints at runtime. Defense-in-depth but not in critical path. **ACTION: Move to ~/stock_trader/tools/, not delete.** | MEDIUM | YES | SAFE if moved to tools/ — policy_validator enforces same 3 hard constraints. Keep as on-demand verification tool. |

### 1.3 Stock Trader Scripts → MIGRATE to eagle_eye or ARCHIVE

| # | Name | Type | Location | Why Remove | Risk | Rollback | Owner Rule |
|---|------|------|----------|------------|------|----------|------------|
| 12 | config.py | script | ~/stock_trader/ | eagle_eye/core/config.py (296 lines) is the V7 equivalent. Only 4 scripts still import stock_trader config.py. | LOW | YES | SAFE — Migrate imports to eagle_eye config first |
| 13 | indicators.py | script | ~/stock_trader/ | eagle_eye/strategy/indicator_engine.py (257 lines) is V7 equivalent. Same indicator set. | LOW | YES | SAFE — Verify output parity, then archive |
| 14 | trading.py | script | ~/stock_trader/ | eagle_eye/broker/alpaca_client.py + eagle_eye/execution/trade_executor.py replace this entirely. V7 OMS is production-tested. | LOW | YES | SAFE — V7 execution path is active and tested |
| 15 | market_data.py | script | ~/stock_trader/ | Sina/Eastmoney CN market data. US data path is Alpaca bars API. CN data only needed for CN auto trader (being archived). | LOW | YES | SAFE — US system uses Alpaca exclusively |
| 16 | audit_stops.py | script | ~/stock_trader/ | Merging stop audit logic into eagle_eye/ops/audit_engine.py. Simple merge, 58 lines. | NONE | YES | SAFE — Logic absorbed into canonical audit engine |
| 17 | run_google_searches.py | script | ~/stock_trader/ | market_news.py (hermes) + market-event-monitor skill already provide Google News RSS search. Duplicate capability. | LOW | YES | SAFE — Active search via market_news.py + skill |

### 1.4 Notification Scripts → DELETE (V3 Obsoleted)

| # | Name | Type | Location | Why Remove | Risk | Rollback | Owner Rule |
|---|------|------|----------|------------|------|----------|------------|
| 18 | ops_notify_relay.py | script | ~/.hermes/scripts/ | Every-minute spool reader. WeChat Push Policy V3 uses direct delivery, not spool. Only 20 lines. | LOW | YES | SAFE — V3 direct delivery replaced spool system |
| 19 | ops_scheduler_receipt.py | script | ~/.hermes/scripts/ | Every-5-min failure alerts. Redundant — Hermes cron already reports errors directly. V3 blocks its WeChat output anyway. | LOW | YES | SAFE — Hermes cron error reporting is active |

### 1.5 Orphaned Scripts → DELETE (Cron Job Removed)

| # | Name | Type | Location | Why Remove | Risk | Rollback | Owner Rule |
|---|------|------|----------|------------|------|----------|------------|
| 20 | cron_watchdog.py | script | ~/.hermes/scripts/ | Cron交付监控 cron job (5bbde6a44f31) is being deleted. This script was its sole caller. eagle_heartbeat.py covers health monitoring. | LOW | YES | SAFE — eagle_heartbeat.py provides health monitoring |

**Section 1 Total: 20 scripts (~6,432 lines)**

---

## SECTION 2: CRON JOBS TO REMOVE (12 items)

### 2.1 Paused Jobs → DELETE (6 jobs)

| # | Job ID | Name | Type | Why Remove | Risk | Rollback | Owner Rule |
|---|--------|------|------|------------|------|----------|------------|
| 1 | d2378848e547 | 港股盘中事件监控 | cron | Paused due to connection errors. CN/HK market monitoring not in US trading pipeline. | LOW | YES | SAFE — CN/HK market orthogonal to US system |
| 2 | 5bbde6a44f31 | Cron交付监控 | cron | Paused. Every-5-min delivery check is overhead for monitoring monitors. eagle_heartbeat.py covers health. | LOW | YES | SAFE — Redundant with heartbeat system |
| 3 | 31bbb6eeb546 | 信号衰减检测 | cron | Paused. Signal decay already checked within AI decision cycle (us_report.py reads signal_decay.json). | LOW | YES | SAFE — Covered by main AI pipeline |
| 4 | 8bce957367ec | Eagle Eye Heartbeat | cron | Paused. Health check 4x/day delivers to WeChat but V3 blocks it. Replace with single daily health check. | LOW | YES | SAFE — V3 policy blocks output; eagle_heartbeat.py stays as script |
| 5 | f185a347cd9f | Ops Notification Relay | cron | Paused. Every-minute spool reader. WeChat Push Policy V3 uses direct delivery, not spool. | LOW | YES | SAFE — V3 made spool delivery obsolete |
| 6 | 8290d4140d57 | Scheduler Receipt | cron | Paused. Every-5-min failure alerts. Redundant with main cron error reporting in Hermes. | LOW | YES | SAFE — Hermes cron already reports errors directly |

### 2.2 Active Jobs → MERGE (6 jobs consolidated into 3)

| # | Job ID | Name | Type | Why Remove | Risk | Rollback | Owner Rule |
|---|--------|------|------|------------|------|----------|------------|
| 7 | d3f17ab4ca86 | 午间速报 | cron | Merged into 早间速报 → single "市场速报" at 09:00. Midday briefing adds noise, not signal. Owner reads morning briefing. | LOW | YES | SAFE — Morning scan covers pre-market + Asia close |
| 8 | 147cc7f5088a | 早间速报 | cron | Becomes consolidated "市场速报" job. Original job replaced by merged version. | LOW | YES | SAFE — Functionality preserved in new consolidated job |
| 9 | 156e40a9c859 | 市场环境采集 | cron | Merged into market-event-monitor schedule. Both use same data pipeline. | LOW | YES | SAFE — Same data pipeline, fewer invocations |
| 10 | d65b06eddcad | 市场事件监控 | cron | Becomes consolidated "市场事件+环境" at key times (09:00, 15:00, 20:30). | LOW | YES | SAFE — Functionality preserved in new consolidated job |
| 11 | 1da0dc5f927c | 参数自校准 | cron | Becomes consolidated "周末维护" (Sat 06:00). Runs first, then audit validates. | LOW | YES | SAFE — No dependency conflict; sequential execution |
| 12 | 8604888631f4 | 规则合规审计 | cron | Merged into "周末维护" (Sat 06:00). Both Saturday morning, both local-only, both read/write same JSON directory. | LOW | YES | SAFE — Calibrator runs first, audit validates after |

**Section 2 Total: 12 cron jobs (6 deleted, 6 consolidated into 3 new)**

---

## SECTION 3: CONFIG FILES TO ARCHIVE (14 items)

### 3.1 Legacy/Duplicate JSON Files → ARCHIVE

| # | Name | Type | Location | Why Remove | Risk | Rollback | Owner Rule |
|---|------|------|----------|------------|------|----------|------------|
| 1 | macro_context.json | config | ~/stock_trader/ | V5 legacy output. market_env.json V6 is canonical. us_report.py reads market_env first. Fallback path should be removed from us_report.py. | LOW | YES | SAFE — market_env.json V6 is sole source of truth |
| 2 | market_breadth.json | config | ~/stock_trader/ | V5 legacy output. Same data in market_env.json. Deprecated per DEPENDENCY_MAP. | LOW | YES | SAFE — Data preserved in market_env.json |
| 3 | cn_risk_state.json | config | ~/stock_trader/ | CN market risk state. No US trading pipeline references it. Last updated 2026-05-15. | LOW | YES | SAFE — CN market orthogonal to US system |
| 4 | cn_risk_state.bak.json | config | ~/stock_trader/ | CN market risk state backup. Last updated 2026-05-14. | LOW | YES | SAFE — CN market backup, no US references |
| 5 | cn_signal_latest.json | config | ~/stock_trader/ | CN market signal. No US trading references. Last updated 2026-05-15. | LOW | YES | SAFE — CN market orthogonal to US system |
| 6 | us_signal_latest.json | config | ~/stock_trader/ | Last updated 2026-06-08 (11+ days stale). signal_decay.json is the active equivalent. | LOW | YES | SAFE — Verify no reader, then archive |

### 3.2 Vanity/Non-Actionable Data → ARCHIVE

| # | Name | Type | Location | Why Remove | Risk | Rollback | Owner Rule |
|---|------|------|----------|------------|------|----------|------------|
| 7 | behavior_fingerprint.json | config | ~/stock_trader/ | Output of behavior_fingerprint.py. No readers in any guard or decision path. Vanity data (1,620 bytes). | LOW | YES | SAFE — No guard or trade decision reads it |
| 8 | market_scan_raw_latest.json | config | ~/stock_trader/ | Raw scan data from 2026-06-04. 15+ days stale. Intermediate data, not consumed by any pipeline. | LOW | YES | SAFE — Stale intermediate data |
| 9 | compliance_report.json | config | ~/stock_trader/ | Weekly compliance audit output. Reviewed manually on Saturdays. No automated action. Audit data is in source code. | LOW | YES | SAFE — Human convenience only; source of truth is code |
| 10 | us_screener_log.json | config | ~/stock_trader/ | 64KB scanner log. Only consumer is calibrator.py (reads score distributions). Calibrator can read last N entries instead. | LOW | YES | SAFE — Calibrator can use subset; not in critical path |

### 3.3 Data Directories → ARCHIVE or DELETE

| # | Name | Type | Location | Why Remove | Risk | Rollback | Owner Rule |
|---|------|------|----------|------------|------|----------|------------|
| 11 | backup_json_20260618_100945/ (15 files) | config | ~/stock_trader/ | Backup snapshot from 2026-06-18. Not active data. Move to ~/stock_trader/archives/. | LOW | YES | SAFE — Historical snapshot, not consumed |
| 12 | scan_work/ (8 files) | config | ~/stock_trader/ | Work-in-progress scan JSONs. Stale intermediate files. Move to archives. | LOW | YES | SAFE — Intermediate work files |
| 13 | notifications/spool/processed/*.json (4 files) | config | ~/stock_trader/ | Historical processed notification data. V3 uses direct delivery; spool history is dead data. | LOW | YES | SAFE — Notification history, no system dependency |
| 14 | cache/smoke_test.json | config | ~/stock_trader/ | 2-byte smoke test artifact. Not consumed by any pipeline. | LOW | YES | SAFE — Test artifact only |

**Section 3 Total: 14 config items (~77,500 bytes + 27 files in directories)**

---

## SECTION 4: EAGLE EYE MODULES TO CONSOLIDATE (12 items)

### 4.1 Duplicate Ops Modules → MERGE or DELETE

| # | Name | Type | Location | Why Remove | Risk | Rollback | Owner Rule |
|---|------|------|----------|------------|------|----------|------------|
| 1 | watchdog.py | module | eagle_eye/ops/ | eagle_heartbeat.py + cron_watchdog.py provide same monitoring. 243 lines of duplicate. Merge into ops/monitor.py. | LOW | YES | SAFE — eagle_heartbeat.py is most-tested health monitor |
| 2 | health_check.py | module | eagle_eye/ops/ | Duplicate of watchdog. eagle_heartbeat.py does identical Alpaca ping + DNS check. 260 lines. Merge into ops/monitor.py. | LOW | YES | SAFE — eagle_heartbeat.py covers all health checks |
| 3 | scheduler.py | module | eagle_eye/ops/ | Hermes cron already handles all scheduling. Internal scheduler adds a layer nobody queries. 322 lines. | LOW | YES | SAFE — All scheduling via Hermes cron; no internal callers |
| 4 | behavior_fingerprint.py | module | eagle_eye/ops/ | Vanity analysis. No trading decision reads fingerprints. No guard references it. 376 lines of "interesting insights." | LOW | YES | SAFE — Zero guards or decisions depend on fingerprints |
| 5 | shadow_mode.py | module | eagle_eye/ops/ | Development tool. Alpaca paper trading IS shadow mode. Double-shadow is redundant. 217 lines. | LOW | YES | SAFE — Paper trading already provides dry-run |
| 6 | emergency_stop.py | module | eagle_eye/ops/ | eagle_eye/risk/trading_lock.py (277 lines) provides identical lock functionality. Two implementations of "stop all trading." 323 lines. | LOW | YES | SAFE — trading_lock.py is simpler, in risk/ where it belongs. Both do same thing. |

### 4.2 Unused Strategy Modules → ARCHIVE

| # | Name | Type | Location | Why Remove | Risk | Rollback | Owner Rule |
|---|------|------|----------|------------|------|----------|------------|
| 7 | strategy/market_breadth.py | module | eagle_eye/strategy/ | Already merged into strategy/market_env.py (407 lines). V7 port is unused — V6 hermes script is active. 301 lines. | LOW | YES | SAFE — strategy/market_env.py is superset |
| 8 | strategy/signal_decay.py | module | eagle_eye/strategy/ | V6 us_signal_decay.py is the active script. V7 port has no active callers. 234 lines. Archive until full V7 migration. | LOW | YES | SAFE — V6 hermes script is active and tested |

### 4.3 Storage Modules → MERGE

| # | Name | Type | Location | Why Remove | Risk | Rollback | Owner Rule |
|---|------|------|----------|------------|------|----------|------------|
| 9 | storage/repositories.py | module | eagle_eye/storage/ | Abstract interface (30 lines). Only defines abstract class. Merge interface into repos/__init__.py. | LOW | YES | SAFE — Trivial merge; concrete repos unchanged |
| 10 | storage/repos/*.py (6 files) | module | eagle_eye/storage/repos/ | 6 tiny per-entity repository files (~180 lines total). Merge into single repos.py. | LOW | YES | SAFE — Same functionality, fewer files |
| 11 | storage/migrate.py | module | eagle_eye/storage/ | Run-once DB migration utility (340 lines). Not in any cron. Move to tools/ or archive. | LOW | YES | SAFE — One-time utility; keep as manual tool |

### 4.4 Portfolio Module → MERGE

| # | Name | Type | Location | Why Remove | Risk | Rollback | Owner Rule |
|---|------|------|----------|------------|------|----------|------------|
| 12 | allocation_engine.py | module | eagle_eye/portfolio/ | Simple sector allocation logic (123 lines). Can merge into portfolio_manager.py (379 lines). Pure function, easy to merge. | LOW | YES | SAFE — Pure function; portfolio_manager.py absorbs it |

**Section 4 Total: 12 modules (2,786 lines) — merge 5 into parents, archive 5, delete 2**

---

## OWNER RULE AUDIT

**Question applied to every item:** "If this component disappears, can Owner lose money?"

### Components That COULD Cause Money Loss If Removed Prematurely

| Item | Condition | Mitigation |
|------|-----------|------------|
| us_common.py (item 1.2#7) | If removed BEFORE us_screener.py migration, GARP scanner breaks → no watchlist → degraded AI trading decisions | Migrate us_screener imports to eagle_eye HTTP FIRST. Test thoroughly. |
| verify_hard_constraints.py (item 1.2#11) | If deleted (not moved), defense-in-depth safety net is lost. policy_validator.py handles constraints, but independent check is valuable. | MOVE to tools/, don't delete. Keep as on-demand verification. |
| emergency_stop.py (item 4.1#6) | If trading_lock.py has a bug, emergency_stop was the backup. Both do identical "stop all trading." | Verify trading_lock.py handles all emergency_stop.py scenarios before removing. |

### Items Marked NEVER DELETE

**NONE.** All 56 proposed removals have functional replacements in the active critical path. The core trading pipeline is untouched:

- Core execution: us_trader.py → trade_executor.py → order_manager.py → alpaca_client.py ✓ INTACT
- Risk guards: policy_validator.py, trading_lock.py, degraded_mode.py ✓ INTACT
- Position management: stop_loss_manager.py, take_profit_manager.py ✓ INTACT
- Data pipeline: market_env.py, us_kelly.py, calibrator.py ✓ INTACT
- AI decisions: us_report.py → AI model → us_trader.py ✓ INTACT

No component proposed for removal is a single point of failure in the money-impacting pipeline.

---

## SUMMARY

| Metric | Value |
|--------|-------|
| **Total items proposed for removal** | **56** |
| Scripts (Section 1) | 20 |
| Cron jobs (Section 2) | 12 |
| Config files (Section 3) | 14 |
| Eagle Eye modules (Section 4) | 12 |

### Risk Breakdown

| Risk Level | Count | Percentage |
|------------|-------|------------|
| NONE | 9 | 16% |
| LOW | 45 | 80% |
| MEDIUM | 2 | 4% |
| HIGH | 0 | 0% |
| NEVER DELETE | 0 | 0% |

### Rollback Coverage

| Rollback Available | Count | Percentage |
|--------------------|-------|------------|
| YES (archived or reversible) | 56 | 100% |
| NO (permanent loss) | 0 | 0% |

### Risk Notes

- **MEDIUM items (2):** us_common.py and verify_hard_constraints.py require migration/move before archival. Both have clear prerequisites documented above.
- **All items archived, not deleted.** Estimated restore time: <5 minutes per item.
- **Implementation order matters.** Follow SIMPLIFICATION_PLAN.md Phase 1-7 sequence to minimize risk. Phase 7 (validation) runs full trading cycle before declaring cleanup complete.
- **Weekend execution recommended** for Phase 4 (cron consolidation) to avoid disrupting live trading.

### Lines of Code Impact

| Category | Lines Removed |
|----------|---------------|
| Scripts (Section 1) | ~6,432 |
| Eagle Eye modules (Section 4) | ~2,786 |
| **Total code removed** | **~9,218** |
| **System total before** | **~19,996** |
| **Reduction** | **~46%** |

---

*End of DELETE_MANIFEST.md*
