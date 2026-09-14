"""
core/cache.py — 缓存管理器

提供文件缓存和内存缓存，支持 TTL 过期。
替代 V6 中分散的 JSON 文件缓存（earnings_cache.json 等）。

用法：
    from eagle_eye.core.cache import FileCache, MemoryCache

    # 文件缓存（持久化）
    cache = FileCache('earnings')
    cache.set('AAPL', {'date': '2026-07-20'}, ttl=86400)
    data = cache.get('AAPL')

    # 内存缓存（进程内）
    mem = MemoryCache(ttl=300)
    mem.set('key', 'value')
    val = mem.get('key')
"""

import json
import time
import threading
from pathlib import Path
from typing import Any, Optional

from eagle_eye.core.config import cfg
from eagle_eye.core.logger import get_logger

logger = get_logger('cache')


class MemoryCache:
    """
    内存缓存（线程安全）

    用于进程内的临时数据缓存。
    """

    def __init__(self, ttl: int = 300):
        """
        Args:
            ttl: 默认过期时间（秒）
        """
        self._store = {}
        self._ttl = ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值，过期返回 None"""
        with self._lock:
            if key not in self._store:
                return None
            value, expire_at = self._store[key]
            if expire_at and time.time() > expire_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None 使用默认
        """
        with self._lock:
            expire_at = time.time() + (ttl if ttl is not None else self._ttl)
            self._store[key] = (value, expire_at)

    def delete(self, key: str):
        """删除缓存项"""
        with self._lock:
            self._store.pop(key, None)

    def clear(self):
        """清空所有缓存"""
        with self._lock:
            self._store.clear()

    def cleanup(self):
        """清理过期项"""
        with self._lock:
            now = time.time()
            expired = [k for k, (_, exp) in self._store.items() if exp and now > exp]
            for k in expired:
                del self._store[k]
            if expired:
                logger.debug(f'清理 {len(expired)} 个过期缓存项')

    def size(self) -> int:
        """当前缓存项数"""
        with self._lock:
            return len(self._store)


class FileCache:
    """
    文件缓存（持久化到 JSON）

    用于需要跨进程共享的缓存数据。
    替代 V6 中的 earnings_cache.json 等。

    文件格式：
    {
        "key": {"value": ..., "expire_at": timestamp},
        ...
    }
    """

    def __init__(self, name: str, cache_dir: Optional[Path] = None):
        """
        Args:
            name: 缓存名称（用于文件名）
            cache_dir: 缓存目录（默认 data_dir/cache/）
        """
        if cache_dir is None:
            cache_dir = cfg.data_dir / 'cache'
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._path = cache_dir / f'{name}.json'
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict:
        """从文件加载缓存"""
        if self._path.exists():
            try:
                with open(self._path, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f'缓存文件加载失败 {self._path}: {e}')
        return {}

    def _save(self):
        """保存缓存到文件"""
        try:
            with open(self._path, 'w') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.error(f'缓存文件保存失败 {self._path}: {e}')

    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值

        Args:
            key: 缓存键

        Returns:
            缓存值，过期或不存在返回 None
        """
        with self._lock:
            if key not in self._data:
                return None
            entry = self._data[key]
            expire_at = entry.get('expire_at')
            if expire_at and time.time() > expire_at:
                del self._data[key]
                self._save()
                return None
            return entry.get('value')

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None=永不过期
        """
        with self._lock:
            expire_at = time.time() + ttl if ttl else None
            self._data[key] = {
                'value': value,
                'expire_at': expire_at,
                'updated_at': time.time(),
            }
            self._save()

    def delete(self, key: str):
        """删除缓存项"""
        with self._lock:
            if key in self._data:
                del self._data[key]
                self._save()

    def clear(self):
        """清空所有缓存"""
        with self._lock:
            self._data.clear()
            self._save()

    def cleanup(self):
        """清理过期项"""
        with self._lock:
            now = time.time()
            expired = [
                k for k, v in self._data.items()
                if v.get('expire_at') and now > v['expire_at']
            ]
            for k in expired:
                del self._data[k]
            if expired:
                self._save()
                logger.info(f'清理 {len(expired)} 个过期缓存项: {self._path.name}')

    def keys(self) -> list:
        """所有有效键"""
        with self._lock:
            now = time.time()
            return [
                k for k, v in self._data.items()
                if not v.get('expire_at') or now <= v['expire_at']
            ]

    def size(self) -> int:
        """当前缓存项数"""
        return len(self.keys())

    def has(self, key: str) -> bool:
        """检查键是否存在且未过期"""
        return self.get(key) is not None


# ─── 预定义缓存实例 ─────────────────────────────────

# 财报日期缓存（24h TTL）
earnings_cache = FileCache('earnings')

# 市场数据缓存（5min TTL）
market_cache = FileCache('market')

# 通用内存缓存
memory_cache = MemoryCache(ttl=300)
