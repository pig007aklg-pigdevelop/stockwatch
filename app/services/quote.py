"""统一实时报价 — 默认 akshare, 可选 futu。"""
from __future__ import annotations

import logging
import time
from datetime import datetime

import pandas as pd

from app.config import config
from app.services.ticker import normalize_symbol

log = logging.getLogger(__name__)

_CACHE_TTL_SEC = 30
_hk_map_cache: tuple[float, dict[str, dict]] | None = None
_us_map_cache: tuple[float, dict[str, dict]] | None = None


def _parse_code(futu_code: str) -> tuple[str, str] | None:
    """US.BABA → (market, symbol)"""
    if not futu_code or "." not in futu_code:
        return None
    market, symbol = futu_code.split(".", 1)
    return market.upper(), normalize_symbol(market, symbol)


def _quote_row(price: float, change_pct: float, volume: float) -> dict:
    return {
        "price": float(price),
        "change_pct": float(change_pct),
        "volume": float(volume),
        "ts": datetime.utcnow(),
    }


def _safe_float(val, default: float = 0.0) -> float:
    try:
        v = float(val)
        if pd.isna(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def _load_hk_map() -> dict[str, dict]:
    """symbol(5位) → quote dict"""
    global _hk_map_cache
    now = time.monotonic()
    if _hk_map_cache and now - _hk_map_cache[0] < _CACHE_TTL_SEC:
        return _hk_map_cache[1]

    result: dict[str, dict] = {}
    try:
        import akshare as ak

        df = ak.stock_hk_spot_em()
        if df is not None and not df.empty and "代码" in df.columns:
            for _, row in df.iterrows():
                sym = normalize_symbol("HK", str(row.get("代码", "")))
                if not sym:
                    continue
                price = _safe_float(row.get("最新价"))
                if price <= 0:
                    continue
                result[sym] = _quote_row(
                    price,
                    _safe_float(row.get("涨跌幅")),
                    _safe_float(row.get("成交量")),
                )
    except Exception as e:
        log.warning("quote fetch HK spot failed: %s", e)
        return {}

    _hk_map_cache = (now, result)
    return result


def _load_us_map() -> dict[str, dict]:
    """symbol → quote dict (从 105.AAPL 解析 ticker)"""
    global _us_map_cache
    now = time.monotonic()
    if _us_map_cache and now - _us_map_cache[0] < _CACHE_TTL_SEC:
        return _us_map_cache[1]

    result: dict[str, dict] = {}
    try:
        import akshare as ak

        df = ak.stock_us_spot_em()
        if df is not None and not df.empty and "代码" in df.columns:
            for _, row in df.iterrows():
                raw_code = str(row.get("代码", ""))
                sym = raw_code.split(".", 1)[-1].upper() if raw_code else ""
                if not sym:
                    continue
                price = _safe_float(row.get("最新价"))
                if price <= 0:
                    continue
                result[sym] = _quote_row(
                    price,
                    _safe_float(row.get("涨跌幅")),
                    _safe_float(row.get("成交量")),
                )
    except Exception as e:
        log.warning("quote fetch US spot failed: %s", e)
        return {}

    _us_map_cache = (now, result)
    return result


def _akshare_snapshot(codes: list[str]) -> dict[str, dict]:
    if not codes:
        return {}

    need_hk = any(_parse_code(c) and _parse_code(c)[0] == "HK" for c in codes)
    need_us = any(_parse_code(c) and _parse_code(c)[0] == "US" for c in codes)

    hk_map = _load_hk_map() if need_hk else {}
    us_map = _load_us_map() if need_us else {}

    out: dict[str, dict] = {}
    for code in codes:
        parsed = _parse_code(code)
        if not parsed:
            log.warning("quote fetch %s failed: invalid code format", code)
            continue
        market, sym = parsed
        try:
            if market == "HK":
                row = hk_map.get(sym)
            elif market == "US":
                row = us_map.get(sym)
            else:
                log.warning("quote fetch %s failed: unsupported market", code)
                continue
            if row:
                out[code] = row
            else:
                log.warning("quote fetch %s failed: symbol not in spot table", code)
        except Exception as e:
            log.warning("quote fetch %s failed: %s", code, e)

    return out


def snapshot(codes: list[str]) -> dict[str, dict]:
    """
    输入: ["US.BABA", "HK.00700", ...]  (Position.futu_code 格式)
    输出: { "US.BABA": {"price": 110.2, "change_pct": 1.5, "volume": ..., "ts": datetime} }

    单只失败跳过; 整体拉取失败返回 {}。
    """
    if config.QUOTE_PROVIDER == "futu":
        from app.services.futu_client import futu

        raw = futu.get_snapshot(codes)
        ts = datetime.utcnow()
        for v in raw.values():
            v.setdefault("ts", ts)
        return raw
    return _akshare_snapshot(codes)


def clear_cache() -> None:
    """测试用: 清空模块缓存。"""
    global _hk_map_cache, _us_map_cache
    _hk_map_cache = None
    _us_map_cache = None
