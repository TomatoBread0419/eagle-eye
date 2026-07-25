# 午间速报（Cn Midday Briefing，12:00 工作日）

> 2026-06-03 首次跑通。A 股午间收盘 / 港股半日 / 欧股盘前 1 小时 cron 模板。
> 数据源以**腾讯 qt.gtimg.cn**为主（A股 / 港股指数 / 港股个股全覆盖），**Yahoo Finance v8 chart** 补位。
> 输出 ≤500 字，4 段固定格式（A股/港股/欧美/预警）。

## 触发条件

用户配置 `schedule: "0 12 * * 1-5"`（A 股工作日 11:30 收盘后 30 分钟内），`deliver: weixin`，prompt 包含：
- 「午间速报」/「A 股午盘 / 港股半日 / 欧美盘前」
- 必查：A股三大指数 / 主力资金板块 / 涨停跌停 / 恒指 / 港股板块 / 美股期货 / 欧股期货 / 今日盘前财报 / 持仓距止损 / 14:00-16:00 事件
- 输出格式：4 段简报（A股/港股/欧美/预警）

## 数据源（全部 No-Key，墙内可用）

### 主源 A：腾讯 qt.gtimg.cn（**6/3 实测发现的全覆盖源**）

```python
import urllib.request, ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {'User-Agent': 'Mozilla/5.0',
           'Referer': 'https://stockapp.finance.qq.com/'}

def qt_get(sym):
    url = f"https://qt.gtimg.cn/q={sym}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=5, context=ctx) as r:
        data = r.read().decode('gbk', 'replace')
    if 'pv_none_match' in data:
        return None
    parts = data.split('"')[1].split('~')
    return parts  # 见下方字段说明
```

**字段顺序（沪深指数 / 行业，s_ 前缀）：**
```
0: 数字标识  1: 中文名  2: 代码  3: 当前价  4: 涨跌额  5: 涨跌幅%
6: 成交量  7: 成交额  8-9: 买/卖盘  10: 5日分钟K
```

**字段顺序（港股指数，hk 前缀无 s_）：**
```
0: 数字标识  1: 中文名  2: 英文代码  3: 现价  4: 昨收  5: 今开
6: 成交额  7: 5日均量  8-9: 买/卖盘  10: 时间戳  11: 涨跌额  12: 涨跌幅%
13-16: 最高/最低/振幅  17-19: 52w 区间
```

**字段顺序（港股个股，hk + 5位代码）：**
```
0: 数字标识  1: 名称  2: 代码  3: 现价  4: 昨收  5: 今开
6: 成交额(港元)  10: 时间戳  11: 涨跌额  12: 涨跌幅%
13-14: 最高/最低
```

**为什么 qt.gtimg.cn 是 6/3 实测的更优源：**
- **覆盖全面**：A股（s_sh000001 / s_sz399006）、港股指数（hkHSI / hkHSTECH / hkHSCEI）、港股个股（hk00700 / hk09988 / hk03690 / hk01810 等）、A 股行业指数（s_sh000933 医药 / s_sz399986 银行 / s_sh000688 科创50 / s_sh000852 中证1000）一次性拿全
- **3 秒刷新**（与 Sina 实时流同量级）
- **港股个股** Sina 走 `rt_hk00700` 是空字符串，但 qt.gtimg.cn 的 `hk00700` 是真数据
- **美股**：usSPX / usDJI / usDXY 等 prefix 都返回 `pv_none_match="1"`，要走 Yahoo v8 chart 补位

**A 股行业指数代码（6/3 实测可用）：**
```python
A_INDICES = {
    's_sh000001': '上证',
    's_sh000300': '沪深300',
    's_sh000688': '科创50',
    's_sh000852': '中证1000',
    's_sh000933': '中证医药',
    's_sh000934': '中证金融',
    's_sh000935': '中证信息(休闲)',  # 申万一级
    's_sz399001': '深证',
    's_sz399006': '创业板',
    's_sz399905': '中证500',
    's_sz399986': '中证银行',
    's_sz399995': '基建工程',
    's_sz399996': '金融地产',
    's_sz399997': '中证消费',
    's_sz399970': 'ESG',
    's_sz399971': '云计算',
    's_sz399989': '医疗',
    's_sz399994': '信息安全',
}
```

