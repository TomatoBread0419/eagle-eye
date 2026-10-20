#!/usr/bin/env python3
"""governor_gate.py — Governor L3 出口守卫（下单前 BUY 开仓检查）。

插入点: order_manager.place_market_order / place_limit_order 的 client.place_order 之前
        （经 _l3_gate 钩子；place_stop_order 永不设闸）。
覆盖口径: 仅 side=='buy' 且真正走到下单行的意图（dedupe 早退不评估，防 would_block 虚高）。
          与 _shadow_hook（只记带 shadow_intent_type 标签、下单后写）是两套口径，故意如此。

三态 SHRINK_GATE_MODE（每次调用现读，kill switch 即时生效）:
  off     默认。不评估、不写日志、零开销——未接线时行为的逐字节等价物。
  shadow  评估 + 写 gate_shadow.jsonl + 照常下单（would_block=原本会拦，blocked=False）。
  enforce 命中可拦规则白名单才 return None（拦截）。双钥匙: 另需 SHRINK_GATE_ACK=YES，
          否则自动降级 shadow 并记 MODE_REFUSED（防环境变量拼错静默停买）。本轮不启用。
配置兜底: env 未设时读 CONFIG_PATH(governor_guard_config.json) 的 {"mode": ...}，再缺省 off。

规则分级（enforce 语义预置，本轮仅记录）:
  READY        HALT / HOLDING_CAP — 输入新鲜、规则稳定，可拦
  DATA_GATE    ACCOUNT/HOLDINGS/VIX/STOPS/ORDERS 的 *_UNAVAILABLE/*_STALE — 可拦(fail-closed)
               但必须同时告警（11 周静默前科）
  INPUT_MISSING KELLY_FLOOR/CONFIDENCE_FLOOR 且对应输入缺失（payload 仅 {symbol}）— 永不拦
               + BLIND_REJECT_SUPPRESSED（不能用缺数据当拒绝理由）
  WATCH_ONLY   EXPANSION_RATE(净额口径缺陷=死规则)/REDUCE/UNKNOWN_INTENT_*/其余未知 — 永不拦
  GATE_ERROR   check_governor 异常 / GOVERNOR_UNAVAILABLE / GOVERNOR_CRASH — 放行 + 记录

失败模式: 任何异常 fail-open（放行 + GATE_ERROR）。守卫绝不能因自身故障阻断交易。
审计: 只写自己的 gate_shadow.jsonl（check_governor 传 audit_path=os.devnull 抑制 bridge 自写，
      shadow_decisions.jsonl 语义零漂移）。join: gate 记录的 (symbol, intent_type, ts±5s)
      可对齐 shadow_decisions 的 actual_action.order_id（gate 在下单前运行，彼时 order_id 不存在）。
零 import 铁律: 模块自身只用 stdlib；check_governor 懒加载或由调用方注入（decider=），
      可整体 exec 进隔离命名空间测试。
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

MODE_ENV = "SHRINK_GATE_MODE"
ACK_ENV = "SHRINK_GATE_ACK"
LOG_ENV = "SHRINK_GATE_LOG"
CONFIG_PATH = os.path.expanduser("~/stock_trader/governor_guard_config.json")
DEFAULT_LOG = "D:/Hermes/audit_live/governor_stage0/gate_shadow.jsonl"

# ── 规则分级常量（enforce 白名单的唯一事实源，报告直接引用） ──
READY_RULES = {"HALT"}
READY_PERMISSIONS = {"HOLDING_CAP"}
DATA_GATE_RULES = {
    "ACCOUNT_UNAVAILABLE", "HOLDINGS_UNAVAILABLE", "HOLDINGS_STALE",
    "VIX_UNAVAILABLE", "STOPS_UNAVAILABLE", "STOP_STALE",
    "ORDERS_UNAVAILABLE", "ORDERS_STALE",
}
WATCH_ONLY_RULES = {"KELLY_FLOOR", "CONFIDENCE_FLOOR", "EXPANSION_RATE", "REDUCE"}
GATE_ERROR_RULES = {"GOVERNOR_UNAVAILABLE", "GOVERNOR_CRASH", "GATE_ERROR"}
INPUT_FIELDS = ("kelly", "confidence", "adv")


def get_mode():
    """env 优先 → 配置文件兜底 → 'off'。未知值 = off + stderr 警告。每次现读（kill switch）。"""
    m = (os.environ.get(MODE_ENV) or "").strip().lower()
    if not m:
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                m = (json.load(f).get("mode") or "").strip().lower()
        except Exception:
            m = ""
    if m in ("off", "shadow", "enforce"):
        return m
    if m:
        print(f"[governor_gate] WARN unknown {MODE_ENV}={m!r} -> off", file=sys.stderr)
    return "off"


def _classify(reason_code, permitted, missing):
    """→ (rule_class, blind_reject_suppressed)。未知 reason 一律 WATCH_ONLY：宁漏勿错拦。"""
    rc = reason_code or ""
    if rc == "GOVERNOR_ALLOW" or permitted == "ALLOW":
        return "ALLOW", False
    if rc.startswith("UNKNOWN_INTENT") or rc.startswith("BYPASS") or rc == "SELL_NOT_BLOCKED":
        return "WATCH_ONLY", False
    if rc in ("KELLY_FLOOR", "CONFIDENCE_FLOOR"):
        blind = (("kelly" in missing) if rc == "KELLY_FLOOR"
                 else ("confidence" in missing))
        return ("INPUT_MISSING" if blind else "WATCH_ONLY"), bool(blind)
    if rc in WATCH_ONLY_RULES:
        return "WATCH_ONLY", False
    if rc in READY_RULES or rc in READY_PERMISSIONS:
        return "READY", False
    if rc in DATA_GATE_RULES:
        return "DATA_GATE", False
    if rc in GATE_ERROR_RULES:
        return "GATE_ERROR", False
    return "WATCH_ONLY", False


def _log(rec):
    """append-only JSONL。写日志失败绝不影响下单（外层 try 兜底也放行）。"""
    path = os.environ.get(LOG_ENV) or DEFAULT_LOG
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def pre_order_check(symbol, qty, side, intent_type=None, caller="",
                    mode=None, decider=None):
    """下单前 BUY 守卫。返回 dict（绝不抛异常）:
    {mode, would_block, blocked, rule_class, reason_code, rule_hits, missing_inputs,
     blind_reject_suppressed, intent_unspecified, gov, error, logged}
    blocked=True 时调用方必须 return None（与 dedupe 早退同款返回契约）。
    """
    out = {"mode": "off", "would_block": False, "blocked": False,
           "rule_class": "SKIPPED", "reason_code": None, "rule_hits": [],
           "missing_inputs": [], "blind_reject_suppressed": False,
           "intent_unspecified": False, "gov": None, "error": None, "logged": False}
    try:
        if (side or "").lower() != "buy":
            out["rule_class"] = "NOT_BUY"   # 零评估零日志：SELL/退出链结构性不触碰
            return out
        m = (mode or get_mode()).lower()
        if m not in ("off", "shadow", "enforce"):
            m = "off"
        if m == "off":
            out["mode"] = "off"
            return out

        # enforce 双钥匙：无 ACK 自动降级 shadow 并记 MODE_REFUSED
        mode_used = m
        refused = ""
        if m == "enforce" and (os.environ.get(ACK_ENV) or "").strip().upper() != "YES":
            mode_used = "shadow"
            refused = f"MODE_REFUSED({MODE_ENV}=enforce without {ACK_ENV}=YES -> shadow)"
        out["mode"] = mode_used

        # check_governor 调用协议与 _shadow_hook 逐字一致（audit_path 抑制 bridge 自写）
        if decider is None:
            try:
                from eagle_eye.execution.governor_bridge import check_governor as decider
            except ImportError:
                from governor_bridge import check_governor as decider
        try:
            gov = decider(intent_type, candidates=[{"symbol": symbol}],
                          side=side, audit_path=os.devnull)
        except Exception as e:
            out["error"] = f"{type(e).__name__}: {e}"
            out["rule_class"] = "GATE_ERROR"
            rec = _mk_rec(out, mode_used, caller, intent_type, symbol, qty, side,
                          None, refused)
            _log(rec); out["logged"] = True
            return out   # fail-open: 异常即放行

        missing = [k for k in INPUT_FIELDS]   # payload 本轮仅 {symbol}：三字段恒缺
        rc = gov.get("reason_code")
        rule_class, blind = _classify(rc, gov.get("permitted"), missing)
        rule_hits = [rc] if rc else []
        for p in (gov.get("governor_permissions") or []):
            prc = p.get("reason_code") if isinstance(p, dict) else None
            if prc and prc not in rule_hits:
                rule_hits.append(prc)

        would_block = rule_class in ("READY", "DATA_GATE")
        blocked = would_block and mode_used == "enforce"
        out.update({
            "would_block": would_block, "blocked": blocked,
            "rule_class": rule_class, "reason_code": rc, "rule_hits": rule_hits,
            "missing_inputs": missing, "blind_reject_suppressed": blind,
            "intent_unspecified": intent_type is None,
            "gov": {k: gov.get(k) for k in
                    ("permitted", "reason_code", "regime", "halt_flag",
                     "exposure_cap", "data_freshness", "governor_permissions")},
        })
        if refused:
            out["error"] = refused
        rec = _mk_rec(out, mode_used, caller, intent_type, symbol, qty, side,
                      gov, refused)
        _log(rec)
        out["logged"] = True
        return out
    except Exception as e:   # 守卫自身故障：fail-open，绝不阻断下单
        out["error"] = f"GUARD_FAIL_OPEN: {type(e).__name__}: {e}"
        out["rule_class"] = "GATE_ERROR"
        try:
            _log(_mk_rec(out, out.get("mode", "off"), caller, intent_type,
                         symbol, qty, side, None, ""))
        except Exception:
            pass
        return out


def _mk_rec(out, mode_used, caller, intent_type, symbol, qty, side, gov, refused):
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "gate_id": uuid.uuid4().hex[:12],
        "mode": mode_used,
        "caller": caller,
        "intent_type": intent_type,
        "symbol": symbol, "qty": qty, "side": side,
        "would_block": out.get("would_block"), "blocked": out.get("blocked"),
        "rule_class": out.get("rule_class"), "reason_code": out.get("reason_code"),
        "rule_hits": out.get("rule_hits"),
        "inputs_present": {k: k not in (out.get("missing_inputs") or [])
                           for k in INPUT_FIELDS},
        "missing_inputs": out.get("missing_inputs"),
        "blind_reject_suppressed": out.get("blind_reject_suppressed"),
        "intent_unspecified": out.get("intent_unspecified"),
        "gov": out.get("gov"),
        "error": refused or out.get("error"),
    }
