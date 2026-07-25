#!/usr/bin/env python3
"""
A股全自动交易系统 v1
  特朗普访华概念股监控 + 虚拟模拟盘 + 双层风控
  纯Python，无第三方依赖
"""
import sys, os, json, time
from datetime import datetime, timezone, timedelta
import urllib.request
import urllib.error

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SRC_DIR)

STATE_FILE = f'{SRC_DIR}/cn_risk_state.json'
STATE_FILE_BAK = f'{SRC_DIR}/cn_risk_state.bak.json'
SIGNAL_FILE = f'{SRC_DIR}/cn_signal_latest.json'
BACKUP_DIR = f'{SRC_DIR}/backups'
MAX_BACKUPS = 10

# ======================== 特朗普访华概念股池 ========================
CONCEPT_WATCH = {
    # 特斯拉链 (FSD入华利好)
    'sz300750': {'name': '宁德时代', 'concept': '特斯拉链', 'desc': '电池主供'},
    'sz002594': {'name': '比亚迪', 'concept': '新能源车', 'desc': '整车龙头'},
    'sh601689': {'name': '拓普集团', 'concept': '特斯拉链', 'desc': '底盘供应商'},
    'sz002050': {'name': '三花智控', 'concept': '特斯拉链', 'desc': '热管理'},
    'sh603305': {'name': '旭升集团', 'concept': '特斯拉链', 'desc': '铝合金压铸'},
    # AI芯片 (黄仁勋随团利好)
    'sz300308': {'name': '中际旭创', 'concept': 'AI芯片', 'desc': '光模块龙头'},
    'sh688256': {'name': '寒武纪', 'concept': 'AI芯片', 'desc': 'AI芯片设计'},
    'sh601138': {'name': '工业富联', 'concept': 'AI芯片', 'desc': 'AI服务器'},
    # 苹果链 (库克随团利好)
    'sz002475': {'name': '立讯精密', 'concept': '苹果链', 'desc': '连接器龙头'},
    'sz002241': {'name': '歌尔股份', 'concept': '苹果链', 'desc': '声学组件'},
    # 其他
    'sh600519': {'name': '贵州茅台', 'concept': '消费', 'desc': '外资回流'},
}

# 初始资金
INITIAL_CASH = 1000000  # 100万模拟资金
MAX_POSITIONS = 5       # 最多同时持仓5只

# 风控参数
TRAIL_DISTANCE = 0.05   # 移动止损5%
STOP_LOSS_PCT = 0.05    # 硬止损5%
TP_PROFIT_PCT = 0.15    # 止盈15%

