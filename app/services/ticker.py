"""Ticker 格式适配 — akshare(5位港股) / yfinance(0700.HK) / 富途(已有 futu_code)。"""
from __future__ import annotations


def normalize_symbol(market: str, symbol: str) -> str:
    """统一 symbol：去空格、大写；港股补零到 5 位。"""
    s = (symbol or "").strip().upper()
    if market == "HK":
        digits = "".join(c for c in s if c.isdigit())
        if digits:
            return digits.zfill(5)
    return s


def to_akshare_symbol(market: str, symbol: str) -> str | None:
    """akshare A/H 个股接口用 5 位港股代码；美股返回 None。"""
    if market == "US":
        return None
    if market in ("HK", "SH", "SZ"):
        return normalize_symbol(market, symbol)
    return None


def to_yfinance_symbol(market: str, symbol: str) -> str:
    sym = normalize_symbol(market, symbol)
    if market == "HK":
        digits = "".join(c for c in sym if c.isdigit())
        if not digits:
            return f"{sym}.HK"
        core = digits.lstrip("0") or "0"
        hk4 = core.zfill(4) if len(core) <= 4 else core[-4:]
        return f"{hk4}.HK"
    if market == "US":
        return sym
    if market == "SH":
        return f"{sym}.SS"
    if market == "SZ":
        return f"{sym}.SZ"
    return sym


def is_us_market(market: str) -> bool:
    return (market or "").upper() == "US"
