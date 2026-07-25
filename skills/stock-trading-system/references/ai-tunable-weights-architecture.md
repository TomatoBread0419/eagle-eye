# AI 可调评分权重系统 (v4.5, 2026-06-10)

## 动机

用户问了一个关键问题：「如果用Python的话，代表有些数据是在本地写死的，这样子真的够智能吗？」

13维度评分的权重（如 `ret_1m × 0.4`、`RSI > 75 → -10`、`gap > 3% → +5`）全是拍脑袋的硬编码数字。它们不会自己进化，如果市场风格从「动量驱动」变成「价值回归」，脚本不知道。

## 架构原理：本地算数 ≠ 本地分析

用户另一个灵魂拷问：「本地怎么算？我平板这点算力用python还能比大模型分析要厉害啦？」

关键区别：
```
本地 Python  =  计算器（算指标、算分数、算板块缺口）—— 加减乘除，骁龙比大模型快1000倍
DeepSeek     =  基金经理（看计算器结果，结合新闻和战略做判断）
```

所有技术指标（RSI/MACD/ATR/波动率/均线）是**纯数学公式**：
```python
RSI = 100 - (100 / (1 + 平均涨幅/平均跌幅))   # 5行加减乘除
MACD = EMA(12) - EMA(26)                      # 两个指数移动平均相减
```

让大模型算这个会：① 浪费 tokens（78只×~800tokens=62,400tokens/次）② 可能算错。本地算：0.3秒，零成本。

而大模型的价值在「看结果做判断」而不是「算数字」。

## 解决方案：AI 每天早上调权重

### 文件结构

```
~/stock_trader/
├── ai_weight_config.json     ← AI 可调的评分参数（新增）
├── us_screener.py            ← 改成读 config 而不是硬编码（已改）
└── us_report.py              ← +--update-weights 参数让 AI 更新配置（已改）
```

### ai_weight_config.json 结构

13个评分维度全部参数化，每个都有默认值（=之前的硬编码数字）：

```json
{
  "score_weights": {
    "ret_1m": 0.4, "ret_3m": 0.25, "ret_short": 0.15
  },
  "rsi_scoring": {
    "normal_threshold": 75, "defensive_threshold": 65,
    "normal_penalty": -10, "extreme_threshold": 85, "extreme_penalty": -20
  },
  "volatility_scoring": {
    "low_vol_threshold": 20, "low_vol_bonus": 3,
    "mid_vol_threshold": 30, "mid_vol_bonus": 1,
    "high_vol_threshold": 40, "high_vol_penalty": -1,
    "extreme_vol_threshold": 50, "extreme_vol_penalty": -3
  },
  "ma_scoring": {
    "uptrend_bonus": 3, "cross_bonus": 2
  },
  "volume_scoring": {
    "bullish_confirmation": 3, "divergence_penalty": -3, "bearish_penalty": -2
  },
  "macd_scoring": {
    "golden_cross": 3, "death_cross": -2, "above_zero_bonus": 1
  },
  "rs_vs_spy_scoring": {
    "strong_rs_threshold": 5.0, "strong_rs_bonus": 2,
    "moderate_rs_threshold": 2.0, "moderate_rs_bonus": 1,
    "weak_rs_threshold": -5.0, "weak_rs_penalty": -2
  },
  "sector_gap_scoring": {
    "large_gap_threshold": 0.03, "large_gap_bonus": 5,
    "medium_gap_threshold": 0.02, "medium_gap_bonus": 3,
    "small_gap_threshold": 0.01, "small_gap_bonus": 2
  },
  "sector_event_bias": {
    "max_bonus": 3, "max_penalty": -3
  },
  "yfinance_scoring": {
    "beta_high_threshold": 2.0, "beta_high_penalty": -2,
    "beta_mid_threshold": 1.5, "beta_mid_penalty": -1,
    "beta_low_threshold": 0.5, "beta_low_bonus": 1,
    "pe_expensive_threshold": 50, "pe_expensive_penalty": -2,
    "pe_fair_low": 10, "pe_fair_high": 25, "pe_fair_bonus": 2,
    "pe_moderate_high": 35, "pe_moderate_bonus": 1,
    "div_yield_threshold": 0.02, "div_yield_bonus": 1
  },
  "buy_filter": {
    "defensive_rsi_limit": 65, "normal_rsi_limit": 70,
    "min_momentum_score": 5, "defensive_max_volatility": 45
  },
  "defense_sector_bonus": {
    "telecom": 5, "defense": 5, "energy": 4, "pharma": 3,
    "consumer": 2, "resources": 1, "finance": 0,
    "industrial": 0, "tech": -2, "ai": -3
  }
}
```

### AI 调权重流程

每天首轮交易决策时，先做一步权重调优：

```bash
# AI 根据市场风格调权重
python3 us_report.py --update-weights '{
  "score_weights": {"ret_1m": 0.3, "ret_3m": 0.35, "ret_short": 0.15}
}'

# 或单独调某个维度
python3 us_report.py --update-weights '{
  "rsi_scoring": {"normal_threshold": 80, "normal_penalty": -15}
}'

# 然后正常生成报告（权重已更新）
python3 us_report.py --mode aggressive
```

### 用户核心规则

- 权重更新只在每天**首轮 cron** 做一次。之后同一交易日不再改，保持评分一致性。
- 权重不写死——如果某个权重每周都调成同一个值，说明应该改默认值。
- 改变权重时必须给出理由（如「CPI 超预期→高波动扣分加严」或「动量持续有效→提高动量权重」）。

### 涉及的修改

| 文件 | 改动 |
|------|------|
| `~/stock_trader/ai_weight_config.json` | 新增 — 所有评分参数的默认值 |
| `~/.hermes/scripts/us_screener.py` | 新增 `load_weights()` 函数 + `W = load_weights()` 全局变量 + 所有 `_scan_one()` 硬编码改为 `W[...]` 查询 |
| `~/.hermes/scripts/us_report.py` | 新增 `--update-weights` 参数，接受 JSON 字符串，合并更新到 `ai_weight_config.json` |
