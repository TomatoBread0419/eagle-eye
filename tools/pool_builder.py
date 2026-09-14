#!/usr/bin/env python3
"""
pool_builder.py — 动态池粗筛模块
从 S&P 500 成分出发，用 AlpacaClient.get_bars 拉价格/成交量，
筛选出 200-300 只流动性好的标的，写入 scan_universe.json。
每周六运行一次。
"""
import csv, io, json, os, sys, time, logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────
HOME = os.path.expanduser('~')
STOCK_TRADER = os.path.join(HOME, 'stock_trader')
UNIVERSE_FILE = os.path.join(STOCK_TRADER, 'scan_universe.json')
BACKUP_DIR = os.path.join(STOCK_TRADER, 'backups')
SP500_CSV_URL = 'https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv'

# ── GICS Sector → 自定义 sector 映射 ─────────────────────────────────
GICS_TO_SECTOR = {
    'Information Technology': 'tech',
    'Health Care': 'pharma',
    'Financials': 'finance',
    'Consumer Discretionary': 'consumer',
    'Consumer Staples': 'consumer',
    'Industrials': 'industrial',
    'Communication Services': 'telecom',
    'Utilities': 'energy',
    'Real Estate': 'finance',
    'Materials': 'resources',
    'Energy': 'energy',
}

# ── 筛选参数（从 cfg.pool 读取，单一真相来源）────────────────────
from eagle_eye.core.config import cfg as _cfg


def _parse_csv(text):
    """解析 S&P 500 CSV 文本"""
    rows = list(csv.DictReader(io.StringIO(text)))
    result = []
    for row in rows:
        sym = row['Symbol']  # 不做点号替换，保持原始格式（BRK.B 等）
        gics = row['GICS Sector']
        result.append((sym, gics))
    log.info(f'S&P 500: {len(result)} 只')
    return result


def fetch_sp500():
    """从 GitHub 获取 S&P 500 成分列表（curl 降级 + 24h 本地缓存）"""
    import subprocess
    cache_path = os.path.join(STOCK_TRADER, '.sp500_cache.csv')

    # 本地缓存 24h 有效
    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < 86400:
            with open(cache_path) as f:
                text = f.read()
            if len(text) > 500:
                log.info(f'使用本地缓存 (age={age/3600:.1f}h)')
                return _parse_csv(text)

    text = None

    # 尝试 requests
    try:
        import requests
        r = requests.get(SP500_CSV_URL, timeout=15)
        r.raise_for_status()
        text = r.text
        log.info('通过 requests 获取')
    except Exception as e:
        log.warning(f'requests 失败: {e}')

    # curl 降级（Termux SSL 兼容）
    if not text:
        try:
            result = subprocess.run(
                ['curl', '-s', '-L', '--max-time', '15', SP500_CSV_URL],
                capture_output=True, text=True, timeout=20)
            if result.returncode == 0 and len(result.stdout) > 500:
                text = result.stdout
                log.info('通过 curl 获取')
        except Exception as e:
            log.error(f'curl 也失败: {e}')

    if not text:
        raise RuntimeError('无法获取 S&P 500 成分列表')

    # 写缓存
    try:
        with open(cache_path, 'w') as f:
            f.write(text)
    except Exception:
        pass

    return _parse_csv(text)


def _fetch_single(client, sym):
    """拉取单只标的的 bars 数据，失败则连字符替换再试，最后 get_last_price 降级"""
    symbols_to_try = [sym]
    if '.' in sym:
        symbols_to_try.append(sym.replace('.', '-'))

    for try_sym in symbols_to_try:
        try:
            bars = client.get_bars(try_sym, days=5)
            if bars and len(bars) > 0:
                prices = [b['c'] for b in bars]
                volumes = [b['v'] for b in bars]
                avg_vol_usd = sum(v * c for v, c in zip(volumes, prices)) / len(bars)
                return (sym, {
                    'avg_volume_usd': avg_vol_usd,
                    'last_price': prices[-1],
                    'bars_count': len(bars),
                })
        except Exception:
            pass

    # 最终降级：get_last_price
    for try_sym in symbols_to_try:
        try:
            price = client.get_last_price(try_sym)
            if price and price > 0:
                return (sym, {
                    'avg_volume_usd': 0,
                    'last_price': price,
                    'bars_count': 0,
                })
        except Exception:
            pass

    return (sym, None)


def fetch_bars_parallel(client, symbols):
    """并发获取所有标的的 bars 数据"""
    total = len(symbols)
    results = {}
    done = 0

    log.info(f'并发拉取 bars: {total} 只, {_cfg.pool.workers} 线程')
    with ThreadPoolExecutor(max_workers=_cfg.pool.workers) as executor:
        futures = {
            executor.submit(_fetch_single, client, sym): sym
            for sym in symbols
        }
        for future in as_completed(futures):
            sym, data = future.result()
            if data:
                results[sym] = data
            done += 1
            if done % 50 == 0:
                log.info(f'  进度: {done}/{total} ({len(results)} 有数据)')
            time.sleep(_cfg.pool.batch_sleep)

    log.info(f'完成: {done}/{total}, 有数据: {len(results)}')
    return results


