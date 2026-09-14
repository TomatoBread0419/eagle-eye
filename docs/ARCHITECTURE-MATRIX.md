# 🦅 Eagle Eye V8 — ARCHITECTURE MATRIX（组件状态矩阵）

> 生成：2026-09-13 ｜ 全部行项以 `docs/ARCHITECTURE-CURRENT.md` §0-§12 与 K-0~K-11 直接探针为准
> 状态取值：**ACTIVE / DORMANT / LEGACY / DEAD / READY-UNWIRED / ABSENT**
> 列说明：`Reads Governor?` = 该组件是否处于 Governor/lock 门控之内；`Can Trigger Order?` = 该组件是否持有产生订单的权限

---

## 一、组件矩阵

| Layer | Component | Status | Current Role | Data In | Data Out | Reads Governor? | Can Trigger Order? | Runtime Active? | Source of Truth |
|---|---|---|---|---|---|---|---|---|---|
| Market Data | Yahoo yfinance（^VIX/^TNX/^FVX/DX-Y） | ACTIVE | 采集器主源（VIX/利差/DXY） | HTTP（无 timeout） | 行情值 → 采集器 | 否（上游） | 否 | ✅（每采集时） | RUNTIME（.hermes/scripts/market_env.py:34） |
| Market Data | FRED fredgraph.csv（DGS2） | ACTIVE（回退） | yield_2y 回退源（免Key） | HTTP | DGS2 值 → 采集器 | 否 | 否 | ✅（主源失败时） | RUNTIME（get_2y_yield:91） |
| Market Data | Alpaca IEX bars | ACTIVE | VIXY 回退【结构性死亡】+ 82 只广度 | REST（IEX feed） | 日K → 采集器 | 否 | 否 | ✅（广度活跃；VIXY 路径死） | RUNTIME（us_common.get_daily_bars:250） |
| Market Data | Alpaca Trading API | DORMANT | 行情/账户/下单通道 | REST（paper） | 订单/账户 | 是（经 v7_safety_check） | 是（执行链内） | ❌（执行链未迁移） | IMPLEMENTATION（broker/alpaca_client.py） |
| Market Data | CBOE CSV（vix_history_cboe.csv） | LEGACY（stale 08-03） | Governor VIX 兜底腿 | 本地文件 | CSV 双日均值 | 是（Governor fallback） | 否 | ❌（freshness 必失败） | RUNTIME（governor_bridge:58） |
| Collector | ~/.hermes/scripts/market_env.py | **ACTIVE** | 唯一活采集器：宏观+广度→JSON | Yahoo/FRED CSV/Alpaca IEX | market_env.json | 否（上游生产者） | 否 | ✅（cron 驱动） | **RUNTIME**（活体，cron 实际执行） |
| Adapter | FRED（fred_macro.py） | READY-UNWIRED | 宏观增强（DFF/DGS2/DGS10/T10Y2Y） | fredgraph CSV / REST API | dict（context 层） | 否 | **否（设计禁止）** | ❌（无调度无消费者） | IMPLEMENTATION（新文件，实测通过） |
| Adapter | SEC EDGAR（sec_edgar.py） | READY-UNWIRED | 基本面/事件增强（facts/subs/8-K） | data.sec.gov（UA 必需） | cache/sec/ JSON | 否 | **否（设计禁止）** | ❌（仅用户显式 --live） | IMPLEMENTATION（selftest 11/11） |
| Strategy | GARP 扫描/执行链（screener+trade_executor） | DORMANT | 估值动量选股与调仓 | scan_universe.json + Alpaca | 候选/订单意图 | 是（v7_safety_check） | 是（链内） | ❌（Windows 无 cron） | IMPLEMENTATION（repo 代码） |
| Strategy | Event System（tools/event_*.py 五环） | DORMANT | 新闻→AI 推理→模拟单→复盘 | market_events_latest.json + hermes chat | events_log/scoreboard/微信 | 是（经执行边界） | 是（模拟盘链内） | ❌（cron 未迁移） | IMPLEMENTATION（stock_trader/tools/） |
| Strategy | repo strategy/market_env.py | **DEAD**（DEPRECATED 标注） | 无（活体在外部脚本同名文件） | — | — | 否 | 否 | ❌（零调用方） | DEAD CODE（仅 __init__ re-export 兼容） |
| Strategy | us_trader.py / us_trader_v6.py / macro_context.py / retired/ | LEGACY | Termux 时代历史版本 | — | — | — | — | ❌ | LEGACY（仅档案） |
| Risk | Governor（governor_bridge.py） | DORMANT（门本体完备） | GO/NO-GO 决策门：VIX regime/breadth/stop/drawdown/account | market_env.json + DB + account | GO/NO-GO | —（本体） | 间接（否决权） | ❌（仅被 trade_executor 调用时激活） | IMPLEMENTATION + RUNTIME 双查（freshness 阈值 :47-48） |
| Risk | 锁① MARKET_CLOSED | ACTIVE-ON-CALL | 闭市锁 | clock.is_open | lock | — | 是（可阻止） | ✅（喂食方就绪） | RUNTIME（trade_executor:166） |
| Risk | 锁② API_UNHEALTHY | ACTIVE-ON-CALL | API 健康锁 | client.is_healthy() | lock | — | 是 | ✅（喂食方就绪） | RUNTIME（同上） |
| Risk | 锁③ DEGRADED_MODE | ACTIVE-ON-CALL | 连续失败降级锁 | api_failure_count | lock | — | 是 | ✅（喂食方就绪） | RUNTIME（degraded_mode.py） |
| Risk | 锁④ MARKET_DATA_MISSING | **DORMANT（无喂食方）** | VIX/SPY 数据缺失锁 | 无（market_data_healthy=None） | — | — | 设计上是 | ❌（gate by omission） | IMPLEMENTATION（trading_lock.py:128） |
| Risk | 锁⑤ DATABASE_UNHEALTHY | **DORMANT（无喂食方）** | DB 异常锁 | 无（db_healthy 无调用） | — | — | 设计上是 | ❌（gate by omission） | IMPLEMENTATION（同上） |
| Execution | order_manager.py | DORMANT | 订单编排：买入去重/止损单/替代单 | 决策意图 | place_order 调用 | 是（上游已过门） | 是 | ❌ | IMPLEMENTATION（:145 去重实测） |
| Execution | **alpaca_client.place_order :120 → POST /v2/orders :164** | DORMANT（出口本体唯一且明确） | **唯一订单最终出口** | payload | Alpaca Paper 订单 | 是（全链门前置） | **是（唯一持有者）** | ❌（执行链未迁移） | IMPLEMENTATION + RUNTIME 双查 |
| Scheduler | Hermes Cron | ACTIVE | 唯一调度器：1 job | cron 表 | 进程派生 | 否 | 否（仅拉起脚本） | ✅ | RUNTIME（job e565b9a8723b 实测） |
| Scheduler | Gateway（PID 15880） | ACTIVE | 常驻调度宿主 + control pipe | — | ticker 心跳 | 否 | 否 | ✅（心跳实测） | RUNTIME（Startup 自启已装） |
| Scheduler | repo scheduler/ 目录 | DEAD（空占位） | 无（仅 __init__.py） | — | — | — | — | ❌ | DEAD CODE（find 实测） |
| State | market_env.json | **ACTIVE** | 唯一活跃 state：宏观+广度快照 | 采集器 | governor/health/fingerprint/main | 消费者侧是 | 否 | ✅（mtime 09-11 22:17） | RUNTIME |
| State | us_risk_state.json | DORMANT | position_manager 活接口（VIX 键为 Termux 残留） | GARP 执行链 | 同左 | 间接 | 否 | ❌（mtime 08-02，GARP 未跑） | RUNTIME（writer=position_manager:38/48） |
| State | eagle_eye.db（+wal/shm） | DORMANT | 审计/持仓/风控表 | storage/db.py | repos/governor | 是（stop_health） | 否 | ❌（mtime 08-30） | RUNTIME |
| State | cache/sec/（facts+subs JSON） | READY-UNWIRED | SEC 适配器 last-good 缓存 | sec_edgar.py | 未来消费者 | 否 | 否 | ❌（仅显式触发写入） | RUNTIME（4.2MB+180KB 实测） |
| Runtime | Termux 环境 | **UNKNOWN** | 最后已知 2026-07-21 全链活跃；未停未删 | — | — | — | — | ❓（本会话不可达） | 不可取证，如实标注 |

