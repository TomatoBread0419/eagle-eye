# 港股盘中事件监控（HK Intraday Event Monitor）

> 2026-06-02 首次验证可用的 cron job 模板。每 60 分钟跑一次，09:30-16:00 HKT。
> 三步：恒指 → 板块异动 → A/H 联动 + 中概。多源交叉验证，触发条件才推。
> 6/3 12:00 午间速报 cron 实测：**新浪 hq.sinajs.cn 已全面 404**（`rt_hkHSI` / `s_sh000001` / `gb_baba` / `int_nasdaq` 全部挂掉），**全面改用腾讯 qt.gtimg.cn**（`hkHSI / hkHSTECH / hk00700 / s_sh000001 / s_sh000933 行业`）。Yahoo v8 chart 仍是港股个股 / 指数的备份。

## 触发条件

用户配置 `schedule: "*/60 9-15 * * 1-5"`（或类似），`deliver: weixin`，prompt 包含：
- 「恒指实时动态」/「港股板块异动」/「A/H 联动 + 中概股」
- 触发阈值：恒指 ±1.5% / 单板块 ±3% / 重大政策 / 突发新闻
- 输出格式：4 行简报（恒指 / 板块 / 中概 / 触发事件）+ 沙盘推演

## 数据源（全部 No-Key）

### 主源 A：腾讯 qt.gtimg.cn（**指数 + 行业 + 个股全覆盖，墙内可用**）—— 6/3 实测替代 Sina

```bash
# 港股指数：HSI / HSCEI / HSTECH（恒生科技）
curl -sL --max-time 8 "https://qt.gtimg.cn/q=hkHSI,hkHSCEI,hkHSTECH" \
  -H "Referer: https://stockapp.finance.qq.com/"

# 港股个股：腾讯 / 阿里 / 美团 / 小米 / 京东 / 网易 / 快手 / 百度
curl -sL --max-time 8 "https://qt.gtimg.cn/q=hk00700,hk09988,hk03690,hk01810,hk09618,hk09999" \
  -H "Referer: https://stockapp.finance.qq.com/"

# A 股指数 + 行业：上证 / 沪深300 / 创业板 / 科创50 / 医药 / 银行 / 消费 / 半导体
curl -sL --max-time 8 "https://qt.gtimg.cn/q=s_sh000001,s_sh000300,s_sz399006,s_sh000688,s_sh000933,s_sz399986,s_sz399997" \
  -H "Referer: https://stockapp.finance.qq.com/"
```

**港股指数字段顺序**（CSV with `v_hkHSI="..."` wrapper, gbk 编码）：
```
0:数字标识  1:中文名  2:英文代码  3:现价  4:昨收  5:今开
6:成交额(港元)  7:5日均量  8-9:买/卖盘  10:时间戳  11:涨跌额  12:涨跌幅%
13-16:最高/最低/振幅  17-19:52w 区间
```

**港股个股字段顺序**：
```
0:数字标识  1:名称  2:代码  3:现价  4:昨收  5:今开
6:成交额(港元)  10:时间戳  11:涨跌额  12:涨跌幅%
13-14:最高/最低
```

**A 股指数 / 行业字段顺序**（`v_s_sh000001="..."` wrapper, gbk 编码）：
```
0:数字标识  1:中文名  2:代码  3:当前价  4:涨跌额  5:涨跌幅%
6:成交量  7:成交额  8-9:买/卖盘
```

**为什么 qt.gtimg.cn 是 6/3 实测的更优源：**
- 覆盖全面：A股（s_sh000001 / s_sz399006 / s_sh000688 / s_sh000852 中证1000）、港股指数（hkHSI / hkHSTECH / hkHSCEI）、港股个股（hk00700 / hk09988 / hk03690 / hk01810 等）、A 股行业指数（s_sh000933 医药 / s_sz399986 银行 / s_sz399997 消费）一次性拿全
- 3 秒刷新（与 Sina 实时流同量级）
- 港股个股 Sina 走 `rt_hk00700` 是空字符串，但 qt.gtimg.cn 的 `hk00700` 是真数据
- 解析时**必须**用字段 4（昨收）做基点算涨跌幅，**不要**用字段 5（今开）做基点

