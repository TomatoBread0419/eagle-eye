# 持仓审计工作流 (Holdings Audit Workflow)

建立于 2026-06-10。每次 AI 决策前应走完整流程。

## 流程

```
1. 跑扫描器 → us_watchlist.json
   python3 ~/.hermes/scripts/us_screener.py --mode normal

2. 跑持仓报告 → JSON
   python3 ~/.hermes/scripts/us_trader.py --report --mode normal

3. 止损覆盖审计
   查 Alpaca API: 有 open sell order OR stop order → 已保护
   注意：休市时止盈卖出的 market order status=new 会阻止后续 stop 挂单

4. 交叉对比
   ├── 持仓在扫描器 TOP20？→ 系统认可
   ├── 持仓触发 sell_reason？→ 立即卖出
   ├── 持仓 buy_score 多少？→ 负分/0分=不应持有
   ├── 板块排名 #1-2？→ 可能已无增值空间
   ├── 有硬止损保护？→ 风控到位
   └── 量价信号？→ 放量下跌=出货，缩量虚涨=假突破

5. 三档分类输出
   🟢 符合鹰眼标准 → 继续持有
   🟡 信号矛盾/偏弱 → 减仓或观察
   🔴 触发卖出信号 → 立即处理
```

## 优先级

1. 先补止损漏洞（裸奔 = 最大风险）
2. 再执行止盈卖出（系统已判定）
3. 最后评估弱信号（手动干预）

## 弱信号判断标准

| 条件 | 含义 |
|------|------|
| buy_score <= 0 | 如果现在重新扫描，不会推荐买入 |
| buy_score = 1 | 仅勉强过关，可能很快触发止损 |
| RSI > 75 且无放量上涨 | 高位风险，主力可能在出货 |
| RSI < 30 且放量下跌 | 跌势未止，不要抄底 |
| MACD 死叉 | 中期趋势转空 |
| 缩量虚涨 | 假突破，随时可能反转 |
| 板块龙头但放量下跌 | 头部出货信号 |

## 止损覆盖审计代码（含 open sell 检测）

```python
import json, urllib.request, sys
sys.path.insert(0, '$HOME/stock_trader')
from config import ALPACA_API_KEY, ALPACA_SECRET_KEY

HEADERS = {
    'APCA-API-KEY-ID': ALPACA_API_KEY,
    'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY,
}
BASE = 'https://paper-api.alpaca.markets/v2'

def api_get(path):
    req = urllib.request.Request(f'{BASE}{path}', headers=HEADERS)
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

positions = api_get('/positions') or []
orders = api_get('/orders?status=open&limit=50') or []

# 已有保护：stop order + open sell order（止盈卖单等开盘）
stop_symbols = {o['symbol'] for o in orders if o['type'] == 'stop' and o['side'] == 'sell'}
sell_symbols = {o['symbol'] for o in orders if o['side'] == 'sell' and o['type'] != 'stop'}
protected = stop_symbols | sell_symbols

no_stop = [p for p in positions if p['symbol'] not in protected]
if no_stop:
    print(f"⚠️ {len(no_stop)} 只裸奔: {[p['symbol'] for p in no_stop]}")
    # 有 open sell 的说明 --stops 已处理
    if sell_symbols:
        print(f"   {len(sell_symbols)} 只已有卖单等开盘: {sorted(sell_symbols)}")
else:
    print("✅ 所有持仓有保护")
```
