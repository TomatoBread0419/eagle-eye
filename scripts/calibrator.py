#!/usr/bin/env python3
"""
参数自校准器 v1 (2026-06-17)
从实际交易数据中校准评分/止损/凯利参数。
每周六运行一次，输出 calibrated_params.json。

校准逻辑:
  1. kelly: 用实际交易的score vs 涨跌拟合sigmoid参数
  2. stop_loss: 用被止损标的的后续走势反推最优止损距离
  3. score_weights: 用滚动回测验证评分权重预测准确率
  4. sector_bonus: 用板块实际贡献调整板块加分
"""
import json, os, math
from datetime import datetime, timedelta

SRC_DIR = os.path.expanduser('~/stock_trader')
TRADE_HISTORY = f'{SRC_DIR}/trade_history.json'
SCREENER_LOG = f'{SRC_DIR}/us_screener_log.json'
RISK_STATE = f'{SRC_DIR}/us_risk_state.json'
WEIGHT_CONFIG = f'{SRC_DIR}/ai_weight_config.json'
OUTPUT = f'{SRC_DIR}/calibrated_params.json'
DRIFT_CAP = 0.20
BASELINE_PATH = f'{SRC_DIR}/baseline_params.json'

# ========== 工具函数 ==========

def load_json(path):
    """安全加载JSON，失败返回空dict"""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def save_json(path, data):
    """保存JSON"""
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def clamp(val, lo, hi):
    """限幅"""
    return max(lo, min(hi, val))


def sigmoid(x, k, midpoint):
    """sigmoid函数: p = 1/(1+exp(-k*(x-midpoint)))"""
    try:
        return 1.0 / (1.0 + math.exp(-k * (x - midpoint)))
    except OverflowError:
        return 0.0 if k * (x - midpoint) < 0 else 1.0


# ========== 校准模块 ==========

def calibrate_kelly(history):
    """
    用交易汇总数据校准凯利sigmoid参数
    
    trade_history.json 只有汇总统计(win_rate, odds_ratio)，没有逐笔明细。
    用实际胜率和赔率反推sigmoid参数。
    
    回退: 数据不足时返回默认参数
    """
    kelly = history.get('kelly', {})
    total_trades = kelly.get('total_trades', 0) or history.get('matched_trades', 0)
    
    # 默认参数
    defaults = {
        'sigmoid_k': 0.12,
        'sigmoid_midpoint': 12,
        'atr_to_odds_slope': 0.3,
        'atr_to_odds_intercept': 1.0,
        'target_alloc': 0.85,
        'max_pct_large_cap': 0.20,
        'max_pct_small_cap': 0.10,
        'sample_size': total_trades,
        'calibration_quality': 'default',
    }
    
    if total_trades < 20 or not kelly:
        print(f'  ⚠️ 交易样本不足({total_trades}笔), 使用默认sigmoid参数')
        return defaults
    
    # 从kelly汇总中提取实际参数
    actual_wr = kelly.get('win_rate', 0.5)
    actual_odds = kelly.get('odds_ratio', 2.0)
    avg_win = kelly.get('avg_win_pct', 5.0)
    avg_loss = kelly.get('avg_loss_pct', 5.0)
    
    # 反推sigmoid参数:
    # 目标: sigmoid(score=15) ≈ actual_wr (让中等score对应实际胜率)
    # sigmoid(midpoint) = 0.5, 所以 midpoint ≈ 15 - ln(1/wr - 1)/k
    # 用实际胜率和odds估算k: k越大, 胜率分化越明显
    # 经验公式: k ≈ (actual_odds - 1) * 0.08, 限幅在0.05-0.25
    k_opt = clamp((actual_odds - 1) * 0.08, 0.05, 0.25)
    
    # midpoint: 让 sigmoid(midpoint) = 0.5, 即中等score对应50%胜率
    # 如果实际胜率>50%, midpoint应该更低(更容易达到高胜率)
    # midpoint ≈ 15 - (actual_wr - 0.5) * 50
    mid_opt = clamp(15 - (actual_wr - 0.5) * 50, 0, 30)
    
    # ATR→赔率: 用实际赔率校准
    # b = atr_intercept + atr_pct * atr_slope
    # 平均ATR约4%, 期望b≈actual_odds
    atr_slope = clamp(actual_odds / 15, 0.1, 0.5)
    atr_intercept = clamp(actual_odds * 0.6, 0.8, 2.0)
    
    return {
        'sigmoid_k': round(k_opt, 4),
        'sigmoid_midpoint': round(mid_opt, 2),
        'atr_to_odds_slope': round(atr_slope, 3),
        'atr_to_odds_intercept': round(atr_intercept, 2),
        'target_alloc': 0.85,
        'max_pct_large_cap': 0.20,
        'max_pct_small_cap': 0.10,
        'actual_win_rate': round(actual_wr, 3),
        'actual_avg_win': round(avg_win, 2),
        'actual_avg_loss': round(avg_loss, 2),
        'actual_odds': round(actual_odds, 2),
        'sample_size': total_trades,
        'calibration_quality': 'from_kelly_summary',
    }