---

## 二、ACTIVE PATH（当前真正存在的生产运行链——仅此一条）

```text
Hermes Gateway (PID 15880, Startup 自启, 心跳活跃)
  ↓ cron scheduler：30 20 * * 1-5（工作日 20:30 BJT）
  ↓ job e565b9a8723b "market_env"（no-agent, deliver local）
  ↓ run_market_env.sh（venv Python 3.11.15 解释器锁定桥接）
  ↓ ~/.hermes/scripts/market_env.py main()
      ├─ Yahoo yfinance：^VIX → vix ／ ^TNX → yield_10y ／ ^FVX(5Y) → "yield_2y" ／ DX-Y.NYB → dxy
      ├─ FRED fredgraph.csv：DGS2（yield_2y 回退，免 Key）
      └─ Alpaca IEX：82 只广度（VIXY fallback 路径结构性死亡，恒空）
  ↓ interpret_macro 阈值 → regime（NORMAL/CAUTIOUS/CRISIS）
  ↓ C:/Users/[user]/stock_trader/market_env.json
      {timestamp, macro{regime,vix,dxy,yield_10y,yield_2y,spread_10y2y,fomc,warnings}, breadth, _meta}
【链到此为止——下游 governor/execution 代码完整但零调度】
```

---

## 三、NOT CONNECTED YET（尚未接线清单）