# ======================== 数据源 ========================
def get_quote_sina(codes):
    """新浪实时行情"""
    url = f"https://hq.sinajs.cn/list={','.join(codes)}"
    headers = {"Referer": "https://finance.sina.com.cn"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200: return {}
        result = {}
        for line in r.text.strip().split('\n'):
            if '=' not in line: continue
            parts = line.split('=')
            code = parts[0].split('_')[-1].strip('"').strip()
            data = parts[1].strip('\';"').split(',')
            if len(data) >= 32:
                price = float(data[3]) if data[3] else 0
                if price > 0:
                    result[code] = {
                        "name": data[0], "price": price,
                        "close": float(data[2]) if data[2] else 0,
                        "high": float(data[4]), "low": float(data[5]),
                        "vol": int(data[8]) if data[8] else 0,
                    }
    except: pass
    return result

def get_kline_em(code, days=60):
    """东方财富K线"""
    secid = f"1.{code[2:]}" if code.startswith("sh") else f"0.{code[2:]}"
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {"secid": secid, "fields1": "f1,f2,f3", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
              "klt": "101", "fqt": "1", "end": "20500101", "lmt": days}
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            d = r.json()
            if d.get("data") and d["data"].get("klines"):
                return d["data"]["klines"]
    except: pass
    return []

def get_kline_sina(code, days=60):
    """新浪K线（备用）"""
    url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    params = {"symbol": code.lower(), "scale": 240, "datalen": days}
    try:
        r = requests.get(url, params=params, timeout=10, headers={"Referer": "https://finance.sina.com.cn"})
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                data = list(reversed(data))
                return [f"{d['day']},{d['open']},{d['close']},{d['high']},{d['low']},{d['volume']}" for d in data]
    except: pass
    return []

def parse_kline(klines):
    result = []
    for k in klines:
        parts = k.split(',')
        result.append({"date": parts[0], "open": float(parts[1]),
                        "close": float(parts[2]), "high": float(parts[3]),
                        "low": float(parts[4]), "vol": float(parts[5])})
    return result

# ======================== 指标计算 ========================
def calc_sma(prices, period):
    if len(prices) < period: return None
    return sum(prices[-period:]) / period

def calc_rsi(prices, period=14):
    if len(prices) < period + 1: return None
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0 for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0: return 100
    return 100 - (100 / (1 + avg_gain / avg_loss))

def calc_boll(prices, period=20, mult=2):
    if len(prices) < period: return None, None, None
    last = prices[-period:]
    mean = sum(last) / period
    std = (sum((x - mean)**2 for x in last) / period) ** 0.5
    return round(mean - mult*std, 2), round(mean, 2), round(mean + mult*std, 2)

# ======================== 分析和信号 ========================
def analyze_cn(code, quote, klines):
    """分析单只A股，返回信号"""
    if not klines or not quote: return None
    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    price = quote["price"]
    prev_close = quote["close"]
    if prev_close == 0: return None
    chg = (price - prev_close) / prev_close * 100

    ma5 = calc_sma(closes, min(5, len(closes)))
    ma20 = calc_sma(closes, min(20, len(closes)))
    rsi = calc_rsi(closes)
    lower, mid, upper = calc_boll(closes)

    trend = "震荡"
    if ma5 and ma20:
        if ma5 > ma20 * 1.01: trend = "上涨"
        elif ma5 < ma20 * 0.99: trend = "下跌"

    buy_score = 0
    buy_reasons = []

    if rsi and rsi < 35: buy_score += 2; buy_reasons.append(f'RSI超卖({rsi:.0f})')
    if lower and price < lower: buy_score += 2; buy_reasons.append('触及布林下轨')
    if ma5 and ma20 and price > ma5 and ma5 > ma20:
        buy_score += 1; buy_reasons.append('均线多头')
    if chg > 3: buy_score += 1; buy_reasons.append(f'放量上涨({chg:+.1f}%)')
    if rsi and rsi > 70: buy_score -= 1

    # 高点回落检测：成交量异常放大
    recent_high = max(highs[-10:]) if len(highs) >= 10 else max(highs)

    sell_reason = None
    if rsi and rsi > 80:
        sell_reason = f'RSI超买极端({rsi:.0f})→卖50%'
    elif price < recent_high * 0.92:
        drop = (recent_high - price) / recent_high * 100
        sell_reason = f'从高点回落{drop:.1f}%→卖全部'

    return {
        "code": code, "name": quote["name"],
        "price": price, "prev_close": prev_close, "chg": round(chg, 2),
        "ma5": ma5, "ma20": ma20, "rsi": rsi,
        "lower": lower, "mid": mid, "upper": upper,
        "trend": trend, "buy_score": buy_score,
        "buy_reasons": buy_reasons, "sell_reason": sell_reason,
        "recent_high": recent_high, "bars": len(closes),
    }

# ======================== 虚拟组合管理 ========================
def safe_write(path, data):
    """原子写入：先写.tmp再rename，防止中途崩溃导致文件损坏"""
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)  # 原子操作

