# Stock Trading System - 技术文档

> 全自动股票交易系统 | Android/Termux + Windows 双平台支持
> Version 1.0.0 | 2026-04-30

---

## 目录

1. [系统概述](#1-系统概述)
2. [功能列表](#2-功能列表)
3. [技术架构](#3-技术架构)
4. [快速开始](#4-快速开始)
5. [模块详解](#5-模块详解)
6. [API 密钥配置](#6-api-密钥配置)
7. [使用示例](#7-使用示例)
8. [交易时间](#8-交易时间)
9. [已知限制](#9-已知限制)
10. [故障排查](#10-故障排查)

---

## 1. 系统概述

本系统是一个**全自动股票行情监控与交易系统**，支持：

- **A股/美股/港股** 实时行情获取
- **技术指标分析**（RSI/MACD/布林带等）
- **Alpaca 美股自动化交易**（Paper/Live）
- **多渠道通知报警**（Bark/PushPlus/Telegram）

### 设计目标

| 目标 | 实现 |
|------|------|
| 零成本运行 | 行情数据使用新浪/东方财富免费 API |
| 跨平台 | Android/Termux / Windows / Linux |
| 零依赖 | 不需要 numpy/pandas/ta-lib（纯 Python） |
| 可扩展 | 模块化设计，便于添加新功能 |

---

## 2. 功能列表

### 行情数据

| 功能 | 数据源 | 费用 |
|------|--------|------|
| A股实时行情 | 新浪财经 | 免费 |
| 美股实时行情 | 新浪财经 | 免费 |
| 港股实时行情 | 东方财富 | 免费 |
| 历史K线 | 新浪/东方财富 | 免费 |
| 盘前/盘后行情 | 东方财富 | 免费 |

### 技术指标

| 指标 | 函数 | 说明 |
|------|------|------|
| RSI | `indicators.rsi(candles, period=14)` | 相对强弱指数，0-100 |
| MACD | `indicators.macd(candles)` | 返回 {macd, signal, histogram} |
| 布林带 | `indicators.bollinger_bands(candles)` | 返回 {upper, middle, lower} |
| SMA | `indicators.sma(candles, period=20)` | 简单移动平均 |
| EMA | `indicators.ema(candles, period=20)` | 指数移动平均 |
| ATR | `indicators.atr(candles, period=14)` | 平均真实波幅 |
| 综合信号 | `indicators.generate_signal(candles)` | 返回 BUY/SELL/HOLD |

### 交易执行

| 功能 | 券商 | 状态 |
|------|------|------|
| 市价下单 | Alpaca | ✅ 已实现 |
| 限价下单 | Alpaca | ✅ 已实现 |
| 取消订单 | Alpaca | ✅ 已实现 |
| 查询持仓 | Alpaca | ✅ 已实现 |
| 查询账户 | Alpaca | ✅ 已实现 |
| A股自动化交易 | 富途 (Futu OpenD) | ⏳ 部署中 |

### 通知渠道

| 渠道 | 用途 | 状态 |
|------|------|------|
| Bark (iOS) | 推送通知 | ✅ 已实现 |
| PushPlus (微信) | 微信推送 | ✅ 已实现 |
| Telegram Bot | 即时消息 | ✅ 已实现 |
| 系统日志 | 控制台输出 | ✅ 已实现 |

---

## 3. 技术架构

### 文件结构

```
stock_trader/
├── config.py        # API密钥、策略参数、监控列表
├── market_data.py   # 行情数据获取（新浪/东方财富）
├── indicators.py    # 技术指标计算（纯Python）
├── trading.py       # Alpaca 交易接口封装
├── notifier.py      # 多渠道通知推送
└── monitor.py       # 主监控循环（定时任务）
```

### 数据流

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  新浪/东财  │────→│  market_data │────→│ indicators  │
│  行情API    │     │  行情获取     │     │  技术分析   │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                  │
                                                  ↓
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   通知渠道  │←────│   notifier   │←────│   monitor   │
│ Bark/TG/微信│     │  报警推送    │     │  主监控循环  │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                  │
                                                  ↓
                                        ┌─────────────────┐
                                        │    trading.py   │
                                        │  Alpaca/Futu    │
                                        └────────┬────────┘
                                                 │
                                                 ↓
                                        ┌─────────────────┐
                                        │   Alpaca 服务器  │
                                        │   富途服务器     │
                                        └─────────────────┘
```

### 模块依赖

```
monitor.py
├── config.py      (配置参数)
├── market_data.py  (行情数据)
├── indicators.py   (技术指标)
├── trading.py      (交易执行)  ← 可选（无 Alpaca Key 时跳过）
└── notifier.py     (报警通知)
```

---

## 4. 快速开始

### 环境要求

- Python 3.8+
- 网络访问（获取行情）
- 至少配置一个通知渠道

### 安装步骤

```bash
# 1. 创建项目目录
mkdir -p ~/stock_trader && cd ~/stock_trader

# 2. 复制所有 .py 文件到该目录

# 3. 配置 API 密钥（编辑 config.py）
#    - 设置 Alpaca API Key（如需美股交易）
#    - 设置通知渠道 Token（如需推送）

# 4. 测试运行
cd ~/stock_trader
python3 monitor.py
```

### 首次配置检查清单

- [ ] Alpaca API Key 已填写
- [ ] 至少一个通知渠道已配置
- [ ] `WATCH_STOCKS` 列表包含要监控的股票
- [ ] 网络连接正常

---

## 5. 模块详解

### 5.1 config.py - 配置模块

```python
# ========== API 配置 ==========
ALPACA_API_KEY = "PK2OKX..."        # Alpaca API Key
ALPACA_SECRET_KEY = "Cj578h..."      # Alpaca Secret Key
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"  # Paper交易端点

# ========== 通知配置 ==========
BARK_KEY = ""                         # Bark App Key
PUSHPLUS_TOKEN = ""                    # PushPlus Token
TELEGRAM_BOT_TOKEN = ""                # Telegram Bot Token
TELEGRAM_CHAT_ID = ""                 # Telegram Chat ID

# ========== 策略参数 ==========
WATCH_STOCKS = ["AAPL", "TSLA", "NVDA", "MSFT"]  # 监控股票
CHECK_INTERVAL = 60                   # 检查间隔（秒）
RSI_OVERSOLD = 30                     # RSI 超卖阈值
RSI_OVERBOUGHT = 70                   # RSI 超买阈值
SMA_SHORT = 20                         # 短期均线
SMA_LONG = 50                          # 长期均线
```

### 5.2 market_data.py - 行情数据

**主要函数：**

```python
# 获取单只股票实时行情
get_quote_sina(symbol: str) -> dict
# 参数示例: "sh600519" (A股), "usAAPL" (美股)
# 返回: {"symbol", "name", "price", "change", "change_pct", ...}

# 东方财富行情（支持盘前盘后）
get_quote_em(symbol: str) -> dict
# 参数示例: "1.600519" (上交所), "0.000001" (深交所)

# 获取历史K线
get_historical(symbol: str, period: str = "3mo") -> list
# period: "3mo", "6mo", "1y", "2y"
# 返回: [{"timestamp", "open", "close", "high", "low", "volume"}, ...]

# 批量获取行情
get_batch_quotes(symbols: list) -> dict
```

**股票代码格式：**

| 市场 | 格式 | 示例 |
|------|------|------|
| A股上交所 | sh + 代码 | sh600519 |
| A股深交所 | sz + 代码 | sz000858 |
| 美股 | us + 代码 | usAAPL |
| 港股 | hk + 代码 | hk00700 |

### 5.3 indicators.py - 技术指标

**主要函数：**

```python
# RSI - 相对强弱指数
rsi(candles: list, period: int = 14) -> float (0-100)

# MACD - 平滑异同移动平均线
macd(candles: list, fast: int = 12, slow: int = 26, signal: int = 9)
# 返回: {"macd": float, "signal": float, "histogram": float}

# 布林带
bollinger_bands(candles: list, period: int = 20, num_std: float = 2.0)
# 返回: {"upper": float, "middle": float, "lower": float}

# 简单移动平均
sma(candles: list, period: int = 20) -> float

# 指数移动平均
ema(candles: list, period: int = 20) -> float

# 平均真实波幅
atr(candles: list, period: int = 14) -> float

# 综合交易信号
generate_signal(candles: list) -> str  # "BUY" / "SELL" / "HOLD"

# 综合技术分析
analyze(candles: list, symbol: str = "") -> dict
# 返回所有指标的分析结果
```

**信号生成逻辑：**

```python
# 投票机制：每个指标一票
信号列表: [RSI, MACD, 均线交叉, 布林带]
- BUY 票数 > SELL 票数 + 1 → BUY
- SELL 票数 > BUY 票数 + 1 → SELL
- 其他 → HOLD
```

### 5.4 trading.py - Alpaca 交易接口

```python
from trading import AlpacaTrader

trader = AlpacaTrader(API_KEY, SECRET_KEY, BASE_URL)

# 账户操作
trader.get_account()              # 获取账户信息
trader.print_account()            # 打印账户概览
trader.get_buying_power()         # 获取可用资金

# 持仓操作
trader.get_positions()            # 获取所有持仓
trader.get_position(symbol)        # 获取指定持仓
trader.close_position(symbol)      # 平仓
trader.close_all_positions()       # 清仓

# 订单操作
trader.list_orders()               # 列出订单
trader.submit_order(symbol, qty, side, type, limit_price)
trader.cancel_order(order_id)      # 取消订单
trader.cancel_all_orders()         # 取消所有订单

# 便捷方法
trader.market_buy(symbol, qty)    # 市价买入
trader.market_sell(symbol, qty)    # 市价卖出
trader.limit_buy(symbol, qty, price)   # 限价买入
trader.limit_sell(symbol, qty, price)  # 限价卖出
```

### 5.5 notifier.py - 通知推送

```python
from notifier import notify, notify_trade, notify_price_alert

# 通用通知
notify(title: str, body: str, level: str)
# level: "INFO" | "BUY" | "SELL" | "ALERT"

# 交易通知
notify_trade(side: str, symbol: str, qty: int, price: float, signal: str)

# 价格报警
notify_price_alert(symbol: str, price: float, change_pct: float, threshold: float)
```

---

## 6. API 密钥配置

### 6.1 Alpaca (美股交易)

1. 访问 https://app.alpaca.markets
2. 注册 Paper Trading 账户（免费，$100,000 虚拟资金）
3. 登录后 → Paper Account → API → Create Key
4. 复制 Key 和 Secret 到 config.py

### 6.2 Bark (iOS 推送)

1. App Store 搜索并下载「Bark」
2. 打开 App，自动生成 Key（形如 `XXXXXXXX`）
3. 填入 config.py 的 BARK_KEY

### 6.3 PushPlus (微信推送)

1. 微信关注「PushPlus」公众号
2. 发送「token」获取 Token
3. 填入 config.py 的 PUSHPLUS_TOKEN

### 6.4 Telegram Bot

1. @BotFather 发送 `/newbot`
2. 设置 Bot 名称，获取 Token
3. @userinfobot 获取 Chat ID
4. 填入 config.py

---

## 7. 使用示例

### 7.1 启动监控

```bash
cd ~/stock_trader
python3 monitor.py
```

监控程序会：
1. 每 60 秒检查 WATCH_STOCKS 列表中的股票
2. 获取实时行情和技术指标
3. 生成交易信号
4. 自动执行交易（如果 Alpaca 已配置）
5. 推送通知到所有已配置的渠道

### 7.2 单独获取行情

```python
import market_data

# A股
q = market_data.get_quote_sina("sh600519")
print(f"贵州茅台: ¥{q['price']} ({q['change_pct']:+.2f}%)")

# 美股
q = market_data.get_quote_sina("usAAPL")
print(f"AAPL: ${q['price']} ({q['change_pct']:+.2f}%)")

# 历史K线
candles = market_data.get_historical("sh600519", "3mo")
print(f"K线数据: {len(candles)} 条")
```

### 7.3 技术分析

```python
import market_data, indicators

# 获取数据
candles = market_data.get_historical("AAPL", "3mo")

# 分析
result = indicators.analyze(candles, "AAPL")
print(f"AAPL 技术分析:")
print(f"  价格: ${result['price']}")
print(f"  RSI: {result['rsi']}")
print(f"  MACD: {result['macd']}")
print(f"  信号: {result['signal']}")
```

### 7.4 手动交易

```python
import config, trading

trader = trading.AlpacaTrader(
    config.ALPACA_API_KEY,
    config.ALPACA_SECRET_KEY,
    config.ALPACA_BASE_URL
)

# 市价买入
trader.market_buy("AAPL", 1)

# 限价卖出
trader.limit_sell("AAPL", 1, price=180.00)
```

---

## 8. 交易时间

### 北京时间

| 市场 | 开盘 | 收盘 | 备注 |
|------|------|------|------|
| A股 (上交所/深交所) | 09:30 | 15:00 | 午休 11:30-13:00 |
| 港股 | 09:30 | 16:00 | 无午休 |
| 美股 (夏令时) | 22:30 | 05:00 | 次日凌晨结束 |
| 美股 (冬令时) | 23:30 | 05:00 | 次日凌晨结束 |

### 当前时间判断

```python
from datetime import datetime
import pytz

beijing = pytz.timezone('Asia/Shanghai')
now = datetime.now(beijing)
hour = now.hour

if 9 <= hour < 15:
    print("A股交易时间")
elif 22 <= hour or hour < 5:
    print("美股交易时间")
```

---

## 9. 已知限制

| 限制 | 说明 | 解决方案 |
|------|------|----------|
| 富途A股自动化 | 需要 Futu OpenD，本地需24小时电脑 | 正在部署 Windows + OpenD |
| pip 安装不稳定 | Termux 网络问题 | 已使用纯 Python 实现，无需额外依赖 |
| numpy/pandas 不可用 | aarch64 无编译轮子 | 使用纯 Python 实现指标计算 |
| Alpaca 仅支持美股 | 不能交易 A股/港股 | 使用富途 API（需 OpenD） |
| 小区宽带无公网IP | 无法远程访问家里电脑 | 考虑云服务器或内网穿透 |

---

## 10. 故障排查

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| 行情返回 None | 非交易时间/网络问题 | 确认网络，查看是否在交易时间 |
| Alpaca 连接失败 | API Key 错误 | 核对 Key 和 Secret |
| 通知发送失败 | Token 未配置 | 至少配置一个通知渠道 |
| K线数据为空 | 代码格式错误 | 确认使用 "sh600519" 格式 |
| 买入失败 | 资金不足 | 检查账户余额 |
| 卖出失败 | 无持仓 | 检查当前持仓 |

### 验证命令

```bash
# 测试行情获取
python3 -c "import market_data; print(market_data.get_quote_sina('sh600519'))"

# 测试指标计算
python3 -c "import market_data, indicators; c=market_data.get_historical('sh600519','3mo'); print(indicators.analyze(c,'600519'))"

# 测试 Alpaca 连接
python3 -c "import config, trading; t=trading.AlpacaTrader(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY); t.print_account()"

# 测试通知
python3 -c "import notifier; notifier.notify('测试', '这是一条测试消息', 'INFO')"
```

---

## 更新日志

### v1.0.0 (2026-04-30)
- 初始版本
- 支持新浪/东方财富行情
- 支持 RSI/MACD/布林带/均线/ATR 指标
- 支持 Alpaca Paper Trading
- 支持 Bark/PushPlus/Telegram 通知
- 纯 Python 实现，零依赖