| 待接线 | 从 | 到 | 阻塞条件 | 决策门 |
|---|---|---|---|---|
| FRED 宏观增强 | fred_macro.py | 采集器 `macro.fred` 字段（try/except 嵌入） | 09-14 计划周期验收未发生；活采集器冻结中 | **GATE-1** |
| FRED_API_KEY（REST 回退源） | .env | fred_macro.py `_fetch_api` | 用户注册（免 Key CSV 主源已实测可用，此门可绕开） | **GATE-2** |
| VIX/DB 锁喂食 | trade_executor 调用方 | trading_lock 锁④⑤ | 喂食会改变 GO/NO-GO 行为 | **GATE-3**（推荐 defer） |
| spread 语义修复（DGS2 真 2Y） | FRED DGS2 | 采集器 yield_2y 主源 | 改变 regime 输入 | **GATE-4**（推荐 defer） |
| SEC Fundamental | sec_edgar.py | screener 质量维度 | GARP 链未迁移（无读者） | **B3** |
| SEC Event（8-K/Form 4） | sec_edgar.py | 事件系统映射库 | 事件链未迁移 | **B3** |
| GARP 调度 | v7_scan_runner / trade_executor_runner | Hermes cron | Windows cron 重建评估 | 迁移项 |
| 事件系统五环调度 | event_*_cron.sh | Hermes cron | 同上 | 迁移项 |
| Termux 旧 cron 退役 | — | — | Windows 等价链验收前不删 | 迁移项 |

---

## 四、快速判定口径

- **ACTIVE**：当前正在运行/被真实数据流经（仅 Gateway/Cron/采集器/三个数据源/market_env.json 满足）。
- **DORMANT**：代码与接线完整、唯一缺调度；激活 = 建 cron 或被上游调用。
- **READY-UNWIRED**：适配器就绪且实测，但按设计未接入任何消费者/调度。
- **LEGACY**：Termux 时代历史版本，仅档案价值。
- **DEAD**：无任何运行调用方（repo strategy/market_env.py、scheduler/ 空目录等）。
- **UNKNOWN**：Termux 当前状态（不可取证，不猜）。