**Sina hq.sinajs.cn 6/3 已全面 404 弃用**：原 `rt_hkHSI` / `rt_hkHSCEI` / `rt_hkHSTECH` / `gb_baba` / `gb_jd` / `s_sh000001` / `int_nasdaq` 全部 HTTP 404。

### 主源 B：Yahoo Finance 8 API（无 key、墙内可用，**个股首选**）

```python
import urllib.request, json, datetime
HEADERS = {'User-Agent': 'Mozilla/5.0'}

def yf_chart(sym, interval='1d', rng='2d'):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval={interval}&range={rng}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.load(r)
    m = d['chart']['result'][0]['meta']
    return {
        'symbol':   m['symbol'],
        'price':    m['regularMarketPrice'],
        'prev':     m.get('chartPreviousClose') or m.get('previousClose'),
        'open':     d['chart']['result'][0]['indicators']['quote'][0].get('open',[None])[0],
        'high':     m.get('regularMarketDayHigh'),
        'low':      m.get('regularMarketDayLow'),
        'ts':       m['regularMarketTime'],  # UTC
    }
```

**覆盖标的：**
| 类别 | 符号 | 备注 |
|------|------|------|
| 恒指 | `^HSI` | HKSE 指数；interval=1m 取日内 |
| 国企指数 | `^HSCE` | 港股国企 |
| 恒生科技指数 | `^HSTECH` | **板块温度计首选**（Yahoo 子指数稀疏时用这个） |
| 互联网科技 | `0700.HK 3690.HK 1810.HK 9618.HK 9999.HK 9888.HK 1024.HK 9988.HK 2382.HK` | 自建板块篮子 |
| 消费/餐饮 | `0291.HK 9633.HK 6862.HK 0322.HK 1456.HK 1928.HK` | 自建篮子 |
| 金融(银行) | `1398.HK 0939.HK 3988.HK 1288.HK 3328.HK 0005.HK` | |
| 保险 | `1299.HK 2318.HK 2601.HK 1339.HK 2628.HK` | |
| 地产 | `1109.HK 0016.HK 1997.HK 0001.HK 0012.HK 0688.HK` | |
| 医药 | `1093.HK 1177.HK 2269.HK 1099.HK 1801.HK` | |
| 中概 ADRs | `BABA JD BIDU NIO XPD LI PDD TCEHY` | 美股交易时段才活跃 |
| A股参考 | `000300.SS 000001.SS 399001.SZ` | CSI300 / SSE / SZSE 综合 |

### 备源（cross-verify，必须 ≥2 源）

| 来源 | URL | 用途 | 解析 |
|------|-----|------|------|
| Investing.com | `https://www.investing.com/indices/hang-sen-40` | HSI 价格 + % | regex `(\d{2},\d{3}\.\d{2})` + `([+-]?\d+\.\d{1,2})\s*%` |
| CNBC | `https://www.cnbc.com/quotes/.HSI` | HSI 多档位（prev/high/low/current） | regex `25[,.]?\d{3}[.,]\d{2}`，取 unique set |

CNBC 一次返回的多个值（示例 2026-06-02 11:32 HKT）：
```
25,398.18  ← prev close
25,644.03  ← current
25,812.49  ← day high
25,394.64  ← day low
```
- 用 `prev` vs `current` 算 % change
- 用 `high` vs `prev` 算「日内峰值」%（用于 ±1.5% 触发判断）
- 用 `current` vs `prev` 算「当前 %」（用于实时数字）

## 关键坑点

### 1. `chartPreviousClose` 可能 stale
同一 `^HSI` 调用两次：
- 第一次：`chartPreviousClose=25398.18` → 算 % 偏大
- 第二次：`chartPreviousClose=25599.45` → 算 % 偏小
- **6/3 09:31 复现：** Yahoo 报 `prev=25328.23`，与 Sina 权威 昨收=26038.32 偏差 710 点

