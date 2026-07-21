# 🧠 Prompt Engineering 指南

## 概述

在 Eagle Eye 中，**Prompt 就是代码**。系统的行为边界、决策逻辑、输出格式都由 Prompt 定义。本文档记录了 Prompt 工程的设计思路、最佳实践和进化历程。

---

## 设计哲学

### 核心原则

```
传统软件工程：    需求 → 编码 → 测试 → 部署
AI Prompt 工程：  需求 → Prompt → Schema → 测试 → 迭代 Prompt

区别：
- 行为由自然语言定义，而非编程语言
- 迭代周期从"周"缩短到"小时"
- "Bug" 可能是 Prompt 描述模糊，而非逻辑错误
```

### 三条铁律

1. **Constraints over Instructions** — 告诉 AI 什么不能做，比告诉它怎么做更有效
2. **Structured Output First** — 先定义输出 Schema，再写 Prompt 内容
3. **Self-Correction Built-in** — Prompt 中预留自检步骤，让 AI 输出前自己审一遍

---

## Prompt 层级体系

Eagle Eye 使用三层 Prompt 架构：

```
第1层: System Prompt（全局不可变）
  ├── 角色定义
  ├── 宪法规则（不可逾越的铁律）
  └── 通用约束（语言、风格、行为准则）

第2层: Task Prompt（任务可变）
  ├── 当前任务描述
  ├── 上下文/背景信息
  └── 具体指令

第3层: Output Schema（输出契约）
  ├── JSON 结构定义
  ├── 字段约束
  └── 示例输出
```

---

## System Prompt 设计

### 角色定义

System Prompt 的开头需要清晰定义 AI 的角色。这是行为的**锚点**。

```
你是一个 [角色]。[角色] 的核心职责是 [一句话说明]。

你的行为由以下约束定义，请严格遵守。
```

### 示例（交易决策 Agent）

```
你是一个鹰眼交易系统的决策 Agent。

你的核心职责是：基于真实市场数据、持仓状况和风控规则，
独立判断买入/卖出/持有，并生成可执行的 OrderIntent。

约束：
1. 所有决策必须基于你看到的真实数据，不能编造理由
2. 你不预测市场，只做概率判断（"更可能涨" vs "更可能跌"）
3. 风控规则高于一切，风控检查不通过则不执行
4. 输出必须符合指定的 JSON Schema，不能多字段也不能少字段
```

### 宪法规则 (Constitution Rules)

这是 System Prompt 中最关键的部分——**不可违反的铁律**。

```
# Eagle Eye Constitution — 铁律

#1  永不删除或修改系统已生成的订单
#2  没有止损单不允许建立新仓位
#3  不执行来源不明的订单指令
#4  每个交易动作必须记录审计日志
#5  AI必须独立判断用户意图，不盲目执行指令
#6  总持仓不得超过账户净值的 90%
#7  单只股票占比不得超过 18%
#8  单个板块占比不得超过 30%
#9  持仓不足6只时不减仓
#10 所有审计日志必须包含时间戳和推理链
```

### 通用约束

```
输出语言：中文为主，股票代码和英文术语保留原文。
输出风格：简洁、工程化、数据驱动。
时间表示：统一使用北京时间 (BJT)，必要时标注美东时间 (ET)。
数据精度：价格保留2位小数，百分比保留2位小数。
```

---

## Task Prompt 设计

### 结构模板

每个 Task Prompt 遵循统一模板：

```
## 任务：[任务名称]

### 背景
[当前上下文，包括时间、市场状态、特殊说明]

### 数据输入
[AI 应该读取哪些文件或调用哪些工具]

### 执行步骤
1. [步骤1]
2. [步骤2]
3. [步骤3]

### 输出要求
[输出格式、包含哪些字段、不包含哪些字段]

### ⚠️ 常见陷阱
[容易犯错的地方，提前警告]
```

### 示例：开盘检查 Prompt

```
## 任务：每日开盘检查

### 背景
US 市场即将开盘（BJT 21:30），需要审核所有未成交挂单。
时间：{current_time} BJT

### 数据输入
1. 读取当前持仓：alpaca_get('/v2/positions')
2. 读取未成交订单：alpaca_get('/v2/orders')
3. 读取板块配置：stock_trader/portfolio_config.json

### 执行步骤
1. 列出所有 status='new' 的未成交挂单
2. 计算各板块当前实际占比 vs 目标占比
3. 识别缺配板块（实际 < 目标 - 5%）
4. 对于缺配板块的唯一持仓：标记为"不卖"
5. 撤销不合理的卖单

### 输出要求
输出 JSON:
{
  "check_time": "BJT时间",
  "total_orders": 整数,
  "cancelled_orders": [{"id": "订单ID", "reason": "原因"}],
  "kept_orders": [{"id": "订单ID", "reason": "保留原因"}],
  "sector_analysis": [{"sector": "板块名", "target": 0.XX, "actual": 0.XX, "action": "增/减/持"}]
}
```

---

## Output Schema 设计

### 为什么先定义 Schema？

