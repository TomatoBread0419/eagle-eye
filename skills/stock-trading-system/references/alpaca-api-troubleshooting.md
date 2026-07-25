# Alpaca API 连接问题排查

## 环境变量名不匹配（2026-06-08 教训）

**症状**：Python 脚本调 Alpaca API 返回 401 Unauthorized

**根因**：.env 中的变量名和脚本中读取的不一致
- `.env` 中：`ALPACA_API_KEY=*** + `ALPACA_SECRET_KEY=*** `config.py` 中：`os.environ.get("ALPACA_API_KEY", "")`  ✅ 正确
- 某些旧脚本中：`os.environ.get("APCA_API_KEY_ID", "")`  ❌ 错误

**排查方法**：
```bash
# 检查 .env 中的 key 是否存在
grep -c "ALPACA" ~/.hermes/.env

# 用正确 key 测试
source ~/.hermes/.env
curl -s -H "APCA-API-KEY-ID: $ALPACA_API_KEY" \
        -H "APCA-API-SECRET-KEY: $ALPACA_SECRET_KEY" \
        "https://paper-api.alpaca.markets/v2/account" | head -1

# 注意：HTTP header 字段名是 APCA-API-KEY-ID，但环境变量名是 ALPACA_API_KEY
# 这是 Alpaca 的设计：header 字段名 ≠ 环境变量名
```

**修复**：确保所有脚本从 `config.py` 读取，不要硬编码环境变量名。

## TLS 超时（2026-06-04 教训）

**症状**：cron 报 "Script timed out after 300s"，脚本 hang

**根因**：Alpaca API 不可达时，`api_get()` 内部 3 次重试 × 15s timeout × 3 个端点 = 153s 最小开销

**修复方向**：
- 方案 A：给 api_get 加 `retries=1` 首次快探
- 方案 B：TCP/TLS 探测（5s timeout）

**Cron prompt 要求**：`terminal(timeout=90, ...)` 不要用 300s 默认
