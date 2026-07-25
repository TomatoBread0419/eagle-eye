# Contract Validator (2026-06-18)

## 概述
`contract_validator.py` 定义并验证鹰眼系统各模块之间的数据契约。
任何上游模块改了JSON输出格式,契约验证立刻报错,不会静默失败。

## 位置
`~/.hermes/scripts/contract_validator.py`

## 契约清单 (8个JSON文件)
- trade_history.json → kelly汇总(win_rate, odds_ratio)
- market_env.json → macro(vix)+breadth(pct_above_ma200)
- calibrated_params.json → kelly(sigmoid_k, midpoint, target_alloc)+stop_loss(tier_vol_*)
- us_watchlist.json → buy_candidates + kelly_allocations
- signal_decay.json → alerts
- us_risk_state.json → positions
- compliance_report.json → compliance率+details
- us_pending_replacements.json → pending (optional,首次卖出前不存在)

## 使用
```bash
python3 contract_validator.py  # 退出码1=有错误, 0=全部通过
```

## 契约违反处理
- 上游改了格式 → 契约报错 → 修上游或修契约
- 不崩溃: calibrator/kelly读不到校准参数时回退到默认值
- 自动运行: calibrator.py末尾调用contract_validator

## 关键教训
- trade_history.json的`matched_trades`是int(116),不是list
- v6首次校准时发现格式不匹配,calibrator从逐笔明细改为从kelly汇总反推
- us_pending_replacements.json是optional文件,首次卖出前不存在
