# 扫描池 UNIVERSE — us_screener.py v2 (2026-06-08)

来源：`~/.hermes/scripts/us_screener.py`

## 78只标的（S&P 100 + AI新贵 + 能源/军工/资源）

### 科技（21只）
AAPL, MSFT, NVDA, GOOGL, AMZN, META, AVGO, TSLA,
AMD, INTC, QCOM, TXN, MU, AMAT, CRM, ADBE, ORCL,
CSCO, ACN, IBM, NFLX

### AI/云/安全新贵（12只）— 2026-06-04 扩展
ARM, PLTR, SNOW, CRWD, NOW, PANW,
UBER, DASH, SQ, SHOP, ZS, NET, DDOG

### 消费/零售（10只）
WMT, HD, COST, MCD, SBUX, NKE, DIS, PG, PEP, KO

### 金融（9只）
JPM, BAC, WFC, C, V, MA, GS, MS, BLK

### 医药（8只）
LLY, UNH, MRK, ABBV, PFE, TMO, DHR, ISRG

### 工业（7只）
CAT, BA, GE, HON, UPS, LIN, NEE

### 通讯（2只）
T, VZ

### 能源（3只）— 2026-06-08 新增
XOM (ExxonMobil), CVX (Chevron), COP (ConocoPhillips)

### 军工（3只）— 2026-06-08 新增
LMT (Lockheed Martin), RTX (Raytheon), NOC (Northrop Grumman)

### 资源（2只）— 2026-06-08 新增
FCX (Freeport-McMoRan 铜), NEM (Newmont 金矿)

## 板块标签（v2 新增）

每只股票带 `sector` 标签，用于：
1. 事件驱动映射（伊朗冲突 → 能源/军工受益）
2. 防御模式板块加分
3. 输出统计板块分布

```python
SECTOR_META = {
    'tech':       {'defense_rank': 5, 'div_yield': 'low',  'volatility': 'high'},
    'ai':         {'defense_rank': 6, 'div_yield': 'low',  'volatility': 'very_high'},
    'consumer':   {'defense_rank': 3, 'div_yield': 'mid',  'volatility': 'low'},
    'finance':    {'defense_rank': 4, 'div_yield': 'mid',  'volatility': 'mid'},
    'pharma':     {'defense_rank': 2, 'div_yield': 'mid',  'volatility': 'low'},
    'industrial': {'defense_rank': 4, 'div_yield': 'low',  'volatility': 'mid'},
    'telecom':    {'defense_rank': 1, 'div_yield': 'high', 'volatility': 'low'},
    'energy':     {'defense_rank': 2, 'div_yield': 'high', 'volatility': 'mid'},
    'defense':    {'defense_rank': 1, 'div_yield': 'mid',  'volatility': 'low'},
    'resources':  {'defense_rank': 3, 'div_yield': 'mid',  'volatility': 'high'},
}
```

## 评分公式 v2（2026-06-08 重写）

```
基础分 = ret_1m × 0.4 + ret_3m × 0.25 + ret_short × 0.15

RSI 罚分（阈值随模式调整）:
  正常模式: RSI > 75 → -10
  防御模式: RSI > 65 → -10（更严格）
  通用: RSI > 85 → -20

均线加分:
  ma_uptrend → +3
  ma_cross → +2

波动率因子（v2 新增）:
  vol_20d < 20% → +3（低波动，稳定）
  vol_20d < 30% → +1（正常）
  vol_20d > 50% → -3（高波动，风险大）
  vol_20d > 40% → -1

防御模式板块加分（v2 新增）:
  telecom/defense → +5
  energy/pharma → +3~+4
  consumer → +2
  resources → +1
  finance/industrial → 0
  tech → -2
  ai → -3

板块缺配加分（v2 新增，读 us_portfolio.json）:
  缺口>3% → +5
  缺口>2% → +3
  缺口>1% → +2
```

## 模式系统（v4: AI 决策，非脚本自动判断）

**2026-06-08 变更：删掉脚本自动判断，改为 AI 指定模式。**

脚本只接受模式参数：`--mode aggressive|normal|cautious|defensive`

模式选择（AI 根据事件对持仓的实际影响判断，不是关键词匹配）：
- aggressive：仓位目标 50-70%，RSI 门槛 75，tech/ai 偏重
- normal：仓位目标 40-50%，RSI 门槛 75，均衡
- cautious：仓位目标 35-40%，RSI 门槛 70，防御板块加分
- defensive：仓位目标 30-35%，RSI 门槛 65，高波动过滤

## 买入门槛（v4: AI 决策）

- AI 根据模式、评分、波动率、板块缺配综合判断
- 不再有硬约束门槛（score >= 5 等由 AI 灵活掌握）
- 安全阀保留：回撤>12% 停买，单笔不超过现金 15%

## 已知局限
- 不含国债/REITs/大宗商品ETF
- 不含中概股（BABA/JD/PDD 等）
- 基本面因子（P/E、盈利增长）暂缺数据源
- 波动率用历史20日标准差，不含隐含波动率
