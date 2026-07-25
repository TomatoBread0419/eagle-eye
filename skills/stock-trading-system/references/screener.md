# GARP 动量扫描器

## 扫描池

70 只美股（2026-06-04 扩展），覆盖 S&P 100 + AI 新贵：

- 科技 34 只：AAPL/MSFT/NVDA/GOOGL/AMZN/META/AVGO/TSLA/AMD/INTC/QCOM/TXN/MU/AMAT/CRM/ADBE/ORCL/CSCO/ACN/IBM/NFLX + **ARM/PLTR/SNOW/CRWD/NOW/PANW/UBER/DASH/SQ/SHOP/ZS/NET/DDOG**（新增 AI/云/安全）
- 消费 10 只：WMT/HD/COST/MCD/SBUX/NKE/DIS/PG/PEP/KO
- 金融 9 只：JPM/BAC/WFC/C/V/MA/GS/MS/BLK
- 医药 8 只：LLY/UNH/MRK/ABBV/PFE/TMO/DHR/ISRG
- 工业 7 只：CAT/BA/GE/HON/UPS/LIN/NEE
- 通讯 2 只：T/VZ

## 评分公式

```
score = ret_1m×0.5 + ret_3m×0.3 + ret_5d×0.2 + trend_bonus - rsi_penalty + sector_bonus
```

- `trend_bonus` = +3（价格 > MA20）/ +2（MA20 > MA50）
- `rsi_penalty` = -10（RSI>75）/ -20（RSI>85）
- `sector_bonus` = 由 market_events_latest.json 动态决定（不再硬编码）

## 候选过滤

- score ≥ 5
- RSI < 70
- 价格 > MA20
- 价格 > $10

## 输出

`us_watchlist.json`：
```json
{
  "buy_candidates": ["SYM1", "SYM2", ...],
  "all_ranked": [{"sym": "NVDA", "score": 28.5}, ...]
}
```

## Live RSI Override

扫描器在固定时间跑。如果 top-ranked 被 RSI filter 排除但之后 RSI 回落 → 手动查 live RSI，<70 即可买入。

## 超时配置

`~/.hermes/config.yaml`：
```yaml
cron:
  script_timeout_seconds: 300
```
默认 120s 对 50 只股票不够（实测 ~180s）。

## 已知陷阱

### `_get_daily_bars` 死代码（2026-06-04 trader 修，2026-06-05 screener 修）

screener 的 `__get_daily_bars` wrapper 内部调用了不存在的 `_get_daily_bars`（单下划线）。修复：改为调 `get_daily_bars(symbol, ALPACA_API_KEY, ALPACA_SECRET_KEY, days=limit)`。同样 `__get_us_price` → `get_us_price(symbol, ALPACA_API_KEY, ALPACA_SECRET_KEY)`。

**验证**：修复后跑 `python3 ~/.hermes/scripts/us_screener.py 2>&1 | tail -5`，应看到"成功 N 只"而非"失败 70 只"。

## 详细参考

- `cron-debugging-buffering-timeout.md` — 超时与输出缓冲
