# 🦅 Eagle Eye V8 — CURRENT ARCHITECTURE DIAGRAMS（可视化实然架构）

> 生成：2026-09-13 ｜ 性质：**画出现状，非重设计**
> 证据基线：`docs/ARCHITECTURE-CURRENT.md` §0-§12（K-0~K-11 直接探针）+ repo 实代码 + 外部 runtime 实测
> 勿与 `docs/ARCHITECTURE.md`（V7.1 LTS 应然设计，Termux 时代）混用。

---

## 一、主图：三层 Source of Truth 与唯一 ACTIVE 链

```mermaid
flowchart TB
    subgraph DESIGN["DESIGN 应然设计 - docs/ARCHITECTURE.md (V7.1, Termux 时代)"]
        D1["GARP 动量扫描"]
        D2["AI 决策 MoA"]
        D3["事件驱动链"]
        D4["内部 scheduler 模块"]
    end

    subgraph IMPL["IMPLEMENTATION 代码实现 - [repo-root]/eagle_eye"]
        I1["strategy/screener.py"]
        I2["execution/trade_executor.py"]
        I3["execution/governor_bridge.py"]
        I4["risk/trading_lock.py 五锁"]
        I5["execution/order_manager.py"]
        I6["broker/alpaca_client.py<br/>place_order :120"]
        I7["strategy/market_env.py<br/>DEPRECATED DEAD"]
        I8["ai/ events/ monitoring/ scheduler/<br/>空占位 __init__.py"]
    end

    subgraph RUNTIME["RUNTIME 实际运行 - Windows + .hermes"]
        GW["Hermes Gateway<br/>PID 15880<br/>Startup 自启"]
        CRON["Hermes Cron<br/>job e565b9a8723b market_env<br/>30 20 * * 1-5 工作日 20:30<br/>no-agent deliver local"]
        SH["run_market_env.sh<br/>venv Python 3.11.15"]
        ME["~/.hermes/scripts/market_env.py<br/>collector main() 活体"]
        OUT["stock_trader/market_env.json<br/>唯一活产物"]
    end

    subgraph EXT["EXTERNAL DATA 外部数据源"]
        YF["Yahoo yfinance<br/>^VIX ^TNX ^FVX(5Y) DX-Y"]
        FCSVC["FRED fredgraph.csv<br/>DGS2 回退 免Key"]
        AIEX["Alpaca IEX<br/>82只广度"]
    end

    GW -->|"scheduler tick"| CRON
    CRON --> SH
    SH --> ME
    YF --> ME
    FCSVC --> ME
    AIEX --> ME
    ME --> OUT

    D1 -.->|"代码已实现"| I1
    D2 -.->|"代码已实现"| I2
    D3 -.->|"代码已实现"| I2
    D4 -.->|"空占位"| I8

    classDef design fill:#f0f0f0,stroke:#999,stroke-dasharray: 5 5,color:#000
    classDef impl fill:#fffff0,stroke:#c90,color:#000
    classDef active fill:#d5f5d5,stroke:#2e7d32,stroke-width:3px,color:#000
    classDef dead fill:#f8d7da,stroke:#c62828,stroke-dasharray: 4 4,color:#000
    class DESIGN
    class IMPL
    class GW,CRON,SH,ME,OUT,YF,FCSVC,AIEX active
    class I7,I8 dead
```

> 注：repo 死代码/空占位（红框）与运行时活体（绿框）分属三层——这就是 SOURCE OF TRUTH 分裂的核心事实。

---

## 二、当前唯一 ACTIVE 生产链（端到端实线）

```mermaid
flowchart TB
    GW["Hermes Gateway<br/>PID 15880 · 心跳活跃"]
    CRON["scheduler 30 20 * * 1-5<br/>工作日 20:30 BJT<br/>next run 2026-09-14"]
    JOB["job e565b9a8723b<br/>no-agent · deliver local"]
    SH["run_market_env.sh<br/>解释器锁定桥接"]
    PY["market_env.py main()<br/>采集 + interpret_macro"]
    YF["Yahoo<br/>VIX 10Y 5Y DXY"]
    FC["FRED CSV<br/>DGS2 回退"]
    AX["Alpaca IEX<br/>82只广度扫描"]
    JSON["market_env.json<br/>timestamp macro breadth _meta<br/>mtime 2026-09-11 22:17"]

    GW ==> CRON ==> JOB ==> SH ==> PY
    YF --> PY
    FC --> PY
    AX --> PY
    PY ==> JSON

    classDef active fill:#d5f5d5,stroke:#2e7d32,stroke-width:3px,color:#000
    class GW,CRON,JOB,SH,PY,YF,FC,AX,JSON active
```

