"""
core/config.py — 集中配置管理器（V2 分层结构）

单一真相来源：~/eagle_eye/.env
所有配置通过 cfg 单例访问，按逻辑分组：

    cfg.alpaca.api_key      # Alpaca 凭证
    cfg.alpaca.secret_key
    cfg.alpaca.base_url

    cfg.proxy.enabled       # 代理设置
    cfg.proxy.host

    cfg.risk.max_single     # 风控参数
    cfg.risk.drawdown_pause

    cfg.pool.min_price      # 扫描器/池子参数

向后兼容：cfg.alpaca_api_key 仍然可用（deprecated，逐步迁移）

用法：
    from eagle_eye.core.config import cfg
    print(cfg.alpaca.api_key)
    print(cfg.risk.max_single)
"""

import os
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional


# ═══════════════════════════════════════════════════════════════
# .env 加载（零依赖，纯标准库）
# ═══════════════════════════════════════════════════════════════

def _find_project_root() -> Path:
    """查找项目根目录（eagle_eye/ 的父目录）"""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / 'eagle_eye').is_dir() and (current / 'eagle_eye' / '__init__.py').exists():
            return current
        current = current.parent
    return Path.home()


def _load_env_file(env_path: Path) -> dict:
    """加载 .env 文件为 dict（不依赖 python-dotenv）"""
    env = {}
    if not env_path.exists():
        return env
    try:
        if env_path.is_symlink():
            env_path = env_path.resolve()
    except Exception:
        pass
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                env[key] = value
    return env


# ═══════════════════════════════════════════════════════════════
# 分层 Bean
# ═══════════════════════════════════════════════════════════════

class _Alpaca(SimpleNamespace):
    """Alpaca API 凭证和端点"""
    def __init__(self, get):
        super().__init__(
            api_key=get('ALPACA_API_KEY', ''),
            secret_key=get('ALPACA_SECRET_KEY', ''),
            base_url=get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets'),
            data_url=get('ALPACA_DATA_URL', 'https://data.alpaca.markets/v2/stocks'),
        )

    @property
    def headers(self) -> dict:
        return {
            'APCA-API-KEY-ID': self.api_key,
            'APCA-API-SECRET-KEY': self.secret_key,
            'Content-Type': 'application/json',
        }

    def __repr__(self):
        k = self.api_key[:4] + '...' if self.api_key else 'not_set'
        s = '***' if self.secret_key else 'not_set'
        return f'_Alpaca(api_key={k}, secret_key={s}, base_url={self.base_url})'


class _Proxy(SimpleNamespace):
    """SOCKS5 代理设置"""
    def __init__(self, get):
        super().__init__(
            enabled=get('EAGLE_PROXY_ENABLED', 'false').lower() in ('true', '1', 'yes'),
            host=get('EAGLE_PROXY_HOST', '127.0.0.1'),
            port=int(get('EAGLE_PROXY_PORT', '7891')),
        )


class _Risk(SimpleNamespace):
    """风控参数"""
    def __init__(self, get):
        super().__init__(
            target_allocation=float(get('EAGLE_TARGET_ALLOCATION', '0.85')),
            max_single=float(get('EAGLE_MAX_SINGLE_POSITION', '0.20')),
            min_single=float(get('EAGLE_MIN_SINGLE_POSITION', '0.03')),
            drawdown_pause=float(get('EAGLE_DRAWDOWN_PAUSE', '0.12')),
            drawdown_reduce=float(get('EAGLE_DRAWDOWN_REDUCE', '0.20')),
            low_util_force_market=float(get('EAGLE_LOW_UTIL_FORCE_MARKET', '0.30')),
        )


class _HTTP(SimpleNamespace):
    """HTTP 客户端参数"""
    def __init__(self, get):
        super().__init__(
            timeout_read=int(get('EAGLE_HTTP_TIMEOUT_READ', '30')),
            timeout_write=int(get('EAGLE_HTTP_TIMEOUT_WRITE', '10')),
            max_retries=int(get('EAGLE_HTTP_MAX_RETRIES', '3')),
            retry_delay=float(get('EAGLE_HTTP_RETRY_DELAY', '3')),
        )


class _Pool(SimpleNamespace):
    """扫描器/动态池参数"""
    def __init__(self, get):
        super().__init__(
            min_price=float(get('EAGLE_POOL_MIN_PRICE', '10.0')),
            min_avg_volume=float(get('EAGLE_POOL_MIN_AVG_VOLUME', '5000000')),
            target_min=int(get('EAGLE_POOL_TARGET_MIN', '200')),
            target_max=int(get('EAGLE_POOL_TARGET_MAX', '300')),
            workers=int(get('EAGLE_POOL_WORKERS', '4')),
            batch_sleep=float(get('EAGLE_POOL_BATCH_SLEEP', '0.2')),
        )


class _Log(SimpleNamespace):
    """日志配置"""
    def __init__(self, get):
        super().__init__(
            level=get('EAGLE_LOG_LEVEL', 'INFO'),
            max_bytes=int(get('EAGLE_LOG_MAX_BYTES', str(10 * 1024 * 1024))),
            backup_count=int(get('EAGLE_LOG_BACKUP_COUNT', '5')),
        )


class _Notify(SimpleNamespace):
    """通知渠道凭证"""
    def __init__(self, get):
        super().__init__(
            bark_key=get('BARK_KEY', ''),
            pushplus_token=get('PUSHPLUS_TOKEN', ''),
            telegram_bot_token=get('TELEGRAM_BOT_TOKEN', ''),
            telegram_chat_id=get('TELEGRAM_CHAT_ID', ''),
        )


