# Data Source Reliability Matrix

Last verified: 2026-05-21. EastMoney status is time-sensitive — re-check before relying on it.

## Current Status

| Source | Market | Endpoint | Free? | Reliability | Notes |
|--------|--------|----------|:-----:|:-----------:|-------|
| Sina Finance | A股 实时 | `hq.sinajs.cn/list=sh/szCODE` | ✅ | ★★★★★ | Always works, GBK encoding |
| Sina Finance | A股 日K | `money.finance.sina.com.cn/.../getKLineData` | ✅ | ★★★★ | Reliable fallback when EastMoney down |
| Sina Finance | 美股 实时 | `hq.sinajs.cn/list=usSYM` | ✅ | ★★ | Only during US market hours; returns empty otherwise |
| EastMoney push2 | A股 实时 | `push2.eastmoney.com/api/qt/stock/get` | ✅ | ★★ | Frequent 502 Bad Gateway outages |
| EastMoney push2his | A股 日K | `push2his.eastmoney.com/api/qt/stock/kline/get` | ✅ | ★★ | SSL drops during trading hours; 502 downtime |
| EastMoney push2 | 美股 | `secid=105.SYM` or `106.SYM` | ✅ | ★ | 502 + SSL issues → **DEPRECATED for US stocks** |
| Alpaca IEX | 美股 日K | `data.alpaca.markets/v2/stocks/SYM/bars?timeframe=1Day&feed=iex&start=...&end=...` | ✅ (free tier) | ★★★★ | 60+ bars reliably. Use explicit start/end dates |
| Alpaca IEX | 美股 实时 | `.../SYM/quotes/latest?feed=iex` | ✅ (free tier) | ★★★★ | Ask/bid prices |
| Alpaca | 美股 小时K | `.../bars?timeframe=1Hour&limit=30` | ✅ (free tier) | ★ | **4 bars only** (useless). Date range returns 403 |
| Alpaca | 美股 交易 | `paper-api.alpaca.markets/v2/...` | ✅ (free tier) | ★★★★★ | Paper trading, $100K virtual |

## Recommended Data Source Strategy

### A-shares
```
Primary: Sina Finance (hq.sinajs.cn)
Backup:  EastMoney push2/push2his (use Sina kline API as additional backup)
```

### US Stocks — Screening
```
Primary: Alpaca IEX daily bars (timeframe=1Day&feed=iex&start=...&end=...)
Backup:  None (EastMoney US deprecated)
```

### US Stocks — Trading
```
Primary: Alpaca quotes (latest?feed=iex) for real-time prices
Primary: Alpaca paper-api for orders/account
```

## EastMoney Failure Modes

1. **502 Bad Gateway** — Server-side outage. `push2.eastmoney.com` returns nginx 502. Duration: minutes to hours. No fix from client side.
2. **SSL connection drops** — `RemoteDisconnected` / `unexpected eof while reading`. High during US trading hours (21:00-05:00 BJT). EastMoney CDN terminates connections from certain IP ranges.
3. **Empty response** — HTTP 200 but no data. Rare, usually a partial outage.

## Sina K-line API Quirk

Symbol must be **lowercase**: `sz000657` not `SZ000657`. Using uppercase returns empty data with no error. This is a silent failure mode.

The `scale` parameter: 240 = daily, 60 = 60-min, 30 = 30-min.
Data is ordered oldest-first (chronological) — do NOT reverse for calculation.
The `day` field is the date key (not `date`).
Built-in MA fields (ma_price5, ma_price10, etc.) are available but `change_percent` is always 0.00 — calculate manually.
