# v6 架构变更 (2026-06-17)

## 从开环到闭环

v5的问题: 132个硬编码参数全部拍脑袋，从未根据实际交易结果校准。
执行结果从未反馈回评分/止损参数系统。

v6新增三层:

```
数据采集 → 指标计算 → 评分 → 执行 → 止损
                                      ↓
                              ┌─ 反馈校准层 ─┐
                              │ calibrator.py │ ← 90天交易数据
                              │  → 校准sigmoid/止损/板块加分
                              │ regime检测    │ ← VIX/广度
                              │  → 4种参数组  │
                              │ compliance    │ ← 规则审计
                              │  → 85%合规率  │
                              └───────────────┘
```

## 新增文件

- `~/.hermes/scripts/calibrator.py` — 参数自校准器
- `~/.hermes/scripts/compliance_audit.py` — 规则合规审计
- `~/stock_trader/calibrated_params.json` — 校准输出
- `~/stock_trader/compliance_report.json` — 合规报告
- `~/stock_trader/regime.json` — 市场状态

## eagle-eye v6 新命令

```bash
eagle calibrate   # 参数自校准 (每周六)
eagle audit       # 规则合规审计
```

## 动态凯利集成

us_screener.py 的 kelly_position_sizes() 现在:
1. 自动读 calibrated_params.json 中的 sigmoid_k/sigmoid_midpoint
2. 用校准后的 atr_to_odds_slope/intercept 计算赔率
3. 读 target_alloc (默认85%, 非95%)
4. 无校准文件时回退到默认参数

## 合规审计结果 (2026-06-17)

85%合规 (17/20):
- ✅ 17条有代码实现
- ❌ 3条无代码: sell→buy配对、止损后1h替代、30%仓位门槛→市价单
