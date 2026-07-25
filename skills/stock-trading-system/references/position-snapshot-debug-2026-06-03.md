# 持仓快照调试日志 (2026-06-03)

本 session 用户问「查一下我的持仓」，暴露了 3 个 us_trader.py 接口错用问题。

## 复现路径

```bash
cd ~/.hermes/scripts
python3 -c "
import us_trader as t
acct = t.api_get('/v2/account')   # Bug 1: 路径双斜杠 → 静默 None
print(acct['equity'])              # Bug 2: NoneType 不可下标 → TypeError
"
```

## 三层 bug 链

### Bug 1: `api_get` 路径前导斜杠未规范化
- 调用方传 `/v2/account`（带前导斜杠）
- `_url_get` 拼成 `f'{TRADE_URL}{path}'` = `https://paper-api.alpaca.markets/v2/v2/account`
- 404 Not Found
- `api_get` 内部 `try/except` 吞了所有异常 → 返回 `None`
- 静默失败，调用方拿到 None 完全不知道是网络问题、404、还是 500

### Bug 2: `get_holdings()` 字段被映射为短名
- `us_trader.py` L181-188 把 Alpaca REST 原字段名 `avg_entry_price/current_price/market_value/unrealized_pl` 映射成 `avg/current/market/pnl/pnl_pct`
- 调用方若按 Alpaca REST 文档直接 `p['avg_entry_price']` → KeyError
- 这是设计决策（短名省字）但**没有文档**，新人必踩

### Bug 3: raw HTTP vs alpaca-py SDK
- us_trader.py 自己造了 `_url_get/_url_post/_url_del` 一套
- 重试、限流、错误分类全靠手写 → 容易漏（Bug 1 就是漏了 404 显式 fail）
- 用户原话 pushback：「alpaca不是有接口吗？我们现在在捣鼓什么？」
- 答：`alpaca-py` SDK 已成熟，pip 可装（无 native 依赖），下次重构优先换 SDK

## Caller 正确写法

```python
import us_trader as t

# 1. 用 get_portfolio() 而不是 api_get（它内部已经处理了 None）
acct, equity, cash = t.get_portfolio()   # 永远返回 (dict, float, float)
# 如果 api_get 失败 → equity=0, cash=0, 不会抛错

# 2. 用 get_holdings() 而不是自己 api_get('/positions')
pos = t.get_holdings()   # 短名字段: avg/current/market/pnl/pnl_pct

# 3. 用 get_open_stop_orders() / get_open_buy_orders() 而不是自己拉 /orders
stops = t.get_open_stop_orders()   # {sym: {id, stop_price, qty, submitted}}

# 4. 余额/挂单全用 helper，自己别拼路径
```

## 验证脚本

```bash
cd ~/.hermes/scripts && python3 -c "
import us_trader as t
acct, equity, cash = t.get_portfolio()
print(f'Equity: \${equity:,.2f}  Cash: \${cash:,.2f}  Util: {(equity-cash)/equity*100:.1f}%')
print()
for p in t.get_holdings():
    print(f\"{p['symbol']:6s} qty={int(p['qty']):>3} avg={p['avg']:>7.2f} cur={p['current']:>7.2f} pnl={p['pnl_pct']:>+6.2f}%\")
print()
for sym, o in t.get_open_stop_orders().items():
    print(f'STOP {sym} qty={int(o[\"qty\"])} stop=\${o[\"stop_price\"]:.2f}')
"
```

## 本 session 持仓快照（11:00 北京时间，市场已开）

```
Equity:  $102,621.87
Cash:    $84,985.92   (82.8% 闲置 ← 现金过高)
持仓 15 只（超 ≤5 上限 3 倍）:
  LONG 12: ORCL +24.76% (触 TP1 卖1/3)、GS +10.14%、AMAT +6.42%、
              AMD +5.39%、MSFT +5.43%、BA +3.49%、CAT +1.34%、
              BAC +0.88%、KO +0.20%、NVDA -2.81%、C -1.18%、JPM -4.37% (临止损)
  SHORT 3: BLK -2.83%、INTC +3.68%、QCOM -1.96%
挂单 11 STOP
```

→ 异常（卖 1 股 ORCL 触 TP1；JPM 临 -5% 硬止损；仓位过轻 17.2% vs 目标 30-60%）
→ 用户没要求动手，只问「查一下」，所以收尾给方案 A/B/C/D 不执行
