# Decision Journal — Why The Trading System Needs It

## The Gap (discovered 2026-06-01)

User asked: "看一下最近的买入和卖出都是基于什么推测而做出的决定"

**Result: cannot answer with ground truth.**

Investigated the codebase:
- `us_trader.py` — places orders, but no `reason` field written anywhere
- `market_event_scanner.py` — saves events, but events are not linked to specific buy/sell decisions
- `us_signal_latest.json` — has `buy_score` and `buy_reasons` (e.g. "均线多头"), but only for the *current* scan, not the one at the time of the order
- Alpaca order API only stores `filled_avg_price` and `qty` — no thesis field
- `us_risk_state.json` has `highest` and `trail_trigger` but not "why we entered"

**Historical snapshot problem:** `market_events_latest.json` is overwritten each scan. On 2026-06-01 it contains only the *current* event snapshot — the events from May 27-28 (when most positions were opened) are gone.

## What This Means in Practice

When user asks "why did I buy INTC at $117.29 on May 27?":
- Today (June 1) the LLM has to *guess* — perhaps "NVDA momentum, sector rotation, MA20 crossover"
- But that's rationalization, not fact
- The actual decision rationale (event signals, score, free-text reasoning) was ephemeral in the LLM context and never persisted

## The Required Fix (proposed, not yet implemented)

**Every buy/sell order must write a `decision_journal` entry to disk at the moment of decision, BEFORE the order is placed:**

```json
{
  "ts": "2026-05-27T13:32:00+08:00",
  "side": "buy",
  "symbol": "IBM",
  "qty": 5,
  "price_target": 253.45,
  "thesis": "AI enterprise spend accelerating; IBM mainframe + Watson AI beat consensus; RSI 54 (not overbought); MA20 > MA50 golden cross 2 days ago",
  "event_signals": [
    {"source": "GoogleNews", "title": "IBM Q1 revenue beats on AI services", "ts": "2026-05-26"},
    {"source": "SogouWeixin", "title": "IBM watsonx 签约 3 家中字头", "ts": "2026-05-27"}
  ],
  "buy_score": 2,
  "screener_rank": 4,
  "macro_context": "Fed pause expected, semiconductor export restrictions easing, Trump China visit bullish for tech",
  "alternatives_considered": ["ORCL (passed on, already held)", "ACN (passed on, no clear catalyst)"],
  "risk": "5% hard stop at $240.78, 5% trailing stop active"
}
```

**Storage:** `stock_trader/decision_journal/YYYY-MM-DD.jsonl` (one JSON per line, append-only).

## Why This Matters

1. **Self-review loops** — when a position goes wrong, the user can ask "what did we believe when we entered?" and the answer is on disk, not reconstructed
2. **Pattern detection** — after 100 trades, we can see which *types* of theses correlated with winners vs losers (e.g. "AI enterprise theses win 70% of the time, macro-event theses win 40%")
3. **Anti-fabrication** — without a journal, every "why" answer the LLM gives is hallucination. The user already discovered this (2026-06-01). Future sessions will hit it again
4. **Audit trail** — for tax purposes, having a written rationale at decision time is useful

## Implementation Priority

Medium-high. The skill should treat the absence of decision journal as a known limitation and *not* promise to answer "why did I buy X" until the journal is built. Existing order history can be retroactively annotated by the user manually, but going forward, every new order needs the field.

## When to Reference This File

- User asks "why did I [buy|sell] [symbol]?"
- User wants to review trade history with thesis
- The agent is about to make a claim about historical decision rationale
- The screener is being tuned and we need to know which theses correlate with winners

## Related

- `us_risk_state.json` — runtime state (highest price, stop triggers)
- `us_signal_latest.json` — current scan snapshot
- `market_events_latest.json` — current event snapshot (overwrites, no history)
- Alpaca `/v2/orders` — order book (price/qty/side, no thesis)
