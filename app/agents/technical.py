"""Technical indicators for the agent pipeline (pandas only, 通达信-style EMA/MACD)."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from app.services.futu_client import futu

log = logging.getLogger(__name__)

EMA_FAST = 12
EMA_SLOW = 26
DEA_PERIOD = 9
KLINE_NUM = 120
# Futu history kline: 30 requests / 30 seconds
HISTORY_KLINE_INTERVAL_SEC = 1.1

try:
    from futu import KLType, RET_OK
except ImportError:
    KLType = None  # type: ignore
    RET_OK = 0


def _normalize_kline_df(data: pd.DataFrame) -> pd.DataFrame:
    for col in ("close", "high", "low"):
        if col not in data.columns:
            return pd.DataFrame()
    sorted_df = (
        data.sort_values("time_key").reset_index(drop=True)
        if "time_key" in data.columns
        else data.reset_index(drop=True)
    )
    out = sorted_df[["close", "high", "low"]].copy()
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out["high"] = pd.to_numeric(out["high"], errors="coerce")
    out["low"] = pd.to_numeric(out["low"], errors="coerce")
    out = out.dropna()
    if out.empty:
        return pd.DataFrame()
    return out.reset_index(drop=True)


def get_klines(code: str, num: int = KLINE_NUM) -> pd.DataFrame:
    """Fetch daily K-lines via Futu request_history_kline (no subscription)."""
    if KLType is None:
        log.warning("get_klines %s: futu-api not installed", code)
        return pd.DataFrame()

    try:
        ret, data, _page_key = futu.request_history_kline(
            code,
            ktype=KLType.K_DAY,
            max_count=num,
        )
        if ret != RET_OK or data is None or data.empty:
            log.warning("request_history_kline failed %s: ret=%s data=%s", code, ret, data)
            return pd.DataFrame()
        return _normalize_kline_df(data)
    except Exception as e:
        log.warning("request_history_kline error %s: %s", code, e)
        return pd.DataFrame()


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


def rsi(close: pd.Series, period: int = 14) -> float | None:
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    last_loss = loss.iloc[-1]
    if pd.isna(last_loss) or last_loss == 0:
        return 100.0 if not pd.isna(gain.iloc[-1]) else None
    rs = gain.iloc[-1] / last_loss
    if pd.isna(rs):
        return None
    return float(100 - (100 / (1 + rs)))


def compute_indicators(klines: pd.DataFrame) -> dict[str, Any] | None:
    if klines is None or klines.empty or len(klines) < EMA_SLOW + DEA_PERIOD:
        return None

    close = klines["close"].reset_index(drop=True)
    high = klines["high"].reset_index(drop=True)
    low = klines["low"].reset_index(drop=True)
    price = float(close.iloc[-1])

    dif, dea, macd_hist = macd_series(close)
    rsi_val = rsi(close)
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
    rsi_v = ind.get("rsi")
    if rsi_v is not None:
        parts.append(f"RSI{rsi_v:.0f}")
    if ind.get("price_above_ma20"):
        parts.append("站上MA20")
    if ind.get("ma_bull_align"):
        parts.append("均线多头")
    dist = ind.get("dist_52w_high_pct")
    if dist is not None:
        parts.append(f"距52周高{dist:.1f}%")
    return "，".join(parts) if parts else "技术面数据不足"


def scan_candidates(
    market: str,
    codes: list[str],
    *,
    rate_limit_sec: float = 0,
) -> dict[str, dict[str, Any]]:
    """Fetch K-lines per futu code via Futu and compute indicators."""
    import time

    _ = market
    result: dict[str, dict[str, Any]] = {}
    for i, code in enumerate(codes):
        if i > 0 and rate_limit_sec > 0:
            time.sleep(rate_limit_sec)
        klines = get_klines(code, num=KLINE_NUM)
        if klines.empty:
            log.warning("technical scan skipped %s (empty kline DataFrame)", code)
            continue
        ind = compute_indicators(klines)
        if ind:
            ind["tech_view"] = summarize_tech_view(ind)
            result[code] = ind
        else:
            log.warning("technical scan skipped %s (insufficient bars)", code)
    return result
