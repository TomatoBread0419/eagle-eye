# 早间速报 09:00 BJT 工作流

> 创建日期：2026-06-11 | 适用：工作日 09:00 cron 任务

## 数据源清单（45 秒内完成）

| 步骤 | 数据 | 源 | 耗时 | 备注 |
|------|------|-----|------|------|
| 1 | 当前时间确认 | `date '+%Y-%m-%d %H:%M:%S'` | 1s | 必须第一件事做，避免 time anchor drift |
| 2 | 美股三大指数 + 关键个股 | `qt.gtimg.cn/q=usINX,usDJI,usIXIC,usNVDA,usTSLA,...` | 10s | GBK 解码：`read().decode('gbk')` |
| 3 | 港股三大指数（预开盘参考） | `qt.gtimg.cn/q=hkHSI,hkHSTECH,hkHSCEI` | 5s | 09:30 开盘前返回的是前收价（涨跌=0） |
| 4 | 新闻（唯一可用英文/中文财经源） | wallstreetcn API `channel=global-channel&limit=30` | 15s | 去重：`dedup by title[:30]` 后再过滤今日文章 |
| 5 | 今日经济日历 | wallstreetcn 文中关键词过滤（CPI/PPI/非农/FOMC） | 0s | 合并到步骤 4，不做额外请求 |
| 6 | 持仓数据 | `subprocess Python from ~/.hermes/.env → Alpaca /v2/positions` | 15s | **比 us_trader.py 快得多**（15s vs 90-150s 超时风险） |

## 不可用数据源（已知阻断）

| 数据 | 阻断模式 | 替代 |
|------|---------|------|
| 日经 225 实时 | Yahoo 403 + Google SSL EOF + Nikkei.com SSL EOF + qt `pv_none_match` | 写「因中国大陆 IP 限制，暂无法获取日韩实时数据」|
| KOSPI 实时 | 同上 | 从 wallstreetcn 韩国出口/半导体数据做定性推断 |
| Google News RSS | SSL 超时/空响应（见 pitfall 22） | 已用 wallstreetcn 替代 |
| Yahoo v8 chart | 403（见 pitfall 23） | qt.gtimg.cn US 指数可用 |

## 持仓查询（Alpaca 快速路径）

不要再跑 `us_trader.py`（90-150s 且容易超时）。用以下模式直接查 `/v2/positions`：

```python
import subprocess, json
result = subprocess.run(['python3', '-c', '''
import urllib.request, json, os
with open(os.path.expanduser("~/.hermes/.env")) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ[k.strip()] = v.strip()
api_key = os.environ["ALPACA_API_KEY"]
secret_key = os.environ["ALPACA_SECRET_KEY"]
url = f"{os.environ.get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')}/v2/positions"
req = urllib.request.Request(url)
req.add_header("APCA-API-KEY-ID", api_key)
req.add_header("APCA-API-SECRET-KEY", secret_key)
resp = urllib.request.urlopen(req, timeout=15)
for p in json.loads(resp.read().decode()):
    print(f"{p['symbol']}|{p['qty']}|{float(p['current_price']):.2f}|{float(p['avg_entry_price']):.2f}|{float(p['unrealized_plpc'])*100:+.1f}%|{float(p['change_today'])*100:+.2f}%")
'''], capture_output=True, text=True, timeout=20)
print(result.stdout)
```

输出格式：`TICKER|QTY|现价|成本价|浮动盈亏%|今日涨跌%`

## 持仓风险快速评估（止损距离估算）

```
对于每只持仓：
  stop_pct = -15% if symbol in ['NVDA', 'TSLA', 'AVGO'] else -8%
  stop_price = avg_entry * (1 + stop_pct/100)
  dist_to_stop = ((current - stop_price) / current) * 100
```

重点关注距止损 <5% 的持仓 + 今日跌幅 >3% 的持仓（隔夜续跌风险）。

## 报告格式约束（≤600 字，纯文本，无 markdown）

```
🔔 早间速报 | 2026-06-XX 周X 09:00

🔴 [美股昨晚]  (红/黄/绿取决于指数涨跌)
• 三大：[数字 + %]
• Top 异动：[驱动因子 + 个股涨跌]

📅 [今日日程]
• 财报：TICK1/2/3
• 数据：CPI @ 20:30 (如有)
• 讲话：官员 @ XX:XX

🌏 [亚盘]
• 因中国大陆 IP 限制，暂无法获取实时日韩数据
• 定性参考：[wallstreetcn 今日亚洲新闻]

⚠️ [持仓预警]
• TICK1 现价XX / 距止损 X% / 今日-XX%
• TICK2 ...
```

## 常见陷阱

1. **wallstreetcn 三个 channel（global/us/hk）90% 内容重叠** → 只用 global-channel，按 title[:30] 去重
2. **us_trader.py 耗时不可控** → 永远用 Alpaca API 快速路径替代
3. **港股开盘前（09:00-09:30）qt 返回昨收，涨跌=0** → 不要写「港股平开」，写「港股昨日收盘」
4. **日韩数据全阻** → 不要花时间尝试不同 API（所有路径已测全部失败），直接写不可用
5. **CPI/PPI 发布日当天 wallstreetcn 可能有空档**（6/11 实测：CPI 发布次日 wallstreetcn 前 30 篇无一提及）→ 用 wallstreetcn 中的非通胀文章做定性推断