**终点 = `market_env.json`。** 下游消费者代码存在但零调度（见主图虚线）——首个真实计划周期验收：2026-09-14 20:30（TIME-SUSTAINMENT pending）。

---

## 三、DORMANT 子系统（代码完整、接线完整、仅缺调度）

```mermaid
flowchart TB
    subgraph GARP["DORMANT GARP 扫描执行链"]
        V7["v7_scan_runner.py"] --> SC["strategy/screener.run_scan<br/>5维评分"]
        SC --> UNI["scan_universe.json 327只"]
        TR["trade_executor_runner.py"] --> TE["trade_executor.main()"]
        TE --> SAFE["v7_safety_check"]
    end

    subgraph EVENT["DORMANT 事件驱动链"]
        EV1["scan_market_events.py<br/>RSS 搜狗 华尔街见闻"] --> EV2["event_news_fetcher.py<br/>AI推理+校验层"]
        EV2 --> EV3["event_executor.py<br/>GARP去重 wash-trade防护"]
        EV3 --> EV4["event_exit_checker.py<br/>24h冷静期"]
        EV4 --> EV5["event_review.py<br/>scoreboard 加分制"]
    end

    subgraph OPS["DORMANT 运维层"]
        H["health_check.py"]
        FP["behavior_fingerprint.py"]
        CAL["calibrator.py"]
        KEL["us_kelly.py"]
    end

    classDef dormant fill:#e3e3e3,stroke:#9e9e9e,stroke-dasharray: 5 5,color:#000
    class V7,SC,UNI,TR,TE,SAFE,EV1,EV2,EV3,EV4,EV5,H,FP,CAL,KEL dormant
```

---

## 四、Governor / Trading Lock（5 锁）/ Execution Boundary

```mermaid
flowchart TB
    subgraph GOV["Governor 决策门 governor_bridge.py DORMANT"]
        VIX["macro.vix<br/>freshness 盘中6h 盘后24h<br/>stale 或 missing 到 CRISIS DENY"]
        BR["breadth.health"]
        SH2["stop_health<br/>DB recent_stops"]
        DD["drawdown peak_equity"]
        ACC["account exposure"]
        VIX --> DEC["governor_decide GO 或 NO-GO"]
        BR --> DEC
        SH2 --> DEC
        DD --> DEC
        ACC --> DEC
    end

    subgraph LOCKS["trading_lock.py 五锁"]
        L1["MARKET_CLOSED<br/>已喂食 clock.is_open"]
        L2["API_UNHEALTHY<br/>已喂食 client.is_healthy"]
        L3["DEGRADED_MODE<br/>已喂食 degraded_mode"]
        L4["MARKET_DATA_MISSING<br/>无喂食方 gate by omission"]
        L5["DATABASE_UNHEALTHY<br/>无喂食方 gate by omission"]
    end

    subgraph EXEC["EXECUTION BOUNDARY"]
        SAFE["v7_safety_check DORMANT<br/>唯一喂食点 trade_executor:166"]
        OM["order_manager<br/>买入去重 wash-trade防护"]
        PO["alpaca_client.place_order :120<br/>POST /v2/orders :164<br/>Alpaca Paper 唯一出口"]
        SAFE -->|"GO"| OM
        SAFE -->|"LOCKED NO-GO"| SKIP["跳过全部下单"]
        OM --> PO
    end

    DEC --> SAFE

    classDef fed fill:#d5f5d5,stroke:#2e7d32,color:#000
    classDef unfed fill:#f8d7da,stroke:#c62828,stroke-dasharray: 4 4,color:#000
    classDef gate fill:#fff3cd,stroke:#f9a825,stroke-width:2px,color:#000
    classDef dormant fill:#e3e3e3,stroke:#9e9e9e,stroke-dasharray: 5 5,color:#000
    class VIX,BR,SH2,DD,ACC dormant
    class DEC,SAFE,OM gate
    class PO gate
    class L1,L2,L3 fed
    class L4,L5 unfed
    class SKIP dormant
```

---

## 五、适配器层（READY / UNWIRED —— 未进入任何运行链）