def calibrate_stop_loss(history):
    """
    用止损统计校准止损分档
    
    trade_history.json 没有逐笔止损明细，用默认分档。
    如果kelly中有止损相关统计则使用。
    """
    kelly = history.get('kelly', {})
    total_trades = kelly.get('total_trades', 0)
    
    defaults = {
        'tier_vol_20': 0.07,
        'tier_vol_35': 0.08,
        'tier_vol_50': 0.09,
        'tier_vol_max': 0.10,
        'false_stop_rate': None,
        'sample_size': total_trades,
        'calibration_quality': 'default',
    }
    
    if total_trades < 20:
        print(f'  ⚠️ 交易样本不足({total_trades}笔), 使用默认止损分档')
        return defaults
    
    # 用胜率和赔率间接估算止损是否合理
    # 如果胜率<40%且赔率>3 → 止损可能太紧(频繁止损后反弹)
    # 如果胜率>55%且赔率<1.5 → 止损可能太宽(亏的多赚的少)
    wr = kelly.get('win_rate', 0.5)
    odds = kelly.get('odds_ratio', 2.0)
    
    adjustment = 0
    if wr < 0.40 and odds > 3.0:
        adjustment = 0.01  # 放宽1%
    elif wr > 0.55 and odds < 1.5:
        adjustment = -0.01  # 收紧1%
    
    return {
        'tier_vol_20': round(0.07 + adjustment, 2),
        'tier_vol_35': round(0.08 + adjustment, 2),
        'tier_vol_50': round(0.09 + adjustment, 2),
        'tier_vol_max': round(0.10 + adjustment, 2),
        'adjustment': adjustment,
        'adjustment_reason': f'wr={wr:.2f} odds={odds:.2f}',
        'sample_size': total_trades,
        'calibration_quality': 'from_kelly_summary',
    }


def calibrate_score_weights(history):
    """
    用交易汇总验证评分权重的预测准确率
    
    trade_history.json 没有逐笔score明细，保留当前权重。
    用kelly的win_rate间接验证。
    """
    kelly = history.get('kelly', {})
    total_trades = kelly.get('total_trades', 0)
    
    current = load_json(WEIGHT_CONFIG).get('score_weights', {
        'ret_1m': 0.55, 'ret_3m': 0.28, 'ret_short': 0.12
    })
    
    if total_trades < 15:
        print(f'  ⚠️ 交易样本不足({total_trades}笔), 保留当前权重')
        current['sample_size'] = total_trades
        current['calibration_quality'] = 'default'
        return current
    
    # 用win_rate和odds间接评估
    wr = kelly.get('win_rate', 0.5)
    odds = kelly.get('odds_ratio', 2.0)
    
    current['actual_win_rate'] = round(wr, 3)
    current['actual_odds'] = round(odds, 2)
    current['sample_size'] = total_trades
    current['calibration_quality'] = 'from_kelly_summary'
    
    return current


def calibrate_sector_bonus(history):
    """
    用板块实际贡献调整板块加分
    
    trade_history.json 没有逐笔板块明细，不覆盖。
    返回空dict让系统使用默认板块加分。
    """
    kelly = history.get('kelly', {})
    total_trades = kelly.get('total_trades', 0)
    
    if total_trades < 15:
        print(f'  ⚠️ 交易样本不足({total_trades}笔), 不覆盖板块加分')
        return {}
    
    # 没有逐笔板块数据，无法按板块统计
    # 返回空dict，使用默认defense_sector_bonus
    print(f'  ℹ️ 无逐笔板块数据({total_trades}笔), 使用默认板块加分')
    return {}


