# 代码架构重构记录（2026-06-04）

## 重构前

```
stock_trader/         50+ .py 文件（大量扫描器迭代死代码）
us_trader.py          1113 行（含特朗普板块硬编码、重复指标函数）
us_screener.py         305 行（含特朗普板块硬编码、重复指标函数、days=120 bug）
stock-trading-system SKILL.md  巨型知识库（数千行，加载吃掉全部上下文）
Skills 库             41 个（含 10 个 creative skills 完全无关）
Cron jobs              9 个（含已暂停的 A 股、不需要的港股）
```

## 重构后

```
stock_trader/          8 核心 .py + 状态 JSON（88 死文件归档到 archives/）
us_trader.py          1027 行（-86 行，特朗普硬编码全删，共享 us_common.py）
us_screener.py         221 行（-84 行，特朗普硬编码全删，days=120→85）
us_common.py           122 行（新建：共享 calc_rsi/calc_sma/calc_boll/get_daily_bars/get_us_price）
market_news.py         新文件（多源新闻：Google RSS + 搜狗微信 fallback）
stock-trading-system   150 行行动指南 + 6 个参考索引文档
Skills 库             31 个
Cron jobs              7 个活跃 + 1 暂停（港股）
```

## 关键改动

1. **消除代码重复**：calc_rsi/calc_sma 原来在 3 个文件中各有一份，现统一到 us_common.py
2. **移除特朗普硬编码**：TRUMP_SECTOR_MAP、TRUMP_VISIT_SECTORS、SECTOR_BONUS 全部删除
3. **扫描池扩展**：UNIVERSE 57→70 只，新增 ARM/PLTR/SNOW/CRWD/NOW/PANW/UBER/DASH/SQ/SHOP/ZS/NET/DDOG
4. **实时 RSI 快检**：§6e 硬约束不再盲买 pool[0]，而是对 top 3 候选做实时 RSI 过滤
5. **新闻源冗余**：market_news.py 提供 Google RSS + 搜狗微信双源 fallback
6. **修复 days=120 bug**：us_screener.py 的 get_daily_bars 改用 85 天窗口
