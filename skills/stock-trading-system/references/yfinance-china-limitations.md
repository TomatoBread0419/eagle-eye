# yfinance 中国网络限制

## 安装

yfinance 依赖 pandas/numpy，Termux 上需要从源码编译 C 扩展。

```bash
# 先装编译工具
pkg install cmake ninja -y

# 走 HTTP 代理安装（SOCKS5 代理不行）
pip install numpy pandas yfinance --proxy http://127.0.0.1:7890
```

已验证安装成功：yfinance v1.4.1, pandas 3.0.3, Python 3.13.13 (aarch64 Android/Termux)

## Yahoo Finance 限流

**核心问题**: Yahoo Finance 对中国出口 IP 限流（YFRateLimitError: Too Many Requests）。

- 直连：限流
- 走 mihomo 代理 (SOCKS5:7891 / HTTP:7890)：**同样限流** — 代理出口 IP 也在 Yahoo 黑名单
- 这是 Yahoo 服务端限流，不是网络问题

## 当前方案

`us_common.py` 的 `get_yf_metrics()` 设计为**优雅降级**：

```python
def get_yf_metrics(symbol):
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = ticker.get_info()
        if not info:
            return {}
        return {
            'beta': info.get('beta'),
            'forward_pe': info.get('forwardPE'),
            ...
        }
    except Exception:
        return {}  # 返回空 dict，不影响扫描器运行
```

扫描器中调用：`yf = get_yf_metrics(sym)` — 返回空 dict 时 `yf_score = 0`，扫描器正常完成。

## 限流解除时

无需任何代码改动。`get_yf_metrics()` 会在下次 cron 扫描时自动获取数据。信号：扫描日志中出现 `PE`, `β`, `Div` 标记。

## 评分影响

| 维度 | 有数据 | 无限流 |
|------|:---:|:---:|
| Beta | ±1~2 分 | 0（跳过） |
| Forward PE | ±1~2 分 | 0（跳过） |
| 股息率 | +1 分 | 0（跳过） |
| **最大影响** | **±5 分** | **0** |

不影响扫描器的核心动量/技术面评分（RSI、MACD、成交量、波动率等 12 个维度仍然有效）。
