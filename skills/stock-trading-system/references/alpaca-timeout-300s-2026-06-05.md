# Alpaca TLS 超时 300s cron 教训 — 2026-06-05

## 症状

cron 报 `Script timed out after 300s: ~/.hermes/scripts/us_trader.py`

手动跑 `python3 -u us_trader.py` 同样卡死。

## 根因确认

`api_get()` 签名仍为 `api_get(path, timeout=15)` — **无 `retries` 参数**。方案 A（2026-06-04 提出）从未部署。

旧模式时序（Alpaca 不可达时）：
```
api_get('/account')     → 3 retries × (15s timeout + 2s sleep) = 51s
api_get('/positions')   → 3 retries × (15s timeout + 2s sleep) = 51s
api_get('/orders')      → 3 retries × (15s timeout + 2s sleep) = 51s
─────────────────────────────────────────────────────────────
小计（仅数据获取）    = 153s
加上后续逻辑           = ~150s+
总计                   = 300s+ → 被 cron 强杀
```

## TLS 握手实测

```python
socket.create_connection(('paper-api.alpaca.markets', 443), timeout=5)
# → TimeoutError: _ssl.c:1015: The handshake operation timed out (51.4s)
```

即使 TCP 连接建立，TLS 握手也会超时。这说明 Alpaca 端点要么：
1. 被防火墙拦截（TCP SYN-ACK 但 TLS 不响应）
2. 服务端过载
3. 路由层面丢包

## 修复后的验证

部署 fast-fail 后，运行 `scripts/verify-alpaca-failfast.sh`：
- 阻断 Alpaca IP → 跑 trader → 测量退出时间
- 期望：<30s（fast-fail 生效）
- 实际：300s+（fast-fail 未生效）

## 影响

每次 Alpaca 不可达浪费 300s cron 配额。cron 每小时跑一次，美股时段 8 小时 = 最多浪费 8 次 cron slot。

## 状态

- [ ] 方案 A: `api_get` 加 `retries` 参数
- [ ] 方案 B: TLS 探测（`socket.create_connection` + `ssl.wrap_socket`）
- [ ] 验证脚本部署

当前状态：**未部署**（2026-06-05 确认）
