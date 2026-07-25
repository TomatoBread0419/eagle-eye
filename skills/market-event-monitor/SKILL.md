---
name: market-event-monitor
description: 多源市场事件监控——覆盖半导体/金融/地缘/贸易/原材料五大板块，Google News RSS + 搜狗微信双源交叉验证，输出影响方向评估
category: data-science
---

# 市场事件监控

## 触发条件
- 用户询问市场形势、某板块走势、或要求"扫描一下最近有什么大事"
- 用户说「X怎么涨这么狠」「X凭什么涨」「XX能追吗」——**必须先逆向挖因，再给买卖建议**。详见 `references/stock-surge-reverse-investigation.md`
- 每次做交易决策前（买入/卖出）
- 定时任务自动运行
- **港股盘中事件监控**（09:30-16:00 HKT，每 60 分钟）→ 见 `references/hk-intraday-monitor-2026-06-02.md`（Yahoo Finance + qt.gtimg.cn + CNBC/Investing.com 交叉验证，4 行简报格式） + `references/hk-intraday-monitor-2026-06-03.md`（6/3 13:30 + 15:34 双时段实测：qt + 新浪 HTML 快讯源 + ADR 隔夜标识 + A/H 倒挂模式 + 巨头竞购催化溯源 + 「科技强+指数弱」反向分化 + SCMP 催化源）
- **美股盘后扫描**（BJT 06:00 工作日）→ 见 `references/us-postmarket-scan-2026-06-03.md`（Yahoo Finance 1m + Google News RSS，4 段简报：收盘/盘后财报/评级/要闻 + 持仓评估）
- **A 股个股分析**（用户问「XXX可以买吗」「看看XXX」「推荐几只」）→ 见 `references/a-share-stock-deep-dive.md`（六步法：行情→K线→板块对比→新闻催化→综合判断；以及批量扫描推荐工作流）
- **A 股午间速报**（BJT 12:00 工作日）→ 见 `references/cn-midday-briefing-2026-06-03.md`（qt.gtimg.cn + Yahoo v8 4 段简报：A 股午盘/港股半日/欧美盘前/预警 + 持仓距止损）
- **早间速报 09:00**（BJT 09:00 工作日）→ 见 `references/cn-morning-briefing-2026-06-11.md`（qt.gtimg.cn US + wallstreetcn + Alpaca 快速路径，≤600 字纯文本格式，含日韩数据不可用说明）

## 五大必查板块

| # | 板块 | 关键词 | 关注指标 |
|---|------|--------|----------|
| 1 | 半导体/AI | `semiconductor AI chip NVDA TSM demand 2026` | 财报、产能、台海风险 |
| 2 | 地缘/台海 | `Taiwan semiconductor TSMC China tensions` | 冲突风险、制裁 |
| 3 | 美联储 | `Federal Reserve Warsh interest rate policy` | 加息/降息、点阵图 |
| 4 | 贸易/访华 | `Trump China visit trade deal` | 关税、协议细节 |
| 5 | 原材料 | `tungsten rare earth price China export control` | 价格、出口管制 |

**原材料板块特别说明**：wallstreetcn 对小众有色金属覆盖薄（2026-06-08 实测：wallstreetcn 两个 channel 共 60 篇文章中钨相关为 **零**），专题新闻优先用 Sogou 微信搜索。完整工作流见 `references/commodity-market-research-workflow.md`。
**供应链溯源（2026-06-24 新增）**：当用户问的不是"现在涨没涨"而是"凭什么涨/美股谁受益"时，使用 `references/commodity-market-research-workflow.md#供应链主题研究法` 的五步物理→材料→供应链→美股筛选流程。

## 搜索方法

### Google News RSS 代理访问 (2026-06-10)

在中国大陆 Google News RSS 被墙。已部署 Termux 内部 mihomo (clash-meta) 代理方案：

- **mihomo** 在 Termux 后台运行，提供 SOCKS5:127.0.0.1:7891 + HTTP:127.0.0.1:7890
- **proxy_patch.py** 自动检测 mihomo PID → 通过 PySocks 给 Python socket 打 SOCKS5 补丁
- **market_news.py** 顶部已集成 `from proxy_patch import patch`，mihomo 运行时自动走代理
- Alpaca/微信/搜狗微信/壁虎财经等直连服务不受影响

