#!/usr/bin/env python3
"""Rebuild JSON with proper market data from qt.gtimg.cn"""
import json, os, sys, re, urllib.request

def qt_parse(codes, timeout=10):
    url = f"https://qt.gtimg.cn/q={'/'.join(codes)}"
    try:
        resp = urllib.request.urlopen(url, timeout=timeout)
        raw = resp.read()
        text = raw.decode('gbk', errors='replace')
    except Exception as e:
        return {}

    result = {}
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line or '=' not in line:
            continue
        try:
            key, rest = line.split('=', 1)
            key = key.strip(' v_')
            rest = rest.strip('" \n;')
            parts = rest.split('~')
            if len(parts) >= 5:
                name = parts[1] if parts[1] else key
                price = parts[3] if parts[3] else 'N/A'
                chg_pct = parts[5] if len(parts) > 5 and parts[5] else 'N/A'
                chg = parts[4] if len(parts) > 4 and parts[4] else 'N/A'
                # Extract date from the right field
                date_field = parts[len(parts)-3] if len(parts) > 30 else ''
                result[key] = {
                    'name': name,
                    'price': price,
                    'chg': chg,
                    'chg_pct': chg_pct,
                    'date': date_field,
                }
        except:
            pass
    return result

codes = ['usINX', 'usDJI', 'usIXIC', 'usNVDA', 'usTSLA', 'usAAPL', 'usMSFT', 
         'usAMZN', 'usGOOG', 'usMETA', 'usAVGO', 'usBABA', 'usJD',
         'sh000001', 'sz399001', 'sz399006', 'hkHSI', 'hkHSCEI', 'hkHSTECH']

qt_data = qt_parse(codes)

emoji_map = {}
for code, q in qt_data.items():
    try:
        cp = float(q['chg_pct'])
        emoji_map[code] = '🟢' if cp >= 0 else '🔴'
    except:
        emoji_map[code] = ''

# Build market_data
market_data = {
    "US Indices": [],
    "US Stocks": [],
    "CN Indices": [],
    "HK Indices": [],
}

for code in ['usINX', 'usDJI', 'usIXIC']:
    if code in qt_data:
        q = qt_data[code]
        em = emoji_map.get(code, '')
        market_data["US Indices"].append({
            "code": code,
            "name": q['name'],
            "price": q['price'],
            "chg_pct": f"{em}{q['chg_pct']}%",
        })

us_stocks = ['usNVDA', 'usTSLA', 'usAAPL', 'usMSFT', 'usAMZN', 'usGOOG', 'usMETA', 'usAVGO', 'usBABA', 'usJD']
for code in us_stocks:
    if code in qt_data:
        q = qt_data[code]
        em = emoji_map.get(code, '')
        market_data["US Stocks"].append({
            "code": code,
            "name": q['name'],
            "price": q['price'],
            "chg_pct": f"{em}{q['chg_pct']}%",
        })

for code in ['sh000001', 'sz399001', 'sz399006']:
    if code in qt_data:
        q = qt_data[code]
        em = emoji_map.get(code, '')
        market_data["CN Indices"].append({
            "code": code,
            "name": q['name'],
            "price": q['price'],
            "chg_pct": f"{em}{q['chg_pct']}%",
        })

for code in ['hkHSI', 'hkHSCEI', 'hkHSTECH']:
    if code in qt_data:
        q = qt_data[code]
        em = emoji_map.get(code, '')
        market_data["HK Indices"].append({
            "code": code,
            "name": q['name'],
            "price": q['price'],
            "chg_pct": f"{em}{q['chg_pct']}%",
        })

# Read existing JSON
path = os.path.expanduser('~/stock_trader/market_events_latest.json')
with open(path, 'r', encoding='utf-8') as f:
    report = json.load(f)

report["market_data"] = market_data

with open(path, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("✅ Updated market_data in JSON")
print(f"\n📊 US Indices:")
for v in market_data["US Indices"]:
    print(f"  {v['code']}: {v['name']} {v['price']} {v['chg_pct']}")

print(f"\n📊 US Stocks (key):")
for v in market_data["US Stocks"][:5]:
    print(f"  {v['code']}: {v['name']} {v['price']} {v['chg_pct']}")

print(f"\n📊 CN Indices:")
for v in market_data["CN Indices"]:
    print(f"  {v['code']}: {v['name']} {v['price']} {v['chg_pct']}")

print(f"\n📊 HK Indices:")
for v in market_data["HK Indices"]:
    print(f"  {v['code']}: {v['name']} {v['price']} {v['chg_pct']}")

# Wallstreetcn news that arrived recently
print(f"\n📰 wallstreetcn latest headlines:")
for sect in report.get("sectors", []):
    wsc = sect.get("wsc", [])
    if wsc:
        print(f"  [{sect['sector']}]")
        for it in wsc[:3]:
            print(f"    • {it['title'][:70]} | {it.get('date','')}")

# Print assessments
print(f"\n🔍 Summary Assessments:")
for a in report.get("summary", {}).get("assessments", []):
    sig = " 🔥" if a.get("significant") else ""
    hot = f" [{', '.join(a.get('hot_events', []))}]" if a.get("hot_events") else ""
    print(f"  {a['sector']}: {a['direction']}{sig}{hot}")
