---
date: 2026-06-07
topic: 大宗商品/有色金属市场研究工作流
validated: wallstreetcn + Sogou + qt.gtimg.cn 实测
---

# 大宗商品市场研究工作流

## 核心发现：wallstreetcn 对细分大宗商品覆盖薄

wallstreetcn 是综合财经媒体，钨/钼/锡/锑等小众有色金属的专题文章极少。
**Sogou 微信搜索**是大宗商品/有色金属的**最佳中文新闻源**——公众号文章时效性好，
覆盖当日/近3天，且有专业深度（如"中钨在线""富宝资讯"等垂直账号）。

## 推荐工作流

### Step 1: Sogou 微信搜专题新闻
```python
import urllib.parse, subprocess, re
q = urllib.parse.quote("钨价 行情 2026年6月")
r = subprocess.run(['curl', '-s', '--max-time', '12', '-L',
    f'https://weixin.sogou.com/weixin?type=2&query={q}&ie=utf8',
    '-H', 'User-Agent: Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36'],
    capture_output=True, text=True, timeout=15)
# 提取: h3 > a 标题, p.txt-info 摘要
titles = re.findall(r'<h3>.*?<a[^>]*>(.*?)</a>.*?</h3>', r.stdout, re.DOTALL)
snippets = re.findall(r'<p class="txt-info">(.*?)</p>', r.stdout, re.DOTALL)
```

### Step 2: wallstreetcn 补充宏观面
```bash
# limit 必须 ≤100，否则 data 字段可能变 string
curl -s "https://api-one.wallstcn.com/apiv1/content/articles?channel=global-channel&limit=50"
# 本地过滤 title + content_short 关键词（API 的 search endpoint 不过滤）
```

### Step 3: qt.gtimg.cn 拉龙头股行情
```python
# A 股有色金属板块龙头（实时行情，GBK 编码）
stocks = 's_sh600549,s_sz002378,s_sz000657,s_sz002842'
r = subprocess.run(['curl', '-s', '--max-time', '10',
    f'https://qt.gtimg.cn/q={stocks}'], capture_output=True, timeout=12)
text = r.stdout.decode('gbk', errors='replace')  # 注意：GBK 编码！
# 解析: v_s_sh600549="1~厦门钨业~600549~61.73~-2.00~-3.14~..."
```

### Step 4: K 线趋势（可选）
```bash
# 最近 5 天日 K 线（前复权）
curl -s "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600549,day,,,5,qfq"
# 响应: data.sh600549.qfqday = [["2026-06-01","55.56","52.85","57.07","52.75","量"], ...]
```

## 主要有色金属/稀有金属 A 股代码映射

### 钨
| 股票 | 代码 | 特点 |
|------|------|------|
| 厦门钨业 | sh600549 | 龙头，APT 产能最大 |
| 章源钨业 | sz002378 | 钨矿+硬质合金 |
| 中钨高新 | sz000657 | 硬质合金+刀具 |
| 翔鹭钨业 | sz002842 | 钨粉+钨条 |

### 钼（与钨同属小金属）
| 股票 | 代码 | 特点 |
|------|------|------|
| 金钼股份 | sh601958 | 钼业龙头 |
| 洛阳钼业 | sh603993 | 钼+钴+铜 |

### 锆（陶瓷/军工/核电材料，受益涨价逻辑+进口替代）
| 股票 | 代码 | 特点 | 市值/备注 |
|------|------|------|----------|
| 东方锆业 | sz002167 | 锆系产品全链（氧氯化锆/电熔锆/二氧化锆） | 小金属题材，2026年6月年内两度提价，曾连板 |
| 三祥新材 | sh603663 | 氧化锆/海绵锆 | 锆产业链核心标的 |
| 国瓷材料 | sz300285 | 高纯氧化锆/陶瓷材料 | 消费电子+牙科陶瓷 |

