# Review Package Data Sources

## Cross-referencing watchlist data

The `us_watchlist.json` has three candidate representations:
- `buy_candidates`: **list of strings** (symbol names only, no detail)
- `all_ranked`: list of dicts with `{symbol, score, price, sector, earnings_days}`
- `kelly_allocations`: dict of symbol → `{kelly_pct, win_prob, odds, score}`

The `us_screener_log.json` has the full scan results:
- `results`: list of dicts with all 13 dimensions (RSI, MACD, volume signals, RS vs SPY, ATR, etc.)
- `errors`: list of symbols that failed to scan

To get complete candidate data, cross-reference `buy_candidates` (or `all_ranked`) with `us_screener_log.json` results by symbol.

## Data sources by section

| Section | Primary Source | Fallback |
|---------|---------------|----------|
| Portfolio Snapshot | Alpaca `/v2/account` + `/v2/positions` | — |
| Sector Distribution | SECTOR_MAP + positions | — |
| Market Environment | `market_env.json` (macro + breadth) | — |
| FOMC | Hardcoded calendar in `review_package.py` | — |
| Candidate Universe | `us_watchlist.json` + `us_screener_log.json` | cross-ref by symbol |
| Kelly allocations | `us_watchlist.json` → `kelly_allocations` | — |
| Risk Audit | Alpaca `/v2/orders?status=open` + `us_risk_state.json` | — |
| Pending Orders | Alpaca `/v2/orders?status=open` | — |
| Signal Decay | `signal_decay.json` → `alerts` | — |
| Recent Stops | `us_recent_stops.json` | — |
| Critical Alerts | `us_watchlist.json` → `critical_alerts` | — |
| Sector Bias | `us_watchlist.json` → `sector_bias` | — |

## Formatting Rules

- Never include BUY / SELL / HOLD / Trade Intent / Actions Required / Recommendation / Opinion
- The Dashboard section explains the "why" behind the AI's posture using regime/VIX/FOMC/sector gaps/event context
- All numbers are raw — no rounding up/down of P&L, weights, or scores