def filter_and_build(sp500_list, bars_data):
    """筛选 + 构造 universe 字典"""
    universe = {}
    rejected_price = 0
    rejected_volume = 0
    no_data = 0

    for sym, gics in sp500_list:
        if sym not in bars_data:
            no_data += 1
            continue
        price = bars_data[sym]['last_price']
        vol_usd = bars_data[sym]['avg_volume_usd']
        if price < _cfg.pool.min_price:
            rejected_price += 1
            continue
        if vol_usd < _cfg.pool.min_avg_volume:
            rejected_volume += 1
            continue
        sector = GICS_TO_SECTOR.get(gics, 'consumer')
        universe[sym] = sector

    log.info(f'筛选: 通过={len(universe)}, 价格<{_cfg.pool.min_price}={rejected_price}, '
             f'成交额<${_cfg.pool.min_avg_volume/1e6:.0f}M={rejected_volume}, 无数据={no_data}')

    # 超过上限 → 按成交额截断
    if len(universe) > _cfg.pool.target_max:
        ranked = sorted(
            [(s, universe[s]) for s in universe],
            key=lambda x: bars_data.get(x[0], {}).get('avg_volume_usd', 0),
            reverse=True
        )
        universe = dict(ranked[:_cfg.pool.target_max])
        log.info(f'截断至 {_cfg.pool.target_max} 只')

    # 低于下限 → 降低门槛
    if len(universe) < _cfg.pool.target_min:
        log.warning(f'{len(universe)} < {_cfg.pool.target_min}，降低门槛重试')
        universe = {}
        for sym, gics in sp500_list:
            if sym not in bars_data:
                continue
            price = bars_data[sym]['last_price']
            vol_usd = bars_data[sym]['avg_volume_usd']
            if price >= 5.0 and vol_usd >= 2e6:
                sector = GICS_TO_SECTOR.get(gics, 'consumer')
                universe[sym] = sector
        if len(universe) > _cfg.pool.target_max:
            ranked = sorted(
                [(s, universe[s]) for s in universe],
                key=lambda x: bars_data.get(x[0], {}).get('avg_volume_usd', 0),
                reverse=True
            )
            universe = dict(ranked[:_cfg.pool.target_max])

    return universe


def write_universe(new_universe):
    """写入 scan_universe.json，保留旧文件的自定义字段"""
    existing = {}
    try:
        with open(UNIVERSE_FILE) as f:
            existing = json.load(f)
    except Exception:
        pass

    # 合并旧 universe（保留手动添加的 ai/defense/space 等）
    old_universe = existing.get('universe', {})
    merged = dict(old_universe)
    merged.update(new_universe)

    output = {
        'universe': merged,
        'sector_meta': existing.get('sector_meta', {}),
        'defense_bonus': existing.get('defense_bonus', {
            'telecom': 0.03, 'defense': 0.05, 'energy': 0.03,
            'pharma': 0.02, 'consumer': 0.02
        }),
        'target_alloc': existing.get('target_alloc', {
            'tech': 0.25, 'pharma': 0.15, 'finance': 0.12,
            'consumer': 0.10, 'industrial': 0.08, 'energy': 0.08,
            'telecom': 0.05, 'defense': 0.05, 'ai': 0.05,
            'space': 0.03, 'resources': 0.04,
        }),
        'dynamic_additions': existing.get('dynamic_additions', []),
        'updated_at': datetime.now().isoformat(),
        'source': 'pool_builder.py (S&P 500 + Alpaca bars)',
        'sp500_count': len(new_universe),
        'total_count': len(merged),
    }

    # 备份
    os.makedirs(BACKUP_DIR, exist_ok=True)
    if os.path.exists(UNIVERSE_FILE):
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        import shutil
        shutil.copy2(UNIVERSE_FILE, os.path.join(BACKUP_DIR, f'scan_universe_{ts}.json'))

    with open(UNIVERSE_FILE, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    return output


def main():
    log.info('=== 动态池粗筛开始 ===')
    start_time = time.time()

    # 1. S&P 500 成分
    sp500 = fetch_sp500()
    symbols = [s for s, _ in sp500]

    # 2. 并发拉 bars（通过 config.py 加载 .env，不依赖环境变量）
    sys.path.insert(0, STOCK_TRADER)
    from eagle_eye.broker.alpaca_client import get_alpaca_client
    client = get_alpaca_client()

    # 验证 key 有效
    acc = client.get_account()
    if not acc:
        log.error('Alpaca API 不可用，跳过')
        sys.exit(1)
    log.info(f'Alpaca 账户: equity=${float(acc["equity"]):,.2f}')

    bars_data = fetch_bars_parallel(client, symbols)

    # 3. 筛选
    universe = filter_and_build(sp500, bars_data)
    if len(universe) < 50:
        log.error(f'结果过少 ({len(universe)})，跳过写入')
        sys.exit(1)

    # 4. 写入
    result = write_universe(universe)

    # 5. 汇总
    from collections import Counter
    sectors = Counter(universe.values())
    elapsed = time.time() - start_time
    log.info(f'=== 完成: S&P={result["sp500_count"]}, 总计={result["total_count"]}, 耗时={elapsed:.1f}s ===')
    for sec, cnt in sectors.most_common():
        log.info(f'  {sec}: {cnt}')

    # 输出摘要
    print(f'\n✅ 动态池更新完成')
    print(f'   S&P 500: {result["sp500_count"]} 只')
    print(f'   总池: {result["total_count"]} 只')
    print(f'   耗时: {elapsed:.1f}s')
    for sec, cnt in sectors.most_common():
        print(f'   {sec}: {cnt}')


if __name__ == '__main__':
    main()
