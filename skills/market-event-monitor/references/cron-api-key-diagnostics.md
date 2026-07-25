# Cron Job API Key 诊断流程

## 触发条件
- 所有/多个cron job同时报error
- `last_status: "error"` 出现在 `cronjob list` 输出中

## 诊断路径（按顺序执行）

### Step 1: 查看最近日志
```bash
# 列出job输出目录
ls -lt ~/.hermes/cron/output/<job_id>/

# 查看最近一次运行结果
tail -50 ~/.hermes/cron/output/<job_id>/<latest_timestamp>.md
```

**关键信号**：
- `RuntimeError: Error code: 401` → API key 认证失败
- `RuntimeError: Error code: 429` → 速率限制
- `RuntimeError: Error code: 500` → 服务端错误

### Step 2: 查看agent日志
```bash
tail -100 ~/.hermes/logs/agent.log | grep -i "minimax\|error\|401\|auth"
```

**关键信号**：
- `credential pool: marking MINIMAX_CN_API_KEY exhausted (status=401), rotating` → Key失效
- `API call failed (attempt 1/3) error_type=AuthenticationError` → 认证问题

### Step 3: 验证当前session的provider
```bash
grep "provider:" ~/.hermes/config.yaml | head -3
```

**为什么当前session正常但cron失败？**
- 默认provider (如 xiaomi) 的key有效
- Cron job配置了特定provider (如 minimax-cn) 但对应的key失效

### Step 4: 测试API key
```bash
source ~/.hermes/.env 2>/dev/null
curl -s -H "Authorization: Bearer $MINIMAX_CN_API_KEY" \
  -H "Content-Type: application/json" \
  "https://api.minimaxi.com/v1/chat/completions" \
  -d '{"model":"MiniMax-M3","messages":[{"role":"user","content":"hi"}],"max_tokens":5}'
```

**返回值判断**：
- `401 "invalid api key"` → key过期/被重置
- `401 "authorized_error"` → key格式错误
- 正常JSON响应 → key有效

## 常见问题

### Q: 为什么当前对话正常但cron失败？
**A**: 当前session用的是默认provider (如 xiaomi/mimo-v2.5-pro)，而cron job在prompt中指定了其他provider (如 minimax-cn)。检查：
1. `.env` 中对应的 `*_API_KEY` 是否有效
2. config.yaml 中是否有正确的 provider 配置

### Q: 如何修复？
**A**: 
1. 去provider官网获取新API key
2. 更新 `~/.hermes/.env` 中的对应变量
3. 重新加载hermes或重启gateway

### Q: 如何验证修复成功？
**A**: 
```bash
# 手动触发一个job
hermes cron run <job_id>

# 等待完成，检查状态
hermes cron list | grep <job_id>
```

## 2026-06-05 实战案例

**现象**：8个cron job全部报error
**根因**：MINIMAX_CN_API_KEY过期 (返回401 "invalid api key")
**发现路径**：
1. `cronjob list` → 8个error
2. 查看 `~/.hermes/cron/output/d65b06eddcad/` 最新日志
3. 发现 `RuntimeError: 401 - invalid api key`
4. 查看 `~/.hermes/logs/agent.log` 确认 `credential pool: marking MINIMAX_CN_API_KEY exhausted`
5. 测试key：`curl` 直接调API返回401
6. 确认当前session用的是xiaomi provider (key有效)，cron用的是minimax-cn (key失效)

**修复**：用户提供新的 MINIMAX_CN_API_KEY
