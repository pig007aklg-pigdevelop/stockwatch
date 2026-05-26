"""Index constituent lists via Futu OpenAPI."""
import logging
from typing import List

from app.services.futu_client import futu

log = logging.getLogger(__name__)

HK_TECH_FALLBACK: List[str] = [
    "HK.00700",  # 腾讯
    "HK.09988",  # 阿里
    "HK.03690",  # 美团
    "HK.01810",  # 小米
    "HK.01024",  # 快手
    "HK.09618",  # 京东
    "HK.09999",  # 网易
    "HK.02015",  # 理想
    "HK.09868",  # 小鹏
    "HK.09888",  # 百度
]

US_NASDAQ100_FALLBACK: List[str] = [
    "US.AAPL",
    "US.MSFT",
    "US.NVDA",
    "US.GOOGL",
    "US.META",
    "US.AMZN",
    "US.TSLA",
    "US.AVGO",
    "US.COST",
    "US.NFLX",
]


def _fetch_plate_codes(plate_code: str) -> List[str]:
    try:
        from futu import RET_OK
    except ImportError:
        log.warning("futu-api not installed; cannot fetch plate %s", plate_code)
        return []

    futu.connect()
    if futu.ctx is None:
        return []

    ret, data = futu.ctx.get_plate_stock(plate_code)
    if ret != RET_OK or data is None or data.empty:
        log.warning("get_plate_stock(%s) failed: %s", plate_code, data)
        return []

    if "code" not in data.columns:
        log.warning("get_plate_stock(%s) missing code column", plate_code)
        return []

    codes = [str(c).strip() for c in data["code"].tolist() if c]
    return codes


def get_hk_tech_constituents() -> List[str]:
    """恒生科技指数成分股，格式 HK.09988。"""
    try:
        codes = _fetch_plate_codes("HK.800700")
        if codes:
            return codes
    except Exception as e:
        log.warning("get_hk_tech_constituents failed: %s", e)
    log.info("using HK tech fallback list (%d symbols)", len(HK_TECH_FALLBACK))
    return list(HK_TECH_FALLBACK)


def get_us_nasdaq100_constituents() -> List[str]:
    """NASDAQ100 成分股，格式 US.AAPL。"""
    try:
        codes = _fetch_plate_codes("US..NDX")
        if codes:
            return codes
    except Exception as e:
        log.warning("get_us_nasdaq100_constituents failed: %s", e)
    log.info("using US NASDAQ100 fallback list (%d symbols)", len(US_NASDAQ100_FALLBACK))
    return list(US_NASDAQ100_FALLBACK)