**根因：** Yahoo 跨时区切换时 cache 未刷新。**修复（按优先级，6/3 12:00 更新）：**
1. **首选 腾讯 qt.gtimg.cn `hkHSI`** 拿权威昨收 + 实时价（6/3 实测替代 Sina）
2. Yahoo 用 5m interval 取日内 open 字段作为参考
3. CNBC/Investing.com 做 ground truth 兜底

### 2. 触发判断用「日内峰值」不是「当前价」
用户阈值 ±1.5% 指的是「从昨收到日内任意时点的最大偏离」。HSI 高点 25,812 vs 昨收 25,398 = +1.63% → **触发**。但当前 25,644 = +0.97% → 不触发。**报告必须显示「高点触发」但「现价已回落」**，避免误以为当前仍在阈值外。

### 3. 板块判定：恒生科技指数 + 自建篮子组合
HK 板块子指数（`3011.HK 3028.HK 3008.HK` 等）数据稀疏，Yahoo 返回的 `regularMarketPrice` 经常是 ETF 净值或 noise。**首选 Sina `rt_hkHSTECH`**（现成板块温度计，每 3 秒刷新），再用自建篮子做交叉验证：
```python
def sector_pct(symbols):
    pcts = []
    for s in symbols:
        d = yf_chart(s)
        if d['price'] and d['prev']:
            pcts.append((d['price']-d['prev'])/d['prev']*100)
    return sum(pcts)/len(pcts) if pcts else 0
```
触发条件：`|sector_pct| >= 3%` 或 `|HSTECH 涨跌| >= 3%`。

### 4. sandbox 限制
- **`execute_code` 在 cron 沙箱里被 BLOCKED**（见 `stock-trading-system` §11.1a.2）。只能用 `terminal` 跑。
- **`/tmp` 不可写**（Termux 权限）：所有临时文件用 `~/tmp/` 替代。
- **不要用 `cat > file <<EOF`** —— 用 `terminal` 写文件 + `python3 << 'PYEOF'` 处理多行脚本。

### 5. Sina `rt_hk*` 指数 vs 个股流不可混用（6/3 验证）—— **6/3 全网 404，整体弃用**
| 前缀 | 标的 | 状态 |
|------|------|------|
| ~~`rt_hkHSI` / `rt_hkHSCEI` / `rt_hkHSTECH` / `rt_hkHSCCI`~~ | ~~港股指数~~ | ~~✅ 可用~~ ❌ 2026-06-03 全 404 |
| ~~`rt_hk0700` / `rt_hk9988` / `rt_hk3690`~~ | ~~港股个股~~ | ~~❌ 返回空字符串~~ |
| ~~`gb_baba` / `gb_jd` / `gb_bidu` / `gb_pdd` / `gb_ntes`~~ | ~~美股中概 ADR~~ | ~~✅ 可用（隔夜 ET 收盘）~~ ❌ 2026-06-03 全 404 |
| **`hkHSI` / `hkHSTECH` / `hkHSCEI`（qt.gtimg.cn）** | **港股指数** | **✅ 替代 Sina, 6/3 实测** |
| **`hk00700` / `hk09988` / `hk03690` / `hk01810`（qt.gtimg.cn）** | **港股个股** | **✅ 替代 Sina 个股流空字符串问题** |
| **`s_sh000001` / `s_sh000933` / `s_sz399986`（qt.gtimg.cn）** | **A 股指数 + 行业** | **✅ 新增能力** |

**新双源策略（6/3 12:00 后）：** A 股/港股指数/港股个股/行业指数全部走 qt.gtimg.cn；美股/欧洲指数走 Yahoo v8 chart；中概 ADR 隔夜无 API，需走 Google News「BABA 隔夜 涨」拿延迟数据。

## 输出格式（≤400 字）

