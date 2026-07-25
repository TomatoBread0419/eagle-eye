# Eagle Eye Daily Review Package — 格式规范

**生成时间**: 2026-06-19
**用户要求**: "每天生成一次这个就够了" — 自动化为 cron，不要手动每次跑

## Cron 配置

- **Job**: Eagle Eye 日报
- **Schedule**: `0 8 * * *` (每天 BJT 08:00)
- **Script**: `~/.hermes/scripts/review_package.py`
- **Model**: deepseek-v4-flash
- **Deliver**: weixin

## 8个Section（固定格式，不可增减）

### 1. Portfolio Snapshot
- 净值/现金/仓位/持仓数
- 每只持仓: symbol/shares/mkt_value/cost_basis/pnl%/sector/weight%/stop%/signal

### 2. Sector Distribution
- 每个板块: weight%/target%/gap%/status(UNDERWEIGHT/NORMAL/OVERWEIGHT)/holdings

### 3. Market Environment
- Regime/VIX/DXY/Yield Spread/Breadth/Advancers/Decliners/New Highs/Lows/Days to FOMC

### 4. Candidate Universe (Top 10)
- 完整字段: symbol/sector/score/RSI/vol_signal/MACD/RS_vs_SPY/ATR%/Vol20d/Kelly%/Win%/Leader

### 5. Risk Audit
- Stop Covered/Stop%/Ghost/Unprotected/Blacklisted/Signal Decay

### 6. Pending Orders
- Symbol/Side/Qty/Type/Created/Status

### 7. Policy Status
- Exposure≤85%/Single≤20%/Min3Sectors/NoNaked/NoGhost/FOMC Rules — PASS/FAIL

### 8. Dashboard — Decision Rationale
- Market Context (regime/FOMC/VIX解读)
- Sector View (underweight/overweight)
- Event Context (critical_alerts + sector_bias)
- Current AI Posture (mode/capital/stop_coverage/pending/blacklist)

## 数据源

| Section | 数据源 |
|---------|--------|
| Portfolio | Alpaca API `/v2/account`, `/v2/positions`, `/v2/orders` |
| Sector | 持仓 × SECTOR_MAP + TARGET_ALLOC |
| Market | `market_env.json` |
| Candidates | `us_watchlist.json` (buy_candidates + kelly_allocations) + `us_screener_log.json` (完整字段) |
| Risk | Alpaca API (stop orders) + `us_risk_state.json` + `signal_decay.json` + `us_recent_stops.json` |
| Orders | Alpaca API `/v2/orders?status=open` |
| Policy | 计算值 + 配置常量 |
| Dashboard | 以上全部 + critical_alerts + sector_bias |

## 禁止输出

- BUY / SELL / HOLD
- Trade Intent
- Actions Required
- Recommendation
- Opinion

## 脚本位置

`~/.hermes/scripts/review_package.py` — 生成完整 markdown 报告