def detect_regime():
    """
    市场状态检测 — 根据VIX/SPY趋势/广度判断当前状态
    
    四种状态:
      trending  — SPY月涨>3%且广度>60%
      volatile  — VIX>25或SPY月波动>5%
      crisis    — VIX>35
      quiet     — 其他
    """
    env = load_json(f'{SRC_DIR}/market_env.json')
    
    vix = None
    spy_ret_1m = None
    pct_above_ma200 = None
    
    # 从market_env.json提取
    if 'macro' in env:
        macro = env['macro']
        vix = macro.get('vix') if isinstance(macro.get('vix'), (int, float)) else None
    elif 'vix' in env:
        vix = env['vix'].get('current')
    
    if 'breadth' in env:
        breadth = env['breadth']
        pct_above_ma200 = breadth.get('pct_above_ma200')
        ad_ratio = breadth.get('ad_ratio')
    else:
        ad_ratio = None
    
    # 兜底
    vix = vix or 15
    ad_ratio = ad_ratio or 1.0
    pct_above_ma200 = pct_above_ma200 or 50
    
    # 状态判断 (用VIX + 广度 + 涨跌比)
    if vix > 35:
        regime = 'crisis'
    elif vix > 25:
        regime = 'volatile'
    elif pct_above_ma200 > 65 and ad_ratio > 1.5:
        regime = 'trending'
    elif pct_above_ma200 < 40 or ad_ratio < 0.6:
        regime = 'volatile'
    else:
        regime = 'quiet'
    
    return {
        'regime': regime,
        'vix': vix,
        'pct_above_ma200': pct_above_ma200,
        'ad_ratio': ad_ratio,
    }


def build_regime_overrides(regime):
    """
    根据市场状态生成参数覆盖
    """
    overrides = {
        'trending': {
            'score_weights': {'ret_1m': 0.10, 'ret_3m': 0.05},
            'rsi_threshold_relax': 5,
            'stop_loss_widen': 0.01,
            'defense_bonus_boost': -1,
        },
        'volatile': {
            'score_weights': {'ret_1m': -0.10, 'macd_golden_cross': 1},
            'rsi_threshold_relax': -5,
            'stop_loss_widen': -0.01,
            'defense_bonus_boost': 2,
        },
        'crisis': {
            'score_weights': {'ret_1m': -0.15, 'ret_3m': -0.05},
            'rsi_threshold_relax': -10,
            'stop_loss_widen': 0,
            'defense_bonus_boost': 3,
            'target_alloc_drop': 0.15,
            'max_pct_cap': 0.10,
        },
        'quiet': {
            'score_weights': {'volume_bullish': 1, 'rs_vs_spy': 1},
            'rsi_threshold_relax': 0,
            'stop_loss_widen': 0,
            'defense_bonus_boost': 0,
        },
    }
    return overrides.get(regime, overrides['quiet'])


# ========== 主流程 ==========