**港股指数 + 蓝筹个股（6/3 实测可用）：**
```python
HK_INDICES = {
    'hkHSI': '恒指',
    'hkHSCEI': '国企',
    'hkHSTECH': '恒科',
}
HK_BLUES = {
    'hk00700': '腾讯',
    'hk09988': '阿里',
    'hk03690': '美团',
    'hk01810': '小米',
    'hk09618': '京东',
    'hk09999': '网易',
    'hk01024': '快手',
    'hk02628': '中国人寿',
    'hk01211': '比亚迪',
    'hk02015': '理想',
    'hk09888': '百度',
    'hk02318': '平安',
    'hk00388': '港交所',
    'hk00005': '汇丰',
    'hk02269': '药明生物',
}
```

### 主源 B：Yahoo Finance v8 chart（**美股期指 + 隔夜美股**）

```python
import urllib.request, json
def yf(sym, interval='15m', rng='5d'):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval={interval}&range={rng}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.load(r)
    m = d['chart']['result'][0]['meta']
    return {
        'price': m['regularMarketPrice'],
        'prev':  m.get('chartPreviousClose'),
        'open':  d['chart']['result'][0]['indicators']['quote'][0].get('open',[None])[0],
        'high':  m.get('regularMarketDayHigh'),
        'low':   m.get('regularMarketDayLow'),
    }
```

**6/3 12:00 BJT 跑通的标的：**
| 类别 | 符号 | 备注 |
|------|------|------|
| 美股期货 | `ES=F` SP500 / `NQ=F` Nasdaq / `YM=F` 道指 / `RTY=F` 罗素 | 15m interval, 5d range |
| 大宗 | `GC=F` 黄金 / `CL=F` 原油 / `SI=F` 白银 | 隔夜 + 盘前期 |
| 汇率 | `DX-Y.NYB` 美元指数 | 同上 |
| VIX | `VIX` (注意 6/3 报 N/A，要试 `^VIX`) | |
| 欧洲指数 | `^GDAXI` / `^STOXX50E` / `^FTSE` | Yahoo 6/3 直接返回 6/2 收盘，**代表昨日欧股收盘不是今日盘前** |
| A股交叉 | `000001.SS` / `399001.SZ` / `399006.SZ` / `000300.SS` | 沪深指数 |

### 备源：Google News RSS（板块新闻 + 催化事件归因）

```python
def gn(q, hl='zh-CN', gl='CN', n=4):
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl={hl}&gl={gl}&ceid={gl}:zh-cn"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as r:
        rss = r.read().decode('utf-8','replace')
    items = re.findall(r'<item>.*?<title>(.*?)</title>.*?<source[^>]*>(.*?)</source>.*?<pubDate>(.*?)</pubDate>.*?</item>', rss, re.DOTALL)
    out = []
    for t,s,d in items[:n]:
        t = re.sub(r'<[^>]+>', '', t).strip()
        s = re.sub(r'<[^>]+>', '', s).strip()
        if s and t.endswith(f' - {s}'): t = t[:-(len(s)+3)]
        out.append({'t': t, 's': s, 'd': d})
    return out
```

**6/3 验证可用的板块查询关键词：**
- A股资金 + 板块：`6月3日 主力 净流入 板块` / `半导体 通信 净买入 主力`
- 港股半日：`港股 6月3日 板块 涨跌 异动` / `半导体 港股 存储 澜起`
- 美股盘前：`US stock futures premarket June 3 2026` / `US pre market stocks today surge drop`
- 今日盘前财报：`earnings before market open June 3 2026` / `AVGO HPE earnings today`
- 风险事件：`伊朗 特朗普 6月3日 油价` / `Trump Iran June 3 2026`
- **关键词技巧**：用「6月3日」+ 简短语能拿到当天新闻；纯日期通常被「6月2日」新闻污染

## 关键坑点

### 1. Sina hq.sinajs.cn 6/3 已 404（不要花时间试）

```bash
# 这些都返回 404:
https://hq.sinajs.cn/rt_hkHSI
https://hq.sinajs.cn/s_sh000001
https://hq.sinajs.cn/gb_baba
https://hq.sinajs.cn/int_nasdaq
```