管理命令：
```bash
python3 ~/.hermes/scripts/proxy_start.py start    # 启动代理
python3 ~/.hermes/scripts/proxy_start.py status   # 状态
python3 ~/.hermes/scripts/proxy_start.py test     # 测试
```

详见 stock-trading-system skill `references/termux-clash-proxy-setup.md`

### 新闻源优先级（6/5 更新）

| 优先级 | 源 | 可用性 | 适用场景 |
|--------|-----|--------|----------|
| 1 | **wallstreetcn API** | ✅ 稳定 | 中文财经快讯、A/港股/美股新闻、宏观面 |
| 2 | **搜狗微信** | ⚠️ 2026-06-24起疑似反爬改版（部分请求返回空内容） | 中文深度文章、公众号分析、**大宗商品/有色金属专题新闻首选** — 如Sogou失效，改用Google News via代理或wallstreetcn |
| 3 | **Google News RSS** | ⚠️ 需代理（mihomo） | 英文全球财经 — 见 `references/termux-clash-proxy-setup.md` |

**wallstreetcn API 用法**（免 key，JSON 格式）：
```bash
curl -s "https://api-one.wallstcn.com/apiv1/content/articles?channel=global-channel&limit=30"
# 或 us-stock-channel（注意：与 global-channel 有内容重叠，需按 title 去重）
# 响应: {"code":20000,"data":{"items":[{"title":"...","display_time":1780652423,"content_plain":"..."}]}}
# display_time 是 Unix epoch 秒
```
**坑点**：`us-stock-channel`、`global-channel`、`a-stock-channel` 三个 channel 返回高度重叠的文章（6/9 实测：三个 channel 各 30 篇，去重后仅 9 篇独立文章）。**必须按 title[:30] 去重**。如需覆盖更多话题，可尝试其他 channel（如 `hk-stock-channel`），但重叠率仍然很高。

### 多源 fallback（推荐）

使用 `scripts/market_news.py` 统一入口：
```python
from market_news import search_market_news
results, source, err = search_market_news("Federal Reserve Warsh rate June 2026")
# results: list[{title, source, date, snippet?, lang}]
# source: 'google_rss' | 'sogou_weixin' | 'none'
# err: None on success
```

先 Google RSS（英文全球财经）→ 失败则 fallback 搜狗微信（中文深度）。两个源都失败时返回 err 说明原因。

**⚠️ 6/5 实测**：Google News RSS 从中国 IP 持续返回空结果（SSL 超时或空响应）。搜狗微信 fallback 返回结果偏旧（非当日新闻）。**cron 任务如需实时新闻，直接用 wallstreetcn API 而非 market_news.py**。

### 行情源（No-Key）
- **qt.gtimg.cn 全覆盖**（墙内可用、3 秒刷新、免 key）：
  - 港股指数：`hkHSI / hkHSCEI / hkHSTECH`
  - 港股个股：`hk00700 / hk03690 / hk09618 / hk09988 / hk09888`
  - A 股指数：`s_sh000001 / s_sz399001 / s_sz399006`
  - A 股行业：`s_sh000933 医药 / s_sz399986 银行 / s_sz399997 消费`
  - **美股指数**：`usINX`（标普500）/ `usDJI`（道琼斯）/ `usIXIC`（纳斯达克）— 6/5 实测可用
  - 美股个股：`usNVDA / usAAPL / usTSLA / usAMZN / usGOOG / usMSFT / usMETA / usAVGO`
  - 中概 ADR 隔夜（BJT 09:30-21:30 为前一 ET 日收）：`usJD / usBABA / usBIDU / usNIO / usPDD`
- **⚠️ Yahoo Finance v8 chart 已被墙**（6/5 实测 403 "sad panda" 页面）：`query1.finance.yahoo.com/v8/finance/chart/` 从中国大陆 IP 返回 403。**不要再用 Yahoo 做主源**。仅在海外代理/VPN 环境下可用
- **Sina hq.sinajs.cn 6/3 已全面 404**，弃用
- 详见 `references/hk-intraday-monitor-2026-06-02.md`（港股盘中 60min）+ `references/cn-midday-briefing-2026-06-03.md`（12:00 午间速报）的完整数据源 + 交叉验证 + sandbox 坑点

