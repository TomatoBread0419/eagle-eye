# 行情数据源

## 美股

**主源：Alpaca Market Data v2**
- 端点：`https://data.alpaca.markets/v2/stocks/{SYMBOL}/bars`
- 日K：`timeframe=1Day&feed=iex&start={date}&end={date}` → 免费层 60+ bars
- 小时K：`timeframe=1Hour&limit=100` → 免费层仅 ~4 bars（已弃用）
- **字段名是短名**：`c`=close, `h`=high, `l`=low, `o`=open, `v`=volume, `t`=timestamp
- **`days=120` 陷阱**：超出 limit 时 Alpaca 返回最早数据而非最新 → 用 `days=85`

**备用：Sina Finance**
- 实时：`https://hq.sinajs.cn/list=usAAPL`
- 仅交易时段有数据

## A股

- 实时：Sina `hq.sinajs.cn/list=sh600519`（GBK 编码，需 `Referer`）
- 日K：Sina `money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData`
- 备用日K：EastMoney `push2his.eastmoney.com/api/qt/stock/kline/get`
- 前复权长周期：Tencent `web.ifzq.gtimg.cn/appstock/app/fqkline/get`

## 港股

- 实时：Sina `hq.sinajs.cn/list=hk00700`
- 备用：Yahoo Finance v8, qt.gtimg.cn

## 可靠性矩阵

| 源 | 市场 | 可靠性 |
|----|------|:---:|
| Alpaca IEX (日K+日期) | 美股 | ★★★★ |
| Alpaca quotes | 美股 | ★★★★ |
| Sina Finance K-line | A股 | ★★★★★ |
| Tencent Finance qfq | A股 | ★★★★★ |
| EastMoney | A股 | ★★ |
| EastMoney | 美股 | 已弃用 |

## 详细参考

- `a-share-data-sources.md` — A股数据源完整 API
- `data-source-reliability.md` — 可靠性矩阵与 DNS 劫持应对
- `position-snapshot-debug-2026-06-03.md` — API 路径 Bug 记录