**改用 qt.gtimg.cn（腾讯），功能 100% 覆盖。** 6/3 实测 18 个 A 股指数 + 15 个港股蓝筹 + 3 个港股指数全部拉通。

### 2. 南向资金实时数据：API 不可用，必须用新闻源

- qt.gtimg.cn 的 `s_sh_South` / `s_sz_South` / `s_sh_HGT` / `s_sz_SGT` 全部 `pv_none_match`
- Sina 的 `s_sh_South` 等全部 404
- **唯一可行路径**：用 Google News 搜「南向资金 净买入 6月3日 港股通」拿财联社 / 21财经 / 证券时报标题
- 6/3 早盘没有数据，**报告中"南向"一行写「数据未更新」+ 历史背景（昨夜净买入 X 亿）即可**

### 3. 涨停 / 跌停数：API 不可用，靠盘面 + 新闻

- qt.gtimg.cn / Sina / 同花顺 / 雪球 都没有公开涨停跌停计数器 API
- **替代方案 1**：A 股行业指数 + 个股异动新闻推断（`亨通光电 4 分钟涨停` `ST 闻泰 天地板跌停`）
- **替代方案 2**：直接用「财联社 昨日行情回顾」这类新闻（每日 09:10 推送）
- 报告中可写「涨停 龙头: 联讯仪器 / 天孚通信 / 亨通光电 (2 连板)」+「跌停: ST 闻泰」，不写具体数字

### 4. 持仓距止损：用 us_risk_state.json 的 highest 字段

```python
import json
with open('$HOME/stock_trader/us_risk_state.json') as f:
    state = json.load(f)

holdings = state['positions']  # dict: {ticker: {highest, trail_trigger, cost?}}

# 对每只持仓，从 us_signal_latest.json 拿现价
with open('$HOME/stock_trader/us_signal_latest.json') as f:
    sig = json.load(f)
price_map = {r['symbol']: r for r in sig['results']}

for t, meta in holdings.items():
    if t in price_map:
        cur = price_map[t]['price']
        high = meta['highest']
        drawdown = (cur - high) / high * 100
        rsi = price_map[t].get('rsi', 0)
        # 报告: TICK 现价 vs 最高 -X.XX% (RSI Y)
```

**6/3 实测的 15 只持仓**（按 us_signal_latest.json 取数）：
- 半导体强势: AMAT +7.05% RSI 71 / AMD +2.24% RSI 70 / QCOM +5.21% RSI 60
- 半导体弱势: NVDA -0.71% / INTC -1.26% (距最高 -11.2%)
- 金融: GS +1.63% RSI 79 / BAC +1.92% / C +1.70%
- 科技: MSFT -4.15% (距最高 -5.1%, 重点关注)
- 防御: KO -0.25% / BLK -0.06%
- 周期: BA -2.96% / CAT +5.19% / JPM +1.45%

### 5. 港股板块异动归因：A 股共振 vs 港股独自

6/3 出现关键分化信号：A 股半导体 / CPO / 光通信 集体爆发，但港股科技板块 6/2 涨 9% 后 6/3 回调。**报告必须明确写明 A/H 分化方向**，不能只写「港股科技下跌」不说为什么。

### 6. 12:00 cron 跑期指，拿到的是昨夜 ET 收盘 + 6/3 盘前期

- BJT 12:00 = ET -1:00（前一天 23:00）= 美股 6/2 收盘后 1 小时
- Yahoo `ES=F` 15m chart 最后几根柱是 UTC 03:45 / 04:00 = BJT 11:45 / 12:00 = ET 23:45 / 00:00
- 这意味着 **12:00 拿到的期指数据 = 美股 6/2 收盘 + 6/2 盘后 + 6/3 盘前期**（盘前期 = 04:00 ET 开始）
- 用 `meta.regularMarketPrice` 是否被当日新值更新判断「现在是什么时段」

## 输出格式（≤500 字）

