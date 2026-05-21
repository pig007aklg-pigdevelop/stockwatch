"""统一实时报价 — 默认 yfinance, 可选 futu / akshare。"""
from __future__ import annotations

import logging
import math
import time
from datetime import datetime

from app.config import config
from app.services.ticker import normalize_symbol, to_yfinance_symbol

log = logging.getLogger(__name__)

_CACHE_TTL_SEC = 30
_snapshot_cache: tuple[float, str, dict[str, dict]] | None = None


def _parse_code(futu_code: str) -> tuple[str, str] | None:
    """US.BABA → (market, symbol)"""
    if not futu_code or "." not in futu_code:
        return None
    market, symbol = futu_code.split(".", 1)
    return market.upper(), normalize_symbol(market, symbol)


def _to_yf_symbol(futu_code: str) -> str | None:
    """US.BABA → BABA; HK.00700 → 0700.HK — 见 ticker.to_yfinance_symbol。"""
    parsed = _parse_code(futu_code)
    if not parsed:
        return None
    market, sym = parsed
    if market in ("US", "HK"):
        return to_yfinance_symbol(market, sym)
    return None


def _cache_key(codes: list[str]) -> str:
    return ",".join(sorted(codes))


def _quote_row(price: float, change_pct: float, volume: float) -> dict:
    return {
        "price": float(price),
        "change_pct": float(change_pct),
        "volume": float(volume),
        "ts": datetime.utcnow(),
    }


def _fi_get(fi, *keys: str, default: float | None = None) -> float | None:
    for key in keys:
        val = None
        if hasattr(fi, key):
            val = getattr(fi, key, None)
        elif isinstance(fi, dict):
            val = fi.get(key)
        else:
            try:
                val = fi[key]
            except (KeyError, TypeError, AttributeError):
                val = None
        if val is None:
            continue
        try:
            f = float(val)
            if math.isnan(f) or math.isinf(f):
                continue
            return f
        except (TypeError, ValueError):
            continue
    return default


def _quote_from_fast_info(fi) -> dict | None:
    price = _fi_get(fi, "lastPrice", "last_price")
    if not price or price <= 0:
        return None
    prev = _fi_get(
        fi,
        "regularMarketPreviousClose",
        "previousClose",
        "regular_market_previous_close",
    )
    if prev and prev > 0:
        change_pct = (price - prev) / prev * 100
    else:
        change_pct = 0.0
    volume = (
        _fi_get(fi, "lastVolume", "regularMarketVolume", "regular_market_volume")
        or 0.0
    )
    return _quote_row(price, change_pct, volume)


def _yfinance_snapshot(codes: list[str]) -> dict[str, dict]:
    global _snapshot_cache
    if not codes:
        return {}

    key = _cache_key(codes)
    now = time.monotonic()
    if (
        _snapshot_cache
        and _snapshot_cache[1] == key
        and now - _snapshot_cache[0] < _CACHE_TTL_SEC
    ):
        return _snapshot_cache[2]

    yf_symbols: list[str] = []
    code_by_yf: dict[str, str] = {}
    for code in codes:
        yf_sym = _to_yf_symbol(code)
        if not yf_sym:
            log.warning("quote fetch %s failed: invalid code format", code)
            continue
        code_by_yf[yf_sym] = code
        if yf_sym not in yf_symbols:
            yf_symbols.append(yf_sym)

    if not yf_symbols:
        return {}

    out: dict[str, dict] = {}
    try:
        import yfinance as yf

        tickers = yf.Tickers(" ".join(yf_symbols))
        for yf_sym, futu_code in code_by_yf.items():
            try:
                ticker = tickers.tickers.get(yf_sym)
                if ticker is None:
                    log.warning("quote fetch %s failed: yf symbol %s not found", futu_code, yf_sym)
                    continue
                row = _quote_from_fast_info(ticker.fast_info)
                if row:
                    out[futu_code] = row
                else:
                    log.warning("quote fetch %s failed: empty fast_info", futu_code)
            except Exception as e:
                log.warning("quote fetch %s failed: %s", futu_code, e)
    except Exception as e:
        log.warning("quote yfinance batch failed: %s", e)
        return {}

    _snapshot_cache = (now, key, out)
    return out


def _akshare_snapshot(codes: list[str]) -> dict[str, dict]:
    """备用: 东方财富 spot (部分网络环境不可用)。"""
    import pandas as pd

    if not codes:
        return {}

    def _safe_float(val, default: float = 0.0) -> float:
        try:
            v = float(val)
            if pd.isna(v):
                return default
            return v
        except (TypeError, ValueError):
            return default

    hk_map: dict[str, dict] = {}
    us_map: dict[str, dict] = {}
    try:
        import akshare as ak

        need_hk = any(_parse_code(c) and _parse_code(c)[0] == "HK" for c in codes)
        need_us = any(_parse_code(c) and _parse_code(c)[0] == "US" for c in codes)
        if need_hk:
            df = ak.stock_hk_spot_em()
            if df is not None and not df.empty and "代码" in df.columns:
                for _, row in df.iterrows():
                    sym = normalize_symbol("HK", str(row.get("代码", "")))
                    price = _safe_float(row.get("最新价"))
                    if sym and price > 0:
                        hk_map[sym] = _quote_row(
                            price,
                            _safe_float(row.get("涨跌幅")),
                            _safe_float(row.get("成交量")),
                        )
        if need_us:
            df = ak.stock_us_spot_em()
            if df is not None and not df.empty and "代码" in df.columns:
                for _, row in df.iterrows():
                    raw = str(row.get("代码", ""))
                    sym = raw.split(".", 1)[-1].upper() if raw else ""
                    price = _safe_float(row.get("最新价"))
                    if sym and price > 0:
                        us_map[sym] = _quote_row(
                            price,
                            _safe_float(row.get("涨跌幅")),
                            _safe_float(row.get("成交量")),
                        )
    except Exception as e:
        log.warning("quote akshare batch failed: %s", e)
        return {}

    out: dict[str, dict] = {}
    for code in codes:
        parsed = _parse_code(code)
        if not parsed:
            continue
        market, sym = parsed
        row = hk_map.get(sym) if market == "HK" else us_map.get(sym) if market == "US" else None
        if row:
            out[code] = row
    return out


def snapshot(codes: list[str]) -> dict[str, dict]:
    """
    输入: ["US.BABA", "HK.00700", ...]  (Position.futu_code 格式)
    输出: { "US.BABA": {"price", "change_pct", "volume", "ts"} }

    单只失败跳过; 批量失败返回 {}。
    """
    provider = config.QUOTE_PROVIDER
    if provider == "futu":
        from app.services.futu_client import futu

        raw = futu.get_snapshot(codes)
        ts = datetime.utcnow()
        for v in raw.values():
            v.setdefault("ts", ts)
        return raw
    if provider == "akshare":
        return _akshare_snapshot(codes)
    return _yfinance_snapshot(codes)


def clear_cache() -> None:
    """测试用: 清空模块缓存。"""
    global _snapshot_cache
    _snapshot_cache = None
