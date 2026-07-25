# Dynamic Kelly Position Sizing (2026-06-17, updated v6)

## 函数位置
`~/.hermes/scripts/us_screener.py` → `kelly_position_sizes()`

## v6 更新: 校准参数集成

函数现在自动读取 `~/stock_trader/calibrated_params.json`:

```python
# 校准参数来源 (优先级)
1. calibrated_params.json → kelly 字段 (每周六calibrator.py自动生成)
2. 默认参数 (无校准文件时回退)

# 校准后的参数
sig_k = kelly_cal.get('sigmoid_k', 0.12)      # sigmoid斜率
sig_mid = kelly_cal.get('sigmoid_midpoint', 12) # sigmoid中点
atr_slope = kelly_cal.get('atr_to_odds_slope', 0.3)  # ATR→赔率斜率
atr_intercept = kelly_cal.get('atr_to_odds_intercept', 1.0)  # ATR→赔率截距
target_alloc = kelly_cal.get('target_alloc', 0.85)  # 总仓位目标(85%,非95%)
max_pct = kelly_cal.get('max_pct_large_cap', 0.20)  # 单只上限
```

## 算法
```
1. score → sigmoid → p (胜率)
   p = 1/(1+exp(-k*(score-midpoint)))

2. ATR% → 赔率 b
   b = max(1.2, min(3.5, intercept + atr_pct * slope))

3. 凯利: f* = (bp - q) / b
4. 半凯利: f*/2
5. 归一化: 总仓位 = target_alloc (85%)
6. 限幅: 单只 min_pct(3%) ~ max_pct(20%)
```

## 实测结果 (2026-06-17)
```
ASTS +28分, ATR 8.0% → p=87%, b=3.4, 凯利19.3%
NVDA +22分, ATR 4.5% → p=77%, b=2.4, 凯利16.7%
DIS  +13分, ATR 1.9% → p=53%, b=1.6, 凯利3.2%
总仓位: 95.1%
```

## 与旧方案对比
```
旧: 所有标的统一分11.6% (等权, 不是凯利)
新: 高信心19.3% vs 低信心3.0% (动态凯利)
```

## 校准器如何优化sigmoid参数
calibrator.py 从 trade_history.json 的 kelly 汇总数据反推(不用逐笔明细):
- 实际胜率wr → midpoint ≈ 15 - (wr-0.5)*50
- 实际赔率odds → k ≈ (odds-1)*0.08
- ATR→赔率: slope=odds/15, intercept=odds*0.6
- 2026-06-18首次校准(116笔): k=0.1136, mid=17.16, 实际wr=45.7%, odds=2.42