### 其他稀有金属
| 股票 | 代码 | 特点 |
|------|------|------|
| 东方钽业 | sz000962 | 钽铌 |
| 西部材料 | sz002149 | 钛/钨/锆 |
| 湖南黄金 | sz002155 | 金+锑 |
| 北方稀土 | sh600111 | 稀土龙头 |
| 中国稀土 | sz000831 | 稀土 |

## 地缘事件→商品传导分析（6/8 新增）

用户常先问"战争/制裁/关税怎么了"，再问"某商品价格怎么走"。这是两步分析，
不是两个独立问题。**必须在第一步就预判第二步会问什么商品**，主动关联。

### 触发信号
- 用户问战争/冲突/制裁 → 立即关联受影响的战略商品（钨→军工、稀土→科技、石油→能源、锑→弹药）
- 用户直接问"XX价格怎么走" → 同时拉商品新闻 + A股龙头行情 + K线

### 分析框架（以6/8钨-伊朗冲突为例）

```
Step 1: 地缘定性（wallstreetcn + Sogou）
  → 伊朗导弹打以色列，特朗普调停
  → 判断：冲突升级方向

Step 2: 商品关联（知识库，非搜索）
  → 钨 = 穿甲弹/军用硬质合金核心材料
  → 中国占全球80%产量 = 出口管制牌
  → 逻辑：冲突升级 → 军工补库 + 战略囤货 + 管制预期

Step 3: 商品新闻验证（Sogou 微信搜"钨价 + 最新月份"）
  → 6/5报道：单日暴涨3万/吨，周涨20%
  → "价涨量缩"信号 = 下游接货意愿减弱

Step 4: A股龙头交叉验证（qt.gtimg.cn 行情 + K线）
  → 厦门钨业/中钨高新/章源钨业 6/4-6/5 冲高回落
  → 高位放量回调 = 短线获利回吐

Step 5: 综合判断
  → 中期看涨（供需缺口+地缘催化）
  → 短期有回调压力（价涨量缩+技术回调）
  → 建议：等回调企稳再看
```

### 战略商品↔地缘速查表

| 地缘事件 | 直接受影响商品 | A股代理标的 |
|----------|---------------|------------|
| 中东战争/军事冲突 | 钨、锑、钼 | 厦门钨业/章源钨业/中钨高新 |
| 中美科技脱钩 | 稀土、镓、锗 | 北方稀土/中国稀土 |
| 俄乌战争/制裁 | 钯、镍、铝 | 相关期货+龙头股 |
| 台海紧张 | 全部战略金属 | 军工+有色板块 |

### 注意事项
- **不要只报商品价格，要报传导逻辑**。用户要的是"为什么涨"和"还能不能追"
- **价涨量缩 = 风险信号**，必须主动提示，不能只报利好
- 公司发风险提示公告 = 官方确认过热，降低追高建议

## 供应链主题研究法（2026-06-24 新增）

有些时候，用户问的不是"现在哪个商品涨了"，而是**"这个东西凭什么涨？背后是什么结构性逻辑？美股里谁受益？"**

这种问法来自**结构性/主题型投资者**——他们从物理/工程原理出发（"太阳辐射加热航天器→所以太空散热难→所以热障涂层重要→所以YSZ是关键材料→中国控盘钇+锆→所以美股替代标的CRML/IPX有机会"），而不是从价格动量出发。

### 五步供应链主题溯源法