# ═══════════════════════════════════════════════════════════════
# 主配置类
# ═══════════════════════════════════════════════════════════════

class Config:
    """
    集中配置管理器

    优先级：.env 文件 > 环境变量 > 默认值

    分组访问：
        cfg.alpaca.api_key
        cfg.risk.max_single
        cfg.pool.min_price
        cfg.proxy.enabled
        cfg.http.max_retries
        cfg.log.level
        cfg.notify.bark_key

    向后兼容（deprecated）：
        cfg.alpaca_api_key  → cfg.alpaca.api_key
    """

    def __init__(self):
        self._root = _find_project_root()
        self._env_file = self._root / '.env'
        self._env_data = _load_env_file(self._env_file)
        self._weight_config = None

        # ── 初始化分组 Bean ──
        self.alpaca = _Alpaca(self._get)
        self.proxy = _Proxy(self._get)
        self.risk = _Risk(self._get)
        self.http = _HTTP(self._get)
        self.pool = _Pool(self._get)
        self.log = _Log(self._get)
        self.notify = _Notify(self._get)

    # ── 路径（保持 property，因为涉及 Path 对象）──

    @property
    def root_dir(self) -> Path:
        return self._root

    @property
    def eagle_dir(self) -> Path:
        return self._root / 'eagle_eye'

    @property
    def data_dir(self) -> Path:
        d = self._get('EAGLE_DATA_DIR', str(self._root / 'stock_trader'))
        return Path(d)

    @property
    def log_dir(self) -> Path:
        d = self._get('EAGLE_LOG_DIR', str(self._root / 'eagle_eye' / 'logs'))
        return Path(d)

    @property
    def db_path(self) -> Path:
        return self.data_dir / 'eagle_eye.db'

    @property
    def env_file(self) -> Path:
        return self._env_file

    @property
    def weight_config_path(self) -> Path:
        return self.data_dir / 'ai_weight_config.json'

    @property
    def log_file(self) -> Path:
        return self.log_dir / 'eagle_eye.log'

    # ── 权重配置 ──

    def load_weight_config(self) -> dict:
        if self._weight_config is None:
            path = self.weight_config_path
            if path.exists():
                with open(path, 'r') as f:
                    self._weight_config = json.load(f)
            else:
                self._weight_config = {}
        return self._weight_config

    def save_weight_config(self, config: dict):
        self._weight_config = config
        path = self.weight_config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    # ── 向后兼容属性（deprecated，指向新 Bean）──

    @property
    def alpaca_api_key(self) -> str:
        return self.alpaca.api_key

    @property
    def alpaca_secret_key(self) -> str:
        return self.alpaca.secret_key

    @property
    def alpaca_base_url(self) -> str:
        return self.alpaca.base_url

    @property
    def alpaca_data_url(self) -> str:
        return self.alpaca.data_url

    @property
    def alpaca_headers(self) -> dict:
        return self.alpaca.headers

    @property
    def proxy_enabled(self) -> bool:
        return self.proxy.enabled

    @property
    def proxy_host(self) -> str:
        return self.proxy.host

    @property
    def proxy_port(self) -> int:
        return self.proxy.port

    @property
    def target_allocation(self) -> float:
        return self.risk.target_allocation

    @property
    def max_single_position(self) -> float:
        return self.risk.max_single

    @property
    def min_single_position(self) -> float:
        return self.risk.min_single

    @property
    def drawdown_pause_threshold(self) -> float:
        return self.risk.drawdown_pause

    @property
    def drawdown_reduce_threshold(self) -> float:
        return self.risk.drawdown_reduce

    @property
    def low_util_force_market(self) -> float:
        return self.risk.low_util_force_market

    @property
    def http_timeout_read(self) -> int:
        return self.http.timeout_read

    @property
    def http_timeout_write(self) -> int:
        return self.http.timeout_write

    @property
    def http_max_retries(self) -> int:
        return self.http.max_retries

    @property
    def http_retry_delay(self) -> float:
        return self.http.retry_delay

    @property
    def log_level(self) -> str:
        return self.log.level

    @property
    def log_max_bytes(self) -> int:
        return self.log.max_bytes

    @property
    def log_backup_count(self) -> int:
        return self.log.backup_count

    @property
    def bark_key(self) -> str:
        return self.notify.bark_key

    @property
    def pushplus_token(self) -> str:
        return self.notify.pushplus_token

    @property
    def telegram_bot_token(self) -> str:
        return self.notify.telegram_bot_token

    @property
    def telegram_chat_id(self) -> str:
        return self.notify.telegram_chat_id

    # ── 通用方法 ──

    def _get(self, key: str, default: str = '') -> str:
        """优先级：.env 文件 > 环境变量 > 默认值"""
        env_val = self._env_data.get(key)
        if env_val is not None:
            return env_val
        return os.environ.get(key, default)

    def get(self, key: str, default: Any = None) -> Any:
        val = self._get(key)
        if val:
            return val
        return default

    def ensure_dirs(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def validate(self) -> list:
        issues = []
        if not self.alpaca.api_key:
            issues.append('WARNING: ALPACA_API_KEY 未设置')
        if not self.alpaca.secret_key:
            issues.append('WARNING: ALPACA_SECRET_KEY 未设置')
        if not self.data_dir.exists():
            issues.append(f'WARNING: 数据目录不存在: {self.data_dir}')
        return issues

    def __repr__(self):
        return f'Config(root={self._root}, data={self.data_dir}, alpaca_configured={bool(self.alpaca.api_key)})'


# ── 全局单例 ──
cfg = Config()