## 地缘事件级联分析（2026-06-08 新增）

发现重大地缘事件（战争/制裁/冲突升级）后，**必须立即评估对相关大宗商品板块的影响**：

| 地缘事件类型 | 关联商品板块 | 搜索关键词示例 |
|-------------|-------------|--------------|
| 军事冲突/战争 | 钨（穿甲弹/装甲）、稀土（军用永磁） | `钨价 军工 供需` `稀土 出口管制` |
| 中东冲突/制裁 | 石油、天然气 | `油价 伊朗 制裁` |
| 避险情绪升温 | 黄金、美债 | `金价 避险 国债收益率` |
| 贸易战/关税 | 稀土、锂、关键矿产 | `稀土 关税 反制` `锂 供应链` |

**操作流程**：识别地缘事件 → wallstreetcn 搜事件本身 → Sogou 微信搜关联商品价格新闻 → qt.gtimg.cn 查相关A股龙头实时价格+K线 → 交叉验证后纳入报告

**案例（2026-06-08）**：伊朗向以色列发射弹道导弹 → 钨是军工核心材料（穿甲弹）→ 搜钨价发现周涨20% → 查厦门钨业/中钨高新/章源钨业K线确认趋势 → 输出"钨价中期看涨但短期过热"结论

⚠️ 级联分析不是独立板块，而是地缘事件的下游影响链。不做级联 = 只看到事件本身，漏掉市场真正的交易机会。

---

## 输出格式

每个板块报告：
- Top 3-4 新闻标题 + 来源 + 日期
- 影响方向：🟢利好 / 🔴利空 / 🟡中性
- 交叉验证：≥2个独立源确认
- **地缘事件发生时**：附加"关联商品板块"评估（见上方级联分析）

**港股盘中简报（特例，≤400 字）：** 见 `references/hk-intraday-monitor-2026-06-02.md` 的 4 行固定格式

## 🟡 关于追踪知名投资人

**可以**查段永平、巴菲特、木头姐等买了什么，他们是**有价值的数据源**。但**不可以**只看买了什么就去跟。

正确的用法是两段式：

```
发现：段永平买了苹果
  ↓
研究：为什么买？（消费复苏预期？估值合理？AI终端？）
  ↓
判断：我同意这个逻辑吗？
  → 同意 → 我也可以按这个逻辑找标的
  → 不同意 → 跳过，但知道市场上有资金在这么想
```

**搜索时要搜「为什么」，不搜「买了什么」：**
- ✅ 正确：`Duan Yongping investment thesis 2026 rationale`
- ❌ 错误：`段永平 持仓`（这是抄作业心态）

## 关键坑点

1. **百度/新浪搜索 JS 渲染** → curl 返回空壳，不可用。**例外：** hq.sinajs.cn 的实时行情流是纯 CSV 不需 JS 渲染
2. **FT/Bloomberg 付费墙** → 摘要可见，全文需付费
3. **单一来源不决策** → 必须 ≥3 独立源交叉验证
4. **事件双扫协议**：发现重大事件后立即搜索同日 ±3 天内其他事件，冲突时取保守方向
5. **时效性**：重点抓最近 3 天内新闻，超过 7 天的仅作背景参考
6. **Yahoo Finance `chartPreviousClose` 可能 stale**（2026-06-02 港股监控实测 + 6/3 早盘再次复现）：同一 `^HSI` 两次调用返回不同 prev close；用 5m interval 取 open 字段交叉，或用 **腾讯 qt.gtimg.cn `hkHSI` 指数流** 做 ground truth（每 3 秒刷新，权威实时，且 6/3 实测 Sina `hq.sinajs.cn` 已 404）。**Yahoo v7 quote 端点 6/3 实测返回 "Unauthorized"，只可用 v8 chart**
6a. **Sina hq.sinajs.cn 部分端点可恢复（6/23 复测）**：
   - ❌ **HK/全球指数/美股端点仍 404**：`rt_hkHSI` / `s_sh000001` / `gb_baba` / `int_nasdaq` —— 弃用
   - ✅ **A 股个股行情仍可用**（需带上 `Referer: https://finance.sina.com.cn` 头）：
     ```bash
     curl -s "https://hq.sinajs.cn/list=sz002167,sh600519" -H "Referer: https://finance.sina.com.cn"
     # 返回: var hq_str_sz002167="东方锆业,19.510,17.740,19.510,..."
     ```
     字段格式：`名称,今开,昨收,当前价,最高,最低,买一价,买一量,卖一价,卖一量,成交量,成交额,日期,时间`
   - ⚠️ **Sina 裸请求（无 Referer）返回空**——这是反爬策略，不是端点完全不可用
   - **推荐**：A 股个股优先用 **qt.gtimg.cn**（3 秒刷新，无需 Referer），Sina 作为备选或秒级补数据来源
   - 可用的 Sina 端点：`hq.sinajs.cn/list=sz{6位代码}`（深市）、`hq.sinajs.cn/list=sh{6位代码}`（沪市）
