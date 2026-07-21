# 📝 Prompt 模板

本目录包含 Eagle Eye 系统中使用的 Prompt 伪示例。完整的 Prompt 在 Hermes Agent 的 cron 配置和 skill 文件中，这些模板仅作参考。

## 文件列表

| 文件 | 用途 | 对应 Workflow |
|------|------|---------------|
| `system-prompt.md` | 全局 System Prompt 模板 | 所有任务 |
| `daily-scan.md` | 每日市场扫描 Prompt | 扫描 |
| `open-check.md` | 开盘挂单检查 Prompt | 检查 |
| `decision-report.md` | AI 决策报告 Prompt | 报告 |
| `risk-check.md` | 风控验证 Prompt | 风控 |

## 使用说明

这些 Prompt 模板展示了 Eagle Eye 的 Prompt 设计风格和结构。实际使用时，需要：

1. 替换 `{variable}` 为实际值（时间、数据、上下文）
2. 调整输出 Schema 以匹配下游消费者
3. 根据模型特点微调（Flash vs Pro）
