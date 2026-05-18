"""富途 OpenAPI 封装

依赖:
    pip install futu-api
    并需在本机或同网络运行 FutuOpenD 网关 (端口11111默认)
"""
import logging
from typing import List, Dict, Optional
from app.config import config

log = logging.getLogger(__name__)

try:
    from futu import OpenQuoteContext, RET_OK, SubType
except ImportError:
    OpenQuoteContext = None
    RET_OK = 0
    SubType = None
    log.warning("futu-api not installed; FutuClient will be a no-op stub.")


class FutuClient:
    """富途行情客户端 - 单例使用"""
    def __init__(self):
        self.ctx: Optional["OpenQuoteContext"] = None

    def connect(self):
        if OpenQuoteContext is None:
            raise RuntimeError("futu-api not installed")
        if self.ctx is None:
            self.ctx = OpenQuoteContext(host=config.FUTU_HOST, port=config.FUTU_PORT)
            log.info(f"Connected to FutuOpenD at {config.FUTU_HOST}:{config.FUTU_PORT}")

    def close(self):
        if self.ctx:
            self.ctx.close()
            self.ctx = None

    def get_snapshot(self, futu_codes: List[str]) -> Dict[str, dict]:
        """
        获取实时快照
        :param futu_codes: ["US.NVDA", "HK.00700"]
        :return: {"US.NVDA": {"price": 135.2, "change_pct": 1.2, "volume": ...}}
        """
        if not futu_codes:
            return {}
        self.connect()
        ret, data = self.ctx.get_market_snapshot(futu_codes)
        if ret != RET_OK:
            log.error(f"get_market_snapshot failed: {data}")
            return {}

        result = {}
        for _, row in data.iterrows():
            code = row.get("code")
            result[code] = {
                "price": float(row.get("last_price", 0)),
                "change_pct": float(row.get("change_rate", 0)),  # 富途返回百分数
                "volume": float(row.get("volume", 0)),
                "name": row.get("name", ""),
                "prev_close": float(row.get("prev_close_price", 0)),
            }
        return result


# 单例
futu = FutuClient()
