#!/usr/bin/env python3
"""V8 Phase 3 Step 2 — governor_bridge.py (Shadow 模式治理胶水层)

授权: 2026-08-08 Step 2 (仅创建 bridge + tests, 不拦截交易)
契约: GOVERNOR_DATA_CONTRACT.md v1.2
位置: ~/eagle_eye/execution/governor_bridge.py
      (pool_builder.py:281 / us_trader.py:18 已有 sys.path.insert(0, stock_trader))

职责:
  1. 6 类输入加载 (holdings / market_env / stop_health / account_snapshot /
     expansions_7d / held_last_5d), 每项返回 (data, freshness)
  2. check_governor(intent_type 分流):
       strategy_entry / strategy_exit / replacement → governor_decide
       risk_exit / stop_loss / take_profit          → ALLOW (BYPASS, 数据加载前分流)
  3. Shadow audit JSONL (append, 含 intent_type + data_freshness)
  4. safe-by-default: 数据缺失/过期 → 保守 DENY, 永不 crash,
     Governor 永不看到坏数据 (vix 缺失不落入 Governor 默认 15.0 盲区)

冻结遵守:
  - portfolio_governor.py 不修改 (纯 import)
  - order_manager.py 不修改
  - 零 Alpaca 写操作 (account 读取用 requests GET, 可注入 mock)
  - 禁止 import alpaca_trade_api / PlaceOrderRequest (契约 A-1)
"""
import os
import sys
import json
import csv
import sqlite3
import requests
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.expanduser("~/stock_trader")
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from portfolio_governor import governor_decide
except ImportError:
    governor_decide = None

# ══════════════════════════════════════════════════════════
# 契约 v1.2 门限
# ══════════════════════════════════════════════════════════
THRESHOLD_HOLDINGS_INTRADAY_MIN = 10       # holdings ≤10min 盘中
THRESHOLD_HOLDINGS_POST_HOURS = 24         # ≤24h 盘后
THRESHOLD_MARKET_ENV_INTRADAY_HOURS = 6    # market_env ≤6h 盘中 (v1.2 D-2)
THRESHOLD_MARKET_ENV_POST_HOURS = 24       # ≤24h 盘后
THRESHOLD_STOPS_HOURS = 24                 # recent_stops ≤24h
THRESHOLD_ORDERS_HOURS = 24                # orders_all.json ≤24h

BYPASS_INTENTS = {"risk_exit", "stop_loss", "take_profit"}
GOVERNED_INTENTS = {"strategy_entry", "strategy_exit", "replacement"}

DEFAULT_DB = os.path.join(BASE_DIR, "eagle_eye.db")
DEFAULT_MARKET_ENV = os.path.join(BASE_DIR, "market_env.json")
DEFAULT_ORDERS = os.path.join(BASE_DIR, "orders_all.json")
DEFAULT_VIX_CSV = os.path.join(BASE_DIR, "vix_history_cboe.csv")
DEFAULT_AUDIT = os.path.join(BASE_DIR, "audit", "governor_shadow_decisions.jsonl")

# ══════════════════════════════════════════════════════════
# 工具
# ══════════════════════════════════════════════════════════


def _parse_ts(s):
    """ISO 时间戳 → aware datetime (处理 Z / +00:00 / 无时区假定 UTC)。失败返回 None。"""
    if not s:
        return None
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t
    except Exception:
        return None


def _is_market_hours(now):
    """美股盘中判定 (近似): 周一至五 13:30-20:00 UTC (美东 9:30-16:00 夏令时)。"""
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 13 * 60 + 30 <= minutes <= 20 * 60


def _freshness(ts_dt, intraday_min=None, post_hours=None, now=None):
    """按契约门限判定 freshness: 'ok' | 'stale'。ts_dt 为 None → 'missing' 由调用方处理。"""
    now = now or datetime.now(timezone.utc)
    if ts_dt is None:
        return "missing"
    age_h = (now - ts_dt).total_seconds() / 3600.0
    if _is_market_hours(now):
        limit = (intraday_min / 60.0) if intraday_min else post_hours
    else:
        limit = post_hours
    return "ok" if age_h <= limit else "stale"


