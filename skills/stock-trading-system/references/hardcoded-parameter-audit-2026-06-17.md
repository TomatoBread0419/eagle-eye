# Hardcoded Parameter Audit (2026-06-17)

## Finding
132 hardcoded parameters across 4 files. Most are "dead numbers" — set once, never calibrated from actual trading results. Same class of problem as the Kelly 11.6%: looks precise, actually arbitrary.

## File-by-File Breakdown

### ai_weight_config.json (68 parameters)
All 13-dimension scoring weights, thresholds, and bonuses.
- `score_weights`: ret_1m=0.55, ret_3m=0.28, ret_short=0.12 — momentum weighting
- `rsi_scoring`: thresholds 65-90, penalties -10 to -15
- `volatility_scoring`: 4 tiers with bonuses/penalties +3 to -3
- `volume_scoring`: bullish_confirmation=+3, divergence=-3, bearish=-2
- `macd_scoring`: golden_cross=+3, death_cross=-2
- `rs_vs_spy_scoring`: thresholds ±2-5%, bonuses ±1-2
- `sector_gap_scoring`: gap thresholds 1-3%, bonuses +2 to +5
- `yfinance_scoring`: beta/PE/dividend thresholds and bonuses
- `buy_filter`: RSI limits 65-78, min_momentum=3
- `defense_sector_bonus`: 11 sector bonuses (telecom/defense +5, ai -3)

**Status**: AI-tunable via `--update-weights`, but in practice rarely adjusted.

### us_trader.py (~15 parameters)
```python
DEFAULT_STOP_PCT = 0.08      # 8% default stop (when no volatility data)
DEFAULT_TRAIL_PCT = 0.08     # 8% trailing distance
TRAIL_STEP = 0.10            # Raise stop every 10% gain
TP_RSI_SELL = 80             # RSI > 80 sell 50%
TP_DRAWDOWN_PCT = 0.08       # 8% drawdown from high → sell all
DRAWDOWN_PAUSE = 0.12        # 12% account drawdown → stop buying
DRAWDOWN_CUT = 0.20          # 20% account drawdown → cut half
MIN_POSITION_UTIL = 0.40     # Minimum 40% equity in positions
MAX_CASH_RATIO = 0.60        # Maximum 60% cash
FORCE_BUY_SCORE = 1          # Score threshold when underweight
NORMAL_BUY_SCORE = 2         # Score threshold normal mode
```

### us_screener.py kelly function (~8 parameters)
```python
target_alloc = 0.95          # 95% total allocation
min_pct = 0.03               # 3% per position minimum
max_pct = 0.20               # 20% per position maximum
score_floor = -5             # Sigmoid clamp lower bound
score_ceil = 35              # Sigmoid clamp upper bound
sigmoid_k = 0.12             # Sigmoid steepness
sigmoid_midpoint = 12        # Sigmoid center
atr_to_odds_coeff = 0.3      # ATR% → odds linear coefficient
```

### us_kelly.py (~5 parameters)
```python
kelly_half = max(0.01, min(0.25, kelly_half))  # 1-25% range
kelly_full = max(0.01, min(0.50, kelly_full))   # 1-50% range
lookback_days = 90           # Trade history lookback
```

## Classification

| Category | Count | Should Be |
|----------|-------|-----------|
| Should vary with market state | ~15 | VIX/macro-driven |
| Should calibrate from history | ~70 | Rolling backtest |
| Should vary by stock characteristics | ~20 | Per-stock or per-cap-tier |
| Should adjust from performance feedback | ~10 | Outcome tracking |
| Actually fixed (OK) | ~17 | Keep as-is |

## Recommended Approach: Parameter Self-Calibration Module

### Phase 1: Outcome Database
Every scan→execute→outcome cycle produces data:
- What score did the stock have when we bought it?
- What was its ATR%?
- Did it hit stop-loss or take-profit?
- What was the actual holding period return?

Store in `~/stock_trader/trade_outcomes.json`:
```json
[{
  "symbol": "AMAT",
  "entry_date": "2026-06-10",
  "entry_score": 55,
  "entry_atr_pct": 6.1,
  "exit_date": "2026-06-15",
  "exit_reason": "take_profit_1",
  "return_pct": 22.3
}]
```

### Phase 2: Rolling Calibration (weekly)
- For sigmoid: bin all past trades by score bucket (0-5, 5-10, 10-15, ...) → calculate actual win rate per bucket → fit sigmoid
- For ATR→odds: bin by ATR bucket → calculate actual avg_win/avg_loss → fit linear
- For stop tiers: compare actual drawdowns vs triggered stops → adjust tiers
- For sector bonuses: track sector performance vs bonus assignments → recalibrate

### Phase 3: Auto-Apply
- Weekly calibration run writes updated parameters to `ai_weight_config.json`
- Human-readable diff logged to `~/stock_trader/calibration_log.json`
- AI reviews diff before applying (safety check)

### Key Design Decision
Parameters should be SMOOTH-adjusted, not snap-adjusted:
- New calibrated value = 70% old + 30% calibrated (exponential moving average)
- Prevents overfitting to recent outlier trades
- Minimum 30 data points per calibration bucket before adjusting