```
① 物理/工程原理 → 核心材料
   问: 这个东西为什么重要？它在解决什么物理问题？
   例: 太空散热难 → 需要热障涂层 → YSZ（钇稳定氧化锆）
   例: AI芯片漏电 → 需要高k介质 → HfO₂（铪基材料）

② 核心材料 → 供应链地图
   问: 谁控制这个材料的生产和加工？
   例: 钇（中国~90%）+ 锆加工（中国~75%）= 双重供应风险
   例: 铪是锆的共生矿物，生产锆必产铪

③ 供应链风险 → 地缘/政策催化
   问: 有没有正在发生的事件在加速供应链转移？
   例: 中国稀土/钨出口管制 → 美国必须找替代
   例: SpaceX IPO → 航天供应链重估 → 材料端受益
   例: AI芯片产能全开 → 铪需求暴增 + 中国出口限制

④ 催化 → 美股标的筛选
   问: 美股里谁在解决这个供应链缺口？
   搜索关键词: "US hafnium zirconium alternative China supply stock" / "critical minerals substitution"
   重点看: CRML（铪/稀土）、IPX（钛/稀土）、MP（稀土）、UUUU（铀/稀土）
   陷阱: 很多是勘探阶段公司（pre-revenue），波动大、有稀释风险

⑤ 时机评估
   问: 现在什么位置？还要不要等？
   已涨过 → 看回调深度 + 催化剂时间表
   还没涨 → 看是否提前埋伏，还是等催化确认
   横向对比 → 和同板块已盈利的公司（HWM/ATI/BWXT）做风险收益对比
```

### 五步法的关键区别 vs 传统商品研究

| 维度 | 传统商品研究 | 供应链主题研究 |
|------|------------|--------------|
| 起点 | 价格异动 | 结构趋势/工程原理 |
| 标的 | A股龙头（有色板块） | 美股小众（CRML/IPX等） |
| 时间跨度 | 短期（周/月） | 中长期（季/年） |
| 风险特征 | 价格波动 | 勘探风险+稀释+概念 |
| 信息来源 | wallstreetcn/Sogou | Google News英文为主+SMM |

### 美股关键矿物/航天供应链代码映射

| 代码 | 公司 | 概念 | 状态 | 风险等级 |
|:----:|------|------|:----:|:-------:|
| **CRML** | Critical Metals Corp | 铪/稀土——目标抢中国75%铪市场 | 勘探阶段 | 🔴高 |
| **IPX** | IperionX | 钛+稀土，德州项目$813M NPV | 开发阶段 | 🟡中 |
| **MP** | MP Materials | 美国最大稀土商，军工供应链替代 | 运营中 | 🟢中低 |
| **UUUU** | Energy Fuels | 铀+稀土，美国本土供应链 | 运营中 | 🟢中低 |
| **HWM** | Howmet Aerospace | YSZ热障涂层使用方（发动机叶片） | 运营中 | 🟢低 |
| **BWXT** | BWX Technologies | 核热推进+锆合金燃料包壳 | 运营中 | 🟢低 |
| **RKLB** | Rocket Lab | 航天硬件，直接受益SpaceX生态 | 运营中 | 🟡中 |
| **ASTS** | AST SpaceMobile | 卫星通信，太空基建 | 运营中 | 🟡中 |

### 查找方法论

搜索关键词模式（Google News via mihomo代理）：
```
# 材料→供应链
"hafnium zirconium supply chain China export control"
"yttria stabilized zirconia thermal barrier coating aerospace"

# 供应链替代
"US rare earth critical minerals alternative stock"
"China dominance mineral refining supply chain risk stock"

# 具体公司
"CRML hafnium production Greenland Tanbreez"
"Critical Metals Corp hafnium market share China"
```

### 用户偏好提醒

这类用户不希望看 momentum 排名的 Top 10，而是要**结构性的逻辑链**：为什么涨 → 为什么能持续 → 美股谁受益 → 现在什么位置。回答的输出格式应该是**逻辑树**而不是列表。

## 坑点速查

1. Sina 期货代码（nhf_W2507/nf_WI0）对小众品种返回空字符串——走 A 股龙头代理
2. qt.gtimg.cn 返回 GBK 编码——`subprocess.run(capture_output=True)` + `.decode('gbk', errors='replace')`
3. wallstreetcn search endpoint 不过滤 keyword——本地过滤替代
4. wallstreetcn limit=200 时 data 可能变 string——做 isinstance 检查