```
🔔 午间速报 | YYYY-MM-DD 12:00

📈 [A 股午盘]
• 上证 / 深证 / 创业: [点位 + %]
• 科创 50 / 沪深 300: [点位 + %]
• 资金流入 Top3: [板块]
• 涨停龙头: [3 只] | 跌停: [1-2 只]

🌏 [港股半日]
• 恒指 / 国企 / 恒科: [点位 + %]
• 板块异动: [领涨 1] [领跌 1]
• 南向: [净买入 X 亿 或 数据未更新]

🌍 [欧美盘前]
• 美股期货: SPX +0.2% / NDX +0.3% / 道 +0.x%
• 欧股期货: DAX +0.1% / Stoxx50 +0.1%
• 盘前财报: TICK1 / TICK2
• 大宗: 油 +X% / 金 -X% / 美元 +X%

⚠️ [预警]
• 持仓: TICK 距最高 -X% (RSI Y) / TICK 突破前高
• 下午 14:00-16:00: 事件 1 / 事件 2

🔜 下次: [cron 名] HH:MM
```

**没动静的简版：**
```
🔕 午间速报: 市场平静, 无重大事件
```

## 实际跑通示例（2026-06-03 12:00 BJT）

### 数据采集
- qt.gtimg.cn: A 股 18 指数 / 港股 3 指数 / 港股 15 蓝筹 ✅
- Yahoo v8: SP500 +0.37% / Nasdaq +0.99% / 道 +0.59% / 原油 +8.48% / 黄金 -1.01% ✅
- 欧洲指数: DAX +0.48% / Stoxx50 +1.21% (注: Yahoo 报的是 6/2 收盘，不是今日盘前)
- 港股半日 (11:49 timestamp): HSI 25,584 -1.75% / HSCEI 8,577 -2.12% / HSTECH 5,069 -2.50%
- 港股蓝筹: 腾讯 -3.95% / 美团 -6.14% / 阿里 -2.98% / 京东 -3.92% / 理想 -4.77% (集体回调)
- Google News: 6/3 关键词命中当天新闻约 60% (财联社/同花顺/AAStocks/Moomoo)
- 南向资金: 数据未更新 (API 不可用 + 新闻源当日空)
- 持仓: 15 只 us_signal_latest.json 全量 ✅

### 实际输出（4 段格式）
```
🔔 午间速报 | 2026-06-03 12:00

📈 A 股午盘 🔥
  • 上证 4097.94 (+0.56%) / 深证 15951 (+2.31%) / 创业板 4216 (+3.97% 重上 4200)
  • 科创 50 +4.78% / 沪深 300 +1.55% / 中证 1000 +1.67% 普涨
  • 资金: 半导体 + 通信设备 双双百亿主力净流入 (财联社)
  • 龙头: 联讯仪器 / 天孚通信 (主力净买入 17 亿) / 亨通光电 (2 连板)
  • 跌停: ST 闻泰 ("天地板")

🌏 港股半日 🟡
  • 恒指 25,584 (-1.75%) / 国企 8,577 (-2.12%) / 恒科 5,069 (-2.50%)
  • 反差: A 股半导体狂欢, 港股科网 6/2 涨 9% 后 6/3 回调
  • 今日异动: 联想 -7%+ / 蔚理小鹏百度快手京东集体走低
  • 半导体 / 存储 (澜起 +11%) 仍获资金关注
  • 港口海运 -4% (中远海能)
  • 南向: 数据未更新 (昨夜历史净买入 372 亿创纪录, 6/3 早盘待 11:30 后发布)

🌍 欧美盘前 🟢
  • 美股期货: SP500 +0.37% / Nasdaq +0.99% / 道 +0.59% / 罗素 +0.32%
  • 欧股期货: DAX +0.48% / Stoxx50 +1.21% / FTSE +0.33% (注: Yahoo 报 6/2 收盘)
  • 大宗: 原油 94.77 (+8.48% 伊朗紧张) / 黄金 4514 (-1.01%) / 美元 99.24 (+0.34%)
  • 盘前财报: Broadcom (AVGO) Q2, AI 收入预期 107 亿美元 (TradingKey)
  • 美股 6/2 收盘: 标普首破 7600, 三大指小幅新高, 迈威尔 +32% (英伟达背书)

⚠️ 预警
  • 持仓: NVDA 222.82 (-0.71% 距最高 -2.1%) / MSFT 441.35 (-4.15% 距最高 -5.1% 关注) /
    AMD 521.50 (突破前高, RSI 70) / AMAT 490.44 (+7.05% 创新高, RSI 71)
  • INTC 107.92 (-1.26%, 距最高 -11.2%, 弱势)
  • 下午 14:00-16:00: 中东伊朗局势 (特朗普"继续谈判" vs 伊朗"数日未沟通", 原油 +8% 警报);
    中国财新服务业 PMI 数据; 美股盘前 AVGO 财报可能带动半导体板块 (今晚)

🔜 下次: 港股盘中 13:00
```