6b. **南向资金实时数据：API 不可用**（qt.gtimg.cn `s_sh_South` / `s_sz_South` / `s_sh_HGT` / `s_sz_SGT` 全部 `pv_none_match`；Sina 已 404）。**唯一路径：Google News 搜「南向资金 净买入 6月3日 港股通」**。A 股午间速报时段（11:30-12:00）该数据基本未发布，**报告中写「数据未更新」+ 历史背景即可**
6c. **涨停/跌停计数：API 不可用**（qt.gtimg.cn / Sina / 同花顺 / 雪球 都没有公开计数器）。**替代方案**：用 A 股行业指数 + 个股异动新闻（`亨通光电 4分钟涨停` `ST闻泰 天地板跌停`）做定性描述，**不写具体数字**
7. **cron 沙箱里 `execute_code` 被 BLOCKED**（2026-06-01 验证）：用 `terminal` 工具跑；`/tmp` 不可写 → 临时文件用 `~/tmp/`
8. **Yahoo 1m chart 的 `timestamp` 字段是 UTC**（2026-06-03 美股盘后实测）：BJT 07:30 = UTC 23:30(前一天) = ET 19:30(前一天)。cron 在 BJT 早晨跑时拿到的"最后几笔 1m ticks"实际是**昨晚 ET 18:30 起的盘后/盘前期**，不是今天盘前。要判断"这是昨晚 AH 还是今天 PM"必须用 BJT→ET 转换：`BJT - 13h = ET`，或看 `meta.regularMarketPrice` 是否已被当日新值更新
9. **Yahoo `chartPreviousClose` ≠ `regularMarketPrice`**：前者是再前一个交易日的官方收盘，后者是最新已结算的收盘日。在多日 range 里比较 `chg` 时两个基点会给出不同结果；做 ±1d 比较用 `regularMarketPrice`，做 5d 趋势用 `chartPreviousClose`
10. **新浪 `rt_hk*` 指数流 vs 个股流不同**（6/3 实测）：`rt_hkHSI / rt_hkHSTECH / rt_hkHSCEI` 这三个**指数**前缀可用；但 `rt_hk0700 / rt_hk9988` 这类**个股**前缀**返回空字符串**，要走 Yahoo v8 chart。同理 `gb_baba / gb_jd` 是**美股中概**（隔夜 ET 收盘），不是港股个股的镜像
11. **新港股板块指数判定用「恒生科技」一个指数就够**（6/3 实测）：Yahoo 港股板块子指数（`3011.HK 3028.HK`）数据稀疏，Sina 的 `rt_hkHSTECH` 是现成的板块温度计。组合自建篮子（5-9 只股票均值）当主源 + 恒生科技指数做交叉验证
12. **qt.gtimg.cn 美股 ADR 流是「隔夜 ET 收盘」不是实时**（6/3 13:30 实测）：`usJD` / `usBABA` / `usBIDU` / `usNIO` 等格式在 BJT 09:30-21:30 期间返回的是**前一个 ET 交易日的 close**（timestamp 字段 = 16:00 ET）。BJT 21:30 之后到次日 04:00 才有盘中实时数据。**报告里必须明确写「美股 06-02 收：JD +3.64%」而不是「JD 现价 +3.64%」**，否则会误导用户「中概今早正在大涨」——实际 HKT 早盘 ADR 已停更 17 小时
13. **Sina HTML 行情页 `finance.sina.com.cn/stock/hkstock/` 仍可用**（6/3 13:30 实测，区别于 hq.sinajs.cn 6/3 全面 404）：用作"港股午评"标题快讯源（"恒指跌1.69% 科指跌2.35% 科网股普跌 美团跌超6%"），与 qt.gtimg.cn 实时数字交叉验证（午评 12:00 数据 vs 当前 13:30 数据有时间滞后，差异 0.03% 属正常）
14. **A 股 `s_sh000001` / `s_sz399001` qt.gtimg.cn 走 A 股主源**（6/3 实测）：A 股 13:00 开盘后 qt 实时返回当前价/涨跌/成交额。**沙盘推演时优先用 qt 的 A 股数据做 A/H 联动判断**，不要走 Yahoo（Yahoo A 股 `regularMarketPrice` 在开盘前会用昨收估算，盘中有 5-15min 延迟）
15. **A 股早盘 HSI 杀跌 + A 股反涨 = A/H 倒挂**（6/3 13:30 模式）：HSI -1.66% / HSCEI -2.05% / HSTECH -2.47% 但 A 股上证 +0.57% / 深证 +1.70%。**港股 A 股反向开盘时，A/H 联动不传导**——沙盘推演结论应写「A 强 H 弱，跟跌概率低；A 内部科技股补涨空间被压制」而不是默认「A 跟 H 跌」
16. **「巨头竞购」类快讯是港股个股 5% 异动的常见催化**（6/3 11:25 新浪快讯）：阿里、美团、京东三家竞购朴朴超市——朴朴是华南生鲜电商独角兽，被三巨头哄抢本身**利空防守方美团**（防守战 + 估值压力）。**类似的「X 集团竞购 Y」类快讯要快速溯源到受影响板块**，美团 5.79% 跌幅就来自这条 11:25 的快讯。该模式同样适用于：被收购方往往单日 +10-20%，收购方反而 -3-5%（协同效应/反垄断担忧/估值稀释）
17. **港股盘中 cron 13:30 任务标准作业流**（6/3 13:30 实测跑通，60 秒内完成）：
   - 步骤 1（10s）：curl `qt.gtimg.cn/q=hkHSI,hkHSCEI,hkHSTECH` + `q=sh000001,sz399001` 拿主源数据
   - 步骤 2（15s）：curl `qt.gtimg.cn/q=hk00700,hk03690,hk09618,hk09988,hk09888` 拿 5 只核心港股科技股
   - 步骤 3（10s）：curl `qt.gtimg.cn/q=usJD,usBABA,usBIDU,usNIO,usPDD` 拿 5 只中概 ADR（注意：是「隔夜 ET 收」不是实时）
   - 步骤 4（15s）：curl `finance.sina.com.cn/stock/hkstock/` 拿"港股午评"标题快讯
   - 步骤 5（10s）：grep/regex 解析 4 份响应，组装 4 行简报
   - **总耗时 ~60s 全部走完，远低于 1 分钟预算**