```
🔔 港股 [HH:MM]
恒指：[点位] [±%]
成交：[XX 亿，或「无数据」]
板块异动：[板块1] ±X% [原因1行]；[板块2] ±X%
中概：[BABA x.x% / JD y.y% / BIDU z.z%]
触发事件：[一句话；无则写「无」]
```

未触发时：
```
🔕 港股 [HH:MM] 无重大事件
```

## 沙盘推演（A 股 13:00 开盘方向）

读 `000300.SS`（CSI300）、`000001.SS`（SSE）、`399001.SZ`（SZSE）的当前变化做 A 股开/收盘方向参考。**联动规则：**
- HSI 科技/消费板块领涨 + A 股对应板块开盘前走势稳 → A 股开盘后对应板块补涨 0.5-1.5%
- HSI 单板块异动 > 5% → 高度传染，A 股开盘 1h 内必有反应
- HSI 异动 < 1% 但 A 股当前涨幅 > 1% → A 强 H 弱，A/H 倒挂，不传导

报告最后一节「沙盘推演」必须明确写方向 + 幅度区间，不能只写「待观察」。

## 验证步骤

```bash
# 主源 A：新浪指数流（权威实时）
curl -sL --max-time 8 "https://hq.sinajs.cn/list=rt_hkHSI,rt_hkHSTECH" \
  -H "Referer: https://finance.sina.com.cn"
# 解析：去 var hq_str_= 包裹 → 逗号分隔 → fields [2]=今开 [3]=昨收 [5]=低 [6]=现价 [7]=涨跌 [8]=%

# 主源 B：Yahoo v8 chart（个股 + 指数交叉）
curl -sL "https://query1.finance.yahoo.com/v8/finance/chart/^HSI?interval=5m&range=1d" \
  -A "Mozilla/5.0" | python3 -c "
import json, sys, datetime
d = json.load(sys.stdin)
q = d['chart']['result'][0]['indicators']['quote'][0]
m = d['chart']['result'][0]['meta']
print('latest close:', q['close'][-1])
print('open today:', q['open'][0])
print('prev_close:', m['chartPreviousClose'])
print('pct vs prev:', f'{(q[\"close\"][-1] - m[\"chartPreviousClose\"]) / m[\"chartPreviousClose\"] * 100:+.2f}%')
print('day high:', m['regularMarketDayHigh'])
print('pct high vs prev:', f'{(m[\"regularMarketDayHigh\"] - m[\"chartPreviousClose\"]) / m[\"chartPreviousClose\"] * 100:+.2f}%')
"

# 备源 1：Investing.com
curl -sL "https://www.investing.com/indices/hang-sen-40" -A "Mozilla/5.0" \
  -o ~/tmp/inv.html
python3 -c "
import re
with open('~/tmp/inv.html') as f: x = f.read()
print('price:', re.search(r'\d{2},\d{3}\.\d{2}', x).group(0))
print('pct:', re.search(r'[+-]?\d+\.\d{1,2}\s*%', x).group(0))
"

# 备源 2：CNBC
curl -sL "https://www.cnbc.com/quotes/.HSI" -A "Mozilla/5.0" \
  -o ~/tmp/cnbc.html
python3 -c "
import re
with open('~/tmp/cnbc.html') as f: x = f.read()
nums = sorted(set(re.findall(r'25[,.]?\d{3}[.,]\d{2}', x)))
print('CNBC HSI nums:', nums)
"
```

## 实际跑通示例

### 2026-06-02 11:32-11:43 HKT（Yahoo + CNBC 路径）
**触发：** HSI 日内高 +1.63% 触阈值 + 互联网科技板块 +4.44% / 消费板块 +3.65% 双双 >3%

