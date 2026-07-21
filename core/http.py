"""
core/http.py — HTTP 客户端

统一的 HTTP 请求层，带重试、超时、代理支持。
替代 V6 中 us_common.py 的 url_get/url_post 和 us_trader.py 的 _url_get/_url_post/_url_del。

用法：
    from eagle_eye.core.http import http_get, http_post, http_delete
    code, body = http_get('https://api.example.com/data')
    code, body = http_post('https://api.example.com/order', payload={'symbol': 'AAPL'})

⚠️ 2026-07-09 修复：改用 requests 库替代 urllib.request
   urllib.request + socks5h:// ProxyHandler 不兼容（unknown url type: socks5h）
   requests + proxies={'https': 'socks5h://...'} 正常
"""

import json
import time
import subprocess
from typing import Tuple, Optional, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from eagle_eye.core.config import cfg
from eagle_eye.core.logger import get_logger

logger = get_logger('http')

# ─── curl 回退（Python SSL/TLS 在 Termux 上握手失败时使用）───


def _curl_request(method: str, url: str, headers: Optional[dict] = None,
                  data: Optional[bytes] = None,
                  timeout: Optional[int] = None) -> Tuple[int, str]:
    """curl 子进程回退 — Termux 上 Python requests/urllib TLS 握手失败的唯一可靠路径
    使用 shell=True 因为 Termux venv 下 subprocess list 模式 PATH 不完整"""
    import shlex
    cmd_parts = ['curl', '-s', '-w', "'\\n%{http_code}'", '-X', method,
                 '--max-time', str(timeout or 30)]
    for k, v in (headers or {}).items():
        cmd_parts.extend(['-H', shlex.quote(f'{k}: {v}')])
    if data:
        payload = data.decode() if isinstance(data, bytes) else data
        cmd_parts.extend(['-d', shlex.quote(payload)])
    cmd_parts.append(shlex.quote(url))
    cmd_str = ' '.join(cmd_parts)
    try:
        result = subprocess.run(cmd_str, shell=True, capture_output=True,
                                text=True, timeout=(timeout or 30) + 10)
        output = result.stdout
        if '\n' in output:
            body, code_str = output.rsplit('\n', 1)
            code = int(code_str.strip())
        else:
            body, code = output, 0
        return code, body
    except Exception as e:
        logger.warning(f'curl fallback failed for {method} {url}: {e}')
        return 0, ''


