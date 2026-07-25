---
name: cn-stock-auto-trader
description: '[已暂停] A股全自动交易系统 — 纯Python，无第三方依赖，新浪/东方财富数据源，虚拟模拟盘+双层风控'
version: 1.0.0
category: data-science
---

## A股全自动交易系统

纯Python实现，零外部依赖，架构完全对标美股Alpaca系统。

## 系统架构

```
stock_trader/
├── cn_auto_trader.py    # A股主脚本（概念监控+模拟盘+风控）
├── cn_risk_state.json   # 虚拟组合状态
├── cn_signal_latest.json # 信号缓存
└── cn_trader.py         # 原分析脚本（数据源底层）
```

## 数据源

- **实时行情**: 新浪财经 `hq.sinajs.cn/list=sh600519,sz300750`
- **日K线**: 东方财富 `push2his.eastmoney.com`（主），新浪备用
- 纯`requests`，不需要API Key

> 📚 详细的数据源参数（资产负债表/利润表/现金流量表/综合行情指标/新闻搜索/字段映射/编码说明）见 `references/china-stock-fundamental-data-sources.md`

## 概念股池配置（事件驱动型）

按概念分组，便于监控特定主题（如特朗普访华、FSD落地等）：

```python
CONCEPT_WATCH = {
    # 特斯拉链 (FSD入华/访华利好)
    'sz300750': {'name': '宁德时代', 'concept': '特斯拉链', 'desc': '电池主供'},
    'sz002594': {'name': '比亚迪',   'concept': '新能源车', 'desc': '整车龙头'},
    'sh601689': {'name': '拓普集团', 'concept': '特斯拉链', 'desc': '底盘供应商'},
    'sz002050': {'name': '三花智控', 'concept': '特斯拉链', 'desc': '热管理'},
    'sh603305': {'name': '旭升集团', 'concept': '特斯拉链', 'desc': '铝合金压铸'},
    # AI芯片 (黄仁勋随团/特供芯片利好)
    'sz300308': {'name': '中际旭创', 'concept': 'AI芯片',   'desc': '光模块龙头'},
    'sh688256': {'name': '寒武纪',   'concept': 'AI芯片',   'desc': 'AI芯片设计'},
    'sh601138': {'name': '工业富联', 'concept': 'AI芯片',   'desc': 'AI服务器'},
    # 苹果链 (库克访华利好)
    'sz002475': {'name': '立讯精密', 'concept': '苹果链',   'desc': '连接器龙头'},
    'sz002241': {'name': '歌尔股份', 'concept': '苹果链',   'desc': '声学组件'},
    # 消费/外资回流
    'sh600519': {'name': '贵州茅台', 'concept': '消费',     'desc': '外资回流'},
}
```

报告输出会自动按 `concept` 分组显示涨跌幅排名。

## 事件驱动监控策略

适合短期主题炒作（特朗普访华、FSD获批、财报季等）：

1. 按概念分组配置股票 → `CONCEPT_WATCH`
2. 脚本运行时自动报告每个概念板块的"信号分"和涨跌幅
3. 信号分≥2 且 RSI<65 且非持股 → 自动模拟买入（每手100股）
4. 输出中会标注 "🔥" = 当前持有该概念板块股票

## 风控参数

| 参数 | 值 | 说明 |
|------|-----|------|
| TRAIL_DISTANCE | 0.05 | 移动止损5% |
| STOP_LOSS_PCT | 0.05 | 硬止损5% |
| TP_PROFIT_PCT | 0.15 | 止盈15% |
| MAX_POSITIONS | 5 | 最多同时持仓5只 |

## 虚拟组合

- 初始资金 `INITIAL_CASH = 1,000,000`（100万）
- 买入手续费万分之三，卖出口径印花税+手续费
- 状态持久化到 `cn_risk_state.json`

## 定时任务

```yaml
schedule: "30 9-14 * * 1-5"   # 交易时段每30分检查
script: "cn_auto_trader.py"
workdir: "$HOME/stock_trader"
deliver: "weixin"               # 自动投递到微信
```

## Cron Agent 工作流（重要）

