#!/bin/bash
# 验证 Alpaca TLS fast-fail 是否生效
# 用法: bash scripts/verify-alpaca-failfast.sh
#
# 原理: 通过 iptables 阻断 Alpaca IP，然后跑 trader，测量退出时间
# 如果 fast-fail 生效，应在 30s 内退出；否则会卡 300s+
#
# ⚠️ 需要 root 权限（iptables）或手动断网

set -e

ALPACA_IP="52.8.245.161"  # paper-api.alpaca.markets 当前 IP
TIMEOUT_EXPECTED=30
TIMEOUT_ACTUAL=0

echo "=== Alpaca TLS Fast-Fail 验证 ==="
echo ""

# Step 1: 确认 Alpaca 当前可达
echo "Step 1: 测试 Alpaca 连通性..."
if timeout 5 python3 -c "
import socket, ssl
s = socket.create_connection(('paper-api.alpaca.markets', 443), timeout=3)
ctx = ssl.create_default_context()
ss = ctx.wrap_socket(s, server_hostname='paper-api.alpaca.markets')
ss.close()
print('✅ Alpaca 当前可达')
" 2>/dev/null; then
    echo "  继续测试..."
else
    echo "  ⚠️ Alpaca 当前不可达 — 无法测试 fast-fail（脚本会直接超时）"
    echo "  建议：等 Alpaca 恢复后再测，或手动添加 iptables 规则阻断"
    exit 1
fi

# Step 2: 阻断 Alpaca（需要 root）
echo ""
echo "Step 2: 阻断 Alpaca IP（需要 iptables 权限）..."
if sudo iptables -A OUTPUT -d "$ALPACA_IP" -j DROP 2>/dev/null; then
    echo "  ✅ 已阻断 $ALPACA_IP"
    BLOCKED=1
else
    echo "  ⚠️ 无法阻断（需要 root），改用 /etc/hosts 覆盖..."
    # 备用方案：覆盖 DNS
    if grep -q "paper-api.alpaca.markets" /etc/hosts 2>/dev/null; then
        echo "  ⚠️ /etc/hosts 已有 Alpaca 条目，跳过"
        exit 1
    fi
    echo "127.0.0.1 paper-api.alpaca.markets" | sudo tee -a /etc/hosts > /dev/null
    echo "  ✅ 已覆盖 DNS（/etc/hosts）"
    BLOCKED=2
fi

# Step 3: 跑 trader，计时
echo ""
echo "Step 3: 跑 us_trader.py，计时..."
START=$(date +%s)
timeout 60 python3 -u ~/.hermes/scripts/us_trader.py 2>&1 | tail -5
EXIT_CODE=${PIPESTATUS[0]}
END=$(date +%s)
TIMEOUT_ACTUAL=$((END - START))

echo ""
echo "=== 结果 ==="
echo "实际耗时: ${TIMEOUT_ACTUAL}s"
echo "期望: <${TIMEOUT_EXPECTED}s (fast-fail)"
echo ""

# Step 4: 恢复网络
echo "Step 4: 恢复网络..."
if [ "$BLOCKED" = "1" ]; then
    sudo iptables -D OUTPUT -d "$ALPACA_IP" -j DROP 2>/dev/null
    echo "  ✅ 已移除 iptables 规则"
elif [ "$BLOCKED" = "2" ]; then
    sudo sed -i '/paper-api.alpaca.markets/d' /etc/hosts
    echo "  ✅ 已移除 /etc/hosts 条目"
fi

# Step 5: 判定
echo ""
if [ $TIMEOUT_ACTUAL -le $TIMEOUT_EXPECTED ]; then
    echo "✅ PASS: fast-fail 生效 (${TIMEOUT_ACTUAL}s ≤ ${TIMEOUT_EXPECTED}s)"
    exit 0
else
    echo "❌ FAIL: fast-fail 未生效 (${TIMEOUT_ACTUAL}s > ${TIMEOUT_EXPECTED}s)"
    echo "   原因: api_get() 重试循环仍在消耗时间"
    echo "   修复: 给 api_get 加 retries=1 参数，或在 get_portfolio 前加 TLS 探测"
    exit 1
fi
