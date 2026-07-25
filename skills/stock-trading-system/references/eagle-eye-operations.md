# Eagle Eye 系统操作手册

## 统一入口

```bash
# ~/eagle-eye 或 alias eagle
eagle report                    # 生成 AI 决策报告
eagle scan                      # 运行扫描器
eagle portfolio                 # 持仓分析
eagle stops                     # 止损/止盈管理
eagle execute '{"orders":[...]}' # 执行订单
eagle status                    # 系统状态
```

## 工作流

### 1. 决策报告
```bash
# 默认模式（normal，目标 50%）
eagle report

# 指定模式
eagle report --mode aggressive --target-util 0.55
eagle report --mode defensive --target-util 0.35
```

报告包含：
- 市场环境（事件+情绪）
- 账户状态（Equity/Cash/仓位/缺口）
- 持仓分析（14只，板块分布）
- 扫描器候选（TOP10，缺配标注 🎯）
- 风险标记（⚠️近止损/浮亏）

### 2. AI 决策
读报告后判断：
1. 用什么模式？（基于事件对持仓的实际影响）
2. 买什么？（候选 vs 自行补充）
3. 买多少？（波动率、集中度、估值）
4. 加仓还是开新仓？

### 3. 执行
```bash
# 市价单（确保成交）
eagle execute '{"orders":[{"symbol":"LMT","qty":3,"side":"buy"}]}'

# 限价单（更便宜但可能不成交）
eagle execute '{"orders":[{"symbol":"LMT","qty":3,"side":"buy","type":"limit","limit_price":"518.67"}]}'
```

### 4. 止损管理
```bash
eagle stops  # 机械执行，不需要判断
```

## Cron 任务

| 任务 | 时间 | 脚本 |
|------|------|------|
| 美股AI决策 | 每小时 21:10-05:10 工作日 | us_report.py → AI → us_trader.py |
| GARP扫描 | 每日 08:00 工作日 | us_screener.py |
| 市场事件 | 每2小时 09:00-17:00 工作日 | market-event-monitor |

## 常见问题

### Q: 仓位太低怎么办？
A: 用市价单，不纠结价格。限价单追不上市场。
```bash
eagle execute '{"orders":[{"symbol":"CVX","qty":10,"side":"buy"}]}'
```

### Q: 止损触发后怎么处理？
A: 1 小时内必须有替代买入。从扫描器候选里选，或者自己判断。不要让现金闲置。

### Q: 扫描器推荐但 AI 不买？
A: 检查是不是因为：
- 刚止损过 → 等 1 小时就可以重新买（不是 1 天）
- 高波动 → 买少一点（1-2 股），但要买
- 限价太低 → 改市价单

### Q: Google News 扫描失败？
A: 检查 VPN 是否开着。Google News 在中国被墙，需要 VPN 才能访问。

### Q: Wash trade 错误？
A: 已有止损单时不能下同方向买单。等止损触发后再买。不要 cancel 旧止损（触发死锁）。

### Q: --stops 卖掉了刚买的股票？
A: 这是已知 bug。买入后本轮 cron 绝不运行 --stops。详见 SKILL.md §止损覆盖审计。

### Q: 如何评估交易能力？
A: 用户以已投资资本为基准计算收益（24% 利用率 = 100%），不是以总权益为基准。
例如：24% 仓位赚 2.5% → 持仓部分收益 10.3% → 年化 ~94%
