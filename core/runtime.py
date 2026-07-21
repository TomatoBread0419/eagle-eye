"""
core/runtime.py — 运行时层

管理路径解析、环境检测、系统信息。
替代 V6 中分散在各脚本的 SRC_DIR / SCRIPTS_DIR 硬编码路径。

用法：
    from eagle_eye.core.runtime import runtime
    print(runtime.data_path('us_watchlist.json'))
    print(runtime.script_path('us_trader.py'))
    print(runtime.is_market_open())
"""

import os
import sys
import platform
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

from eagle_eye.core.config import cfg
from eagle_eye.core.logger import get_logger

logger = get_logger('runtime')


class Runtime:
    """运行时环境管理"""

    def __init__(self):
        self._platform = self._detect_platform()
        logger.info(f'运行时初始化: platform={self._platform}, root={cfg.root_dir}')

    # ─── 平台检测 ───────────────────────────────────

    @property
    def platform(self) -> str:
        """当前平台: android / macos / windows / linux"""
        return self._platform

    @property
    def is_termux(self) -> bool:
        """是否在 Termux (Android) 环境"""
        return self._platform == 'android'

    @staticmethod
    def _detect_platform() -> str:
        """检测运行平台"""
        system = platform.system().lower()
        if system == 'linux':
            # 检测是否为 Android/Termux
            if os.path.exists('/data/data/com.termux') or 'TERMUX' in os.environ.get('PREFIX', ''):
                return 'android'
            return 'linux'
        elif system == 'darwin':
            return 'macos'
        elif system == 'windows':
            return 'windows'
        return system

    # ─── 路径解析 ───────────────────────────────────

    def data_path(self, *parts) -> Path:
        """
        数据目录下的路径

        替代: ~/stock_trader/xxx
        用法: runtime.data_path('us_watchlist.json')
        """
        return cfg.data_dir / '/'.join(parts)

    def log_path(self, *parts) -> Path:
        """
        日志目录下的路径

        用法: runtime.log_path('trader.log')
        """
        return cfg.log_dir / '/'.join(parts)

    def script_path(self, *parts) -> Path:
        """
        脚本目录下的路径（V6 兼容）

        替代: ~/.hermes/scripts/xxx
        用法: runtime.script_path('us_trader.py')
        """
        return cfg.root_dir / '.hermes' / 'scripts' / '/'.join(parts)

    def config_path(self, *parts) -> Path:
        """
        配置目录下的路径

        用法: runtime.config_path('ai_weight_config.json')
        """
        return cfg.root_dir / 'stock_trader' / '/'.join(parts)

    # ─── 市场时间 ───────────────────────────────────

    @staticmethod
    def get_market_timezone() -> timezone:
        """US 东部时区 (UTC-4 EDT / UTC-5 EST)"""
        # 简化处理：用 UTC-4 (EDT)，实际应根据夏令时调整
        return timezone(timedelta(hours=-4))

    @staticmethod
    def get_bjt_timezone() -> timezone:
        """北京时间 UTC+8"""
        return timezone(timedelta(hours=8))

    def now_utc(self) -> datetime:
        """当前 UTC 时间"""
        return datetime.now(timezone.utc)

    def now_bjt(self) -> datetime:
        """当前北京时间"""
        return datetime.now(self.get_bjt_timezone())

    def now_et(self) -> datetime:
        """当前美东时间"""
        return datetime.now(self.get_market_timezone())

    def is_market_open(self) -> bool:
        """
        判断美股是否开盘

        简化判断：美东 9:30-16:00，周一至周五
        不考虑节假日（应由外部日历管理）
        """
        et = self.now_et()
        # 周末不开盘
        if et.weekday() >= 5:
            return False
        # 交易时间 9:30 - 16:00
        market_open = et.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = et.replace(hour=16, minute=0, second=0, microsecond=0)
        return market_open <= et <= market_close

    def is_premarket(self) -> bool:
        """是否为盘前时间 (4:00-9:30 ET)"""
        et = self.now_et()
        if et.weekday() >= 5:
            return False
        pre_open = et.replace(hour=4, minute=0, second=0, microsecond=0)
        market_open = et.replace(hour=9, minute=30, second=0, microsecond=0)
        return pre_open <= et < market_open

    def is_afterhours(self) -> bool:
        """是否为盘后时间 (16:00-20:00 ET)"""
        et = self.now_et()
        if et.weekday() >= 5:
            return False
        market_close = et.replace(hour=16, minute=0, second=0, microsecond=0)
        after_close = et.replace(hour=20, minute=0, second=0, microsecond=0)
        return market_close < et <= after_close

    def market_status(self) -> str:
        """
        市场状态

        返回: 'open' / 'premarket' / 'afterhours' / 'closed'
        """
        if self.is_market_open():
            return 'open'
        elif self.is_premarket():
            return 'premarket'
        elif self.is_afterhours():
            return 'afterhours'
        return 'closed'

    # ─── 系统信息 ───────────────────────────────────

    def system_info(self) -> dict:
        """系统信息摘要"""
        return {
            'platform': self._platform,
            'python': sys.version.split()[0],
            'root': str(cfg.root_dir),
            'data': str(cfg.data_dir),
            'log': str(cfg.log_dir),
            'market_status': self.market_status(),
            'time_bjt': self.now_bjt().strftime('%Y-%m-%d %H:%M:%S'),
            'time_et': self.now_et().strftime('%Y-%m-%d %H:%M:%S'),
        }

    # ─── V6 兼容层 ─────────────────────────────────

    def v6_data_file(self, filename: str) -> Path:
        """
        V6 数据文件路径兼容

        V6 的数据文件在 ~/stock_trader/，V7 迁移后仍可访问。
        """
        return cfg.data_dir / filename

    def v6_script_file(self, filename: str) -> Path:
        """
        V6 脚本文件路径兼容

        V6 的脚本在 ~/.hermes/scripts/，V7 迁移后仍可访问。
        """
        return self.script_path(filename)


# 全局单例
runtime = Runtime()
