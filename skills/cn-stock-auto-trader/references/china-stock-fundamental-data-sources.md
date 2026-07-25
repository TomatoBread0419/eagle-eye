# A股基本面数据源（补充参考）

除实时行情外的深度财务数据获取方式。所有数据均来自公开免费接口，无需API Key。

---

## 1️⃣ 资产负债表 — Sina Finance（最完整）

**URL**:
```
https://money.finance.sina.com.cn/corp/go.php/vFD_BalanceSheet/stockid/{CODE}/ctrl/part/displaytype/4.phtml
```

**示例**: 东方锆业(002167)
```
https://money.finance.sina.com.cn/corp/go.php/vFD_BalanceSheet/stockid/002167/ctrl/part/displaytype/4.phtml
```

**返回**: 完整HTML表格，5列（最新4个季度+上年同期），单位**万元**。包含：
- 流动资产（货币资金、应收账款、存货、应收款项融资等）
- 非流动资产（固定资产、无形资产、商誉等）
- 流动负债（短期借款、应付账款等）
- 非流动负债（长期借款、递延收益等）
- 所有者权益（股本、资本公积、未分配利润等）

**提取方法**: Python `re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL)` → 找行数最多的表（通常>50行）→ 逐行解析 `<t[dh]>`

⚠️ Sina页面编码为GBK，需 `raw.decode('gbk', errors='replace')`

---

## 2️⃣ 利润表 — Sina Finance

**URL模式**:
```
https://money.finance.sina.com.cn/corp/go.php/vFD_IncomeStatement/stockid/{CODE}/ctrl/part/displaytype/4.phtml
```

与资产负债表同结构。也可通过主页面参数访问：
```
https://money.finance.sina.com.cn/corp/go.php/vFD_FinanceSummary/stockid/{CODE}/displaytype/4.phtml?source=lrb
```

---

## 3️⃣ 现金流量表 — Sina Finance

```
https://money.finance.sina.com.cn/corp/go.php/vFD_FinanceSummary/stockid/{CODE}/displaytype/4.phtml?source=llb
```

---

## 4️⃣ 财务摘要（多期对比）— 东方财富 API ✅ 已验证可用

**请求**:
```
GET https://datacenter-web.eastmoney.com/api/data/v1/get
Params:
  reportName: RPT_LICO_FN_CPD
  columns: SECURITY_CODE,SECURITY_NAME_ABBR,DATATYPE,TOTAL_OPERATE_INCOME,PARENT_NETPROFIT,BASIC_EPS,WEIGHTAVG_ROE,BPS,YSTZ,SJLTZ,XSMLL
  filter: (SECURITY_CODE="{CODE}")
  pageNumber: 1
  pageSize: 6
  sortTypes: -1
  sortColumns: NOTICE_DATE       # 注意：必须用 NOTICE_DATE，用 REPORT_DATE 会报错！
```

**已知字段**:
| 字段 | 含义 |
|------|------|
| DATATYPE | 报告期标签（如 "2026年 一季报"） |
| TOTAL_OPERATE_INCOME | 营业收入 |
| PARENT_NETPROFIT | 归母净利润 |
| BASIC_EPS | 基本每股收益 |
| WEIGHTAVG_ROE | 加权ROE(%) |
| BPS | 每股净资产 |
| YSTZ | 营收同比增速(%) |
| SJLTZ | 净利同比增速(%) |
| XSMLL | 毛利率(%) |
| YSHZ | 营收环比增速(%) |
| SJLHZ | 净利环比增速(%) |
| MGJYXJJE | 每股经营现金流 |

**注意**: NOT_ALL 参数不生效，必须显式列出需要的 columns。

---

## 5️⃣ 综合行情指标 — Tencent gtimg 接口 ✅ 最详细

**URL**: 
```
https://web.sqt.gtimg.cn/q=sz{CODE}
```
(深市加 `sz`，沪市加 `sh`)

**返回**: 以 `~` 分隔的多字段字符串。关键字段索引（0-based）：

| 索引 | 含义 | 示例(东方锆业) |
|:----:|:----:|:--------------:|
| 1 | 股票名称 | 东方锆业 |
| 2 | 代码 | 002167 |
| 3 | 现价 | 19.51 |
| 4 | 昨收 | 17.74 |
| 5 | 今开 | 19.51 |
| 6 | 成交量(手) | 399816 |
| 30 | 时间戳 | 20260623114251 |
| 31 | 涨跌额 | 1.77 |
| 32 | 涨跌幅(%) | 9.98 |
| 33 | 最高 | 19.51 |
| 34 | 最低 | 19.51 |
| 37 | 成交额(万元) | 78004 |
| 38 | 换手率(%) | 5.27 |
| 39 | 市盈率(动) | 278.96 |
| 43 | 振幅(%) | 0.00 |
| 44 | 流通市值(亿) | 148.02 |
| 45 | 总市值(亿) | 151.14 |
| 46 | 市净率 | 8.49 |
| 47 | 涨停价 | 19.51 |
| 48 | 跌停价 | 15.97 |
| 49 | 量比 | 1.21 |
| 52 | 市盈率(静) | 186.63 |
| 53 | 市盈率(TTM) | 286.34 |
| 62 | 52周最高 | 57.98 |
| 63 | 52周最低 | 32.27 |
| 65 | 每股净资产 | 3.04 |
| 72 | 流通股本 | 758712963 |
| 73 | 总股本 | 774673300 |

编码：GBK，需 `raw.decode('gbk')`。

---

## 6️⃣ 实时行情 — 新浪 sinajs

**URL**: 
```
https://hq.sinajs.cn/list=sz{CODE},sh{CODE}
```

**Referer 头**: `https://finance.sina.com.cn`（必需）

**返回**: CSV格式，GBK编码。字段顺序：
```
0=名称, 1=今开, 2=昨收, 3=现价, 4=最高, 5=最低, 8=成交量(手), 9=成交额, 30=日期, 31=时间
```

---

## 7️⃣ 新闻搜索 — Google News RSS（需 DoH 绕过 DNS 劫持）

```python
import urllib.parse
query = urllib.parse.quote('东方锆业 锆 涨价')
url = f'https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN'
```

返回标准RSS XML，解析 `<title>` 标签获取新闻标题。在DNS劫持环境下（如中国移动网络），依赖 `dns-hijack-fix` 技能的 DoH 回退机制。

---

## 8️⃣ 日K线 — 东方财富（复权数据）

**URL**:
```
https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.{CODE}&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57&klt=101&fqt=1&end=YYYYMMDD&lmt=N
```

| 参数 | 含义 |
|------|------|
| secid | 0=深市, 1=沪市，拼接代码 |
| klt=101 | 日K线 |
| fqt=1 | 前复权 |
| lmt | 返回条数 |

返回格式：`"2026-06-23,19.51,19.51,19.51,19.51,399816,780040411.19,9.98"`
字段：日期,开盘,收盘,最高,最低,成交量(手),成交额,涨跌幅

---

## 通用注意事项

1. **DNS劫持**: 所有国内金融站点都可能被运营商DNS劫持到 `198.18.0.x`。依赖 `~/.local/lib/python3.13/site-packages/sitecustomize.py`（dns-hijack-fix skill）的DoH自动回退
2. **编码**: Sina系页面统一用 `gbk`，东方财富API用 `utf-8`
3. **Referer头**: 部分API需要正确Referer，如新浪 `hq.sinajs.cn` 需 `Referer: https://finance.sina.com.cn`
4. **时间**: 东方财富 API 的排序参数必须用 `NOTICE_DATE`（公告日期），用 `REPORT_DATE`（报表日期）会报 `9501` 错误
