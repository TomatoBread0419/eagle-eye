# 🦅 Eagle Eye V8 — CURRENT ARCHITECTURE（当前真实运行架构）

> 生成：2026-09-12 ｜ 证据链：K-0~K-11 直接探针（本会话全部结论经本机实测，未采信转录）
> 性质：**实然架构**（what actually runs）。仓库根 `ARCHITECTURE.md` = 应然设计（V7.1 LTS），`docs/architecture.md` = Termux 时代树状图，均勿混用。
> Source of Truth：Windows 真身 `[repo-root]/eagle_eye` + 运行时 `C:/Users/[user]/.hermes/scripts` + 实际 state（`C:/Users/[user]/stock_trader/`）。

---

## 0. 一句话现状

```text
Windows 上唯一 ACTIVE 生产链 = market_env 采集
（cron e565b9a8723b，工作日 20:30 BJT，Gateway→scheduler→桥接脚本→采集器→market_env.json）
其余子系统（GARP/AI决策/trade_executor/事件/健康检查）代码完整但零调度 = DORMANT。
Termux = UNKNOWN（不可达，最后已知活跃 2026-07-21）。
首个真实计划周期验收 = 2026-09-14 20:30（TIME-SUSTAINMENT pending）。
```

---

## 1. Runtime Source of Truth（DESIGN / IMPLEMENTATION / RUNTIME）

| 维度 | DESIGN | IMPLEMENTATION | RUNTIME |
|---|---|---|---|
| 市场环境采集 | repo `strategy/market_env.py` | 同名完整实现 | **DEAD**（仅被 `strategy/__init__.py` re-export，`main()` 无调用方）。活体 = `.hermes/scripts/market_env.py` |
| 调度器 | repo `scheduler/` | 空 `__init__.py`（占位） | **Hermes Gateway/Cron**（外部，`%LOCALAPPDATA%/hermes`） |
| GARP / 事件系统 | repo 模块 + 事件 tools | 完整实现 | **DORMANT**（Windows 无对应 cron job） |
| 风控 | `risk/trading_lock.py` 5 锁设计 | 已实现 | 3 锁有喂食、2 锁（MARKET_DATA_MISSING / DATABASE_UNHEALTHY）**无喂食方** |
| 下单出口 | — | `broker/alpaca_client.py place_order():120 → alpaca_post('/v2/orders'):164` | DORMANT（执行链未迁移） |
| Termux | 历史生产环境 | cron 全套（最后已知 2026-07-21 全 ok） | **UNKNOWN**（未停未删） |

规则：`设计文档 ≠ 代码 ≠ 实际运行` 时，以 RUNTIME 为准并在本文档记录分歧；不得默默修改任何一方。

---

## 2. Runtime Map（ACTIVE / DORMANT / MIGRATION / LEGACY / DEAD）

```text
[ACTIVE]    Hermes Gateway (PID 15880, Startup 自启)
              ↓ cron scheduler 30 20 * * 1-5
              ↓ job e565b9a8723b "market_env" (no-agent, deliver local)
              ↓ run_market_env.sh（venv Python 3.11.15 解释器锁定桥接）
              ↓ .hermes/scripts/market_env.py main()
              ↓ Yahoo yfinance(^VIX/^TNX/^FVX/DX-Y) + FRED CSV(DGS2 回退) + Alpaca IEX(82只广度)
              ↓ stock_trader/market_env.json          ← 唯一活跃 state 写入

[DORMANT]   GARP:  v7_scan_runner→strategy.screener.run_scan ｜ trade_executor_runner→execution.trade_executor.main
            Event: event_*_cron.sh→stock_trader/tools/event_*.py（采集/AI分析/执行/日报/复盘 5 环）
            Ops:   health_check / behavior_fingerprint / compliance_audit / calibrator / us_kelly
            Risk:  governor_bridge GO/NO-GO（仅被 trade_executor 调用时激活）

[MIGRATION] Termux cron 全套 → Windows（调度层迁移未完成；GARP/事件 cron 尚未在 Windows 重建）

[LEGACY]    us_trader.py / us_trader_v6.py / us_screener.py(.bak) / macro_context.py /
            market_breadth.py(.hermes) / retired/ / backup_refactor_20260715/ / main.py v6_bridge

[DEAD CODE] repo strategy/market_env.py（活体在外部脚本）；repo ai/ events/ monitoring/ scheduler/
            四目录（find -type f 实测各仅含 __init__.py，空占位模块）
```