### 关键解读（报告附注）
- A 股算力硬件 / 光通信 / CPO 全面爆发, 与美股 6/2 迈威尔 +32% 形成共振
- 港股科技板块逆势调整, 联想 6/2 已大跌 7%, 今日继续走弱 (与 A 股分化)
- 伊朗紧张 + 油价 +8% 是今日最大宏观风险点
- 持仓: 半导体类 (NVDA/AMD/AMAT) 表现分化, MSFT 距高点回撤 5% 需重新评估止损

## 验证步骤

```bash
# 1. 主源 A: 腾讯 qt.gtimg.cn
python3 -c "
import urllib.request, ssl
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
for s in ['s_sh000001','s_sz399006','hkHSI','hkHSTECH','hk00700','s_sh000933']:
    url=f'https://qt.gtimg.cn/q={s}'
    req=urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0','Referer':'https://stockapp.finance.qq.com/'})
    with urllib.request.urlopen(req,timeout=5,context=ctx) as r:
        data=r.read().decode('gbk','replace')
    print(f'{s}: {data[:200]}')
"

# 2. 主源 B: Yahoo v8 (美股期指)
python3 -c "
import urllib.request, json
url='https://query1.finance.yahoo.com/v8/finance/chart/ES=F?interval=15m&range=5d'
req=urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
with urllib.request.urlopen(req,timeout=10) as r:
    d=json.load(r)
m=d['chart']['result'][0]['meta']
print('ES=F:', m['regularMarketPrice'], 'vs prev', m['chartPreviousClose'])
"

# 3. 持仓交叉
cat $HOME/stock_trader/us_signal_latest.json | python3 -c "
import json, sys
d=json.load(sys.stdin)
for p in d['results']:
    print(f\"  {p['symbol']:>6}  \${p['price']:>8.2f}  chg={p['change_pct']:+.2f}%  RSI={p['rsi']}\")
"
```

## 已知局限

- **南向资金**: 当日实时数据无 API，依赖新闻源（财联社 9:10 推送、东方财富盘中快讯）。A 股午间速报时该数据基本未发布
- **涨停跌停数**: 同上，需用「龙头股涨停」+「跌停股」定性描述代替定量计数
- **欧股盘前**: Yahoo 报 6/2 收盘不是 6/3 盘前；如需盘前 1h 报价，搜「European stocks open June 3 STOXX」靠新闻源
- **港股板块子指数**: qt.gtimg.cn 没试过板块 ETF（513050 / 513180 等），A 股 6/3 涨+3% 但港股互联网 ETF 跌-2.8%（中概互联网 ETF 513050 在 A 股场内反向），这是 A/H 倒挂的另一证据
- **新闻源时间漂移**: Google News 标题多数是 1-2 周前的「6 月 X 日」回放，必须用「6月3日」强制匹配当天

## 与其他 skill 的协作

- **`market-event-monitor`（本 skill）** — 5 大板块扫描 + 跨市场联动的底层数据范式
- **`hk-intraday-monitor-2026-06-02.md`** — 港股盘中 60min 监控，本文档是它的"午间 snapshot"姊妹篇
- **`us-postmarket-scan-2026-06-03.md`** — 美股盘后 06:00 cron，与 12:00 午间速报形成 18h 闭环
- **`cron-job-llm-binding`** — coverage design §10.6 登记了「12:00 midday recap」层
- **`stock-trading-system`** — 持仓 `us_risk_state.json` + `us_signal_latest.json` 的数据格式定义