18. **HSI/HSCEI 可分化的「恒生指数 ≠ 港股」陷阱**（6/3 15:34 末盘实测）：HSI -1.62% vs HSCEI +1.45% = 300bp 倒挂。HSI 权重 = 金融/地产/公用事业，HSCEI 权重 = 中资互联网/AI/医药/硬科技。**报告必填项：必须同时报 HSI/HSCEI/HSTECH 三个分指数**，不能只报 HSI。触发判断按指数分别算（一破一不破是常态）
19. **Yahoo `chartPreviousClose` 在 5d range 下指向 4 天前**（6/3 15:34 二次确认）：1d range → 昨收 / 5d range → 4 天前 close。**计算 ±1d 涨跌幅必须用 1d range + `regularMarketPrice` vs `chartPreviousClose`**。具体到 6/3 15:34：1d 报 `prev=26038.32`（正确）vs 5d 报 `prev=25328.23`（5/29 close 错误）
20. **SCMP HTML `scmp.com/business/markets` + `/business/china-business` 是「快讯源 #2」**（6/3 15:34 验证）：14 条英文标题可用，包括 "Zhipu AI 港股首发" / "MiniMax 上市 +300%" / "GenScript 国安反驳 +29%" / "Unitree 申请科创板 IPO"。**适用场景：英文催化、个股深度、AI 板块专题**。用法：`curl -L -A "Mozilla/5.0" "https://www.scmp.com/business/markets" | grep -oE '"headline":"[^"]+"|"title":"[^"]+"' | head -20`
21. **末盘（15:30-16:00 HKT）反弹窗口是 13:30 数据失效关键时段**（6/3 15:34 验证）：13:30 报"美团 -5.79% / 港股科技杀跌"到 15:34 已完全反包（美团 +3.35% / 港股科技 +6.86%）。**强制项：末盘报告必须显式标"末盘" + 距收盘 X 分钟**。**未来改进：cron 频率在 15:30-16:00 增至 30min**（15:00 / 15:30 / 16:00 三次）
22. **Google News RSS 从中国 IP 持续不可用（6/4 超时 → 6/5 完全空响应）**：SSL 握手超时或返回空 XML。不再是「偶尔超时」，而是**从大陆 IP 基本不可用**。**必须用 wallstreetcn API 做主新闻源**，或在海外代理环境下用 Google RSS。搜狗微信 fallback 结果偏旧（非当日），不适合实时监控。

   **解决方案（2026-06-10）**：见 `references/termux-clash-proxy-setup.md` — Termux 内跑 mihomo (clash-meta) + PySocks，无需系统 VPN，Python 脚本自动通过 SOCKS5 访问 Google News。
