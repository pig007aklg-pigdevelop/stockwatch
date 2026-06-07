"""富途 OpenAPI 封装

依赖:
    pip install futu-api
    并需在本机或同网络运行 FutuOpenD 网关 (端口11111默认)
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, TypeVar

from app.config import config

log = logging.getLogger(__name__)

try:
    from futu import OpenQuoteContext, RET_OK, SubType
except ImportError:
    OpenQuoteContext = None
    RET_OK = 0
    SubType = None
    log.warning("futu-api not installed; FutuClient will be a no-op stub.")

T = TypeVar("T")


class FutuClient:
    """富途行情客户端 - 单例使用"""

    def __init__(self):
        self.ctx: Optional["OpenQuoteContext"] = None

    def connect(self):
        if OpenQuoteContext is None:
            raise RuntimeError("futu-api not installed")
        if self.ctx is None:
            self.ctx = OpenQuoteContext(
                host=config.FUTU_HOST,
                port=config.FUTU_PORT,
                is_async_connect=False,
            )
            log.info("Connected to FutuOpenD at %s:%s", config.FUTU_HOST, config.FUTU_PORT)

    def close(self):
        if self.ctx:
            self.ctx.close()
            self.ctx = None

    def reconnect(self):
        self.close()
        self.connect()

    def _ctx(self) -> "OpenQuoteContext":
        self.connect()
        if self.ctx is None:
            raise RuntimeError("FutuOpenD context unavailable")
        return self.ctx

    def _request_with_retry(self, label: str, request: Callable[[], T]) -> T:
        try:
            return request()
        except Exception as e:
            log.warning("%s RPC error: %s; reconnecting and retrying once", label, e)
            self.reconnect()
            return request()

    def get_snapshot(self, futu_codes: List[str]) -> Dict[str, dict]:
        """
        获取实时快照
        :param futu_codes: ["US.NVDA", "HK.00700"]
        :return: {"US.NVDA": {"price": 135.2, "change_pct": 1.2, "volume": ...}}
        """
        if not futu_codes:
            return {}

        def _call():
            return self._ctx().get_market_snapshot(futu_codes)

        ret, data = self._request_with_retry("get_market_snapshot", _call)
        if ret != RET_OK:
            log.warning("get_market_snapshot failed: %s; reconnecting and retrying once", data)
            self.reconnect()
            ret, data = self._ctx().get_market_snapshot(futu_codes)
        if ret != RET_OK:
            log.error("get_market_snapshot failed after retry: %s", data)
            return {}

        result = {}
        for _, row in data.iterrows():
            code = row.get("code")
            result[code] = {
                "price": float(row.get("last_price", 0)),
                "change_pct": float(row.get("change_rate", 0)),
                "volume": float(row.get("volume", 0)),
                "name": row.get("name", ""),
                "prev_close": float(row.get("prev_close_price", 0)),
            }
        return result

    def get_plate_stock(self, plate_code: str) -> tuple[Any, Any]:
        def _call():
            return self._ctx().get_plate_stock(plate_code)

        ret, data = self._request_with_retry(f"get_plate_stock({plate_code})", _call)
        if ret != RET_OK:
            log.warning(
                "get_plate_stock(%s) failed: %s; reconnecting and retrying once",
                plate_code,
                data,
            )
            self.reconnect()
            ret, data = self._ctx().get_plate_stock(plate_code)
        return ret, data

    def request_history_kline(self, code: str, **kwargs) -> tuple[Any, Any, Any]:
        def _call():
            return self._ctx().request_history_kline(code, **kwargs)

        ret, data, page_key = self._request_with_retry(
            f"request_history_kline({code})",
            _call,
        )
        if ret != RET_OK:
            log.warning(
                "request_history_kline(%s) failed: %s; reconnecting and retrying once",
                code,
                data,
            )
            self.reconnect()
            ret, data, page_key = self._ctx().request_history_kline(code, **kwargs)
        return ret, data, page_key


# 单例
futu = FutuClient()
