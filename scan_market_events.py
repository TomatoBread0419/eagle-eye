#!/usr/bin/env python3
"""
Full market event scanner — English (Google RSS) + Chinese (Sogou Weixin + wallstreetcn)
Executes all searches, cross-validates, outputs JSON.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

# ── Proxy patch ──────────────────────────────────────────────────────
try:
    from proxy_patch import patch as _proxy_patch
    _proxy_patch()
except:
    pass

# ── Helpers ──────────────────────────────────────────────────────────

TZ_BJT = timezone(timedelta(hours=8))

def now_bjt():
    return datetime.now(TZ_BJT).strftime('%Y-%m-%dT%H:%M:%S+08:00')

def now_utc():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def google_rss(keyword, max_results=4, timeout=15):
    """Search Google News RSS via proxy"""
    url = (f"https://news.google.com/rss/search?"
           f"q={urllib.parse.quote(keyword)}&hl=en-US&gl=US&ceid=US:en")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            rss = resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        return [], f"Google RSS error: {e}"

    items = re.findall(
        r'<item>.*?<title>(.*?)</title>.*?<source[^>]*>(.*?)</source>.*?<pubDate>(.*?)</pubDate>.*?</item>',
        rss, re.DOTALL,
    )
    results = []
    for title, source, date in items[:max_results]:
        title = re.sub(r'<[^>]+>', '', title).strip()
        source = re.sub(r'<[^>]+>', '', source).strip()
        if source and title.endswith(f' - {source}'):
            title = title[:-(len(source) + 3)]
        results.append({'title': title.strip(), 'source': source.strip(), 'date': date.strip(), 'lang': 'en'})
    return results, None


def sogou_weixin(keyword, max_results=4, timeout=12):
    """Search Sogou Weixin articles"""
    url = f"https://weixin.sogou.com/weixin?type=2&query={urllib.parse.quote(keyword)}&ie=utf8"
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml',
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        return [], f"Sogou Weixin error: {e}"

    # Extract titles from h3 > a
    titles = re.findall(r'<h3[^>]*>.*?<a[^>]*>(.*?)</a>', html, re.DOTALL)
    # Extract summaries from p.txt-info
    summaries = re.findall(r'<p class="txt-info"[^>]*>(.*?)</p>', html, re.DOTALL)
    # Extract source/date from div.s-p
    sources = re.findall(r'<div class="s-p"[^>]*>.*?<span[^>]*>(.*?)</span>', html, re.DOTALL)

    results = []
    for i in range(min(max_results, len(titles))):
        title = re.sub(r'<[^>]+>', '', titles[i]).strip() if i < len(titles) else ''
        summary = re.sub(r'<[^>]+>', '', summaries[i]).strip() if i < len(summaries) else ''
        src_info = re.sub(r'<[^>]+>', '', sources[i]).strip() if i < len(sources) else ''
        results.append({
            'title': title,
            'source': '搜狗微信',
            'date': src_info,
            'snippet': summary,
            'lang': 'zh'
        })

    return results, None


def wallstreetcn_news(channel='global-channel', limit=30, timeout=12):
    """Fetch from wallstreetcn API"""
    url = f"https://api-one.wallstcn.com/apiv1/content/articles?channel={channel}&limit={limit}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return [], f"wallstreetcn error: {e}"

    if data.get('code') != 20000:
        return [], f"wallstreetcn bad code: {data.get('code')}"

    d = data.get('data', {})
    if isinstance(d, dict):
        items = d.get('items', [])
    else:
        return [], f"wallstreetcn data is not dict: {type(d)}"

    results = []
    seen_titles = set()
    for item in items:
        title = (item.get('title') or '').strip()
        if not title:
            continue
        # Dedup by first 30 chars
        key = title[:30]
        if key in seen_titles:
            continue
        seen_titles.add(key)
        display_time = item.get('display_time', 0)
        dt_str = datetime.fromtimestamp(display_time, tz=TZ_BJT).strftime('%Y-%m-%d %H:%M') if display_time else ''
        content_short = (item.get('content_short') or item.get('content_plain') or '')[:200]
        results.append({
            'title': title,
            'source': '华尔街见闻',
            'date': dt_str,
            'snippet': content_short,
            'lang': 'zh'
        })

    return results[:20], None


def qt_quote(codes, timeout=8):
    """Get real-time quotes from qt.gtimg.cn"""
    url = f"https://qt.gtimg.cn/q={'/'.join(codes)}"
    try:
        resp = urllib.request.urlopen(url, timeout=timeout)
        raw = resp.read()
        text = raw.decode('gbk', errors='replace')
    except Exception as e:
        return {c: f"Error: {e}" for c in codes}

    result = {}
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line or '=' not in line:
            continue
        # Parse: code="fields...name~price~chg~chg_pct~..."
        try:
            key, rest = line.split('=', 1)
            key = key.strip(' _')
            rest = rest.strip('" \n;')
            parts = rest.split('~')
            if len(parts) >= 5:
                name = parts[1] if parts[1] else key
                price = parts[3] if parts[3] else 'N/A'
                chg_pct = parts[5] if len(parts) > 5 and parts[5] else 'N/A'
                chg = parts[4] if len(parts) > 4 and parts[4] else 'N/A'
                result[key] = {
                    'name': name,
                    'price': price,
                    'chg': chg,
                    'chg_pct': chg_pct,
                }
            else:
                result[key] = {'name': key, 'price': 'N/A', 'chg': 'N/A', 'chg_pct': 'N/A'}
        except:
            pass
    return result


# ── Sectors ──────────────────────────────────────────────────────────

EN_QUERIES = {
    "半导体/AI": "semiconductor AI chip NVDA TSM demand 2026",
    "地缘/台海": "Taiwan semiconductor TSMC China tensions 2026",
    "美联储": "Federal Reserve Warsh interest rate policy hike cut June 2026",
    "贸易/访华": "Trump China visit trade deal 2026",
    "原材料": "tungsten rare earth price China export control 2026",
    "美股大盘": "stock market movers Tesla Nvidia Apple May June 2026",
}

ZH_QUERIES = {
    "特斯拉FSD": "特斯拉 FSD 入华 2026",
    "英伟达": "英伟达 财报 AI芯片 2026",
    "国内宏观": "中国 货币政策 降准降息 2026",
    "外资动向": "A股 外资流入 板块 轮动 2026",
}

# ── Main ─────────────────────────────────────────────────────────────

print("=" * 60, file=sys.stderr)
print(f"Market Event Scan — {now_bjt()}", file=sys.stderr)
print("=" * 60, file=sys.stderr)

results = {
    "scan_time": now_bjt(),
    "scan_time_utc": now_utc(),
    "sectors": [],
    "market_data": {},
    "summary": {"assessments": []},
}

seen_global_titles = set()

# ── 1. English Google RSS searches ───────────────────────────────────
for sector, query in EN_QUERIES.items():
    print(f"\n--- EN: {sector} ---", file=sys.stderr)
    items, err = google_rss(query, max_results=4)
    if err:
        print(f"  ERROR: {err}", file=sys.stderr)
    else:
        print(f"  Got {len(items)} results", file=sys.stderr)
        for it in items:
            print(f"  • {it['title'][:80]} | {it['source']} | {it['date'][:16]}", file=sys.stderr)
            seen_global_titles.add(it['title'][:50])

    sector_data = {"sector": sector, "en": items if not err else [], "zh": [], "wsc": []}
    results["sectors"].append(sector_data)

# ── 2. Chinese Sogou Weixin searches ─────────────────────────────────
zh_sector_idx = 0
zh_sector_names = list(ZH_QUERIES.keys())
for query_name, query in ZH_QUERIES.items():
    print(f"\n--- ZH: {query_name} ---", file=sys.stderr)
    items, err = sogou_weixin(query, max_results=4)
    if err:
        print(f"  ERROR: {err}", file=sys.stderr)
    else:
        print(f"  Got {len(items)} results", file=sys.stderr)
        for it in items:
            print(f"  • {it['title'][:60]} | {it.get('snippet','')[:40]}", file=sys.stderr)

    # Store in the appropriate sector
    if query_name == "特斯拉FSD":
        # Add to 美股大盘 sector (last one)
        results["sectors"][-1]["zh"] = items if not err else []
    elif query_name == "英伟达":
        # Add to 半导体/AI sector (first one)
        results["sectors"][0]["zh"] = items if not err else []
    elif query_name == "国内宏观":
        # Add as separate entry or attach to 美联储 sector
        results["sectors"][2]["zh"] = items if not err else []
    elif query_name == "外资动向":
        # Add to 贸易/访华 or a-stock
        results["sectors"][3]["zh"] = items if not err else []

# ── 3. wallstreetcn API ──────────────────────────────────────────────
print(f"\n--- wallstreetcn global ---", file=sys.stderr)
wsc_items, wsc_err = wallstreetcn_news('global-channel', limit=30)
if wsc_err:
    print(f"  ERROR: {wsc_err}", file=sys.stderr)
else:
    print(f"  Got {len(wsc_items)} results", file=sys.stderr)
    for it in wsc_items[:5]:
        print(f"  • {it['title'][:70]} | {it['date']}", file=sys.stderr)

# Also try us-stock-channel
wsc_us_items, wsc_us_err = wallstreetcn_news('us-stock-channel', limit=30)
if not wsc_us_err:
    # Dedup with global
    seen_wsc = set(it['title'][:40] for it in wsc_items)
    for it in wsc_us_items:
        if it['title'][:40] not in seen_wsc:
            seen_wsc.add(it['title'][:40])
            wsc_items.append(it)
    print(f"  After dedup + us-channel: {len(wsc_items)}", file=sys.stderr)

# Distribute wallstreetcn items to sectors by keyword matching
sector_keywords = {
    "半导体/AI": ['芯片', '半导体', 'AI', '人工智能', '英伟达', 'NVIDIA', '台积电', 'TSMC', 'HBM', '算力', '大模型'],
    "地缘/台海": ['台湾', '台海', '地缘', '制裁', '冲突', '军事', '国防', '南海', '中美'],
    "美联储": ['美联储', '降息', '加息', '利率', '通胀', 'CPI', 'PCE', 'Warsh', '鲍威尔', '点阵图'],
    "贸易/访华": ['特朗普', '关税', '贸易', '访华', '谈判', '关税', '出口管制', '反制'],
    "原材料": ['钨', '稀土', '有色金属', '锂', '钴', '镍', '铜', '铝', '出口管制', '原材料'],
    "美股大盘": ['美股', '特斯拉', '苹果', '微软', '谷歌', '亚马逊', 'meta', '大盘', '股指', '期权', '波动'],
}

for item in wsc_items:
    title = item['title']
    assigned = False
    for si, sector_entry in enumerate(results["sectors"]):
        sector_name = sector_entry["sector"]
        keywords = sector_keywords.get(sector_name, [])
        if any(kw in title for kw in keywords):
            sector_entry["wsc"].append(item)
            assigned = True
            break
    if not assigned:
        # Default to 美股大盘
        results["sectors"][-1]["wsc"].append(item)

# Limit wsc entries per sector to 6
for sector_entry in results["sectors"]:
    sector_entry["wsc"] = sector_entry["wsc"][:6]

# ── 4. Market Data ──────────────────────────────────────────────────
print(f"\n--- Market Data ---", file=sys.stderr)

us_indices = ['usINX', 'usDJI', 'usIXIC']
us_stocks = ['usNVDA', 'usTSLA', 'usAAPL', 'usMSFT', 'usAMZN', 'usGOOG', 'usMETA', 'usAVGO', 'usBABA', 'usJD']
cn_indices = ['sh000001', 'sz399001', 'sz399006']
hk_indices = ['hkHSI', 'hkHSCEI', 'hkHSTECH']

all_quotes = qt_quote(us_indices + us_stocks + cn_indices + hk_indices, timeout=12)

market_data = {"US Indices": [], "US Stocks": [], "CN Indices": [], "HK Indices": []}

for code in us_indices:
    if code in all_quotes:
        q = all_quotes[code]
        chg_pct = q.get('chg_pct', 'N/A')
        emoji = '🟢' if chg_pct not in ['N/A', ''] and float(chg_pct) >= 0 else ('🔴' if chg_pct not in ['N/A', ''] and float(chg_pct) < 0 else '')
        market_data["US Indices"].append({
            "code": code,
            "name": q.get('name', code),
            "price": q.get('price', 'N/A'),
            "chg_pct": f"{emoji}{chg_pct}%",
        })

for code in us_stocks:
    if code in all_quotes:
        q = all_quotes[code]
        chg_pct = q.get('chg_pct', 'N/A')
        emoji = '🟢' if chg_pct not in ['N/A', ''] and float(chg_pct) >= 0 else ('🔴' if chg_pct not in ['N/A', ''] and float(chg_pct) < 0 else '')
        market_data["US Stocks"].append({
            "code": code,
            "name": q.get('name', code),
            "price": q.get('price', 'N/A'),
            "chg_pct": f"{emoji}{chg_pct}%",
        })

for code in cn_indices:
    if code in all_quotes:
        q = all_quotes[code]
        chg_pct = q.get('chg_pct', 'N/A')
        emoji = '🟢' if chg_pct not in ['N/A', ''] and float(chg_pct) >= 0 else ('🔴' if chg_pct not in ['N/A', ''] and float(chg_pct) < 0 else '')
        market_data["CN Indices"].append({
            "code": code,
            "name": q.get('name', code),
            "price": q.get('price', 'N/A'),
            "chg_pct": f"{emoji}{chg_pct}%",
        })

for code in hk_indices:
    if code in all_quotes:
        q = all_quotes[code]
        chg_pct = q.get('chg_pct', 'N/A')
        emoji = '🟢' if chg_pct not in ['N/A', ''] and float(chg_pct) >= 0 else ('🔴' if chg_pct not in ['N/A', ''] and float(chg_pct) < 0 else '')
        market_data["HK Indices"].append({
            "code": code,
            "name": q.get('name', code),
            "price": q.get('price', 'N/A'),
            "chg_pct": f"{emoji}{chg_pct}%",
        })

results["market_data"] = market_data

print(f"\nMarket Data Summary:", file=sys.stderr)
for cat, vals in market_data.items():
    for v in vals:
        print(f"  {v['code']}: {v['name']} {v['price']} {v['chg_pct']}", file=sys.stderr)

# ── 5. Summary Assessments ──────────────────────────────────────────

def assess_sector(sector_name, en_items, zh_items, wsc_items, market_data):
    """AI assessment of sector direction based on gathered news"""
    all_titles = []
    for items in [en_items, zh_items, wsc_items]:
        for it in items:
            all_titles.append(it.get('title', ''))
    
    combined = ' '.join(all_titles).lower()
    
    # Default assessment
    direction = "🟡 中性"
    significant = False
    hot_events = []
    key_news = []
    
    # Get top news titles
    for items in [en_items, zh_items, wsc_items]:
        for it in items[:3]:
            key_news.append(it.get('title', '')[:100])
    key_news = key_news[:4]
    
    # Sector-specific heuristics
    if sector_name == "半导体/AI":
        if any(kw in combined for kw in ['rally', 'surge', 'soar', '新高', '暴涨', '突破']):
            direction = "🟢 利好"
        if any(kw in combined for kw in ['ban', 'restrict', 'sanction', 'export control', 'crackdown', '限制', '制裁']):
            direction = "🔴 利空"
            if 'export control' in combined or '制裁' in combined:
                hot_events.append('sanction')
        if any(kw in combined for kw in ['demand surge', 'shortage', '产能不足', '供不应求']):
            direction = "🟢 利好"
            hot_events.append('supply_shock')
            
    elif sector_name == "地缘/台海":
        if any(kw in combined for kw in ['conflict', 'war', 'military', 'invasion', '冲突', '战争', '军事']):
            direction = "🔴 利空"
            significant = True
            hot_events.append('war')
            hot_events.append('conflict')
        if any(kw in combined for kw in ['sanction', '制裁', 'restrict']):
            hot_events.append('sanction')
        if any(kw in combined for kw in ['de-escalate', 'ceasefire', 'talk', '缓和', '谈判', '对话']):
            direction = "🟡 中性"
            
    elif sector_name == "美联储":
        if any(kw in combined for kw in ['hike', '加息', 'tighten']):
            direction = "🔴 利空"
        if any(kw in combined for kw in ['cut', 'ease', 'lower', '降息', '宽松']):
            direction = "🟢 利好"
        if 'hold' in combined or 'pause' in combined or '不动' in combined:
            direction = "🟡 中性"
            
    elif sector_name == "贸易/访华":
        if any(kw in combined for kw in ['tariff', '关税', 'trade war', '贸易战']):
            direction = "🔴 利空"
            hot_events.append('tariff')
            significant = True
        if any(kw in combined for kw in ['deal', 'agreement', 'visit', '协议', '访问', '合作']):
            direction = "🟡 中性"
            if 'deal' in combined or '协议' in combined:
                direction = "🟢 利好"
                
    elif sector_name == "原材料":
        if any(kw in combined for kw in ['surge', '新高', '暴涨', '飙升', 'price hike']):
            direction = "🔴 利空"  # price surge = cost pressure for most industries
            hot_events.append('price_surge')
        if any(kw in combined for kw in ['export control', '出口管制', 'ban']):
            direction = "🔴 利空"
            hot_events.append('sanction')
        if any(kw in combined for kw in ['shortage', '供应紧张', '供不应求']):
            direction = "🟢 利好原材料股，🔴 利空下游制造"
            
    elif sector_name == "美股大盘":
        if any(kw in combined for kw in ['record high', 'rally', '新高', '暴涨']):
            direction = "🟢 利好"
        if any(kw in combined for kw in ['plunge', 'crash', '暴跌', '崩盘', 'fear', 'panic']):
            direction = "🔴 利空"
            significant = True
            hot_events.append('selloff')
    
    return {
        "sector": sector_name,
        "direction": direction,
        "significant": significant,
        "hot_events": hot_events,
        "key_news": key_news,
    }


for sector_entry in results["sectors"]:
    assessment = assess_sector(
        sector_entry["sector"],
        sector_entry.get("en", []),
        sector_entry.get("zh", []),
        sector_entry.get("wsc", []),
        market_data,
    )
    results["summary"]["assessments"].append(assessment)

# ── 6. Save JSON ────────────────────────────────────────────────────
output_path = os.path.expanduser('~/stock_trader/market_events_latest.json')
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n✅ Saved to {output_path}", file=sys.stderr)
print(f"Total sectors: {len(results['sectors'])}", file=sys.stderr)
print(f"Total assessments: {len(results['summary']['assessments'])}", file=sys.stderr)

# Print summary to stdout for the report
print("\n" + "=" * 60)
print(f"MARKET EVENT SCAN — {now_bjt()}")
print("=" * 60)

for sect in results["sectors"]:
    sn = sect["sector"]
    en = sect.get("en", [])
    zh = sect.get("zh", [])
    wsc = sect.get("wsc", [])
    
    # Find assessment
    ass = next((a for a in results["summary"]["assessments"] if a["sector"] == sn), {})
    direction = ass.get("direction", "🟡 中性")
    sig = ass.get("significant", False)
    hot = ass.get("hot_events", [])
    
    sig_flag = " 🔥" if sig else ""
    hot_flag = f" [{', '.join(hot)}]" if hot else ""
    print(f"\n## {sn} {direction}{sig_flag}{hot_flag}")
    
    all_items = en + zh + wsc
    for i, it in enumerate(all_items[:5]):
        date = it.get('date', '')[:16] if it.get('date') else ''
        src = it.get('source', '')
        title = it.get('title', '')
        print(f"  {i+1}. {title} | {src} | {date}")
    
    if not all_items:
        print("  暂无数据")

# Market data summary
print("\n## 📊 行情快照")
for cat, vals in market_data.items():
    names = [f"{v['name']} {v['price']} {v['chg_pct']}" for v in vals]
    print(f"  {cat}: {' | '.join(names[:4])}")

print("\n--- JSON saved ---")