---

## 3. 系统总览图（按实际调用关系）

```text
Hermes Gateway (Startup 自启, control pipe)
 ↓ cron scheduler（ticker 心跳）
 ↓ job e565b9a8723b
 ↓ run_market_env.sh → Python 3.11.15 (Hermes venv)
 ↓ market_env.py 采集器
 ├─ Yahoo: ^VIX→vix ｜ ^TNX→yield_10y ｜ ^FVX(5Y!)→"yield_2y" ｜ DX-Y.NYB→dxy
 ├─ FRED fredgraph CSV (DGS2): yield_2y 回退（免 Key）
 ├─ Alpaca IEX: VIXY fallback【结构性死亡: limit=1 vs len≥5】+ 82 只广度
 ├─ interpret_macro 阈值 → NORMAL/CAUTIOUS/CRISIS
 ↓ market_env.json {timestamp, macro, breadth, _meta}
 ↓
[DORMANT 消费者]
 governor_bridge:47-48 freshness(盘中≤6h/盘后≤24h) → fail-closed(DENY)  ← 唯一决策消费者
 behavior_fingerprint / health_check / main.py status                    ← 观测
```

---

## 4. 数据源盘点

| 数据源 | 状态 | 调用点 | 数据 | 失败行为 | 影响交易 |
|---|---|---|---|---|---|
| Yahoo yfinance | **ACTIVE** | 采集器 yf_quick:34 | VIX/10Y/5Y/DXY | 异常→None 静默；无 timeout | 是（VIX→regime→DENY） |
| FRED fredgraph CSV（免Key） | ACTIVE（回退） | 采集器 get_2y_yield:91 | DGS2 | try/except→None | 否 |
| Alpaca IEX bars | ACTIVE | us_common get_daily_bars:250 | VIXY + 82 只日K | 返回 [] 静默 | 间接 |
| Alpaca Trading API | DORMANT | broker/alpaca_client 全量 | 行情/账户/下单 | is_healthy→API_UNHEALTHY 锁 | 执行时是 |
| CBOE CSV | DORMANT(stale 08-03) | governor_bridge:58 | VIX 历史 | freshness 必败→missing→DENY | 是（fail-closed 腿） |
| 新闻 RSS/搜狗/华尔街见闻 | DORMANT | scan_market_events.py | 事件新闻 | 跳过 | 经事件链 |
| hermes chat (LLM) | DORMANT | tools/event_news_fetcher | 事件因果分析 | 记录原始事件不分析 | 经事件链 |
| SEC / FRED REST API | **ABSENT**（Windows 无调用代码） | — | — | — | — |

---

## 5. Market Environment 链（唯一活链）

```text
market_env.json
  macro: {regime, vix, dxy, yield_10y, yield_2y, spread_10y2y, fomc, warnings}
  breadth: {health, pct_above_ma50/200, ad_ratio, new_highs/lows, ...}
  _meta: {elapsed_s, version:6.0}
        ↓
governor_bridge.py（6h 盘中 / 24h 盘后 freshness）
  JSON 新鲜 → macro.vix (_source:json) → governor_decide GO/NO-GO
  JSON 过期 → CBOE CSV 双日均值（freshness 同判必败） → (None,'missing') → CRISIS 保守 + DENY
        ↓
trade_executor.v7_safety_check → GO / NO-GO
```

