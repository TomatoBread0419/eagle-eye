# Alpaca API China Network Patterns (2026-06-30)

## Endpoint Reliability Hierarchy

Not all Alpaca API endpoints have equal reliability from China. Observed pattern on 2026-06-30:

| Endpoint | Reliability | Notes |
|----------|:-----------:|-------|
| `/v2/clock` | ✅ OK (intermittent) | Simple GET, small response. Usually works after 1-3 retries. |
| `/v2/positions` | ✅ OK (intermittent) | Works when clock works. |
| `/v2/account` | ✅ OK (intermittent) | Same as positions. |
| `/v2/orders` | ✅ OK (intermittent) | GET works when positions work. DELETE may fail on first attempt. |
| `/v2/stocks/{sym}/trades/latest` | ❌ FAIL (consistent JSONDecodeError) | This endpoint consistently returns JSONDecodeError or SSLError from China. Connection succeeds but response body is truncated/corrupted. **Do not rely on this endpoint for price data.** Use `/v2/bars/{sym}/latest` or `/v2/assets/{sym}` instead. |
| `POST /v2/orders` | ✅ OK (when GET works) | Place order works when connectivity is stable. |

## Typical Failure Sequence

```
21:11 — GET /v2/clock → ✅ works (direct connection, lucky)
21:13 — GET /v2/orders → ❌ SSLError (same endpoint, different attempt)
21:13 — GET /v2/orders (retry) → ❌ ConnectTimeout 
21:19 — V7.1 --stops → ❌ SSL error on 3/3 retries → trading_lock activated
21:20 — GET /v2/orders (retry 5+) → ✅ works (luck)
21:30+ — GET /v2/stocks/{sym}/trades/latest → ❌ JSONDecodeError (5/5 retries)
```

## Recovery Strategy

1. **Retry up to 5 times with 10s backoff** before declaring endpoint unreachable
2. **Prefer batch endpoints** (`/v2/orders?status=open` returns all orders in one call) over per-symbol endpoints
3. **Use `/v2/clock` as connectivity canary**: if clock works, positions/orders should work after retry; if clock fails, assume all Alpaca APIs are down
4. **Avoid `/v2/stocks/{sym}/trades/latest`** — use `us_common.get_us_price(sym, key, secret)` which has built-in retry
5. **If --stops fails due to SSL**, run stop coverage audit manually via direct API calls (Python with 30s timeout, 5 retries)
6. **Do NOT force trades through an unreliable connection** — partial fills, double orders, or silent failures are worse than waiting for next cron cycle

## V7.1 Module Weakness

The V7.1 refactored modules (`eagle_eye/`) have stricter API failure handling:
- Trading lock activates after 4 consecutive API failures
- No SOCKS5 proxy fallback in the V7.1 HTTP module (the V6 `us_common.py` has `url_get()` with retry)
- This means in China network conditions, V7.1 --stops may prematurely lock trading when connectivity is merely intermittent, not dead

**Workaround**: If --stops fails with API errors but direct Python API calls work, proceed manually with stop coverage audit. The next cron cycle will retry --stops.