def rotate_backup():
    """轮换备份，保留最近MAX_BACKUPS份"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M')
    bak = f'{BACKUP_DIR}/cn_risk_state.{ts}.json'
    if os.path.exists(STATE_FILE):
        import shutil
        shutil.copy2(STATE_FILE, bak)
    # 清理旧备份
    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('cn_risk_state.')])
    while len(backups) > MAX_BACKUPS:
        os.remove(os.path.join(BACKUP_DIR, backups.pop(0)))

def load_portfolio():
    """加载组合，支持双重容灾"""
    # 尝试主文件
    for path in [STATE_FILE, STATE_FILE_BAK]:
        try:
            with open(path) as f:
                data = json.load(f)
                # 校验数据完整性
                if 'cash' in data and 'positions' in data:
                    return data
        except: pass
    return {"cash": INITIAL_CASH, "positions": {}, "total_buy": 0, "total_sell": 0,
            "peak_equity": INITIAL_CASH, "paused": False}

def save_portfolio(pf):
    """保存组合 + 自动备份 + Git版本控制"""
    # 1. 先备份旧文件
    if os.path.exists(STATE_FILE):
        import shutil
        shutil.copy2(STATE_FILE, STATE_FILE_BAK)
    # 2. 原子写入主文件
    safe_write(STATE_FILE, pf)
    # 3. 定时轮换备份（每30分钟一次）
    now = datetime.now()
    if now.minute % 30 == 0:
        rotate_backup()
    # 4. Git版本控制（每轮都commit，方便回滚）
    try:
        import subprocess
        subprocess.run(['git', 'add', '-A', '.json', '.gitignore'],
                       cwd=SRC_DIR, capture_output=True, timeout=5)
        ts = now.strftime('%Y-%m-%d %H:%M')
        subprocess.run(['git', 'commit', '--allow-empty', '-m', f'auto {ts}'],
                       cwd=SRC_DIR, capture_output=True, timeout=5)
    except:
        pass  # git失败不阻塞主流程

def calc_equity(pf, prices):
    """计算总权益 = 现金 + 持仓市值"""
    mv = 0
    for code, pos in pf["positions"].items():
        price = prices.get(code, {}).get("price", pos.get("price", 0))
        mv += price * pos["qty"]
    return pf["cash"] + mv

def virtual_buy(pf, code, qty, price, name):
    """虚拟买入"""
    cost = price * qty * 1.0003  # 万分之三手续费
    if pf["cash"] < cost: return False
    pf["cash"] -= cost
    if code in pf["positions"]:
        old = pf["positions"][code]
        total_cost = old["cost"] + cost
        total_qty = old["qty"] + qty
        old["avg_price"] = total_cost / total_qty
        old["qty"] = total_qty
        old["cost"] = total_cost
    else:
        pf["positions"][code] = {"name": name, "qty": qty, "avg_price": price,
                                  "cost": cost, "highest": price}
    pf["total_buy"] += cost
    return True

def virtual_sell(pf, code, qty, price):
    """虚拟卖出"""
    if code not in pf["positions"]: return False
    pos = pf["positions"][code]
    if pos["qty"] < qty: return False
    revenue = price * qty * 0.9997  # 扣除印花税+手续费
    pf["cash"] += revenue
    pos["qty"] -= qty
    pos["cost"] = pos["cost"] * (pos["qty"] / (pos["qty"] + qty)) if pos["qty"] > 0 else 0
    pf["total_sell"] += revenue
    if pos["qty"] <= 0:
        del pf["positions"][code]
    return True

# ======================== 风控 - 移动止损 ========================
def update_trail_stops(pf, prices):
    """移动止损检查，返回需要卖出的列表"""
    sells = []
    for code in list(pf["positions"].keys()):
        pos = pf["positions"][code]
        price = prices.get(code, {}).get("price", 0)
        if price <= 0: continue

        # 更新最高价
        if price > pos["highest"]:
            pos["highest"] = price

        # 移动止损 = max(最高价*0.95, 均价*0.95)
        trail_stop = pos["highest"] * (1 - TRAIL_DISTANCE)
        init_stop = pos["avg_price"] * (1 - STOP_LOSS_PCT)
        soft_stop = max(trail_stop, init_stop)

        if price <= soft_stop and price > init_stop:
            # 触发追踪止损
            sells.append({"code": code, "qty": pos["qty"], "reason": f"追踪止损触发(最高{pos['highest']:.2f}→现价{price:.2f})"})
        elif price <= init_stop:
            sells.append({"code": code, "qty": pos["qty"], "reason": f"硬止损触发(成本{pos['avg_price']:.2f}→现价{price:.2f})"})
    return sells

# ======================== 总账户风控 ========================
def check_account_risk(pf, equity):
    peak = pf.get("peak_equity", equity)
    if equity > peak:
        pf["peak_equity"] = equity
        peak = equity
    drawdown = (peak - equity) / peak if peak > 0 else 0
    alerts = []
    can_buy = True

    if drawdown >= 0.20:
        pf["paused"] = True
        can_buy = False
        alerts.append(f'🚨 总回撤{drawdown*100:.1f}%>20%！强制风控')
    elif drawdown >= 0.12:
        pf["paused"] = True
        can_buy = False
        alerts.append(f'⚠️ 总回撤{drawdown*100:.1f}%>12%，暂停买入')
    else:
        if pf.get("paused") and drawdown < 0.08:
            pf["paused"] = False
            alerts.append(f'✅ 回撤恢复至{drawdown*100:.1f}%，解除风控')
    return can_buy, alerts

# ======================== 主函数 ========================
def main():
    bj_now = datetime.now() + timedelta(hours=8)
    time_str = bj_now.strftime('%Y-%m-%d %H:%M')
    weekday = bj_now.weekday()

    # 周末跳过
    if weekday >= 5:
        print(f"📅 A股模拟盘 | {time_str}")
        print("周末休市，跳过本轮")
        return

    # 交易日9:30~15:00外只分析不下单
    hour = bj_now.hour
    is_trading = 9 <= hour < 15 or (hour == 9 and bj_now.minute >= 30)

    # 加载组合
    pf = load_portfolio()

    # 获取行情
    codes = list(CONCEPT_WATCH.keys())
    quotes = get_quote_sina(codes)

    if not quotes:
        print(f"❌ A股行情 | {time_str}")
        print("行情获取失败，跳过本轮")
        return

    # 获取K线
    all_results = []
    prices = {}
    for code in codes:
        if code not in quotes: continue
        q = quotes[code]
        prices[code] = q
        klines = get_kline_em(code)
        if not klines: klines = get_kline_sina(code)
        parsed = parse_kline(klines) if klines else []
        result = analyze_cn(code, q, parsed)
        if result: all_results.append(result)

    if not all_results:
        print(f"❌ A股分析 | {time_str}")
        print("分析失败")
        return

    # 计算总权益
    equity = calc_equity(pf, prices)
    total_pnl = equity - INITIAL_CASH
    total_pnl_pct = total_pnl / INITIAL_CASH * 100

    # ======= 1. 总账户风控 =======
    can_buy, risk_alerts = check_account_risk(pf, equity)

    # ======= 2. 移动止损 =======
    sells = update_trail_stops(pf, prices)
    sell_msgs = []
    for s in sells:
        code, qty, reason = s["code"], s["qty"], s["reason"]
        name = CONCEPT_WATCH.get(code, {}).get("name", code)
        price = prices.get(code, {}).get("price", 0)
        if virtual_sell(pf, code, qty, price):
            sell_msgs.append(f'  🔴 卖出 {name} x{qty}@{price:.2f} | {reason}')
        else:
            sell_msgs.append(f'  ⚠️ {name} 卖出失败')

    # ======= 3. 止盈检查 =======
    tp_msgs = []
    held_codes = list(pf["positions"].keys())
    for code in held_codes:
        if code not in prices: continue
        pos = pf["positions"].get(code)
        if not pos: continue
        price = prices[code]["price"]
        pnl_pct = (price - pos["avg_price"]) / pos["avg_price"] * 100
        if pnl_pct >= TP_PROFIT_PCT * 100:
            # 止盈：卖一半
            sell_qty = max(1, pos["qty"] // 2)
            if virtual_sell(pf, code, sell_qty, price):
                name = CONCEPT_WATCH.get(code, {}).get("name", code)
                tp_msgs.append(f'  💰 止盈 {name} x{sell_qty}@{price:.2f} (+{pnl_pct:.1f}%)')

    # ======= 4. 买入信号 =======
    buy_msgs = []
    if can_buy and is_trading:
        # 分析的信号排序
        sorted_results = sorted(all_results, key=lambda x: x["buy_score"], reverse=True)
        held_syms = set(pf["positions"].keys())
        new_name = CONCEPT_WATCH

        for r in sorted_results:
            if len(pf["positions"]) >= MAX_POSITIONS: break
            if r["code"] in held_syms: continue
            if r["buy_score"] < 2: continue
            if r["rsi"] and r["rsi"] > 65: continue

            price = r["price"]
            qty = max(1, int(pf["cash"] // 2 // price // 100) * 100)  # 每手100股
            if qty < 100: qty = max(100, int(pf["cash"] // price // 100) * 100)
            if qty <= 0: continue

            cost = qty * price
            if pf["cash"] < cost * 1.003: continue

            if virtual_buy(pf, r["code"], qty, price, r["name"]):
                buy_msgs.append(f'  📗 买入 {r["name"]} {qty}股@{price:.2f} | {" ".join(r["buy_reasons"])}')
                held_syms.add(r["code"])
    elif not is_trading:
        buy_msgs.append(f'  ⏸ 非交易时段，跳过买入')
    elif not can_buy:
        buy_msgs.append(f'  ⏸ 风控中，暂停买入')

    # 保存状态
    save_portfolio(pf)

    # ======= 输出报告 =======
    print(f"📊 A股模拟盘 | {time_str}")
    print("=" * 55)
    print(f"💰 总权益 {equity:>10,.2f}  |  现金 {pf['cash']:>10,.2f}")
    print(f"  盈亏 {total_pnl:+,.2f} ({total_pnl_pct:+.2f}%)  |  峰值 {pf['peak_equity']:>10,.2f}")

    if pf.get("paused"):
        print("  ⛔ 风控暂停中")
    print()

    # 持仓
    if pf["positions"]:
        print("📋 持仓")
        print("-" * 55)
        for code, pos in sorted(pf["positions"].items(), key=lambda x: x[1]["cost"], reverse=True):
            price = prices.get(code, {}).get("price", 0)
            pnl = (price - pos["avg_price"]) / pos["avg_price"] * 100 if pos["avg_price"] > 0 else 0
            mv = price * pos["qty"]
            icon = "🟢" if pnl > 0 else "🔴"
            # 距止损
            trail_stop = pos["highest"] * (1 - TRAIL_DISTANCE)
            init_stop = pos["avg_price"] * (1 - STOP_LOSS_PCT)
            soft_stop = max(trail_stop, init_stop)
            stop_dist = (price - soft_stop) / price * 100 if price > 0 else 0
            print(f"  {icon} {pos['name']:6s} {pos['qty']:>5}股 均价{pos['avg_price']:>7.2f} "
                  f"现价{price:>7.2f} 浮盈{pnl:+5.1f}% | 止损{soft_stop:.2f}距{stop_dist:.0f}%")
    else:
        print("📋 持仓: 空仓")
    print()

    # 操作日志
    if risk_alerts:
        print("🚨 风控告警")
        for a in risk_alerts:
            print(f"  {a}")
        print()
    if tp_msgs:
        print("💰 止盈")
        for m in tp_msgs:
            print(m)
        print()
    if sell_msgs:
        print("🔴 卖出")
        for m in sell_msgs:
            print(m)
        print()
    if buy_msgs:
        print("📗 买入")
        for m in buy_msgs:
            print(m)
        print()
    else:
        if is_trading:
            print("📗 买入: 无信号")
        print()

    # 概念板块涨幅排名
    print("🔍 概念板块监控")
    print("-" * 55)
    concepts = {}
    for r in all_results:
        info = CONCEPT_WATCH.get(r["code"], {})
        concept = info.get("concept", "其他")
        if concept not in concepts: concepts[concept] = []
        concepts[concept].append(f"{r['name']}{r['chg']:+.1f}%")
    for c, items in concepts.items():
        held = sum(1 for code in pf["positions"] if CONCEPT_WATCH.get(code, {}).get("concept") == c)
        icon = "🔥" if held > 0 else "  "
        print(f"  {icon} {c}: {' | '.join(items)}")
    print()

    # 信号最强的3只
    print("🏆 买入信号排名")
    top3 = sorted(all_results, key=lambda x: x["buy_score"], reverse=True)[:3]
    for r in top3:
        info = CONCEPT_WATCH.get(r["code"], {})
        concept = info.get("concept", "")
        held_mark = "✅ 已持" if r["code"] in pf["positions"] else ""
        print(f"  {r['name']:6s}({concept}) 信号{r['buy_score']:+d} "
              f"现价{r['price']:.2f} RSI{r['rsi']:.0f} 趋势{r['trend']} {held_mark}")
    print()
    print("✅ 本轮完成")

    # 保存JSON信号
    with open(SIGNAL_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            "time": time_str, "equity": equity, "cash": pf["cash"],
            "pnl": round(total_pnl, 2), "pnl_pct": round(total_pnl_pct, 2),
            "positions": {k: {"name": v["name"], "qty": v["qty"],
                              "avg_price": v["avg_price"], "cost": round(v["cost"], 2)}
                          for k, v in pf["positions"].items()},
            "top_signals": [{r["code"]: r["buy_score"]} for r in top3],
        }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
