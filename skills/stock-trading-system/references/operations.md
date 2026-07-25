# 运维操作

## 自检流程

```
1. Alpaca 账户     → GET /v2/account
2. 持仓           → GET /v2/positions
3. Open orders    → GET /v2/orders?status=open
4. 市场时钟       → GET /v2/clock
5. 状态文件       → cat us_risk_state.json
6. Cron 状态      → hermes cron status
7. 网关进程       → ps aux | grep "hermes gateway"
8. iLink token    → stat ~/.hermes/weixin/accounts/*.json
```

### 自检顺序的铁律（2026-06-04 cron 教训）

**先做最便宜的 2 件事，再做贵的：**

```
Step 0  iLink token age  → 2 秒，0 成本，预测所有 WeChat 推送成败
        token > 5d = 推送必死，无需任何 send 探测
Step 1  Trader fast-fail  → 10 秒内能完成，0 成本，预测所有下单成败
        Alpaca TLS timeout = 下单必死
Step 2  Cron status  → 1 秒，0 成本，预测所有 cron 推送成败
        Gateway dead = cron 推送必死
Step 3+ 详细 API 诊断  → 只在 Step 0-2 都通过后才做
```

**反模式（多次踩坑）**：直接 `hermes send -t weixin` 探测 — token dead 时会**挂起 60s**才超时，且 exit 0 + "Sent" 误导。先 token age 只需 1 行 Python：

```python
import os, time
f = os.path.expanduser("~/.hermes/weixin/accounts/71384feb8897@im.bot.json")
age_d = (time.time() - os.stat(f).st_mtime) / 86400
print(f"iLink token: {age_d:.1f}d", "✅" if age_d < 5 else "🔴 DEAD")
```

### 多通道同时 outage（2026-06-04 22:32 真实场景）

| Alpaca | WeChat | DeepSeek | 现象 | 行动 |
|:------:|:------:|:--------:|------|------|
| 🔴 | 🔴 | 🔴 | 三层全死 | 仅写 log，等下个 cron tick |
| 🔴 | ✅ | ✅ | 单纯 API 网络 | fast-fail trader；WeChat 推送 OK |
| ✅ | 🔴 | ✅ | token 死了 | trader 可跑；WeChat 推送失败不重试 |
| ✅ | ✅ | 🔴 | DeepSeek 故障 | trader 可跑（纯 Python）；cron 调度逻辑失败 |
| ✅ | ✅ | ✅ | 全通 | 正常流程 |

**决策原则**：**任一通道死亡不影响其他通道独立运行**。不要因为 WeChat 死了就跳过 trader；不要因为 Alpaca 死了就放弃所有 cron 输出。

### 下单前安全锁

用户 on-demand 交易操作前必须：
1. `GET /v2/orders?status=open` 列出全部
2. 检查是否有 cron 并发下的单
3. 可疑单先 cancel + 留 log

## SSL/TLS 修复（Android/Termux）

Python 3.13 on Android → `ssl.SSLEOFError`。修复：
```python
import ssl, certifi
ctx = ssl.create_default_context()
ctx.load_verify_locations(certifi.where())
```

## Cron 调试

### Alpaca API 端点级超时差异（2026-06-05 确认）

Alpaca 不同端点 TLS 握手速度不一致。**`/v2/positions` 明显慢于 `/v2/account` 和 `/v2/orders`**：

| 端点 | timeout=10 | timeout=20 | 备注 |
|------|:---:|:---:|------|
| `/v2/account` | ✅ | ✅ | 正常 |
| `/v2/positions` | ❌ TLS超时 | ✅ | **需要 20s** |
| `/v2/orders` | ✅ | ✅ | 正常 |
| `/v2/clock` | ✅ | ✅ | 正常 |

**影响范围**：
- `trading.py` 的 `_request()` 默认 `timeout=10` — `get_positions()` 在中国网络下必超时
- `quick_diagnostic.py` 的 `alpaca_get()` 默认 `timeout=10` — 同样问题
- `us_trader.py` 的 `api_get()` 如果也用 10s — 持仓获取会失败

**修复**：`trading.py` 和 `quick_diagnostic.py` 的 timeout 改为 20s（或 positions 专用 20s）。

**workaround（不改代码时）**：直接 `urllib.request.urlopen(req, timeout=20)` 手动调 positions 端点，绕过 trading.py 的 10s 默认值。

### 脚本超时
- 默认 120s → 配置 `cron.script_timeout_seconds: 300`
- 超时后 `last_run_at` 不更新

### 输出缓冲
- Cron 无 TTY → Python stdout 全缓冲
- 用 `python3 -u script.py` 或 `PYTHONUNBUFFERED=1`

### execute_code 被禁
- Cron 沙箱中 execute_code = BLOCKED
- 用 `terminal` 工具或 `script` 参数

### 并发锁
- `us_trader.py` 无进程级 mutex
- 多 cron 同时跑 → 先查 open orders

## WeChat 网关

诊断顺序：
1. `hermes cron status` → 网关在跑？
2. `gateway.log` Sending response 行 → ground truth
3. DNS 检查 → 198.18.0.x = 劫持
4. `/etc/hosts` pin `182.50.15.221`
5. iLink token 年龄 → ≥5d 大概率死

### Token 年龄

| 年龄 | 状态 |
|------|------|
| 0-4d | ✅ OK |
| 5d | 🔴 开始退化 |
| 6d+ | 💀 大概率死 |

**关键**：cron 内不能 `hermes gateway stop`（被拒）。修 `/etc/hosts` 后等下个 cron tick 自动用新 hosts。

## 详细参考

- `cron-debugging-buffering-timeout.md`
- `cron-prompt-template.md`
- `decision-journal-gap.md`
