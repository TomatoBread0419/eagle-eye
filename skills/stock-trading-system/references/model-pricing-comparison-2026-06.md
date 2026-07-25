# Mimo vs DeepSeek Pricing Comparison (2026-06-10)

## DeepSeek API (按量计费)

| | V4-Flash | V4-Pro |
|---|---|---|
| 输入（缓存命中）/百万tokens | ¥0.02 | ¥0.025 |
| 输入（缓存未命中）/百万tokens | ¥1 | ¥3 |
| 输出/百万tokens | ¥2 | ¥6 |

**User's actual May 2026 usage:** 2.1 亿 tokens, total cost ¥27.73
- V4-Pro: 1,129 requests, 8,492 万 tokens
- V4-Flash: 1,849 requests, 1.25 亿 tokens
- Effective average: ~¥0.13/百万tokens (heavy cache hit)

## Mimo Token Plan (订阅制)

### Tiers
| Plan | Monthly | Credits | Annual |
|------|---------|---------|--------|
| Lite | ¥39 ($6) | 4.1B | ¥411.84 |
| Basic | ¥99 ($16) | 11B | ¥1,045.44 |
| Pro | ¥329 ($50) | 38B | ¥3,474.24 |
| Enterprise | ¥659 ($100) | 82B | ¥6,959.04 |

### Credit-to-Token Conversion (per Token, NOT per million)

| Model | Input (cache hit) | Input (cache miss) | Output |
|-------|------------------|--------------------|--------|
| mimo-v2.5-pro | 2.5 Credits | 300 Credits | 600 Credits |
| mimo-v2.5 | 2 Credits | 100 Credits | 200 Credits |

**Official example:** 10M tokens of v2.5-pro input (cache miss) = 3,000M Credits = 3B Credits

### Night discount: 0:00-8:00 BJT → 0.8x Credit consumption

## Comparison for User's Usage Pattern

User's 2.1 亿 tokens/month (80% cache hit, 10% miss, 10% output assumed):

| Model | Credits needed | Lite plan (4.1B) lasts |
|-------|---------------|----------------------|
| mimo-v2.5 | ~66 亿 | ~18 days ❌ |
| mimo-v2.5-pro | ~193 亿 | ~6 days ❌ |

**Conclusion:** DeepSeek is 3-10x cheaper than Mimo for text-heavy API use. Mimo's advantage is TTS (free in plan) and night discount. For the trading system's cron jobs (text-heavy), DeepSeek is the clear winner.

## Model Selection Strategy

- **Daily cron tasks** (portfolio, briefings): DeepSeek V4-Flash (cheapest)
- **Complex reasoning** (market analysis): DeepSeek V4-Pro or Mimo v2.5-pro
- **TTS/voice** (WeChat voice messages): Mimo (free in plan)
- **Fallback**: Keep both providers configured, switch via `hermes config set`