def _load_env():
    """从候选 .env 逐个加载密钥 (血训 2026-07-20); 找齐 ALPACA 双键才停。

    2026-09-20 修复: 原命中首个存在的 .env 即 return —— 迁移后 ~/.hermes/.env
    存在但无 ALPACA 键, 真实凭证(~/stock_trader/.env)永远读不到, 导致 account
    输入恒 missing (shadow 记录恒 ACCOUNT_UNAVAILABLE)。现改为找齐双键才停;
    候选耗尽仍缺键 → 维持 "no alpaca keys" 异常 (fail-closed 不变)。
    """
    for p in [os.path.expanduser("~/.hermes/.env"),
              os.path.expanduser("~/.env"),
              os.path.join(BASE_DIR, ".env"),
              os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]:
        if os.path.isfile(p):
            try:
                with open(p, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, _, v = line.partition("=")
                            k, v = k.strip(), v.strip().strip('"').strip("'")
                            if k:
                                os.environ.setdefault(k, v)
            except Exception:
                pass
            if (os.environ.get("ALPACA_API_KEY") or os.environ.get("APCA_API_KEY")) and (
                os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("APCA_SECRET_KEY")
            ):
                return


def _default_account_getter():
    """Alpaca GET /v2/account → {equity, cash, timestamp}。纯只读。"""
    _load_env()
    key = os.environ.get("ALPACA_API_KEY") or os.environ.get("APCA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("APCA_SECRET_KEY")
    base = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    if not key or not secret:
        raise RuntimeError("no alpaca keys")
    resp = requests.get(
        f"{base}/v2/account",
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
        timeout=15,
    )
    resp.raise_for_status()
    d = resp.json()
    return {
        "equity": float(d.get("equity", 0)),
        "cash": float(d.get("cash", 0)),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _audit(record, audit_path):
    """Shadow audit JSONL: append 一行一个决策。永不 crash。"""
    try:
        if audit_path:
            os.makedirs(os.path.dirname(audit_path), exist_ok=True)
            with open(audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════
# Layer A — 数据加载 (每项: (data, freshness))
# ══════════════════════════════════════════════════════════


def load_holdings(db_path=DEFAULT_DB, equity=None, now=None):
    """governor_positions 表 → {symbol: {weight, score}}。

    weight = market_value/equity (契约 §2.1); equity 不可得时用多头市值归一。
    空头 (qty<0) 计入持仓数 (R1) 但 weight 按实际符号。
    """
    now = now or datetime.now(timezone.utc)
    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute("SELECT symbol, qty, market_value, side, synced_at FROM governor_positions")
        rows = cur.fetchall()
        con.close()
        if not rows:
            return None, "missing"
        latest = max(r[4] for r in rows if r[4])
        fresh = _freshness(_parse_ts(latest), THRESHOLD_HOLDINGS_INTRADAY_MIN,
                           THRESHOLD_HOLDINGS_POST_HOURS, now)
        total_mv = sum(float(r[2]) for r in rows if float(r[2]) > 0) or 0.0
        holdings = {}
        for sym, qty, mv, side, _ in rows:
            mv = float(mv)
            if equity:
                w = mv / float(equity)
            elif total_mv:
                w = mv / total_mv
            else:
                w = 0.0
            holdings[sym] = {"weight": round(w, 6), "score": 0}
        return holdings, fresh
    except Exception:
        return None, "missing"


def load_market_env(env_path=DEFAULT_MARKET_ENV, vix_csv_path=DEFAULT_VIX_CSV, now=None):
    """market_env.json → {vix_2dma, snapshot_vix, _source}。

    fallback 链 (契约 §2.2): JSON 新鲜 → 用 macro.vix (2dma 近似, 单点);
    JSON 过期但 CBOE CSV 新鲜 → CSV 最后 2 日 CLOSE 均值; 双源均不可用 → (None,'missing')。
    """
    now = now or datetime.now(timezone.utc)
    vix_json, ts_json, ts_file = None, None, None
    if os.path.exists(env_path):
        try:
            d = json.load(open(env_path, encoding="utf-8"))
            vix_json = float(d.get("macro", {}).get("vix"))
            ts_json = _parse_ts(d.get("timestamp")) or \
                datetime.fromtimestamp(os.path.getmtime(env_path), tz=timezone.utc)
            ts_file = os.path.getmtime(env_path)
        except Exception:
            pass
    csv_vix, csv_ts = None, None
    if os.path.exists(vix_csv_path):
        try:
            with open(vix_csv_path, encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            closes = [float(r["CLOSE"]) for r in rows if r.get("CLOSE")]
            if len(closes) >= 2:
                csv_vix = (closes[-1] + closes[-2]) / 2.0
            csv_ts = datetime.fromtimestamp(os.path.getmtime(vix_csv_path), tz=timezone.utc)
        except Exception:
            pass
    if vix_json is not None:
        f = _freshness(ts_json, THRESHOLD_MARKET_ENV_INTRADAY_HOURS * 60,
                       THRESHOLD_MARKET_ENV_POST_HOURS, now)
        if f == "ok":
            return {"vix_2dma": vix_json, "snapshot_vix": vix_json, "_source": "json"}, "ok"
    if csv_vix is not None:
        f = _freshness(csv_ts, THRESHOLD_MARKET_ENV_INTRADAY_HOURS * 60,
                       THRESHOLD_MARKET_ENV_POST_HOURS, now)
        if f == "ok":
            return {"vix_2dma": csv_vix,
                    "snapshot_vix": vix_json if vix_json is not None else csv_vix,
                    "_source": "csv"}, "stale"
    # 双源均不可用/过期 → 契约: CRISIS 保守 + DENY (由 check_governor 执行)
    return None, "missing"


def load_stop_health(db_path=DEFAULT_DB, now=None):
    """recent_stops 表 → {last_loss_stop_days, stale_recalc_days, recent_stops}。

    last_loss_stop_days 仅 loss_pct<=0 的 LOSS_STOP 参与 (契约 §2.3 / 4.1 裁决)。
    表不存在/空 → (None,'missing') — 无法证明止损健康。
    """
    now = now or datetime.now(timezone.utc)
    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute("SELECT symbol, stopped_at, loss_pct, created_at FROM recent_stops")
        rows = cur.fetchall()
        con.close()
        if not rows:
            return None, "missing"
        created_ts = max(_parse_ts(r[3]) or now for r in rows)
        fresh = _freshness(created_ts, None, THRESHOLD_STOPS_HOURS, now)
        loss_stops = [r for r in rows if r[2] is None or float(r[2]) <= 0]
        last_loss_ts = None
        for r in loss_stops:
            t = _parse_ts(r[1])
            if t and (last_loss_ts is None or t > last_loss_ts):
                last_loss_ts = t
        last_loss_days = 999 if last_loss_ts is None else max((now - last_loss_ts).days, 0)
        stale_recalc_days = max((now - created_ts).days, 0)
        recent = []
        for r in rows:
            t = _parse_ts(r[1])
            if t and (now - t).days <= 30:
                recent.append({
                    "symbol": r[0],
                    "loss_pct": float(r[2]) if r[2] is not None else 0.0,
                    "stopped_at": r[1],
                })
        return {
            "last_loss_stop_days": last_loss_days,
            "stale_recalc_days": stale_recalc_days,
            "recent_stops": recent,
        }, fresh
    except Exception:
        return None, "missing"


def load_orders(orders_path=DEFAULT_ORDERS, now=None):
    """orders_all.json → ({expansions_7d, held_last_5d}, freshness)。

    expansions_7d = 近 7 天 filled BUY 去重 symbol 数 (契约 §2.4)
    held_last_5d  = 近 5 天 filled BUY symbol 集合 (契约 §7)
    空文件 (合法) → 0/set(); 损坏 JSON → (None,'missing')。
    """
    now = now or datetime.now(timezone.utc)
    try:
        data = json.load(open(orders_path, encoding="utf-8"))
        if not isinstance(data, list):
            return None, "missing"
        fresh = _freshness(
            datetime.fromtimestamp(os.path.getmtime(orders_path), tz=timezone.utc),
            None, THRESHOLD_ORDERS_HOURS, now)
        cutoff_7d = now - timedelta(days=7)
        cutoff_5d = now - timedelta(days=5)
        expansions, held = set(), set()
        net_qty_5d = {}  # symbol → 5 天窗口净买入量 (buy +, sell −)
        net_qty_7d = {}  # symbol → 7 天窗口净买入量
        for o in data:
            if not isinstance(o, dict):
                continue
            sym = o.get("symbol")
            if not sym:
                continue
            ts = o.get("filled_at") or o.get("created_at") or o.get("submitted_at")
            t = _parse_ts(ts)
            if t is None:
                continue
            side = o.get("side")
            try:
                qty = float(o.get("qty") or 0)
            except (TypeError, ValueError):
                qty = 0.0
            if t >= cutoff_5d:
                if side == "buy":
                    held.add(sym)
                    net_qty_5d[sym] = net_qty_5d.get(sym, 0.0) + qty
                elif side == "sell":
                    net_qty_5d[sym] = net_qty_5d.get(sym, 0.0) - qty
            if t >= cutoff_7d:
                if side == "buy":
                    expansions.add(sym)
                    net_qty_7d[sym] = net_qty_7d.get(sym, 0.0) + qty
                elif side == "sell":
                    net_qty_7d[sym] = net_qty_7d.get(sym, 0.0) - qty
        # SELL 后修正 (契约 §7.2 + §2.4 "净新增"): 窗口内净仓位 ≤ 0 → 已清仓 → 移除
        for sym in list(held):
            if net_qty_5d.get(sym, 0.0) <= 0:
                held.discard(sym)
        for sym in list(expansions):
            if net_qty_7d.get(sym, 0.0) <= 0:
                expansions.discard(sym)
        return {"expansions_7d": len(expansions), "held_last_5d": held}, fresh
    except Exception:
        return None, "missing"


def load_account_snapshot(account_getter=None, now=None):
    """account_snapshot {equity, cash, timestamp} (契约 §6)。可注入 getter (测试)。"""
    now = now or datetime.now(timezone.utc)
    if account_getter is None:
        account_getter = _default_account_getter
    try:
        snap = account_getter()
        if snap is None:
            return None, "missing"
        return {
            "equity": float(snap.get("equity", 0)),
            "cash": float(snap.get("cash", 0)),
            "timestamp": snap.get("timestamp") or now.isoformat(),
        }, "ok"
    except Exception:
        return None, "missing"


# ══════════════════════════════════════════════════════════
# Layer B — check_governor (intent_type 分流)
# ══════════════════════════════════════════════════════════


def check_governor(intent_type, candidates=None, side="buy", *,
                   db_path=None, market_env_path=None, orders_path=None,
                   vix_csv_path=None, audit_path=None, account_getter=None,
                   now=None) -> dict:
    """治理入口 (Shadow 模式, 不拦截交易)。

    intent 分流:
      risk_exit / stop_loss / take_profit → ALLOW (BYPASS_xxx), 数据加载前返回
      strategy_entry / strategy_exit / replacement → 加载数据 → governor_decide
      其他 → DENY (UNKNOWN_INTENT_xxx)

    买方向数据 gate (safe-by-default, 任一不过 → DENY):
      account missing    → ACCOUNT_UNAVAILABLE
      holdings missing   → HOLDINGS_UNAVAILABLE ; stale → HOLDINGS_STALE
      market_env missing → VIX_UNAVAILABLE     ; stale(CSV fallback) → 继续
      stops missing      → STOPS_UNAVAILABLE   ; stale → STOP_STALE (契约: BUY/REPLACE DENY)
      orders missing     → ORDERS_UNAVAILABLE  ; stale → ORDERS_STALE (契约: DENY 全部 BUY)

    卖出 (side=sell): 永不阻断 (SELL_NOT_BLOCKED); 数据可用时记录 Governor 输出。
    返回 dict 同时写 shadow audit JSONL。
    """
    now = now or datetime.now(timezone.utc)
    candidates = candidates or []
    audit_path = audit_path or DEFAULT_AUDIT

    record = {
        "timestamp": now.isoformat(),
        "intent_type": intent_type,
        "side": side,
        "candidates": [
            {"symbol": c.get("symbol"), "confidence": c.get("confidence"),
             "kelly": c.get("kelly"), "adv": c.get("adv")}
            for c in candidates if isinstance(c, dict)
        ],
        "permitted": "DENY",
        "reason_code": None,
        "regime": None,
        "exposure_cap": None,
        "halt_flag": None,
        "governor_permissions": None,
        "vix_source": None,
        "data_freshness": {},
    }

    # ── 1) bypass intent (数据加载前分流) ──
    if intent_type in BYPASS_INTENTS:
        record["permitted"] = "ALLOW"
        record["reason_code"] = f"BYPASS_{intent_type.upper()}"
        _audit(record, audit_path)
        return record

    if intent_type not in GOVERNED_INTENTS:
        record["reason_code"] = f"UNKNOWN_INTENT_{intent_type}"
        _audit(record, audit_path)
        return record

    # ── 2) 加载全部输入 ──
    acct, a_fresh = load_account_snapshot(account_getter, now=now)
    holdings, h_fresh = load_holdings(db_path or DEFAULT_DB,
                                      equity=(acct or {}).get("equity"), now=now)
    m_env, m_fresh = load_market_env(market_env_path or DEFAULT_MARKET_ENV,
                                     vix_csv_path or DEFAULT_VIX_CSV, now=now)
    stops, s_fresh = load_stop_health(db_path or DEFAULT_DB, now=now)
    orders, o_fresh = load_orders(orders_path or DEFAULT_ORDERS, now=now)

    record["data_freshness"] = {
        "holdings": h_fresh, "account": a_fresh, "market_env": m_fresh,
        "stop_health": s_fresh, "orders": o_fresh,
    }
    if m_env:
        record["vix_source"] = m_env.get("_source")

    gov_market_env = {
        "vix_2dma": m_env["vix_2dma"] if m_env else 0.0,
        "snapshot_vix": m_env.get("snapshot_vix") if m_env else None,
        "expansions_7d": orders["expansions_7d"] if orders else 0,
        "held_last_5d": orders["held_last_5d"] if orders else set(),
    }
    gov_stops = {
        "last_loss_stop_days": stops["last_loss_stop_days"] if stops else 0,
        "stale_recalc_days": stops["stale_recalc_days"] if stops else 0,
        "recent_stops": stops["recent_stops"] if stops else [],
    }

    # ── 3) 卖出意图: 永不阻断, 数据可用时记录 Governor 输出 ──
    if side == "sell":
        if (governor_decide is not None and m_env and holdings and orders
                and a_fresh == "ok" and h_fresh == "ok" and o_fresh == "ok"):
            try:
                out = governor_decide(candidates, holdings, gov_market_env, None, gov_stops)
                record["regime"] = out.get("regime")
                record["exposure_cap"] = out.get("exposure_cap")
                record["halt_flag"] = out.get("halt_flag")
                record["governor_permissions"] = _summarize_perms(out.get("permissions", []))
            except Exception:
                pass
        record["permitted"] = "ALLOW"
        record["reason_code"] = "SELL_NOT_BLOCKED"
        _audit(record, audit_path)
        return record

    # ── 4) 买方向数据 gate ──
    gates = [
        (a_fresh == "missing", "ACCOUNT_UNAVAILABLE"),
        (h_fresh == "missing", "HOLDINGS_UNAVAILABLE"),
        (h_fresh == "stale", "HOLDINGS_STALE"),
        (m_fresh == "missing", "VIX_UNAVAILABLE"),
        (s_fresh == "missing", "STOPS_UNAVAILABLE"),
        (s_fresh == "stale", "STOP_STALE"),
        (o_fresh == "missing", "ORDERS_UNAVAILABLE"),
        (o_fresh == "stale", "ORDERS_STALE"),
    ]
    for blocked, code in gates:
        if blocked:
            record["reason_code"] = code
            _audit(record, audit_path)
            return record

    # ── 5) 全部数据通过 → Governor ──
    if governor_decide is None:
        record["reason_code"] = "GOVERNOR_UNAVAILABLE"
        _audit(record, audit_path)
        return record
    try:
        out = governor_decide(candidates, holdings or {}, gov_market_env, None, gov_stops)
    except Exception:
        record["reason_code"] = "GOVERNOR_CRASH"
        _audit(record, audit_path)
        return record

    record["regime"] = out.get("regime")
    record["exposure_cap"] = out.get("exposure_cap")
    record["halt_flag"] = out.get("halt_flag")
    perms = out.get("permissions", [])
    record["governor_permissions"] = _summarize_perms(perms)

    if out.get("halt_flag"):
        record["permitted"] = "DENY"
        record["reason_code"] = "HALT"
    elif any(p.get("permitted") == "DENY" for p in perms):
        record["permitted"] = "DENY"
        record["reason_code"] = next((p.get("reason_code") or "DENY")
                                     for p in perms if p.get("permitted") == "DENY")
    elif any(p.get("permitted") == "REDUCE" for p in perms):
        record["permitted"] = "REDUCE"
        record["reason_code"] = next((p.get("reason_code") or "REDUCE")
                                     for p in perms if p.get("permitted") == "REDUCE")
    else:
        record["permitted"] = "ALLOW"
        record["reason_code"] = "GOVERNOR_ALLOW"
    _audit(record, audit_path)
    return record


def _summarize_perms(perms):
    return [
        {"symbol": p.get("symbol"), "permitted": p.get("permitted"),
         "reason_code": p.get("reason_code"), "mandatory": p.get("mandatory")}
        for p in perms if isinstance(p, dict)
    ]