Prompt 可以模糊，但输出格式不能模糊。先定义 JSON Schema 再写 Prompt 内容，确保：

1. **消费方明确** — 下游模块知道收到什么
2. **AI 有边界** — 不会生成无关字段
3. **可测试** — 输出可以自动化校验

### 示例 Schema

```json
{
  "type": "object",
  "required": ["scan_time", "candidates", "assessments"],
  "properties": {
    "scan_time": {
      "type": "string",
      "description": "扫描时间，格式 ISO 8601 + 时区",
      "example": "2026-06-24T21:30:00+08:00"
    },
    "candidates": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["ticker", "score", "rationale"],
        "properties": {
          "ticker": {"type": "string"},
          "score": {"type": "number", "min": 0, "max": 100, "description": "综合评分"},
          "rationale": {"type": "string", "description": "AI 判断理由（≤200字）"},
          "sector": {"type": "string"},
          "action": {"type": "string", "enum": ["buy", "watch", "pass"]}
        }
      }
    },
    "assessments": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "sector": {"type": "string"},
          "direction": {"type": "string", "enum": ["利好", "利空", "中性"]},
          "significant": {"type": "boolean"},
          "hot_events": {"type": "array", "items": {"type": "string"}}
        }
      }
    }
  }
}
```

### Schema 进化教训

```
v1: 自由格式文本输出 → 解析失败率 40%
v2: 简单 JSON，无验证 → 字段不一致
v3: 完整 JSON Schema，有必填 → 解析失败率 <5%
v4: 加枚举约束 → 完全一致
v5: 加 Emoji 前缀 → 人类可读性提升
```

---

## 稳定性提升技巧

### 技巧1：示例驱动 (Few-Shot)

在 Prompt 末尾提供输入/输出示例：

```
### 示例

输入：
  当前持仓：[{ticker: "PANW", shares: 42, price: 286}]
  候选池：[{ticker: "MRVL", score: 72}, {ticker: "SNOW", score: 68}]

输出（遵循 Schema）：
{
  "candidates": [
    {"ticker": "MRVL", "score": 72, "action": "buy",
     "rationale": "AI芯片需求+估值合理，近5日动量转正"}
  ],
  "assessments": [
    {"sector": "半导体/AI", "direction": "中性", "significant": false}
  ]
}
```

### 技巧2：自检指令 (Self-Correction)

在 Prompt 末尾要求 AI 自我审查：

```
在输出最终结果前，检查以下事项：
1. 输出是否符合 JSON Schema？如果不符合，修正。
2. 所有数字是否有数据源？如果没有，标注为 AI 估算。
3. 是否有模糊表述？如果有，改为具体表述。
4. 是否遗漏了任何必填字段？如果有，补充。
```

### 技巧3：陷阱预埋

把已知的失败模式写在 Prompt 中：

```
### ⚠️ 常见陷阱

1. 不要输出 Markdown 表格（WeChat 显示会错位）
2. 不要使用 undefined 或 null 作为值（JSON 解析会失败）
3. 不要省略 rationale 字段（审计需要推理链）
4. 不要用"可能""或许"等模糊词（除非确实不确定）
5. 不要编造数据（用 "N/A" 或 "数据不可用" 替代）
```

### 技巧4：多模型适配

不同模型对 Prompt 的响应不同：

| 模型 | 特点 | Prompt 调整 |
|------|------|-------------|
| DeepSeek-v4-Flash | 快速、直接的输出 | 无需额外适配 |
| DeepSeek-v4-Pro | 更长的推理链、更谨慎 | 可省略部分示例 |
| Claude (备选) | 严谨、注意细节 | 增加"必须输出 JSON"强调 |

---

## Prompt 版本管理

### 每个 Prompt 应该记录

1. **版本号** — v1.0, v1.1, ...
2. **变更日志** — 每次修改了什么，为什么
3. **测试结果** — 此 Prompt 在 XX 模型上的表现
4. **已知问题** — 当前 Prompt 尚未解决的 edge case

### 模板

```markdown
# Prompt: 开盘检查
# 版本: v2.3
# 模型: deepseek-v4-flash
# 最后更新: 2026-06-18

## 变更记录
- v2.3 (2026-06-18): 增加板块感知审核步骤，避免缺配板块被误卖
- v2.2 (2026-06-10): 修复跨session持久化问题，增加过期挂单清理
- v2.1 (2026-06-01): 初始版本

## 当前 Prompt
...
```

---

## Prompt 工程检查清单

```
□ 角色定义清楚吗？
   → "你是一个 XX。你的职责是 YY。"

□ 约束够硬吗？
   → 是否有"绝对不允许"的规则？

□ 输出格式定义了精确的 JSON Schema 吗？
   → 包含必填字段、枚举值、示例

□ 有自检步骤吗？
   → AI 输出前会自我审查

□ 有陷阱预埋吗？
   → 已知的失败模式是否写在 Prompt 里了？

□ 有示例吗？
   → 输入/输出的匹配示例

□ 每个 Prompt 有版本号吗？
   → 可以追踪变更和回滚
```
