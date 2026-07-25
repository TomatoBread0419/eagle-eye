# Market News Sources — Verified Working (China / Termux)

## Primary: Google News RSS ⭐

Works in China's restricted network. No proxy needed. Returns XML RSS feed.

```bash
# General market news (past 7 days)
curl -sL "https://news.google.com/rss/search?q=stock+market+Fed+May+2026&hl=en-US"

# Stock-specific
curl -sL "https://news.google.com/rss/search?q=ARM+stock+earnings&hl=en-US"

# Sector-specific
curl -sL "https://news.google.com/rss/search?q=semiconductor+chips+2026&hl=en-US"
```

**Parse titles:** `grep -oP '<title>[^<]+</title>' | sed 's/<[^>]*>//g' | head -20`

**Parse full items (title + pubDate + description):**
```python
import xml.etree.ElementTree as ET
root = ET.fromstring(xml_text)
for item in root.findall('.//item'):
    title = item.find('title').text
    pubDate = item.find('pubDate').text
    desc = item.find('description').text
    print(f"{pubDate[:16]} | {title}")
```

## Fallback: Sogou WeChat (Chinese articles)

```bash
curl -sL "https://weixin.sogou.com/weixin?type=2&query=美联储" \
  -H "User-Agent: Mozilla/5.0 (Linux; Android 13)"
```

## Key Events to Monitor (Weekly Checklist)

- [ ] Fed: rate decisions, FOMC minutes, Fed Chair speeches/transitions
- [ ] Geopolitical: state visits, trade deals, conflicts
- [ ] Earnings: major company earnings dates (NVDA, AAPL, MSFT, etc.)
- [ ] Economic data: CPI, PPI, jobs report, GDP
- [ ] Regulatory: FTC/DOJ antitrust, export controls, tariff changes

## ARM Holdings (ARM) — Watchlist Addition Candidate

**Status:** Not in current 57-stock scanner pool.
**Why add:** "ARM Holdings Has Doubled in 2026" — AI chip IP licensing story. All AI chip makers (NVDA, Apple, Qualcomm) pay ARM royalties. Stock received wave of analyst target hikes after AI earnings beat.
**Sector:** 🌟半导体
**Exchange:** NASDAQ (secid: 105.ARM)