脚本输出 + 预运行脚本输出 只是原始数据。代理层（你）需要进一步加工成有价值报告：

### 1. 自动投递规则
当 cron 任务 `deliver: "weixin"` 时，**你的最终回复内容会自动发送到微信**。
- ❌ **不要**调用 `send_message` 推送到 WeChat — 会被系统跳过并报 `cron_auto_delivery_duplicate_target`
- ✅ 把报告内容直接写在最终回复中，系统自动投递
- ✅ 如果无新信息，回复 `[SILENT]` 可阻止投递

### 2. 报告增强策略
原始脚本只输出涨跌数据和信号分，代理层应补充：

**a) 新闻/事件研究：**
```python
# 在代理层，用 delegate_task(web tools) 搜索概念主题的最新动态
# 例如特朗普访华概念 -> 搜 "特朗普访华 最新消息 随行企业"
```

**b) 综合分析：**
- 板块内个股涨跌对比（领先/落后标的）
- 技术面点评（RSI超买超卖、放量/缩量走势）
- 将新闻事件与股价走势交叉验证

**c) 交易建议：**
- 信号分≥2且RSI<65的候选标的说明
- 提醒已持仓股票的风险（止损距离、浮盈浮亏）
- 非交易时段注明下次检查时间

### 3. 板块深度分析模板
```
📊 概念板块监控日报 | YYYY-MM-DD

💰 模拟盘状态
  总权益 | 持仓 | 盈亏

📉 板块表现（按概念分组）
  ⚡ 特斯拉链: 代码 A% | B% | C%
  💻 AI芯片: 代码 A% | B%

🏆 买入信号排名（Top 3）
  ① 股票名 信号+N RSI X → 点评

🔍 事件/新闻交叉分析
  [最新动态摘要 + 影响评估]
  [板块轮动观察]
```

详见历史案例：用 `session_search(query="特朗普访华概念股监控日报")` 查看之前成功案例的格式。

## 关键限制

- A股交易时间：9:30-15:00 BJT（非交易时段不买入，仅分析）
- A股制度限制（本地模拟未实现）：T+1、涨跌停板（±10%）、最小100股/手、滑点
- pip网络不稳定（即使在VPN下）：小包(six)可通过清华镜像安装，大包(pandas)仍超时
- `gm`（掘金量化SDK）在PyPI上已不可用，官网myquant.cn也不稳定(502)。替代方案：纯Python自建

## Termux pip 诊断流程

当 pip 超时或失败时：

```bash
# 1. 验证网络通不通
curl -s --max-time 10 https://pypi.org/simple/ | head -3
curl -s --max-time 10 https://www.baidu.com | head -3

# 2. 验证 pip 版本
pip --version

# 3. 装小包测试（小包能过说明pip本体没问题）
pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple --timeout 60 six

# 4. 装大包（可能超时，即使VPN下也不行）
pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple --timeout 300 pandas

# 5. 搜包是否在PyPI上
pip install gm --timeout 60  # ERROR=包不存在
```

已知：小包可以通过清华镜像安装，大包(pandas)和已下架的包(gm)不可用。

## 与掘金量化的对比

| 维度 | 本系统 | 掘金量化 |
|:---|:---:|:---:|
| 安装依赖 | 零（纯requests） | pip install gm（已不可用） |
| 数据源 | 新浪/东方财富 | 同源 |
| 成交模拟 | 现价直接成交 | 撮合引擎（带滑点） |
| A股制度 | ❌ T+1/涨跌停未实现 | ✅ 内置 |
| 实盘对接 | 需自行对接券商API | 支持华泰/国信等 |
| 运行环境 | Termux (已测试) | 需要Windows客户端 |
| 市值/策略 | 无限制 | 免费版10策略 |

结论：模拟盘阶段本系统够用。实盘时建议开华泰证券账户，用券商自有量化接口或掘金网页版策略。

## 📚 参考文件

- `references/china-stock-fundamental-data-sources.md` — A股基本面数据源大全（资产负债表/利润表/现金流量表/综合行情指标/新闻搜索），包含已验证的API参数、字段映射、编码说明和注意事项
