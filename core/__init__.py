"""
eagle_eye.core — 核心基础设施层

提供配置、日志、运行时、HTTP、缓存等基础服务。
所有其他模块依赖 core 层。
"""

from eagle_eye.core.config import cfg, Config
from eagle_eye.core.logger import get_logger, setup_logging, log_trade, log_signal, log_risk
from eagle_eye.core.runtime import runtime, Runtime
from eagle_eye.core.http import (
    http_get, http_post, http_patch, http_delete,
    alpaca_get, alpaca_post, alpaca_patch, alpaca_delete
)
from eagle_eye.core.cache import (
    MemoryCache, FileCache,
    earnings_cache, market_cache, memory_cache
)

__all__ = [
    # config
    'cfg', 'Config',
    # logger
    'get_logger', 'setup_logging', 'log_trade', 'log_signal', 'log_risk',
    # runtime
    'runtime', 'Runtime',
    # http
    'http_get', 'http_post', 'http_patch', 'http_delete',
    'alpaca_get', 'alpaca_post', 'alpaca_patch', 'alpaca_delete',
    # cache
    'MemoryCache', 'FileCache', 'earnings_cache', 'market_cache', 'memory_cache',
]