**实际输出：**
```
🔔 港股 11:43
恒指：25,644 +0.97%（盘中最高 25,812，+1.63% 触发 ±1.5% 阈值；昨收 25,398）
成交：Yahoo 未返回实时额
板块异动：
  🟢 互联网科技 +4.4% (Meituan +13.8% / Tencent +8.7% / Alibaba +6.5%)
  🟢 消费/餐饮 +3.6% (Sands China +4.9% / Tingyi +6.6%)
中概：NIO +6.8% / PDD +3.3% / BABA +0.9% / JD +0.9% / BIDU -2.2% / LI -3.1% / TCEHY +1.3%
触发事件：港股科技/消费板块爆发；新闻源受限，疑似 AI/平台经济政策预期+财报抢筹
沙盘推演：A 股 13:00 开盘后科技/消费/新能源车板块（恒生科技 4 大权重对标）补涨 0.5-1.5%
```

**交叉验证：** Yahoo + CNBC 报价一致（HSI ~25,644，+0.96%），2 源同向通过。

### 2026-06-03 09:30-09:33 HKT（Sina + Yahoo 路径，**无触发**）
**实际输出：**
```
🔕 港股 09:33 无重大事件
```

**Sina 权威数据：**
- HSI 现价 25,868.60，昨收 26,038.32，**涨跌 -0.65%**（不触发 ±1.5%）
- 恒生科技 现价 5,142.09，昨收 5,199.28，**涨跌 -1.10%**（不触发 ±3%）
- 成交额 9.74 亿港元（开早盘，初始成交）

**Yahoo 数据交叉（验证 Sina）：**
- HSI dayHigh 26,045.07 / dayLow 25,394.64，区间包含 Sina 现价
- 但 `chartPreviousClose=25328.23` stale——**若用 Yahoo prev 算 % 会误报 +2.80%**
- 中概 ADR 隔夜：JD +3.64% / BABA +4.32% / BIDU +3.26% / PDD +1.08% / NTES +1.20%（全数 🟢，隔夜强势但今日港股未兑现高开）

**A 股交叉：** 沪指 -0.17% / 深成 +0.36% / 创业 +0.82%（A 股 09:30 开盘）——A 强 H 弱，A/H 倒挂，不传导。

**沙盘推演：** HSI 早盘微跌不构成触发，但中概 ADR 隔夜 +3% 普遍 → 港股科技板块 09:30-10:00 仍有补涨可能，重点观察 10:00 第一根 30m K 线是否突破 -0.5%。A 股 13:00 开盘方向跟随美股 ADR，开盘初期科技/新能源车板块或补涨 0.3-0.8%。

## 已知局限

- **新闻催化源受限**：Google News / Reuters / Bing 在 Termux 网络下抓不到独家 HK 财经新闻全文，催化归因只能基于盘面 + 板块领涨股的近期新闻 RSS 标题（多数为 1-2 周前）
- **成交额部分缺失**：Yahoo `regularMarketVolume` 对指数（^HSI）始终返回 0；但 **qt.gtimg.cn `hkHSI` 字段 6 是真实成交额**（港元），早盘 09:33 实测 9.74 亿
- **A/H 联动数据延迟**：Yahoo A 股指数的 `regularMarketPrice` 在 A 股开盘前会用昨收 + 估算，A 股盘中才实时
- ~~**Sina 个股流付费墙**：`rt_hk*` 指数免费，`rt_hk0700` 等个股前缀不返回数据；个股要绕道 Yahoo v8 chart~~ → **6/3 已解决：qt.gtimg.cn `hk00700` 真实个股流**（参见 6a/6b 坑点）
- **南向资金 / 涨停跌停计数 API 缺失**：见 `cn-midday-briefing-2026-06-03.md` §已知局限

## 与其他 skill 的协作

- **`cron-job-llm-binding`** — 此监控 cron 已在它的 §10.6 coverage design 里登记（09:30-16:00 HKT, 60min）
- **`stock-trading-system`** — 同样用 Yahoo Finance API，但 `stock-trading-system` 关注 US；A/H 联动分析时可参考其数据源可靠性矩阵 §10.6
- **`market-news-sources.md`** (在 `stock-trading-system` 下) — 备用新闻源
