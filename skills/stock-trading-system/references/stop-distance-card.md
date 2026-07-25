# 止损距离一览卡片（Stop-Loss Distance Card）

## 用途

持仓风控看板。每个交易日 09:30 BJT（盘前）自动推送，或用户查持仓时 on-demand 触发。显示距止损最近的持仓及其距离百分比。

## 数据源

`python3 ~/.hermes/scripts/us_trader.py --report` 的 `stops` 区段（详见 `references/report-stops-section.md`）。

## 字段提取

| 卡片列 | JSON 字段 | 格式 |
|--------|----------|------|
| 股票 | `stops[].symbol` | 4字符左对齐 |
| 现价 | `stops[].current` | $ 前缀，7字符右对齐 |
| 止损价 | `stops[].trail_stop`（优先）或 `hard_stop` | $ 前缀，7字符右对齐 |
| 距离 | (现价 - 止损价) / 现价 × 100% | 1位小数，5字符宽 + 标记 |

## 过滤规则（硬约束）

1. 只列 distance ≤ 8% 的持仓
2. 按 distance 升序排列（最近的在前）
3. 最多 10 行，超出标注 "+N只已隐藏"
4. 对无 stop 数据的持仓跳过（理论上不应发生，但防御性处理）

## 标记规则

| 距离 | 标记 | 含义 |
|------|:----:|------|
| < 0.5% | 🚨 | 贴脸止损，随时触发 |
| 0.5% ~ < 1.0% | ⚠️ | 濒临止损 |
| 1.0% ~ < 3.0% | ⚠️ | 接近止损区 |
| 3.0%+ | (无) | 安全距离 |

## 渲染格式（ClawBot 模板，微信侧栏友好）

```
止损距离一览

股票    现价      止损价    距离
GS    $994.00  $993.87   0.0% 🚨
CAT   $859.80  $850.85   1.0% ⚠️
...
+8只已隐藏

GS 离止损极近——再跌0.0%左右就会触发。今晚开盘要盯一下。

总结
1. 距止损≤3%: GS / CAT / MS。开盘优先检查卖单状态。
2. GS $994.00 距止损仅0.0%！考虑撤旧stop重建或接受触发。
3. CAT $859.80 距止损1.0%，接近止损区。
```

### 格式规则
- 4 列固定宽度：股票(4) | 现价(7) | 止损价(7) | 距离(5+标记)
- 数字右对齐，`$` 统一前缀
- 表格前空 1 行，表格后空 1 行，总结前空 1 行
- 不用 markdown table (`|`/`---`)，直接空格对齐
- 不用 emoji 块字符（🟩⬜ 在微信侧栏糊）

### 末尾总结规则
- 至少 1 条具体行动（卖/加仓/撤stop重建/关注开盘）
- 距止损 <1% 的标的单独点名 + 行动建议
- 不要泛泛"关注市场"

## Python 生成脚本骨架

```python
import json, subprocess

# 1. 获取数据
result = subprocess.run(
    ['python3', '~/.hermes/scripts/us_trader.py', '--report'],
    capture_output=True, text=True, timeout=120
)
report = json.loads(result.stdout)
stops = report.get('stops', [])

# 2. 过滤+排序
entries = []
for s in stops:
    cur = s.get('current', 0)
    trail = s.get('trail_stop', 0)
    hard = s.get('hard_stop', 0)
    eff_stop = trail if trail > 0 else hard
    if eff_stop == 0 or cur == 0:
        continue
    dist_pct = (cur - eff_stop) / cur * 100
    if dist_pct <= 8.0:
        entries.append({'sym': s['symbol'], 'cur': cur,
                        'stop': eff_stop, 'dist_pct': dist_pct})

entries.sort(key=lambda x: x['dist_pct'])
display = entries[:10]
hidden = len(entries) - 10

# 3. 构建卡片字符串
lines = ['止损距离一览', '',
         '股票    现价      止损价    距离']
for e in display:
    d = e['dist_pct']
    flag = ' 🚨' if d < 0.5 else (' ⚠️' if d < 1.0 else (' ⚠️' if d < 3.0 else ''))
    lines.append(f"{e['sym']:<4s}  ${e['cur']:>6.2f}  ${e['stop']:>6.2f}  {d:>4.1f}%{flag}")
if hidden > 0:
    lines.append(f'+{hidden}只已隐藏')
lines.append('')

# 4. 风险警告
crit = [e for e in entries if e['dist_pct'] < 1.0]
if crit:
    names = ' 和 '.join([e['sym'] for e in crit])
    lines.append(f'{names} 离止损极近——再跌{min(e["dist_pct"] for e in crit):.1f}%左右就会触发。今晚开盘要盯一下。')
    lines.append('')

# 5. 总结
lines.append('总结')
near = [e for e in entries if e['dist_pct'] < 3.0]
lines.append(f'1. 距止损≤3%: {" / ".join([e["sym"] for e in near])}。开盘优先检查卖单状态。')
# ... 具体行动项
```

## 注意事项

1. **terminal() 需要 timeout=150** — us_trader.py --report 含 Alpaca API 调用，可能慢
2. **不要用 execute_code** — 直接 terminal 调用 us_trader.py，然后用 Python 解析 stdout
3. **`$PREFIX/tmp` 路径用于临时脚本** — Termux `/tmp` 只读
4. **多只离止损极近时** — 优先点名距止损最近的 1-2 只，不要全部列出
