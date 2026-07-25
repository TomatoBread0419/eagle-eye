# 个股异动逆向研究流程

## 触发场景

用户说「X怎么涨这么狠」「X能追吗」「X凭什么涨」——在给出买卖建议之前，必须**先搞清楚涨的原因**。

与 commodity-market-research-workflow.md 的区别：该流程是已知商品品种的例行价格跟踪；本流程是**对突然被用户提及的个股做逆向催化挖掘**，用户可能不知道自己在问什么。

## 标准流程（五步法）

### Step 1: 确认涨势规模

先获取数据，不要直接搜新闻。确认涨幅/时间窗口/成交量：

```bash
# 1a. 实时行情（qt.gtimg.cn，墙内可用，无需 Referer）
curl -s "https://qt.gtimg.cn/q=sz002167" | python3 -c "import sys; print(sys.stdin.buffer.read().decode('gbk'))"

# 1b. K 线趋势（qt 日K线，前复权）
curl -s "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz002167,day,,,30,qfq" | python3 -c "
import json,sys;d=json.load(sys.stdin)
kl=d.get('data',{}).get('sz002167',{}).get('qfq day',[])or d.get('data',{}).get('sz002167',{}).get('day',[])
for k in kl[-10:]:print(f'{k[0]} C:{float(k[1]):.2f} H:{float(k[2]):.2f} L:{float(k[3]):.2f} V:{k[4]}')"
# sh=上海，sz=深圳  |  字段: [date, open, close, high, low, volume]
```

**关注什么**：从哪天开始涨的？涨幅%？是否加速（最近3天涨幅 > 之前7天）？成交量是否持续放大？

### Step 2: 中文新闻挖掘

Sogou 微信 > wallstreetcn（wallstreetcn 对小众题材覆盖薄）。

**分层搜索策略**（从具体到抽象）：

| 轮次 | 搜索词策略 | 预期收获 |
|:----:|-----------|---------|
| 1 | `公司名 + 涨停/大涨 + 概念 + 2026` | 当日涨停分析、概念归类 |
| 2 | `核心产品/矿物名 + 价格 + 涨 + 2026` | 现货涨价信息 |
| 3 | `板块名 + 全线爆发/轮动 + 2026` | 确认是板块行情还是个股独立行情 |
| 4 | `下游应用 + 风口 + 2026`（如"固态电池 锆"） | 技术路线催化 |

```bash
curl -s -L "https://weixin.sogou.com/weixin?type=2&query=<URL编码关键词>&ie=utf8" -A "Mozilla/5.0" | python3 -c "
import sys, re
html = sys.stdin.read()
# p.txt-info = 摘要
summaries = re.findall(r'<p class=\"txt-info\">(.*?)</p>', html, re.DOTALL)
# h3 > a = 标题+链接
titles = re.findall(r'<h3>.*?<a[^>]*?>(.*?)</a>', html, re.DOTALL)
for t in titles[:5]:
    print(f'T:{re.sub(r\"<[^>]+>\",\"\",t).strip()[:100]}')
for s in summaries[:5]:
    print(f'S:{re.sub(r\"<[^>]+>\",\"\",s).strip()[:200]}')
"
```

### Step 3: 英文源交叉验证（走代理）

仅当 mihomo 代理运行时可用：

```bash
curl -s --socks5-hostname 127.0.0.1:7891 \
  "https://news.google.com/rss/search?q=<URL编码英文关键词>&hl=en-US&gl=US&ceid=US:en" \
  -A "Mozilla/5.0" | python3 -c "
import sys, re
titles = re.findall(r'<title>(.*?)</title>', sys.stdin.read())
for t in titles[1:11]: print(f'• {t}')
"
```

**关键词策略**：不搜公司名，搜**矿种/材料名 + price/surge/supply/demand + 2026**。例如：
- 错：`Oriental Zirconia` → 0 结果
- 对：`zirconium price surge rare earth` → SMM 快讯 + solid-state battery 文章

### Step 4: 产业链溯源（核心步骤）

这是**最有价值的一步**——找到驱动因素的底层逻辑，而不只是读标题。

问自己三个问题：

| # | 问题 | 锆的示例 | 方法 |
|:-:|------|-----------|------|
| 1 | **生产什么？副产品是什么？** | 锆 → 铪（hafnium）是共生矿 | 查公司主营业务 + 矿物共生关系 |
| 2 | **副产品在哪行业有刚需？** | 铪 → AI芯片高k介质（HfO₂）、核控制棒、航发高温合金 | SMM / Google 搜 `hafnium + AI chip` 验证 |
| 3 | **近期有供应侧变化吗？** | 中国出口管制收紧？ | 搜 `export control + 材料名` |

**值得记住的产业链钩子**：
- 🪢 **锆 → 铪（AI芯片）**：生产锆不分离铪就是废品，锆产量受铪需求驱动
- 🪢 **钨 → 硬质合金（军工/工业）**：中国主导全球80%+供应
- 🪢 **稀土 → 永磁/军工**
- 🪢 **镓/锗 → 半导体衬底**

**现实案例（2026-06-24）**：东方锆业 10 天 +23% 的表面催化是「小金属板块轮动」，底层催化是**铪的AI芯片需求 + 中国出口管制**。两者之间通过「锆铪无法分离」这条矿物学规律连接。

### Step 5: 分层输出

按三层组织答案：

```
🥇 核心催化（结构性、底层逻辑）—— 决定能不能持续
  例：铪的AI芯片需求 + 中国出口管制 → 中期强
🥈 次级催化（题材/技术路线）—— 市场在讲的story
  例：固态电池锆需求 → 中长期但不确定
🥉 情绪催化（板块轮动/资金溢出）—— 随时退潮
  例：稀土3连涨带动小金属板块 → 短期
```

**要不要追的判断规则**：
- 只有 🥉 没有 🥇 → **不追**，纯情绪
- 🥇 存在但涨速过快（10天+20%+） → **等回调**
- 🥇 + 🥈 且涨幅不大 → **可考虑分批建仓**

## 已知局限

1. **Sogou 微信搜索结果可能偏旧**（不是当日），综合复盘类文章可能不包含最新催化剂。需要配合 Google News（代理）或 wallstreetcn
2. **wallstreetcn 对小众题材覆盖薄**，锆/铪/钨等专用金属的文章在 wallstreetcn 几乎为零（2026-06-08 实测）
3. **产业链知识需要积累**——不同矿种的共生/应用关系不在 API 数据中，需要搜索 + 推理
