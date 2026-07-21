"""
portfolio/allocation_engine.py — Kelly 仓位计算引擎 (Phase 5)

纯计算模块 — 不接受 API 调用，不读写文件，无副作用。
输入：买入候选列表 [{symbol, score, atr_pct}, ...]
输出：每只的 Kelly 仓位百分比

用法：
    from eagle_eye.portfolio.allocation_engine import kelly_position_sizes
    sized = kelly_position_sizes(buy_candidates, target_alloc=0.85)
"""

import math

# ─── 可调参数（优先从 calibrator 读取，回退到硬编码）──
import json as _json, os as _os
_CALIBRATED_PATH = _os.path.expanduser('~/stock_trader/calibrated_params.json')
_c = {}
try:
    with open(_CALIBRATED_PATH) as _f:
        _c = _json.load(_f)
except Exception:
    pass

SIGMOID_K = _c.get('kelly', {}).get('sigmoid_k', 0.12)
SIGMOID_MIDPOINT = _c.get('kelly', {}).get('sigmoid_midpoint', 12)
ATR_B_INTERCEPT = _c.get('kelly', {}).get('atr_to_odds_intercept', 1.5)
ATR_B_SLOPE = _c.get('kelly', {}).get('atr_to_odds_slope', 0.3)

# ATR% → b（赔率/赔付比）映射参数
ATR_B_MIN = 1.2           # b 下限
ATR_B_MAX = 3.5           # b 上限

# 仓位约束默认值
DEFAULT_TARGET_ALLOC = 0.85
DEFAULT_HALF_KELLY = True
DEFAULT_MIN_PCT = 0.03
DEFAULT_MAX_PCT = 0.20
DEFAULT_SCORE_FLOOR = -5
DEFAULT_SCORE_CEIL = 35


def kelly_position_sizes(buy_candidates, target_alloc=0.85, half_kelly=True,
                         min_pct=0.03, max_pct=0.20, score_floor=-5, score_ceil=35):
    """
    动态 Kelly 仓位计算。

    算法流程：
      1.  score → sigmoid → p（估计胜率）
      2.  ATR% → b（估计赔付比）
      3.  Kelly 公式：f* = (b*p - q) / b
      4.  可选 Half-Kelly：f = f* / 2
      5.  归一化到目标总仓位 target_alloc
      6.  施加单只上下限 [min_pct, max_pct]
      7.  二次归一化

    Args:
        buy_candidates: list of dicts，每个包含 {symbol, score, atr_pct}
        target_alloc: 目标总仓位比例（0.85 = 85%）
        half_kelly: True=半凯利（更保守），False=全凯利
        min_pct: 单只最低仓位（0.03 = 3%）
        max_pct: 单只最高仓位（0.20 = 20%）
        score_floor: 评分下限（用于 sigmoid，未使用但保留接口）
        score_ceil: 评分上限（用于 sigmoid，未使用但保留接口）

    Returns:
        list of dicts，每个包含:
            {symbol, kelly_pct, kelly_dollars, score, atr_pct,
             p_est, b_est, f_star, raw_kelly_pct}
    """
    results = []

    for c in buy_candidates:
        score = c.get('score', 0)
        atr_pct = c.get('atr_pct', 3.0)

        # Step 1: score → sigmoid → p (win probability)
        p = 1.0 / (1.0 + math.exp(-SIGMOID_K * (score - SIGMOID_MIDPOINT)))

        # Step 2: ATR% → b (odds/payout ratio)
        # Higher ATR = higher potential payout = higher b
        b = max(ATR_B_MIN, min(ATR_B_MAX, ATR_B_INTERCEPT + atr_pct * ATR_B_SLOPE))
        q = 1.0 - p

        # Step 3: Kelly formula
        if b > 0:
            f_star = (b * p - q) / b
        else:
            f_star = 0

        # Step 4: Half-Kelly
        if half_kelly:
            f = f_star / 2.0
        else:
            f = f_star

        # Clamp negative
        f = max(0.0, f)

        results.append({
            'symbol': c['symbol'],
            'score': score,
            'atr_pct': atr_pct,
            'p_est': round(p, 4),
            'b_est': round(b, 2),
            'f_star': round(f_star, 4),
            'raw_kelly_pct': round(f, 4),
        })

    # Step 5: Normalize to target allocation
    total_raw = sum(r['raw_kelly_pct'] for r in results)
    if total_raw > 0:
        scale = target_alloc / total_raw
        for r in results:
            r['kelly_pct'] = round(r['raw_kelly_pct'] * scale, 4)
            r['kelly_pct'] = max(min_pct, min(max_pct, r['kelly_pct']))
    else:
        for r in results:
            r['kelly_pct'] = 0.0

    # Step 7: Re-normalize after clamping
    total_clamped = sum(r['kelly_pct'] for r in results)
    if total_clamped > 0 and abs(total_clamped - target_alloc) > 0.01:
        scale2 = target_alloc / total_clamped
        for r in results:
            r['kelly_pct'] = round(r['kelly_pct'] * scale2, 4)

    return results
