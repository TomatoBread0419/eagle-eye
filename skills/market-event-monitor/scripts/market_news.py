#!/usr/bin/env python3
"""
market_news.py — 多源市场新闻搜索（Google RSS + 搜狗微信 fallback）
用于 market-event-monitor 和 cron 任务。

用法:
    from market_news import search_market_news
    results, source, err = search_market_news("Federal Reserve Warsh rate June 2026")
"""

import urllib.request
import urllib.parse
import re
import time


def search_google_rss(keyword, max_results=5, timeout=12):
    """
    Google News RSS（主源，英文全球财经新闻）。
    墙内可用但偶尔超时。
    返回: (results, error_string_or_None)
    """
    url = (f"https://news.google.com/rss/search?"
           f"q={urllib.parse.quote(keyword)}&hl=en-US&gl=US&ceid=US:en")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            rss = resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        return [], f"Google RSS error: {e}"

    items = re.findall(
        r'<item>.*?<title>(.*?)</title>.*?<source[^>]*>(.*?)</source>'
        r'.*?<pubDate>(.*?)</pubDate>.*?</item>',
        rss, re.DOTALL,
    )
    results = []
    for title, source, date in items[:max_results]:
        title = re.sub(r'<[^>]+>', '', title).strip()
        source = re.sub(r'<[^>]+>', '', source).strip()
        if source and title.endswith(f' - {source}'):
            title = title[:-(len(source) + 3)]
        results.append({
            'title': title, 'source': source, 'date': date, 'lang': 'en',
        })
    return results, None


def search_sogou_weixin(keyword, max_results=5, timeout=10):
    """
    搜狗微信搜索（备用源，中文深度内容）。
    墙内可用，稳定。不需要登录。
    返回: (results, error_string_or_None)
    """
    url = (f"https://weixin.sogou.com/weixin?"
           f"type=2&query={urllib.parse.quote(keyword)}")
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Linux; Android 13; Pixel 7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 '
            'Mobile Safari/537.36'
        ),
    }
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        return [], f"Sogou Weixin error: {e}"

    items = re.findall(
        r'<h3>.*?<a[^>]*?href="([^"]*)"[^>]*?>(.*?)</a>.*?</h3>.*?'
        r'<p class="txt-info"[^>]*?>(.*?)</p>',
        html, re.DOTALL,
    )

    results = []
    for url, title, snippet in items[:max_results]:
        title = re.sub(r'<[^>]+>', '', title).strip()
        title = (title.replace('&amp;', '&').replace('&lt;', '<')
                 .replace('&gt;', '>').replace('&quot;', '"')
                 .replace('&#39;', "'"))
        snippet = re.sub(r'<[^>]+>', '', snippet).strip()
        snippet = (snippet.replace('&amp;', '&').replace('&lt;', '<')
                   .replace('&gt;', '>'))

        results.append({
            'title': title,
            'source': '搜狗微信',
            'date': '',
            'snippet': snippet[:200],
            'lang': 'zh',
        })
    return results, None


def search_market_news(keyword, max_results=5):
    """
    多源市场新闻搜索：先 Google RSS，失败则 fallback 到搜狗微信。

    返回: (results, source_used, error)
      results: list of dicts with title/source/date/(snippet)/(lang)
      source_used: 'google_rss' | 'sogou_weixin' | 'none'
      error: None on success, error string if both sources failed
    """
    # 主源：Google News RSS
    results, err = search_google_rss(keyword, max_results)
    if results:
        return results, 'google_rss', None

    # 备用源：搜狗微信
    results2, err2 = search_sogou_weixin(keyword, max_results)
    if results2:
        return results2, 'sogou_weixin', None

    # 全部失败
    return [], 'none', f"Google: {err}; Sogou: {err2}"
