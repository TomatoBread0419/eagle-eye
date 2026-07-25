# Kelly 仓位整合执行记录 (2026-06-16)

## 背景
- 整合前：27只持仓，平均每只~2%，总仓位41.3%，现金58.7%闲置
- 凯利目标：8只 × 11.6% = 92.8%仓位
- 用户纠正：不是4-5只（50%÷11.6%），而是8-9只（用户要高利用率）

## 执行步骤

### 1. 排名选股（错误做法 → 正确做法）
**错误**：按浮盈排名取TOP8，保留了4只板块龙头（JPM/GS/BAC/PANW）
**正确**：按浮盈排名取TOP12-15 → 剔除板块#1-2龙头 → 从剩余取TOP8-9

**⚠️ 第二次错误（2026-06-17）**：剔除龙头后选出8只，但全是家喻户晓的大盘股（INTC/AMAT/QCOM/PANW/CRWD/MRVL/DDOG/TXN）。用户反馈"怎么感觉你挑的这8只股票我都叫得出名字呢这么大名鼎鼎的也能叫成长股吗"。

**根因**：扫描池只有83只，全是大盘蓝筹。从里面挑来挑去，怎么挑都是家喻户晓的名字。真正符合"AI投机者"风格的中小盘高成长股不在池子里。

**正确做法**：
1. 先扩充扫描池（加入SMCI/IONQ/SOUN/COHR/AXTI等中小盘成长股）
2. 再从扩充后的池子中按龙头回避+凯利选股

### 2. 取消止损单
```python
# 取消所有open orders（为清仓做准备）
orders = requests.get(f'{base}/v2/orders?status=open', headers=headers).json()
for o in orders:
    requests.delete(f'{base}/v2/orders/{o["id"]}', headers=headers)
```
⚠️ 取消后状态变为 `pending_cancel`，不是立即 `canceled`

### 3. 等待取消完成
- 闭市时 pending_cancel 会持续到开盘
- 必须等开盘后才能执行清仓
- 等待时间：至少5-8秒（开盘时段）

### 4. 清仓卖出
```python
sell_syms = ['CAT','MS','LIN','JPM','MA','MCD','DDOG','LMT','UNH','WMT','CSCO','UPS','SNOW','ABBV','LLY','IBM','KO']
for sym in sell_syms:
    pos = requests.get(f'{base}/v2/positions/{sym}', headers=headers).json()
    requests.post(f'{base}/v2/orders', headers=headers, json={
        'symbol': sym, 'qty': pos['qty'], 'side': 'sell',
        'type': 'market', 'time_in_force': 'day'
    })
```

### 5. 加仓到凯利目标
```python
target = equity * 0.116  # 每只目标金额
for p in positions:
    need = target - float(p['market_value'])
    shares_to_buy = int(need / float(p['current_price']))
    requests.post(f'{base}/v2/orders', headers=headers, json={
        'symbol': p['symbol'], 'qty': str(shares_to_buy), 'side': 'buy',
        'type': 'market', 'time_in_force': 'day'
    })
```

### 6. 设置止损（波动率分档）
```python
# 板块快捷法
STOPS = {
    'BAC': 0.08, 'JPM': 0.08, 'C': 0.08, 'GS': 0.08,  # 金融 8%
    'ARM': 0.10, 'AMAT': 0.10, 'MU': 0.10, 'PANW': 0.10,  # 半导体/网安 10%
}
for sym, pct in STOPS.items():
    current = get_current_price(sym)
    stop_price = round(current * (1 - pct), 2)
    requests.post(f'{base}/v2/orders', headers=headers, json={
        'symbol': sym, 'qty': str(qty), 'side': 'sell',
        'type': 'stop', 'stop_price': str(stop_price), 'time_in_force': 'gtc'
    })
```

## 结果
- 整合前：27只 × ~2% = 41.3%仓位
- 整合后：8只 × ~11.5% = 91.1%仓位
- 现金：从58.7%降至8.9%

## 教训
1. **选股要同时应用龙头回避**：不能只看浮盈，要剔除板块#1-2
2. **Alpaca pending_cancel陷阱**：闭市取消止损→开盘才能卖
3. **止损分档用板块快捷法**：金融8%，科技10%
4. **用户偏好投机成长股**：不要选稳定蓝筹，不要家喻户晓的大盘股
5. **扫描池局限性**：83只全是大盘蓝筹，无法满足投机需求，需扩充
