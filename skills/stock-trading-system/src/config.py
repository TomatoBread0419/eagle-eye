import os
# ========================
# 配置文件
# ========================

# Alpaca 券商 API（Paper Trading 模拟交易）
# 申请地址: https://app.alpaca.markets/
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"     # Paper 交易端点

# 报警通知配置
# 支持 Bark（iOS）/ PushPlus/ Telegram Bot，选择其一或组合启用
BARK_KEY = ""                      # Bark App 的 Key
PUSHPLUS_TOKEN = ""                # PushPlus 的 Token
TELEGRAM_BOT_TOKEN = ""            # Telegram Bot Token
TELEGRAM_CHAT_ID = ""              # Telegram Chat ID

# 策略参数
WATCH_STOCKS = ["AAPL", "TSLA", "NVDA", "MSFT"]  # 监控的股票列表
CHECK_INTERVAL = 60               # 检查间隔（秒）
PRICE_CHANGE_THRESHOLD = 0.02     # 价格变化报警阈值（2%）
RSI_OVERSOLD = 30                 # RSI 超卖阈值
RSI_OVERBOUGHT = 70               # RSI 超买阈值
SMA_SHORT = 20                    # 短期均线周期
SMA_LONG = 50                     # 长期均线周期

# 交易参数
DEFAULT_QTY = 1                   # 默认每笔交易数量
