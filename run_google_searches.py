"""Run all 6 Google News RSS searches via proxy_patch"""
import sys, json, urllib.request, urllib.parse, urllib.error, ssl, time, re
from html.parser import HTMLParser

# Apply proxy
sys.path.insert(0, '$HOME/.hermes/scripts')
from proxy_patch import patch
patch(force=True)

QUERIES = [
    "semiconductor+AI+chip+NVDA+TSM+demand+2026",
    "Taiwan+semiconductor+TSMC+China+tensions",
    "Federal+Reserve+Warsh+interest+rate+policy+hike+cut",
    "Trump+China+visit+trade+deal",
    "tungsten+rare+earth+price+China+export+control",
    "stock+market+movers+Tesla+Nvidia+Apple+May+2026",
]

LABELS = [
    "semiconductor_ai",
    "taiwan_tsmc",
    "fed_rates",
    "trump_china_trade",
    "tungsten_rare_earth",
    "stock_movers",
]

def fetch_google_news(query):
    """Fetch Google News RSS for a query"""
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        resp = urllib.request.urlopen(req, timeout=20, context=ctx)
        data = resp.read().decode('utf-8', errors='replace')
        return data
    except Exception as e:
        return f"ERROR: {e}"

class RSSParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_item = False
        self.in_title = False
        self.in_source = False
        self.in_date = False
        self.in_link = False
        self.items = []
        self.current = {}
        self.tag_stack = []
    
    def handle_starttag(self, tag, attrs):
        self.tag_stack.append(tag)
        if tag == 'item':
            self.in_item = True
            self.current = {}
        elif tag == 'title' and self.in_item:
            self.in_title = True
        elif tag == 'source' and self.in_item:
            self.in_source = True
        elif tag in ('pubdate', 'dc:date'):
            # Just track date from pubDate
            pass
    
    def handle_endtag(self, tag):
        if tag == 'item':
            self.in_item = False
            if self.current.get('title'):
                self.items.append(self.current)
            self.current = {}
        elif tag == 'title':
            self.in_title = False
        elif tag == 'source':
            self.in_source = False
        self.tag_stack.pop()
    
    def handle_data(self, data):
        data = data.strip()
        if not data:
            return
        if self.in_title:
            if 'title' in self.current:
                self.current['title'] += ' ' + data
            else:
                self.current['title'] = data
        elif self.in_source:
            self.current['source'] = data

def parse_rss(xml_text):
    """Simple RSS item extraction without full parsing"""
    items = []
    # Split by <item>...</item>
    parts = re.split(r'<item>', xml_text)
    for part in parts[1:]:
        item_end = part.find('</item>')
        if item_end == -1:
            continue
        item_xml = part[:item_end]
        
        title_match = re.search(r'<title>(.*?)</title>', item_xml, re.DOTALL)
        source_match = re.search(r'<source[^>]*>(.*?)</source>', item_xml, re.DOTALL)
        date_match = re.search(r'<pubDate>(.*?)</pubDate>', item_xml, re.DOTALL)
        link_match = re.search(r'<link>(.*?)</link>', item_xml, re.DOTALL)
        
        title = title_match.group(1).strip() if title_match else ''
        source = source_match.group(1).strip() if source_match else ''
        pubdate = date_match.group(1).strip() if date_match else ''
        link = link_match.group(1).strip() if link_match else ''
        
        if title:
            # Clean CDATA
            title = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', title)
            items.append({
                'title': title,
                'source': source,
                'pubdate': pubdate,
                'link': link
            })
    return items

results = {}
for i, (query, label) in enumerate(zip(QUERIES, LABELS)):
    print(f"[{i+1}/{len(QUERIES)}] Searching: {label}...", file=sys.stderr)
    xml_data = fetch_google_news(query)
    if xml_data.startswith("ERROR:"):
        results[label] = {"status": "error", "error": xml_data, "items": []}
        print(f"  ERROR: {xml_data}", file=sys.stderr)
    else:
        items = parse_rss(xml_data)[:10]  # Top 10 per query
        results[label] = {"status": "ok", "items": items}
        print(f"  Got {len(items)} items", file=sys.stderr)
    time.sleep(1)  # Rate limit

print(json.dumps(results, ensure_ascii=False, indent=2))
