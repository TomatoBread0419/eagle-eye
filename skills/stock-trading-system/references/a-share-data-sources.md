# A股数据源详细参考

## 1. Sina Finance 日K线 API（已验证）

```bash
curl -s "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sz002429&scale=240&ma=5&datalen=30" -H "Referer: https://finance.sina.com.cn"
```

**参数说明：**
| 参数 | 值 | 说明 |
|------|-----|------|
| symbol | `sh600519` / `sz002429` | **必须小写** sh/sz + 6位代码 |
| scale | `240` | 240=日K，60=60分钟K，30=30分钟K |
| ma | `5` | 均线周期，返回 ma_price5 字段 |
| datalen | `30` | 返回K线条数 |

**返回字段（JSON数组）：**
```json
{"day":"2026-05-28","open":"12.310","high":"12.410","low":"11.810","close":"12.340","volume":"113798659","ma_price5":12.388,"ma_volume5":138954322}
```

- 数组正序排列（最早→最新）
- volume 单位：股（非手），除以10000得"万手"
- Referer header 是必须的，否则返回空

## 2. 腾讯财经 K线 API（已验证）

```bash
curl -s "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz002429,day,2026-01-01,2026-05-29,10,qfq"
```

**参数格式：** `param={symbol},{period},{start},{end},{count},{adjust}`

| 参数 | 值 | 说明 |
|------|-----|------|
| symbol | `sz002429` / `sh600519` | 小写 |
| period | `day` / `week` / `month` | K线周期 |
| start/end | `2026-01-01` / `2026-05-29` | 日期范围 |
| count | `10` | 最多返回条数（实际可能更少） |
| adjust | `qfq`（前复权）/ `hfq`（后复权）/ 空（不复权） |

**返回格式：**
```json
{"data":{"sz002429":{"qfqday":[["2026-05-28","12.310","12.340","12.410","11.810","113798659",...]]}}}
```

**字段顺序：** `[date, open, close, high, low, volume, ...]` — **注意：第二个字段是close不是high！** 与 Sina 的 open-high-low-close 顺序不同。

- 数组正序排列
- 响应 key 根据 period 不同：`qfqday` / `qfqweek` / `qfqmonth`
- HTTP（非HTTPS），但稳定性好
- 适合获取长时间段的前复权数据

## 3. 新浪个股新闻页面（GB2312编码）

```bash
curl -s "https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllNewsStock/symbol/sz002429.phtml" -H "Referer: https://finance.sina.com.cn"
```

**⚠️ 关键坑点：返回内容是 GB2312 编码！** 直接用 UTF-8 解码会得到乱码。

**正确解码方式：**
```python
data = response.buffer.read()  # 读取原始字节
text = data.decode('gb2312', errors='ignore')  # 或 'gbk'
```

在 shell 中用 `iconv -f gb2312 -t utf-8`，或在 Python 中：
```python
import sys
data = sys.stdin.buffer.read()
text = data.decode('gb2312', errors='ignore')
```

**提取新闻标题：**
```python
import re
titles = re.findall(r'<a[^>]*>(.*?)</a>', text)
for t in titles:
    clean = re.sub(r'<[^>]+>', '', t).strip()
    if clean and len(clean) > 10:
        print(clean)
```

**用途：** 获取某只A股的公司公告、新闻、研报标题列表。适合快速了解个股近期动态。

## 4. 数据源对比（A股）

| 来源 | 市场 | 数据类型 | 可靠性 | 需要认证 | 编码 |
|------|------|---------|:------:|:------:|:---:|
| Sina 日K API | A股 | K线+均线 | ★★★★★ | 否（需Referer） | UTF-8 |
| 腾讯 qfq K线 | A股 | 前复权K线 | ★★★★★ | 否 | UTF-8 |
| Sina 个股新闻 | A股 | 新闻标题 | ★★★★ | 否（需Referer） | **GB2312** |
| EastMoney K线 | A股 | K线 | ★★ | 否 | UTF-8 |
| 东方财富搜索 | A股/综合 | 新闻 | ★★ | 否 | UTF-8 |
| Google News RSS | 全球 | 新闻 | ★★★ (超时) | 否 | UTF-8 |

**推荐组合：** Sina日K（短期） + 腾讯qfq（长期/复权） + Sina个股新闻（公司动态）

## 5. 已知不可靠/不可用的A股数据源

| 来源 | 问题 |
|------|------|
| Yahoo Finance | 中国网络环境下连接超时 |
| Google News RSS | 从Termux发起经常超时（>60s），成功率不稳定 |
| EastMoney push2 实时报价 | 返回空或502 |
| Baidu 搜索 | JS渲染，curl抓不到有用内容 |
| 财联社 cls.cn | 需要JS渲染 |