def run_calibration():
    """
    主校准流程:
    1. 读取交易历史
    2. 校准凯利sigmoid参数
    3. 校准止损分档
    4. 校准评分权重
    5. 校准板块加分
    6. 检测市场状态
    7. 合并输出 calibrated_params.json
    """
    print(f'🔧 参数自校准器启动 | {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print(f'{"="*55}')
    
    history = load_json(TRADE_HISTORY) or {}
    kelly = history.get('kelly') or {}
    total_trades = kelly.get('total_trades', 0) or history.get('matched_trades', 0)
    print(f'交易历史: {total_trades} 笔')
    
    results = {
        '_meta': {
            'version': 1,
            'calibration_date': datetime.now().strftime('%Y-%m-%d'),
            'lookback_days': 90,
            'total_trades': total_trades,
        }
    }
    
    # 1. 凯利sigmoid校准
    print(f'\n📊 校准凯利sigmoid参数...')
    results['kelly'] = calibrate_kelly(history)
    k = results['kelly']
    print(f'  sigmoid k={k["sigmoid_k"]}, midpoint={k["sigmoid_midpoint"]}')
    print(f'  实际胜率={k.get("actual_win_rate","?")}, 实际赔率={k.get("actual_odds","?")}')
    print(f'  质量: {k["calibration_quality"]}')
    
    # 2. 止损分档校准
    print(f'\n📊 校准止损分档...')
    results['stop_loss'] = calibrate_stop_loss(history)
    sl = results['stop_loss']
    print(f'  分档: <20%→{sl["tier_vol_20"]*100:.0f}% | <35%→{sl["tier_vol_35"]*100:.0f}% | <50%→{sl["tier_vol_50"]*100:.0f}% | >50%→{sl["tier_vol_max"]*100:.0f}%')
    if sl.get('false_stop_rate') is not None:
        print(f'  假止损率: {sl["false_stop_rate"]*100:.1f}% (调整{sl["adjustment"]*100:+.0f}%)')
    
    # 3. 评分权重校准
    print(f'\n📊 校准评分权重...')
    results['score_weights'] = calibrate_score_weights(history)
    sw = results['score_weights']
    print(f'  Top10胜率: {sw.get("top10_win_rate","?")} | 分辨力: {sw.get("discrimination","?")}')
    
    # 4. 板块加分校准
    print(f'\n📊 校准板块加分...')
    results['sector_bonus'] = calibrate_sector_bonus(history)
    if results['sector_bonus']:
        for k, v in results['sector_bonus'].items():
            if not k.endswith('_n') and not k.endswith('_avg_pnl'):
                print(f'  {k}: {v:+d}')
    else:
        print(f'  数据不足, 不覆盖')
    
    # 5. 市场状态检测
    print(f'\n📊 检测市场状态...')
    regime_info = detect_regime()
    results['regime'] = regime_info
    print(f'  状态: {regime_info["regime"]} (VIX={regime_info["vix"]}, %>MA200={regime_info["pct_above_ma200"]:.0f}%, AD={regime_info["ad_ratio"]:.2f})')
    
    # 6. Regime覆盖
    results['regime_overrides'] = build_regime_overrides(regime_info['regime'])

    # ── P1.2: 漂移守卫 ──────────────────────────────────────────────
    # 检查累积参数漂移是否超过 20% 阈值
    baseline = load_json(BASELINE_PATH)
    drift_exceeded = False
    drift_details = []

    if baseline and baseline.get('_meta', {}).get('version'):
        # 有 baseline → 对比关键参数
        bl_k = baseline.get('kelly', {})
        bl_sl = baseline.get('stop_loss', {})
        rk = results['kelly']
        rsl = results['stop_loss']

        def _check_drift(name, new_val, base_val):
            if base_val is None or abs(base_val) < 1e-9:
                return None
            drift = abs(new_val - base_val) / abs(base_val)
            return drift

        checks = [
            ('sigmoid_k', rk.get('sigmoid_k'), bl_k.get('sigmoid_k')),
            ('sigmoid_midpoint', rk.get('sigmoid_midpoint'), bl_k.get('sigmoid_midpoint')),
            ('stop_tier_20', rsl.get('tier_vol_20'), bl_sl.get('tier_vol_20')),
            ('stop_tier_35', rsl.get('tier_vol_35'), bl_sl.get('tier_vol_35')),
            ('stop_tier_50', rsl.get('tier_vol_50'), bl_sl.get('tier_vol_50')),
            ('stop_tier_max', rsl.get('tier_vol_max'), bl_sl.get('tier_vol_max')),
        ]
        for name, new_v, base_v in checks:
            drift = _check_drift(name, new_v, base_v)
            if drift is not None and drift > DRIFT_CAP:
                drift_exceeded = True
                drift_details.append(f'{name}: {base_v}→{new_v} ({drift*100:.0f}% drift > {DRIFT_CAP*100:.0f}%)')

        results['_drift_check'] = {
            'baseline_date': baseline.get('_meta', {}).get('calibration_date'),
            'max_drift': DRIFT_CAP,
            'exceeded': drift_exceeded,
            'details': drift_details,
            'verdict': 'REJECTED — calibration skipped' if drift_exceeded else 'PASSED — within bounds',
        }
    else:
        # 首次运行 — baseline 将在下面保存（line 453）
        print(f'\n📌 首次校准 — 将创建 baseline')
        results['_drift_check'] = {
            'baseline_date': 'NEW',
            'max_drift': DRIFT_CAP,
            'exceeded': False,
            'details': ['First calibration — baseline created'],
            'verdict': 'PASSED — initial baseline',
        }

    if drift_exceeded:
        print(f'\n⛔ DRIFT GUARD TRIGGERED:')
        for d in drift_details:
            print(f'  • {d}')
        print(f'  校准已跳过——参数未写入。Owner 必须手动批准。')
        print(f'  Baseline: {BASELINE_PATH}')
        print(f'  恢复 baseline: cp {BASELINE_PATH} {OUTPUT}')
        results['_meta']['drift_guard_triggered'] = True
        # 不保存 OUTPUT —— 校准被拒绝
    else:
        # 保存
        save_json(OUTPUT, results)
        print(f'\n✅ 校准完成 → {OUTPUT}')
        if not baseline:
            save_json(BASELINE_PATH, results)


    print(f'\n{"="*55}')
    print(f'📋 校准摘要:')
    print(f'  凯利: k={results["kelly"]["sigmoid_k"]}, mid={results["kelly"]["sigmoid_midpoint"]}')
    print(f'  止损: <20%→{results["stop_loss"]["tier_vol_20"]*100:.0f}% ... >50%→{results["stop_loss"]["tier_vol_max"]*100:.0f}%')
    print(f'  市场: {results["regime"]["regime"]}')
    print(f'  总仓位目标: {results["kelly"]["target_alloc"]*100:.0f}%')
    
    return results


if __name__ == '__main__':
    run_calibration()
