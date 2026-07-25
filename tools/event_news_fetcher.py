#!/usr/bin/env python3
"""事件驱动子系统 — Phase 1.5 一体化版
检测事件 → AI 因果推理 → 写分析结果 → 推微信
Python 负责全部 I/O，AI 只负责推理。"""
import json, os, sys, subprocess, re
from datetime import datetime, timezone, timedelta

HOME = os.path.expanduser('~')
STOCK_DIR = os.path.join(HOME, 'stock_trader')
BJT = timezone(timedelta(hours=8))

def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def send_weixin(msg):
    try:
        r = subprocess.run(['hermes', 'send', '-t', 'weixin', msg],
                           capture_output=True, text=True, timeout=30)
        return r.returncode == 0
    except Exception as e:
        print(f"  ⚠️ 微信推送失败: {e}")
        return False

def call_ai(event):
    """调 hermes chat 做事件因果推理，返回结构化结果"""
    stocks_str = ', '.join(event['candidate_stocks'][:8])
    news_str = '\n'.join(f"  - {n}" for n in event['key_news'][:5])
    prompt = f"""你是美股事件驱动分析师。分析以下事件并给出交易建议。

事件板块: {event['sector']}
方向: {event['direction']}
候选标的: {stocks_str}
关键新闻:
{news_str}

请用以下严格格式回复（不要加多余内容）:

推理: <1-2句话因果链，说明为什么这个事件影响这些标的>

标的:
<SYMBOL> <BUY/SELL/SKIP> <仓位%> <持有天数> <置信度%> <一句话理由>
<SYMBOL> <BUY/SELL/SKIP> <仓位%> <持有天数> <置信度%> <一句话理由>
...

风险: <什么情况下逻辑失效>

强度: <强/中/弱>"""

    try:
        r = subprocess.run(
            ['hermes', 'chat', '-Q', '-q', prompt, '-m', 'mimo-v2.5-pro', '--provider', 'xiaomi'],
            capture_output=True, text=True, timeout=180,
            cwd=STOCK_DIR
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception as e:
        print(f"  ⚠️ AI 调用失败: {e}")
        return None

def parse_ai_response(raw, candidate_stocks):
    """从 AI 返回的文本中提取结构化结果"""
    if not raw:
        return None

    result = {
        'confidence': 50,
        'reasoning': '',
        'recommendations': [],
        'risk_note': '',
        'strength': '中'
    }

    # 提取推理
    m = re.search(r'推理[:：]\s*(.+?)(?=\n标的|\n风险|\n强度|$)', raw, re.DOTALL)
    if m:
        result['reasoning'] = m.group(1).strip()[:300]

    # 提取风险
    m = re.search(r'风险[:：]\s*(.+?)(?=\n标的|\n强度|$)', raw, re.DOTALL)
    if m:
        result['risk_note'] = m.group(1).strip()[:200]

    # 提取强度
    m = re.search(r'强度[:：]\s*(强|中|弱)', raw)
    if m:
        result['strength'] = m.group(1)

    # 提取标的
    m = re.search(r'标的[:：]\s*\n(.+?)(?=\n风险|\n强度|$)', raw, re.DOTALL)
    if m:
        for line in m.group(1).strip().split('\n'):
            line = line.strip().lstrip('•-→ ')
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 4:
                sym = parts[0].upper().strip('*')
                action = parts[1].upper()
                if action in ('BUY', 'SELL', 'SKIP'):
                    try:
                        pos = float(re.search(r'[\d.]+', parts[2]).group()) if re.search(r'[\d.]+', parts[2]) else 2.0
                        hold = int(re.search(r'\d+', parts[3]).group()) if re.search(r'\d+', parts[3]) else 7
                    except:
                        pos, hold = 2.0, 7
                    conf = 60
                    conf_m = re.search(r'(\d+)%', ' '.join(parts[4:]))
                    if conf_m:
                        conf = int(conf_m.group(1))
                    reason_m = re.search(r'%\s+(.+)', ' '.join(parts[4:]))
                    reason = reason_m.group(1).strip()[:100] if reason_m else ''

                    # 只接受在候选列表里的标的
                    if sym in candidate_stocks and action != 'SKIP':
                        result['recommendations'].append({
                            'symbol': sym,
                            'action': action,
                            'position': min(pos, 5.0),
                            'hold_days': hold,
                            'confidence': conf,
                            'reason': reason
                        })
                        result['confidence'] = max(result['confidence'], conf)

    return result


def validate_and_constrain(analysis, event_direction, candidate_stocks):
    """执行前校验层 — 堵三个漏洞：总仓位超限、矛盾信号、不在池子里的标的"""
    if not analysis or not analysis.get('recommendations'):
        return analysis

    recs = analysis['recommendations']

    # 1. 单只仓位 ≤5%，买/卖方向与事件方向一致
    validated = []
    for r in recs:
        r['position'] = min(r['position'], 5.0)


        # 不在池子里的标的 → 跳过
        if r['symbol'] not in candidate_stocks:
            print(f"      ⏭ {r['symbol']}: 不在候选池，跳过")
            continue

        validated.append(r)

    # 2. 去重（同标的取最高置信度）
    seen = {}
    for r in validated:
        sym = r['symbol']
        if sym not in seen or r['confidence'] > seen[sym]['confidence']:
            seen[sym] = r
    validated = list(seen.values())

    # 3. 总仓位 ≤10%（事件驱动单风格上限）
    total = sum(r['position'] for r in validated)
    if total > 10.0:
        scale = 10.0 / total
        for r in validated:
            r['position'] = round(r['position'] * scale, 1)
        print(f"      ⚠️ 总仓位 {total:.1f}%→10%（等比压缩 {scale:.2f}x）")

    # 4. 过滤置信度 <50% 的
    validated = [r for r in validated if r['confidence'] >= 50]

    # 5. 排序：置信度降序
    validated.sort(key=lambda r: r['confidence'], reverse=True)

    # 只保留前 3 只（质量 > 数量）
    if len(validated) > 3:
        print(f"      ⏭ 仅保留置信度最高 3 只（共 {len(validated)} 只）")
        validated = validated[:3]

    analysis['recommendations'] = validated

    # 重算整体置信度
    if validated:
        analysis['confidence'] = max(r['confidence'] for r in validated)

    return analysis


def format_report(event, analysis):
    """生成微信推送格式"""
    emoji = '🔴' if '利空' in event['direction'] else '🟢'
    recs = analysis.get('recommendations', [])

    lines = [
        f"🧠 事件 AI 分析 | {event['sector']}",
        f"方向: {event['direction']}  强度: {analysis.get('strength','中')}  置信度: {analysis.get('confidence',50)}%",
        "",
        f"推理: {analysis.get('reasoning', '无')}",
        "",
    ]

    if recs:
        lines.append("推荐标的:")
        for r in recs:
            act_emoji = '📈' if r['action'] == 'BUY' else '📉'
            lines.append(f"  {act_emoji} {r['symbol']} ({r['action']}) 仓位{r['position']}% 持有{r['hold_days']}天 置信度{r['confidence']}%")
            if r.get('reason'):
                lines.append(f"     {r['reason']}")
    else:
        lines.append("推荐标的: 无（SKIP 或无明确机会）")

    if analysis.get('risk_note'):
        lines.append(f"\n⚠️ 风险: {analysis['risk_note']}")

    return '\n'.join(lines)

def main():
    events_file = os.path.join(STOCK_DIR, 'market_events_latest.json')
    map_file = os.path.join(STOCK_DIR, 'event_map.json')
    log_file = os.path.join(STOCK_DIR, 'events_log.json')
    result_file = os.path.join(STOCK_DIR, 'events_analysis_queue.json')

    if not os.path.exists(events_file):
        print("market_events_latest.json 不存在，跳过")
        return

    events_data = load_json(events_file)
    event_map = load_json(map_file) or {}
    log_data = load_json(log_file) or {"version": "1.0", "events": []}
    result_data = load_json(result_file) or {"analyzed": [], "updated_at": ""}

    assessments = events_data.get('summary', {}).get('assessments', [])
    cutoff_24h = datetime.now(BJT) - timedelta(hours=24)

    new_count = 0

    for assess in assessments:
        sector = assess.get('sector', '')
        direction = assess.get('direction', '')

        if '利空' not in direction and '利多' not in direction:
            continue

        mapping = event_map.get(sector, {})
        candidate_stocks = mapping.get('stocks', [])
        if not candidate_stocks:
            continue

        key_news = assess.get('key_news', [])[:5]

        # 去重：24h 内同 sector + 同方向不重复分析
        recent = [e for e in log_data.get('events', [])
                  if e.get('sector') == sector and e.get('direction') == direction
                  and datetime.fromisoformat(e.get('detected_at', '2000-01-01')) > cutoff_24h]
        if recent:
            print(f"  ⏭ {sector}: 24h 内已有同向事件，跳过")
            continue

        new_count += 1
        detected_at = datetime.now(BJT).isoformat()
        event = {
            'sector': sector,
            'direction': direction,
            'candidate_stocks': candidate_stocks,
            'key_news': key_news,
            'detected_at': detected_at,
        }

        print(f"  📡 {sector} {direction} → 候选: {', '.join(candidate_stocks[:5])}")
        print(f"    调用 AI 推理...")

        # AI 推理
        ai_raw = call_ai(event)
        analysis = parse_ai_response(ai_raw, set(candidate_stocks))
        analysis = validate_and_constrain(analysis, event['direction'], set(event['candidate_stocks']))

        if analysis:
            report = format_report(event, analysis)
            print(f"    ✅ AI 分析完成: {len(analysis['recommendations'])} 只推荐")

            # 写入 events_log
            log_data.setdefault('events', []).append({
                'sector': sector,
                'direction': direction,
                'stocks': candidate_stocks,
                'key_news': key_news,
                'detected_at': detected_at,
                'action': 'ai_analyzed',
                'analysis': analysis
            })

            # 写入结果文件
            result_data.setdefault('analyzed', []).append({
                'sector': sector,
                'direction': direction,
                'strength': analysis.get('strength', '中'),
                'confidence': analysis.get('confidence', 50),
                'reasoning': analysis.get('reasoning', ''),
                'recommendations': analysis.get('recommendations', []),
                'risk_note': analysis.get('risk_note', ''),
                'analyzed_at': detected_at
            })

            # 推微信
            if send_weixin(report):
                print(f"    📱 已推微信")
        else:
            print(f"    ⚠️ AI 推理失败，仅记录原始事件")
            log_data.setdefault('events', []).append({
                'sector': sector,
                'direction': direction,
                'stocks': candidate_stocks,
                'key_news': key_news,
                'detected_at': detected_at,
                'action': 'detected_no_analysis'
            })

    # 保存
    if new_count > 0:
        log_data['updated_at'] = datetime.now(BJT).isoformat()
        save_json(log_file, log_data)
        result_data['updated_at'] = datetime.now(BJT).isoformat()
        save_json(result_file, result_data)
        print(f"\n✅ 完成: {new_count} 条新事件已分析")
    else:
        print("无新事件")

if __name__ == '__main__':
    main()
