# 航天板块 (space) 新增记录 — 2026-06-12

## 背景

用户询问 SpaceX 相关股票是否在鹰眼扫描中，以及是否有持仓。

## 发现

1. **无持仓**：6 只航天股全部清仓，zero positions
2. **幽灵挂单**：144 笔 stop sell order（每只 24 笔 × 6 只 = 144），全部 status=new。股票已卖出但 stop order 未自动取消，堆积在账上
3. **扫描池不含航天股**：原 78 只池中无商业航天标的

## 代码修改

### us_screener.py — UNIVERSE 新增 space 板块

```python
# 商业航天（SpaceX生态/卫星/发射）
'RKLB': 'space', 'ASTS': 'space', 'LUNR': 'space',
'PL': 'space', 'RDW': 'space',
```

### SECTOR_META

```python
'space': {'defense_rank': 5, 'div_yield': 'low', 'volatility': 'very_high'},
```

- defense_rank=5: 靠近 tech (5) 和 ai (6)，非防御板块
- volatility=very_high: 与 ai 同档

### DEFENSE_SECTOR_BONUS

```python
'space': -3  # 与 ai 同档，激进模式下不受惩罚
```

## 选股逻辑

| 股票 | 入选理由 | 价格 | 波动率 |
|------|---------|------|:---:|
| RKLB | SpaceX 直接竞争对手（小型发射） | $114.67 | 103% |
| ASTS | 星基手机直连，SpaceX 发射合作伙伴 | $97.59 | 131% |
| LUNR | 月球着陆器，NASA CLPS 承包商 | $30.66 | — |
| PL | 卫星影像 | $34.17 | — |
| RDW | 空间基础设施 | $17.09 | 188% |

排除的候选：SPCE（财务困难）、BKSY/SPIR/SATL（流动性差）

## 首轮扫描结果（2026-06-12 11:14 BJT）

| 股票 | 得分 | 1月涨幅 | 5日涨幅 | RSI | 波动率 | MACD |
|------|:---:|:--:|:--:|:--:|:--:|:--:|
| RDW | 32.6 | +47.9% | -20.2% | 53.0 | 188% | None |
| ASTS | — | +33.7% | -9.1% | 50.6 | 131% | None |
| RKLB | — | -2.5% | -4.4% | 44.6 | 103% | None |

RDW 进入全局 #5，但技术指标残缺（MACD/成交量信号未计算）

## 决策：延迟买入

**理由**：
1. 数据管线未完全验证 — MACD/成交量信号缺失
2. 仓位已 58%，超过 50% 目标
3. 真正缺口是 tech ($6,095) 和 ai ($5,718)
4. 三只航天股都在 5 日回调中，方向未确认
5. US 市场休市（BJT 12:00），市价单会挂成 new

**下次行动**：今晚 21:30 开盘后 cron 自动跑扫描，数据管线应产出完整指标。届时 AI 根据完整数据重新评估。

## 幽灵挂单详情

```
RKLB: 24笔 stop sell, 合计201股
ASTS: 24笔 stop sell, 合计201股
PL:   24笔 stop sell, 合计201股
RDW:  24笔 stop sell, 合计201股
LUNR: 24笔 stop sell, 合计201股
SPCE: 24笔 stop sell, 合计201股
总计: 144笔, 1206股
```

处理：不操作（Alpaca cancel 会死锁，无持仓不会触发，无害）