23. **Yahoo Finance v8 chart 被墙（6/5 实测 403）**：query1.finance.yahoo.com/v8/finance/chart/ 从中国大陆 IP 返回 403 HTML（sad panda 页面）。不要再用 Yahoo 做行情主源。替代方案：qt.gtimg.cn usINX/usDJI/usIXIC（美股指数）+ usNVDA/usAAPL/...（美股个股）已验证可用。Yahoo 仅在海外代理/VPN 环境下可用
24. **wallstreetcn API limit 参数敏感（6/7-6/8 实测）**：limit=30 稳定返回数据 ✅；limit=50 有时返回空 items ❌；limit=100+ 返回空 ❌。**推荐始终用 limit=30**，宁可多请求几次不同 channel 也不要一次拉太多。此外 data 字段类型也不稳定：limit=200 时 data 有时变成 string。必须做类型检查：`d = parsed.get('data', {}); if isinstance(d, dict): items = d.get('items', []) else: skip`。不要假设 data 一定是 dict。
24a. **wallstreetcn 单篇文章详情 API 不可用（6/8 实测）**：`/apiv1/content/articles/<id>` 返回空 title/content。**只有列表端点** `?channel=X&limit=N` 能用。要获取文章摘要，必须从列表响应的 `content_plain` 或 `content_short` 字段提取，不要尝试单独拉取文章详情。
25. **wallstreetcn search endpoint /apiv1/search/live 不过滤关键词（6/7 实测）**：keyword=钨 返回的是通用文章流（特朗普/NBA/哈马斯），完全无视 keyword 参数。不要用此端点做定向搜索。替代方案：拉大 article 列表（limit=50-100）后本地关键词过滤 title + content_short。
26. **Sogou 微信搜索是大宗商品专题新闻最佳中文源（6/7 实测）**：weixin.sogou.com/weixin?type=2&query=钨价+行情+2026 返回公众号文章标题+摘要，时效性好（含当日/近3天文章），特别适合有色金属/大宗商品等专业细分领域——wallstreetcn 作为综合财经媒体对此类细分话题覆盖薄。用法：curl -s -L 'https://weixin.sogou.com/weixin?type=2&query=<URL编码关键词>&ie=utf8'，提取 h3...a 标题 + p.txt-info 摘要。
27. **qt.gtimg.cn K 线数据接口（6/7 实测可用）**：https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600549,day,,,5,qfq 返回最近 N 天日 K 线（前复权）。响应 JSON：data.sh600549.qfqday 或 data.sh600549.day（数组，每项 [date, open, close, high, low, vol]）。适用于快速拉取个股近期走势做趋势判断。前缀：sh = 上海，sz = 深圳。
28. **qt.gtimg.cn GBK 编码 + iconv 可能不存在（6/7+6/9 实测）**：qt.gtimg.cn 返回 GBK 编码。两种解码方式：
    - `iconv -f GBK -t UTF-8`（shell 方式）—— 部分环境（如 Termux）可能没有 iconv
    - **推荐**：`python3 -c "import sys; print(sys.stdin.buffer.read().decode('gbk', errors='replace'))"` — 纯 Python，始终可用
    - ❌ 不要用 `text=True`（默认 UTF-8 会抛 UnicodeDecodeError）