```mermaid
flowchart TB
    subgraph FAD["FRED 适配器 Phase B1 READY UNWIRED"]
        F1["fredgraph.csv 免Key主源<br/>DFF DGS2 DGS10 T10Y2Y<br/>实测 DFF 3.63"]
        F2["api.stlouisfed.org<br/>有Key回退 无Key时跳过"]
        F3["~/.hermes/scripts/fred_macro.py<br/>selftest 通过 永不抛异常"]
        F1 --> F3
        F2 -.->|"FRED_API_KEY 缺失"| F3
    end

    subgraph SAD["SEC 适配器 Phase B2 READY UNWIRED"]
        S1["companyfacts 30d TTL"]
        S2["submissions 24h TTL<br/>8-K Form 3/4/5 过滤"]
        S3["~/.hermes/scripts/sec_edgar.py<br/>selftest 11/11 UA通道实测200"]
        S4["stock_trader/cache/sec/<br/>Apple facts 4.2MB 已缓存"]
        S1 --> S3
        S2 --> S3
        S3 --> S4
    end

    F3 -.->|"UNWIRED GATE-1<br/>验收后 try/except 嵌入 macro.fred"| TGT1["market_env.py 活体"]
    S3 -.->|"UNWIRED B3<br/>GARP/事件系统迁移后才有读者"| TGT2["screener 与 事件系统"]

    classDef ready fill:#d4edda,stroke:#28a745,stroke-width:2px,color:#000
    class F1,F3,S1,S3,S4 ready
```

> 审计要点：**ADAPTER READY ≠ CONSUMER CONNECTED**。两适配器当前无任何调度、无任何消费者、无 Governor 权限。

---

## 六、Fail-Safe 流向（VIX 链）

```mermaid
flowchart TB
    YF["Yahoo ^VIX 主源"] -->|"成功"| REG["interpret_macro<br/>NORMAL CAUTIOUS CRISIS"]
    YF -->|"失败"| VIXY["VIXY fallback<br/>结构性死亡 limit=1 vs len>=5"]
    VIXY -->|"恒空"| NULL["macro.vix = null"]
    REG --> JSON["market_env.json"]
    NULL --> JSON
    JSON -->|"新鲜"| GOV["governor_bridge GO"]
    JSON -->|"过期"| CSV["CBOE CSV 兜底<br/>stale 08-03 必失败"]
    CSV --> MISSING["None missing"]
    MISSING --> CRISIS["CRISIS 保守 DENY<br/>FAIL-CLOSED"]
    GOV --> TR["trade_executor DORMANT"]
    CRISIS --> TR
    TR -->|"locked"| SKIP["skip"]
    TR -->|"unlocked"| ORD["place_order"]

    classDef ok fill:#d4edda,stroke:#28a745,color:#000
    classDef risk fill:#f8d7da,stroke:#c62828,color:#000
    class YF,REG,JSON,GOV,TR,ORD ok
    class VIXY,CSV,MISSING,CRISIS,SKIP risk
```

---

## Architectural Reading Rules（审计阅读规则）

| 规则 | 含义 |
|---|---|
| **实线 `-->`** | 当前真实存在的运行/调用关系 |
| **虚线 `-.->`** | 尚未接线的未来关系，或存在但无调度的 DORMANT 关系（图内已标注） |
| **🟢 绿色节点** | ACTIVE（正在运行） |
| **🟡 黄色节点** | 决策门/边界节点（Governor、trading_lock、place_order） |
| **🔴 红色节点** | 风险/缺陷（无喂食的锁、stale 兜底、死路径）或 DEAD CODE |
| **ACTIVE ≠ DESIGN** | 本图画的是 RUNTIME（实然）；`ARCHITECTURE.md` 是应然设计，两者允许不一致 |
| **ADAPTER READY ≠ CONSUMER CONNECTED** | FRED/SEC 适配器已就绪且实测，但零消费者零调度 |
| **DORMANT ≠ DEAD** | DORMANT = 代码与接线完整、仅缺调度；DEAD = 无任何运行调用方 |
| **DEAD CODE ≠ 当前运行链** | repo `strategy/market_env.py` 已标废弃，活体在外部脚本同名文件 |

---

## 事实锚点（供审计比对，全部经直接探针验证）

- 唯一 ACTIVE cron：`market_env`（job e565b9a8723b），周一至周五 20:30 BJT；无重复 job；`macro_context` 未注册。
- Gateway：PID 15880，Startup 登录自启（UAC 回退方案），心跳活跃。
- Governor 仍是决策门（fail-closed）；`place_order:120` 是唯一执行出口（paper 端点）。
- GARP = DORMANT；Event system = DORMANT；repo `strategy/market_env.py` = DEAD/DEPRECATED；旧 Termux = LEGACY（仅文档记载）。
- FRED adapter = READY / UNWIRED（GATE-1）；SEC adapter = READY / UNWIRED（B3）。
- trading locks = 5（其中 MARKET_DATA_MISSING / DATABASE_UNHEALTHY 两锁无喂食方）。
- 首个真实计划周期验收：2026-09-14 20:30（K-10 九条 PASS 标准就绪）。
