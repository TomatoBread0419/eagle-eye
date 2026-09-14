"""
core/logger.py — 结构化日志

替代所有 print() 输出，统一日志格式。
支持文件输出（带轮转）和控制台输出。

用法：
    from eagle_eye.core.logger import get_logger
    logger = get_logger(__name__)
    logger.info("扫描完成", extra={'symbols': 87})
"""

import logging
import logging.handlers
import sys
from pathlib import Path

from eagle_eye.core.config import cfg


# 日志格式
_FORMAT = '%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s'
_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# 控制台格式（带颜色）
_COLORS = {
    'DEBUG': '\033[36m',     # 青色
    'INFO': '\033[32m',      # 绿色
    'WARNING': '\033[33m',   # 黄色
    'ERROR': '\033[31m',     # 红色
    'CRITICAL': '\033[35m',  # 紫色
}
_RESET = '\033[0m'


class ColorFormatter(logging.Formatter):
    """控制台带颜色的格式化器"""

    def format(self, record):
        color = _COLORS.get(record.levelname, '')
        record.levelname = f'{color}{record.levelname}{_RESET}'
        return super().format(record)


_initialized = False


def setup_logging():
    """
    初始化全局日志配置

    只执行一次，重复调用无副作用。
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    # 确保日志目录存在
    cfg.log_dir.mkdir(parents=True, exist_ok=True)

    # 根 logger
    root_logger = logging.getLogger('eagle_eye')
    root_logger.setLevel(getattr(logging, cfg.log_level.upper(), logging.INFO))

    # 清除已有 handler（防止重复）
    root_logger.handlers.clear()

    # ─── 控制台 handler ─────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = ColorFormatter(_FORMAT, _DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # ─── 文件 handler（带轮转）──────────────────────
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            str(cfg.log_file),
            maxBytes=cfg.log_max_bytes,
            backupCount=cfg.log_backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(_FORMAT, _DATE_FORMAT)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        root_logger.warning(f'无法创建日志文件 {cfg.log_file}: {e}')

    # ─── 第三方库日志级别 ───────────────────────────
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('yfinance').setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    获取模块日志器

    Args:
        name: 模块名（通常用 __name__）

    Returns:
        logging.Logger 实例
    """
    setup_logging()
    return logging.getLogger(f'eagle_eye.{name}')


# 便捷函数
def log_trade(action: str, symbol: str, qty: int, price: float, reason: str = ''):
    """记录交易日志"""
    logger = get_logger('trade')
    msg = f'{action} {symbol} x{qty} @ ${price:.2f}'
    if reason:
        msg += f' | {reason}'
    logger.info(msg)


def log_signal(signal_type: str, symbol: str, score: float, details: str = ''):
    """记录信号日志"""
    logger = get_logger('signal')
    msg = f'{signal_type} {symbol} score={score:.1f}'
    if details:
        msg += f' | {details}'
    logger.info(msg)


def log_risk(level: str, message: str):
    """记录风控日志"""
    logger = get_logger('risk')
    if level == 'CRITICAL':
        logger.critical(message)
    elif level == 'WARNING':
        logger.warning(message)
    else:
        logger.info(message)
