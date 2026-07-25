# Cron Prompt Template — 2026-06-01 重构

## 背景

a638e8d3 (美股信号检查) 在 2026-06-01 凌晨 5:15 报错，根因：
1. model 未显式绑定 → fallback 到 xiaomi mimo → mimo 已停 → 报 model 错误
2. prompt 模糊"运行脚本" → agent 习惯用 execute_code → cron 沙箱 BLOCKED
3. 微信推送 weixin StopIteration 异常 → 没有 fallback 路径
4. 用户不在屏前时没有"自主决策"原则 → 任务失败就停，没抢救

## 重构后的 prompt 模板

```yaml
【{任务名} — 必做】

每 {频率} 跑一次, {触发时段/条件}。

**核心原则**:用户可能不在屏幕前。{突发条件}时,在风控框架内自主决策+执行+{通知渠道}推。

**风控框架(硬约束,不可破)**:
- 单股硬止损 5% (从成本) / 追踪止损 5% (从最高)
- 止盈阶梯: +20% 卖 1/3, +35% 卖 1/3, 移动止损跑最后 1/3
- 持仓上限 ≤ 5 只
- 仓位目标 30-60% (默认 40%)
- 现金 > 70% 触发恐惧偏误检测 → 强制回补
- 决策后必留 log: stock_trader/logs/YYYY-MM-DD_topic.md

**禁止 execute_code (cron 沙箱会 BLOCKED) — 必须用 terminal 工具**:
- ❌ execute_code → BLOCKED
- ✅ terminal 跑脚本
- ✅ cron job 配 `script:` 直接跑, agent 只负责解读结果

**多源验证**:任何决策必须 ≥3 源 (Google News RSS + 搜狗微信 + 至少一个备用)

**微信推送 fallback**:
- weixin StopIteration → 写 log + Bark
- gateway 死亡 → 写 log, 等下一轮自动恢复 (不重 auth, iLink 限流)

**绑定 (cron job 配置层)**:
- model: Minimax-M3
- provider: minimax-cn
- skills: [stock-trading-system, cron-job-llm-binding, weixin-gateway-debug]
- enabled_toolsets: [terminal, file, web] (不需要 delegation/cronjob 二次调用)
```

## 实操案例 — a638e8d3 (美股信号检查)

原始 prompt:
```
运行美股信号检查脚本 ~/.hermes/scripts/us_trader.py,分析结果通过微信推送给你。
```

→ 6/1 5:15 报错（model fallback + 微信 StopIteration + 6+ 小时没跑）

重构后 prompt (见 `cronjob list`):
```
【美股盘中自主决策任务 — 必做】
每 1 小时跑一次,美股交易时段(北京 21:10-05:10)。
核心原则:用户可能不在屏幕前... (见上面模板)
```

→ 6/1 12:40 manual run 验证：model=Minimax-M3 + provider=minimax-cn 正确, 链路通, 微信通, API call 通, 没 BLOCKED

## 模板的关键点 (复用指南)

| 必含元素 | 为什么 | 漏了的代价 |
|---------|--------|----------|
| 显式 model + provider | 防 fallback | mimo/xiaomi 复活 → 报 model 错 |
| "禁止 execute_code" 明确写 | cron 沙箱限制 | agent 用 execute_code → BLOCKED |
| "用 terminal 工具" 或 `script:` 配 | 强制走白名单 | 默认 execute_code → 死 |
| 风控硬约束 | 用户不在屏前 = 自主决策需要边界 | 没边界 = 乱搞 |
| 通知 fallback | iLink 限流 / StopIteration | 推不到 = 任务静默失败 |
| 多源验证 ≥3 源 | 单源 = 假信号 / 微信谣言 | 决策基于谣言 |
| 决策后留 log | 调试 + 用户审阅 | 任务跑完没记录 = 失忆 |
| 必绑 skill: stock-trading-system | 100% 加载 | skill 漏加载 = 框架走样 |

## 不要写在 prompt 里

- ❌ 完整脚本代码（用 `script:` 配置, 不要塞在 prompt）
- ❌ 完整 API key（用 `~/.hermes/.env` + `import config`, prompt 永远不存 key）
- ❌ "要不要...？" 收尾（直接做, 留 log）
- ❌ 占位符（如 "PK2OKX...ECHE"）— 这会覆盖真实 config

## 验证清单 (新 cron job 上线前)

- [ ] `cronjob list` 显示 model + provider 正确
- [ ] `cronjob list` 显示 skills 至少含 stock-trading-system (交易类)
- [ ] manual run 一次, agent.log 显示 API call 成功 + 微信 Sending response
- [ ] last_run_at 更新, last_status=ok
- [ ] 没有 BLOCKED 字样
- [ ] 通知渠道能收到 (用户实际确认, 不是看 API 错误码)

## 相关
- §8.2 stop 单死锁 (死锁本身 cron 跑时也会撞, prompt 里加 "等收盘" 提示)
- §8.5a LLM override TP (prompt 写"框架不可破" 是缓解, 终极修复在脚本级)
- §10.8 双扫协议 (cron 必须 ≥3 源, 单源决策会被 §10.8 标 "未验证")
- §11.1a.2 execute_code BLOCKED (本 reference 解决了这个具体坑)
- §11.1b.1 "显而易见" 边界 (prompt 应该直接写动作, 不留反问空间)