**已知语义问题（记录不修，见 §10 风险登记册）**：
1. `yield_2y` 主源 = `^FVX` = **5 年期**（源码注释"5年期近似"自证），`spread_10y2y` 实为 10Y−5Y；FRED DGS2 回退才是真 2Y。→ 修复需换数据源，影响 regime 输入 = **决策门**。
2. VIXY fallback 结构性死亡（:65 传 `limit=1`，us_common:268 要求 `len≥5` → 恒 []）。Yahoo 失败实际走向 = fail-closed DENY，非坏值采信。若未来修复：**必须捆绑缩放语义（实测 VIX/VIXY≈0.9，非旧注释的 10）+ 合理区间校验（如 10≤VIX≤80）；禁止只改 limit**。
3. VIX 时效语义 = T-1 收盘（cron 20:30 BJT = 美东盘前，当日 bar 未收）。

---

## 6. Governor / Trading Lock / Execution Boundary

**Governor 检查项**（governor_bridge）：VIX regime（CRISIS→DENY）、breadth health、stop_health（DB recent_stops）、drawdown、account/exposure。

**trading_lock 五锁**（trading_lock.py:36-40，喂食实测）：

| 锁 | 喂食方 | 状态 |
|---|---|---|
| MARKET_CLOSED | trade_executor:166（clock.is_open） | ✅ 活 |
| API_UNHEALTHY | 同上（client.is_healthy） | ✅ 活 |
| DEGRADED_MODE | 同上（degraded_mode.check_and_update，risk/degraded_mode.py） | ✅ 活 |
| MARKET_DATA_MISSING | **无**（market_data_healthy 默认 None，全树 0 调用） | ⚠️ 永不触发（gate by omission） |
| DATABASE_UNHEALTHY | **无**（db_healthy 全树无喂食） | ⚠️ 同上 |

**Execution Boundary 最终出口**：`alpaca_client.place_order():120 → POST /v2/orders:164`（paper 端点）。保护层：买入去重（order_manager:145）、wash-trade 防护（事件执行器先取消旧止损）、trading_lock 前置门。

---

## 7. State / Cache / DB