def _get_session(timeout: Optional[int] = None) -> requests.Session:
    """创建带重试和代理的 requests Session"""
    session = requests.Session()

    # 重试策略
    retry_strategy = Retry(
        total=cfg.http_max_retries if hasattr(cfg, 'http_max_retries') else 3,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount('https://', adapter)
    session.mount('http://', adapter)

    # 代理（中国网络必需 — SOCKS5 via mihomo）
    if cfg.proxy_enabled:
        proxy_url = f'socks5h://{cfg.proxy_host}:{cfg.proxy_port}'
        session.proxies = {
            'https': proxy_url,
            'http': proxy_url,
        }

    # 超时
    session.headers.update({'User-Agent': 'EagleEye/7.1'})
    return session


def http_get(url: str, headers: Optional[dict] = None,
             timeout: Optional[int] = None, retries: Optional[int] = None) -> Tuple[int, str]:
    """
    HTTP GET 请求

    Args:
        url: 请求 URL
        headers: 请求头
        timeout: 超时秒数（默认从配置读取）
        retries: 重试次数（默认从配置读取）

    Returns:
        (status_code, response_body) 元组
        失败时 status_code=0
    """
    if timeout is None:
        timeout = cfg.http_timeout_read if hasattr(cfg, 'http_timeout_read') else 30
    if retries is None:
        retries = cfg.http_max_retries if hasattr(cfg, 'http_max_retries') else 3

    session = _get_session(timeout=timeout)
    last_error = None

    for attempt in range(retries):
        try:
            r = session.get(url, headers=headers or {},
                            timeout=timeout)
            return r.status_code, r.text
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_error = str(e)
            logger.warning(f'Request error GET {url} (attempt {attempt + 1}/{retries}): {last_error[:120]}')
            # TLS/连接失败 → 直接回退到 urllib（不重试 requests）
            logger.info(f'Falling back to urllib.request for GET {url}')
            return _curl_request('GET', url, headers=headers, timeout=timeout)
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            logger.warning(f'Request error GET {url} (attempt {attempt + 1}/{retries}): {last_error}')
            if attempt < retries - 1:
                time.sleep(cfg.http_retry_delay * (attempt + 1) if hasattr(cfg, 'http_retry_delay') else 3)

    logger.error(f'GET {url} failed after {retries} attempts: {last_error}')
    # 最终回退
    return _curl_request('GET', url, headers=headers, timeout=timeout)


def http_post(url: str, payload: Optional[dict] = None,
              headers: Optional[dict] = None,
              timeout: Optional[int] = None, retries: Optional[int] = None) -> Tuple[int, str]:
    """HTTP POST 请求"""
    if timeout is None:
        timeout = cfg.http_timeout_write if hasattr(cfg, 'http_timeout_write') else 30
    if retries is None:
        retries = cfg.http_max_retries if hasattr(cfg, 'http_max_retries') else 3

    session = _get_session(timeout=timeout)
    last_error = None

    for attempt in range(retries):
        try:
            r = session.post(url, json=payload, headers=headers or {},
                             timeout=timeout)
            return r.status_code, r.text
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_error = str(e)
            logger.warning(f'Request error POST {url} (attempt {attempt + 1}/{retries}): {last_error[:120]}')
            body = json.dumps(payload).encode() if payload else None
            hdrs = dict(headers or {})
            hdrs['Content-Type'] = 'application/json'
            return _curl_request('POST', url, headers=hdrs, data=body, timeout=timeout)
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            logger.warning(f'Request error POST {url} (attempt {attempt + 1}/{retries}): {last_error}')
            if attempt < retries - 1:
                time.sleep(cfg.http_retry_delay * (attempt + 1) if hasattr(cfg, 'http_retry_delay') else 3)

    logger.error(f'POST {url} failed after {retries} attempts: {last_error}')
    body = json.dumps(payload).encode() if payload else None
    hdrs = dict(headers or {})
    hdrs['Content-Type'] = 'application/json'
    return _curl_request('POST', url, headers=hdrs, data=body, timeout=timeout)


def http_patch(url: str, payload: Optional[dict] = None,
               headers: Optional[dict] = None,
               timeout: Optional[int] = None, retries: Optional[int] = None) -> Tuple[int, str]:
    """HTTP PATCH 请求"""
    if timeout is None:
        timeout = cfg.http_timeout_write if hasattr(cfg, 'http_timeout_write') else 30
    if retries is None:
        retries = cfg.http_max_retries if hasattr(cfg, 'http_max_retries') else 3

    session = _get_session(timeout=timeout)
    last_error = None

    for attempt in range(retries):
        try:
            r = session.patch(url, json=payload, headers=headers or {},
                              timeout=timeout)
            return r.status_code, r.text
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_error = str(e)
            logger.warning(f'Request error PATCH {url} (attempt {attempt + 1}/{retries}): {last_error[:120]}')
            body = json.dumps(payload).encode() if payload else None
            hdrs = dict(headers or {})
            hdrs['Content-Type'] = 'application/json'
            return _curl_request('PATCH', url, headers=hdrs, data=body, timeout=timeout)
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            logger.warning(f'Request error PATCH {url} (attempt {attempt + 1}/{retries}): {last_error}')
            if attempt < retries - 1:
                time.sleep(cfg.http_retry_delay * (attempt + 1) if hasattr(cfg, 'http_retry_delay') else 3)

    logger.error(f'PATCH {url} failed after {retries} attempts: {last_error}')
    body = json.dumps(payload).encode() if payload else None
    hdrs = dict(headers or {})
    hdrs['Content-Type'] = 'application/json'
    return _curl_request('PATCH', url, headers=hdrs, data=body, timeout=timeout)


def http_delete(url: str, headers: Optional[dict] = None,
                timeout: Optional[int] = None, retries: Optional[int] = None) -> Tuple[int, str]:
    """HTTP DELETE 请求"""
    if timeout is None:
        timeout = cfg.http_timeout_read if hasattr(cfg, 'http_timeout_read') else 30
    if retries is None:
        retries = cfg.http_max_retries if hasattr(cfg, 'http_max_retries') else 3

    session = _get_session(timeout=timeout)
    last_error = None

    for attempt in range(retries):
        try:
            r = session.delete(url, headers=headers or {},
                               timeout=timeout)
            return r.status_code, r.text
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_error = str(e)
            logger.warning(f'Request error DELETE {url} (attempt {attempt + 1}/{retries}): {last_error[:120]}')
            return _curl_request('DELETE', url, headers=headers, timeout=timeout)
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            logger.warning(f'Request error DELETE {url} (attempt {attempt + 1}/{retries}): {last_error}')
            if attempt < retries - 1:
                time.sleep(cfg.http_retry_delay * (attempt + 1) if hasattr(cfg, 'http_retry_delay') else 3)

    logger.error(f'DELETE {url} failed after {retries} attempts: {last_error}')
    return _curl_request('DELETE', url, headers=headers, timeout=timeout)


# ─── Alpaca API 便捷函数 ───────────────────────────────

def alpaca_get(path: str, timeout: Optional[int] = None) -> Tuple[int, Any]:
    """Alpaca API GET 请求"""
    url = f'{cfg.alpaca_base_url}{path}'
    code, body = http_get(url, headers=cfg.alpaca_headers, timeout=timeout)
    try:
        return code, json.loads(body) if body else None
    except json.JSONDecodeError:
        return code, body


def alpaca_post(path: str, payload: dict, timeout: Optional[int] = None) -> Tuple[int, Any]:
    """Alpaca API POST 请求"""
    url = f'{cfg.alpaca_base_url}{path}'
    code, body = http_post(url, payload=payload, headers=cfg.alpaca_headers, timeout=timeout)
    try:
        return code, json.loads(body) if body else None
    except json.JSONDecodeError:
        return code, body


def alpaca_patch(path: str, payload: dict, timeout: Optional[int] = None) -> Tuple[int, Any]:
    """Alpaca API PATCH 请求"""
    url = f'{cfg.alpaca_base_url}{path}'
    code, body = http_patch(url, payload=payload, headers=cfg.alpaca_headers, timeout=timeout)
    try:
        return code, json.loads(body) if body else None
    except json.JSONDecodeError:
        return code, body


def alpaca_delete(path: str, timeout: Optional[int] = None) -> Tuple[int, Any]:
    """Alpaca API DELETE 请求"""
    url = f'{cfg.alpaca_base_url}{path}'
    code, body = http_delete(url, headers=cfg.alpaca_headers, timeout=timeout)
    try:
        return code, json.loads(body) if body else None
    except json.JSONDecodeError:
        return code, body