28a. **qt.gtimg.cn 盘前/盘后空数据（6/9 实测）**：A 股/港股个股在开盘前（09:03 HKT）返回空字符串（市场 09:30 开盘）。美股 `usXXX` 格式在盘前仍有数据。**早间 09:00 速报获取 A 股/港股数据时，qt 可能为空，需提前在前一交易日收盘后拉取，或用 wallstreetcn 文章中的收盘数据做替代**
29. **Sina 期货代码对小众品种无效（6/7 实测）**：hq.sinajs.cn/list=nhf_W2507 和 nf_WI0（钨期货）均返回空字符串。只有上市品种（螺纹/铜/铝等主流）才有数据，小众有色金属品种走 Sina 期货拿不到报价。替代：用 A 股板块龙头股（厦门钨业/章源钨业/中钨高新）做行业代理指标。
30. **qt.gtimg.cn VIX 数据不可靠（6/8 实测）**：`usVIX` 返回的 timestamp 是 2026-02-06（4 个月前），说明 qt 的 VIX 数据不更新或更新极慢。**不要用 qt.gtimg.cn 做 VIX 主源**。替代方案：wallstreetcn 文章中提及的 VIX 数值，或直接在报告中写"VIX 参考值"并标注数据来源和时间。
31. **周末盘后扫描行为（6/8 实测）**：周日 06:00 跑盘后扫描时，没有"盘后财报"和"评级调整"可报告（周末无交易）。报告应调整为：重点报道周末要闻 + 上周五收盘回顾 + 下周展望。不要硬套"盘后财报"模板。
32. **日本/韩国指数从中国大陆 IP 完全不可获取（6/11 实测）**：以下所有途径均失败：
    - Yahoo Finance v8（`^N225` / `^KS11`）→ 403（已知）
    - Google Finance（`INDEXNIKKEI:.N225` / `INDEXKOSPI:KS11`）→ SSL UNEXPECTED_EOF
    - Nikkei.com / 日本经济新闻直连 → SSL UNEXPECTED_EOF
    - qt.gtimg.cn（`usNKY` / `usN225` / `usKOSPI`）→ `pv_none_match`（qt 无此数据）
    - 即使 mihomo 代理也无法绕过（SSL 握手中途断连，非 DNS 封锁而是 TLS 层阻断）
    **替代方案**：从 wallstreetcn 文章中提取定性信息（如"韩国6月前10天半导体出口+206%"）、用 qt US 指数做全球风险情绪代理指标（usINX/usDJI/usIXIC）。**09:00 早报中该段写「因中国大陆 IP 限制，暂无法获取实时日韩指数数据」**

## 常见故障诊断

### 所有Cron Job同时报错
**症状**：`cronjob list` 显示多个job的 `last_status: "error"`
**诊断**：见 `references/cron-api-key-diagnostics.md` 完整流程
**常见原因**：
- API key过期/失效 → 更新 `~/.hermes/.env` 中的对应变量
- Provider配置错误 → 检查config.yaml中的provider配置
- 网络/DNS问题 → 使用dns-hijack-fix skill

### 单个Job持续失败
**诊断路径**：
1. 查看 `~/.hermes/cron/output/<job_id>/` 最新日志
2. 查看 `~/.hermes/logs/agent.log` 对应时间段
3. 检查job配置的provider/model是否可用

## 输出 JSON 结构契约（消费者依赖）

输出文件：`~/stock_trader/market_events_latest.json`

