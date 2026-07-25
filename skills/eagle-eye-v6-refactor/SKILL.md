---
name: eagle-eye-v6-refactor
description: 鹰眼v6重构方案——从开环系统(132个死参数)升级为闭环系统(参数自校准)。需求矛盾调和、参数审计、架构设计。
version: 6.0.0
category: data-science
status: IMPLEMENTED (2026-06-18)
---

# 鹰眼 v6 重构方案 — 已实现

## 状态: ✅ 已完成 (2026-06-18)

所有计划中的模块已实现并验证:
- calibrator.py: 参数自校准器 ✅
- compliance_audit.py: 规则合规审计 ✅ (20/20, 100%)
- contract_validator.py: 契约验证器 ✅ (8个JSON契约)
- us_screener.py: 动态凯利+校准集成 ✅
- us_trader.py: sell→buy配对+低仓位市价单 ✅
- eagle-eye v6: +calibrate/+audit命令 ✅
- cron: 每周六自动校准+审计 ✅

## 触发背景 (2026-06-17)

用户发现凯利11.6%是"死数字"——不随持仓变化而变化。进一步审计发现整个系统有132个同类问题。

## 核心问题

**开环系统**: 扫描→评分→执行→止损→...→扫描。中间的执行结果从未反馈回参数系统。

**规则三层断裂**: Memory有偏好→SKILL有规则→脚本不执行。

**132个硬编码参数**: 全部拍脑袋，从未根据实际交易结果校准。

## 用户需求矛盾清单 (已确认调和方案)

1. 仓位95% vs 回撤12%停买 → 仓位降到85%留缓冲
2. FOMC不做操作 vs 止损后替代 → FOMC日止损照常,替代推迟次日
3. 投机小盘 vs 凯利需准确参数 → 小盘凯利上限10%,大盘20%
4. 龙头回避 vs 8-9只90%仓位 → 凑不够时允许选龙头,仓位减半
5. 激进 vs 安全阀 → 不改安全阀,改止损距离(小盘10%/大盘7%)
6. 不分散 vs 板块缺配加分 → 最多3板块,每板块最少2只
7. 全权自主 vs 规则断裂 → 规则必须写进代码+自动审计

## 用户角色定义

**用户是老板不是工程师。** 提需求说意图(如"不想大跌时满仓"),不说参数(如"回撤12%停买")。参数由AI定,定完告诉用户为什么,用户拍板。

## 架构设计

新增三层:
1. **参数自校准器 (calibrator.py)** — 从90天交易数据拟合sigmoid/止损/板块加分
2. **市场状态检测器 (market_regime.py)** — trending/volatile/crisis/quiet四态
3. **规则合规审计 (compliance_audit.py)** — 自动检查偏好是否有代码实现

## 实施状态 (2026-06-17 完成)

全部6个task完成:
- ✅ calibrator.py — 参数自校准器 (sigmoid/止损/板块/权重/市场状态)
- ✅ us_screener.py 集成 — kelly_position_sizes()读calibrated_params.json
- ✅ compliance_audit.py — 20条规则合规审计 (100%合规)
- ✅ eagle-eye v6 — 新增calibrate/audit命令
- ✅ Cron — 每周六06:00校准+06:10审计
- ✅ P14/P15/P19代码缺口修复 — sell→buy配对/替代买入/低仓位市价单

## 详细计划

见 `~/.hermes/plans/2026-06-17-eagle-eye-v6-refactor.md`
- ✅ calibrator.py — 参数自校准器(含市场状态检测)
- ✅ compliance_audit.py — 规则合规审计(20条规则,85%合规)
- ✅ us_screener.py — 动态凯利集成(读calibrated_params)
- ✅ eagle-eye v6入口 — calibrate/audit命令
## 端到端验证

- ✅ 34/34 V7.1模块导入成功
- ✅ `python3 main.py status` — 8个数据文件全部存在且新鲜
- ✅ `python3 main.py health` — 配置/数据/日志/API全部通过
- ✅ SQLite 21张表, 167KB, WAL模式, integrity_check=ok
- ✅ 14个cron任务运行中 (12 active, 1 paused, 1 local-only)
- ⚠️ 10项已知技术债务 (详见 references/v7.1-production-audit.md)

### 已知风险 (2026-06-18 审计发现)

1. **CRITICAL**: 幽灵止损单未清理 (TECH-DEBT-006)
2. **HIGH**: V6脚本仍通过桥接处理60%交易逻辑 (TECH-DEBT-001)
3. **HIGH**: DNS劫持依赖非仓库文件sitecustomize.py (TECH-DEBT-009)
4. **HIGH**: yfinance国内限速无解 (TECH-DEBT-005)
5. 共10项，全部有缓解措施

详见: `references/v7.1-production-audit.md`
