"""Technical indicators for the agent pipeline (pandas only, 通达信-style EMA/MACD)."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from app.services import market_data
from app.services.market_data import OhlcvBundle

log = logging.getLogger(__name__)

EMA_FAST = 12
EMA_SLOW = 26
DEA_PERIOD = 9


def ema_series(close: pd.Series, period: int) -> pd.Series:
    """
    EMA with SMA seed at bar `period` (1-based) / index `period-1` (0-based).
    Matches 通达信: first EMA(N) = mean(close[0:N]), then recursive α=2/(N+1).
    """
    n = len(close)
    if n < period:
        return pd.Series([np.nan] * n, index=close.index, dtype=float)

    alpha = 2.0 / (period + 1)
    out = np.full(n, np.nan, dtype=float)
    seed = float(close.iloc[:period].mean())
    out[period - 1] = seed
    prev = seed
    values = close.to_numpy(dtype=float, copy=False)
    for i in range(period, n):
        prev = alpha * values[i] + (1.0 - alpha) * prev
        out[i] = prev
    return pd.Series(out, index=close.index)


def macd_series(
    close: pd.Series,
    fast: int = EMA_FAST,
    slow: int = EMA_SLOW,
    signal: int = DEA_PERIOD,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """DIF, DEA (9-day EMA of DIF), MACD histogram = 2*(DIF-DEA)."""
    ema_fast = ema_series(close, fast)
    ema_slow = ema_series(close, slow)
    dif = ema_fast - ema_slow

    dea = pd.Series(np.nan, index=close.index, dtype=float)
    first_valid = dif.first_valid_index()
    if first_valid is not None:
        dif_tail = dif.loc[first_valid:].dropna()
        if len(dif_tail) >= signal:
            dea_tail = ema_series(dif_tail.reset_index(drop=True), signal)
            dea.loc[dif_tail.index] = dea_tail.values

    hist = 2.0 * (dif - dea)
    return dif, dea, hist


def _parse_futu_code(futu_code: str) -> tuple[str, str] | None:
    if "." not in futu_code:
        return None
    market, symbol = futu_code.split(".", 1)
    return market.upper(), symbol


def compute_indicators(bundle: OhlcvBundle | None) -> dict[str, Any] | None:
    if bundle is None or len(bundle.close) < EMA_SLOW + DEA_PERIOD:
        return None

    close = bundle.close.reset_index(drop=True)
    high = bundle.high.reset_index(drop=True)
    low = bundle.low.reset_index(drop=True)
    price = float(close.iloc[-1])

    dif, dea, macd_hist = macd_series(close)
    rsi_val = market_data.rsi(close)
    ma5 = float(close.rolling(5).mean().iloc[-1]) if len(close) >= 5 else None
    ma10 = float(close.rolling(10).mean().iloc[-1]) if len(close) >= 10 else None
    ma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None
    high_52w = float(high.tail(252).max()) if len(high) >= 20 else float(high.max())
    low_20d = float(close.tail(20).min()) if len(close) >= 20 else float(close.min())

    last_dif = _safe_float(dif.iloc[-1])
    last_dea = _safe_float(dea.iloc[-1])
    last_hist = _safe_float(macd_hist.iloc[-1])
    prev_hist = _safe_float(macd_hist.iloc[-2]) if len(macd_hist) >= 2 else None

    dist_52w_high_pct = (
        (high_52w - price) / high_52w * 100.0 if high_52w > 0 else None
    )

    return {
        "price": price,
        "dif": last_dif,
        "dea": last_dea,
        "macd_hist": last_hist,
        "macd_hist_prev": prev_hist,
        "rsi": rsi_val,
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "high_52w": high_52w,
        "low_20d": low_20d,
        "dist_52w_high_pct": dist_52w_high_pct,
        "macd_bullish": (
            last_dif is not None
            and last_dea is not None
            and last_dif > last_dea
        ),
        "price_above_ma20": (
            ma20 is not None and not np.isnan(ma20) and price > ma20
        ),
        "ma_bull_align": (
            ma5 is not None
            and ma10 is not None
            and ma20 is not None
            and ma5 > ma10 > ma20
        ),
    }


def _safe_float(v) -> float | None:
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        f = float(v)
        return None if np.isnan(f) or np.isinf(f) else f
    except (TypeError, ValueError):
        return None


def summarize_tech_view(ind: dict[str, Any]) -> str:
    parts: list[str] = []
    if ind.get("macd_bullish"):
        parts.append("MACD金叉(DIF>DEA)")
    else:
        parts.append("MACD偏弱")
    rsi = ind.get("rsi")
    if rsi is not None:
        parts.append(f"RSI{rsi:.0f}")
    if ind.get("price_above_ma20"):
        parts.append("站上MA20")
    if ind.get("ma_bull_align"):
        parts.append("均线多头")
    dist = ind.get("dist_52w_high_pct")
    if dist is not None:
        parts.append(f"距52周高{dist:.1f}%")
    return "，".join(parts) if parts else "技术面数据不足"


def scan_candidates(market: str, codes: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch OHLCV per futu code and compute indicators."""
    result: dict[str, dict[str, Any]] = {}
    mkt = (market or "hk").lower()
    for code in codes:
        parsed = _parse_futu_code(code)
        if not parsed:
            continue
        mkt_code, symbol = parsed
        bundle = market_data.fetch_ohlcv(mkt_code, symbol)
        ind = compute_indicators(bundle)
        if ind:
            ind["tech_view"] = summarize_tech_view(ind)
            result[code] = ind
        else:
            log.warning("technical scan skipped %s (insufficient bars)", code)
    return result