```json
{
  "scan_time": "2026-06-15T18:02:00+08:00",
  "scan_time_utc": "2026-06-15T10:02:55Z",
  "sectors": [
    {
      "sector": "半导体/AI",
      "en": [{"title": "...", "source": "...", "date": "..."}],
      "zh": [{"title": "...", "source": "...", "date": "", "snippet": "..."}],
      "wsc": [{"title": "...", "source": "...", "date": "..."}]
    }
  ],
  "market_data": {
    "US Indices": [{"name": "标普500", "code": ".INX", "price": "7431.46", "chg_pct": "🟢+0.50%"}],
    "US Stocks": [{"name": "英伟达", "code": "NVDA.OQ", "price": "205.19", "chg_pct": "🟢+0.16%"}]
  },
  "summary": {
    "assessments": [
      {
        "sector": "半导体/AI",
        "direction": "🟡 中性",
        "significant": true,
        "hot_events": ["war", "tariff"],
        "key_news": ["标题1", "标题2"]
      }
    ]
  }
}
```

**⚠️ v5.2 教训**（2026-06-15）：消费者 `us_screener.py` 的 `load_sector_event_bias()` 原来读的是不存在的 `events` 和 `position_impact` 字段——事件板块评分 ±3 **从未生效**。正确字段是 `summary.assessments[].direction`。

**关键字段**：
- `direction`: 🟢利好 / 🔴利空 / 🟡中性（emoji + 中文）
- `significant`: boolean，是否重大事件
- `hot_events`: list[str]，热点关键词（war/tariff/conflict/sanction 等）
- `sector`: **中文**板块名（"半导体/AI"），消费者需通过 SECTOR_CN_TO_EN 映射到英文

**修改此结构时必须同步更新**：`us_screener.py` 的 `load_sector_event_bias()` 和 `SECTOR_CN_TO_EN` 映射表。

## 与交易系统的集成

事件信号通过 `market_events_latest.json` 流入交易系统。

**v4 变更（2026-06-08）：模式判断从脚本移到 AI。**

```
之前（v3）：market_narrative → 脚本自动判断模式 → 硬约束执行
现在（v4）：market_events_latest.json → AI 读事件 → AI 判断模式 → AI 决策
```

脚本不再根据 `market_narrative` 自动切换防御模式。AI 读取事件数据后，根据事件对持仓的实际影响自行判断用什么模式（aggressive/normal/cautious/defensive）和目标仓位。

事件数据仍流入 us_report.py，但只是参考信息，不是自动决策依据。

**2026-06-04 重构**：us_trader.py 和 us_screener.py 中的特朗普板块硬编码已移除。
所有板块调整现在由 market_events_latest.json 动态驱动。

**当前活跃的监控 cron**：
- 美股信号检查（21:10-05:10 工作日）
- 市场事件监控（每 2h 工作日）
- 美股盘后扫描（06:00 工作日）
- GARP 动量扫描（08:00 工作日）

港股盘中、A 股午间速报已暂停（用户确认仅关注美股）。

## 参考文件

- `references/hk-intraday-monitor-2026-06-02.md` — 港股盘中监控
- `references/us-postmarket-scan-2026-06-03.md` — 美股盘后扫描
- `references/cn-midday-briefing-2026-06-03.md` — A 股午间速报
- `references/cn-morning-briefing-2026-06-11.md` — 早间速报 09:00 BJT（工作流 + 数据源 + Alpaca 快速路径 + 日韩数据阻断说明）
- `references/commodity-market-research-workflow.md` — 大宗商品/有色金属研究工作流（钨/钼/锆/稀土等小众品种：Sogou 微信 + wallstreetcn + qt.gtimg.cn 股价+K 线 + 代码映射）
- `references/stock-surge-reverse-investigation.md` — 个股异动逆向研究流程：用户问「X怎么涨这么狠」时的五步调查法（K线确认→中文新闻→英文交叉→产业链溯源→分层输出）
- `references/v5.2-event-signal-fix.md` — 输出 JSON 结构契约 + 板块名映射（避免数据生产者/消费者结构不匹配）

## 脚本

- `scripts/market_news.py` — 多源新闻搜索（Google RSS → 搜狗微信 fallback）
