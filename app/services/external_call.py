"""外部接口调用 — 单调用超时保护。"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Callable, TypeVar

log = logging.getLogger(__name__)

API_CALL_TIMEOUT = 10.0
SCORE_POSITION_TIMEOUT = 30.0
INTER_STOCK_SLEEP = 0.3

T = TypeVar("T")


def call_with_timeout(
    func: Callable[..., T],
    timeout: float,
    *args: Any,
    default: T | None = None,
    **kwargs: Any,
) -> T | None:
    """在独立线程中执行 func，超时或异常时 log warning 并返回 default。"""
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(func, *args, **kwargs)
        try:
            return fut.result(timeout=timeout)
        except FuturesTimeoutError:
            log.warning("Call timeout after %.0fs: %s", timeout, getattr(func, "__name__", func))
            return default
        except Exception as e:
            log.warning("Call failed %s: %s", getattr(func, "__name__", func), e)
            return default