| 文件 | 写者 | 读者 | 状态 |
|---|---|---|---|
| market_env.json | 采集器 cron（**唯一活 writer**） | governor_bridge/fingerprint/health_check/main/storage | ACTIVE（新鲜） |
| us_risk_state.json | position_manager:38/48、portfolio_manager:76 | 同左 + health_check(CRITICAL_FILES)/migrate | **DORMANT**（mtime 08-02；VIX 键为 Termux 残留；文件本身是 position_manager 活接口，**非废物**） |
| eagle_eye.db(+wal/shm) | storage/db.py | repos/market、governor stop_health | DORMANT（mtime 08-30） |
| events_log / queue / scoreboard / event_map | 事件链 tools/* | 同左 | DORMANT |
| vix_history_cboe.csv | （Termux 时代） | governor_bridge CSV 腿 | STALE（08-03） |

---

## 8. Fail-Safe 矩阵

| 失败 | 行为 | 类型 |
|---|---|---|
| Yahoo 失败 | →VIXY（死）→None→macro.vix:null→governor missing→**DENY** | FAIL-CLOSED |
| Alpaca 行情失败 | 返回 []，静默 | FAIL-SOFT |
| Alpaca 交易 API 失败 | API_UNHEALTHY 锁 + degraded_mode | FAIL-CLOSED |
| DB 异常 | 锁存在但无喂食 | 设计 FAIL-CLOSED / 实际 FAIL-OPEN(by omission) |
| state stale / market_env 缺失 | freshness 过期 → missing → DENY | FAIL-CLOSED |
| AI/采集失败（事件链） | 记录原始事件不分析 | FAIL-SOFT |
| cron/Gateway 失败 | job 不触发，watchdog DORMANT | 无自动恢复 |

---

## 9. 运行边界

```text
Windows（生产，K-7/K-10 已验收至 Gateway 层）
├── Hermes Gateway PID 15880（Startup 自启；Scheduled Task 因 UAC 跳过，回退 Startup 文件夹）
├── Hermes cron：1 job（market_env）；无重复；macro_context 未注册
├── V8 真身：[repo-root]/eagle_eye（HEAD c82a2f4, main）
├── 运行时脚本：C:/Users/[user]/.hermes/scripts（含桥接 run_market_env.sh）
├── state：C:/Users/[user]/stock_trader/
└── logs：C:/Users/[user]/AppData/Local/hermes/logs/gateway.log

Termux：UNKNOWN（本会话不可达；未检查未停止未修改）
```

---

## 10. 风险登记册（A4 裁决）

| # | 风险 | 级别 | 裁决 |
|---|---|---|---|
| R1 | VIXY fallback 死路径 + 无缩放语义 | NON-BLOCKING（不可达且当前安全） | 记录；修复须捆绑缩放+校验（见 §5.2） |
| R2 | MARKET_DATA_MISSING / DATABASE_UNHEALTHY 无喂食 | NON-BLOCKING（Governor 腿已 fail-closed 兜底） | **决策门**：喂食会改 GO/NO-GO，需显式签核 |
| R3 | spread_10y2y 实为 10Y−5Y（^FVX） | 数据语义 | **决策门**：换 FRED DGS2 修语义但改变 regime 输入 |
| R4 | yfinance 无 timeout、静默 None | 可靠性 | 记录；Phase B 适配器必须带显式 timeout |
| R5 | .hermes/scripts 内 Termux 残留（owner_report 等） | 可维护性 | 不在活链，仅记录 |
| R6 | 双 market_env.py 同名（repo vs .hermes） | 可维护性 | 记录；repo 侧不应移动（防破坏 re-export/历史） |
| R7 | "双状态文件消费者分裂"（K-4 旧结论） | 已裁决撤销 | 实为单 writer 双产物（同秒 mtime 铁证），非分裂 |

---

## 11. 未决决策门

1. **GATE-1（2026-09-14 20:30 后）**：首个真实计划周期验收（PASS 九条标准见 K-10）通过后，才允许触碰活采集器（FRED 接线）。
2. **GATE-2**：FRED_API_KEY 注册（用户动作，agent 不得代建）；若采用免 Key fredgraph.csv 路径则此门可绕开。
3. **GATE-3**：R2 两锁是否喂食（改 GO/NO-GO，需显式签核）。
4. **GATE-4**：R3 spread 数据源是否换 FRED DGS2（改 regime 输入，需显式签核）。


---

## 12. Phase B 适配器状态（2026-09-12，外部运行时侧）

| 适配器 | 路径 | 状态 | 实测 | 消费者 | 调度 |
|---|---|---|---|---|---|
| FRED（B1） | `~/.hermes/scripts/fred_macro.py` | 适配器完成+实测 | DFF 3.63 / DGS2 4.43 / DGS10 4.83 / T10Y2Y 0.39（免 Key fredgraph CSV，经 us_common.url_get 加固通道；裸 urllib 实测必超时） | **无**（GATE-1 后才以 try/except 嵌入采集器 macro.fred） | 无 |
| SEC EDGAR（B2） | `~/.hermes/scripts/sec_edgar.py` | 适配器+cache+离线自检 11/11 | live 探针: Apple facts 4.2MB + submissions 180KB 落盘 `stock_trader/cache/sec/`；UA 通道 200 | **无**（B0: screener/事件系统 DORMANT，不建无读者依赖） | 无 |

边界声明：两者均为 pure-additive context 层——不改 Governor 阈值 / trading_lock / 执行边界 /
仓位规则；不持有 BUY/SELL/Order 权限；任何失败返回 None，绝不阻塞采集器。
SEC cache TTL 分源：companyfacts 30d / submissions 24h（B4）。
接入时序：FRED 接线（3 行 try/except）= 09-14 计划周期验收后的第一个活路径编辑（GATE-1）。
