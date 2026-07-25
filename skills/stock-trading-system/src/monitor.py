# ========================
# 主监控程序
# 定时获取行情 -> 计算指标 -> 生成信号 -> 自动下单 -> 异常报警
# ========================

import time
import sys
import json
import os
from datetime import datetime, timezone

# 导入项目模块
import market_data
import indicators
import trading
import notifier
import config


class StockMonitor:
    def __init__(self):
        self.trader = None
        self.last_prices = {}      # 上次价格（用于波动检测）
        self.last_alert_time = {}  # 上次报警时间（防轰炸）
        self.candle_cache = {}     # 缓存K线数据
        self.candle_cache_time = {} # 缓存时间

        # 初始化交易接口
        if config.ALPACA_API_KEY and config.ALPACA_API_KEY != "PKXXXXXXXXXXXXXXXXXX":
            self.trader = trading.AlpacaTrader(
                config.ALPACA_API_KEY,
                config.ALPACA_SECRET_KEY,
                config.ALPACA_BASE_URL
            )
            print(f"[系统] Alpaca 交易接口已初始化")
        else:
            print(f"[系统] Alpaca API 未配置，跳过自动交易功能")

    # ---------- 行情获取 ----------

    def fetch_quotes(self):
        """获取监控列表的实时行情"""
        quotes = {}
        for sym in config.WATCH_STOCKS:
            q = market_data.get_quote_sina(sym)
            if q and q.get("price", 0) > 0:
                quotes[sym.upper()] = q
            time.sleep(0.1)
        return quotes

    def fetch_candles(self, symbol: str, refresh: bool = False) -> list:
        """
        获取历史K线（带缓存，5分钟内不重复请求）
        东方财富不可用时：尝试新浪 + fallback
        """
        cache_ttl = 300  # 5分钟缓存
        now = time.time()
        sym = symbol.upper()

        if not refresh and sym in self.candle_cache:
            if now - self.candle_cache_time.get(sym, 0) < cache_ttl:
                return self.candle_cache[sym]

        candles = market_data.get_historical(sym, "3mo")

        if candles:
            self.candle_cache[sym] = candles
            self.candle_cache_time[sym] = now
        return candles or []

    # ---------- 波动检测 ----------

    def check_price_alert(self, quotes: dict):
        """检测价格异常波动并报警"""
        now = time.time()
        for sym, q in quotes.items():
            price = q.get("price")
            change_pct = q.get("change_pct", 0)
            if price is None:
                continue

            # 价格变化检测
            last_price = self.last_prices.get(sym)
            if last_price:
                price_delta = abs(price - last_price) / last_price
                if price_delta >= config.PRICE_CHANGE_THRESHOLD:
                    # 防轰炸：同一标的1分钟内不重复报警
                    if now - self.last_alert_time.get(sym, 0) > 60:
                        notifier.notify_price_alert(sym, price, change_pct, config.PRICE_CHANGE_THRESHOLD)
                        self.last_alert_time[sym] = now
            self.last_prices[sym] = price

    # ---------- 信号分析 ----------

    def analyze_all(self, quotes: dict) -> dict:
        """对所有监控标的进行技术分析和信号生成"""
        results = {}
        for sym in config.WATCH_STOCKS:
            sym = sym.upper()
            candles = self.fetch_candles(sym)
            if not candles or len(candles) < 30:
                results[sym] = {"signal": "NO_DATA", "reason": "K线不足"}
                continue

            analysis = indicators.analyze(candles, sym)
            signal = analysis.get("signal", "HOLD")

            # 结合RSI和MACD综合判断
            rsi = analysis.get("rsi")
            macd = analysis.get("macd", {})
            bb = analysis.get("bollinger")
            current_price = analysis.get("price")

            # 过滤虚假信号
            if signal == "BUY" and bb and current_price:
                if current_price > bb.get("middle"):
                    signal = "HOLD"  # 价格在均线上方的超卖可能反弹较弱

            analysis["final_signal"] = signal
            results[sym] = analysis
        return results

    # ---------- 自动交易 ----------

    def auto_trade(self, quotes: dict, analyses: dict):
        """根据信号执行自动交易"""
        if not self.trader:
            return

        for sym, analysis in analyses.items():
            signal = analysis.get("final_signal", "HOLD")
            if signal == "HOLD" or signal == "NO_DATA":
                continue

            price = quotes.get(sym, {}).get("price")
            if not price:
                continue

            # 检查持仓
            position = self.trader.get_position(sym)

            if signal == "BUY":
                if position:
                    print(f"[交易] {sym} 已有持仓，跳过买入")
                    continue
                # 市价买入
                order = self.trader.market_buy(sym, config.DEFAULT_QTY)
                if order:
                    notifier.notify_trade("BUY", sym, config.DEFAULT_QTY, price, f"RSI={analysis.get('rsi')}, MACD={'金叉' if analysis.get('macd',{}).get('histogram',0)>0 else '死叉'}")

            elif signal == "SELL":
                if not position:
                    print(f"[交易] {sym} 无持仓，跳过卖出")
                    continue
                # 市价卖出
                qty = int(position.get("qty", config.DEFAULT_QTY))
                order = self.trader.market_sell(sym, qty)
                if order:
                    notifier.notify_trade("SELL", sym, qty, price, f"RSI={analysis.get('rsi')}, MACD={'死叉' if analysis.get('macd',{}).get('histogram',0)<0 else '金叉'}")

    # ---------- 定时报告 ----------

    def print_report(self, quotes: dict, analyses: dict):
        """打印市场行情和技术分析报告"""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n{'='*60}")
        print(f"  市场监控报告  [{now}]")
        print(f"{'='*60}")

        if not quotes:
            print("  无行情数据")
            return

        for sym in config.WATCH_STOCKS:
            sym = sym.upper()
            q = quotes.get(sym, {})
            a = analyses.get(sym, {})
            if not q:
                print(f"\n  {sym}: 行情获取失败")
                continue

            price = q.get("price")
            pct = q.get("change_pct", 0)
            change = q.get("change", 0)
            arrow = "▲" if change >= 0 else "▼"

            signal = a.get("final_signal", "?")
            signal_color = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}.get(signal, "⚪")

            rsi = a.get("rsi")
            macd = a.get("macd", {})
            bb = a.get("bollinger")

            print(f"\n  {arrow} {sym}  {signal_color} {signal}")
            print(f"     价格: {price}  涨跌: {change:+.2f} ({pct:+.2f}%)")
            if rsi:
                rsi_emoji = "🟢" if rsi < 30 else "🔴" if rsi > 70 else "⚪"
                print(f"     RSI:  {rsi_emoji} {rsi:.1f}")
            if macd:
                hist = macd.get("histogram", 0)
                macd_str = "▲" if hist > 0 else "▼"
                print(f"     MACD: {macd_str} {macd.get('macd'):.3f} / Signal {macd.get('signal'):.3f}")
            if bb:
                print(f"     布林带: {bb.get('lower')} - {bb.get('middle')} - {bb.get('upper')}")
            if a.get("sma_20"):
                print(f"     SMA20/50: {a.get('sma_20'):.2f} / {a.get('sma_50'):.2f}")

    # ---------- 主循环 ----------

    def run(self, interval: int = None):
        """启动监控循环"""
        if interval is None:
            interval = config.CHECK_INTERVAL

        print(f"[系统] 启动股票监控")
        print(f"[系统] 监控标的: {', '.join(config.WATCH_STOCKS)}")
        print(f"[系统] 检查间隔: {interval}秒")
        if self.trader:
            self.trader.print_account()
        print(f"{'='*60}")

        consecutive_errors = 0
        max_errors = 3

        while True:
            try:
                # 1. 获取实时行情
                quotes = self.fetch_quotes()
                if quotes:
                    consecutive_errors = 0
                    # 2. 波动报警
                    self.check_price_alert(quotes)
                    # 3. 技术分析
                    analyses = self.analyze_all(quotes)
                    # 4. 打印报告
                    self.print_report(quotes, analyses)
                    # 5. 自动交易
                    self.auto_trade(quotes, analyses)
                else:
                    consecutive_errors += 1
                    print(f"[警告] 行情获取失败 (连续第 {consecutive_errors} 次)")

                if consecutive_errors >= max_errors:
                    notifier.notify_error("行情获取", f"连续{max_errors}次获取失败，请检查网络")

                time.sleep(interval)

            except KeyboardInterrupt:
                print("\n[系统] 用户中断，退出监控")
                break
            except Exception as e:
                print(f"[错误] 监控异常: {e}")
                notifier.notify_error("监控异常", str(e))
                time.sleep(30)


if __name__ == "__main__":
    monitor = StockMonitor()
    monitor.run()
