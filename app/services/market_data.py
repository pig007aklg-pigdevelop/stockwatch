"""yfinance 历史行情 + 估值/技术指标。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from app.services.external_call import API_CALL_TIMEOUT, call_with_timeout
from app.services.ticker import to_yfinance_symbol

log = logging.getLogger(__name__)


@dataclass
class OhlcvBundle:
    close: pd.Series
    high: pd.Series
    low: pd.Series
    pe_ttm: float | None = None
    pb: float | None = None


def fetch_ohlcv(market: str, symbol: str, years: int = 5) -> OhlcvBundle | None:
    yf_sym = to_yfinance_symbol(market, symbol)

    def _fetch() -> OhlcvBundle | None:
        import yfinance as yf

        t = yf.Ticker(yf_sym)
        hist = t.history(period=f"{years}y", auto_adjust=True)
        if hist is None or hist.empty or len(hist) < 30:
            return None
        info = {}
        try:
            info = t.info or {}
        except Exception:
            pass
        pe = _safe_float(info.get("trailingPE") or info.get("forwardPE"))
        pb = _safe_float(info.get("priceToBook"))
        return OhlcvBundle(
            close=hist["Close"],
            high=hist["High"],
            low=hist["Low"],
            pe_ttm=pe,
            pb=pb,
        )

    try:
        import yfinance  # noqa: F401
    except ImportError:
        log.warning("yfinance not installed")
        return None

    return call_with_timeout(_fetch, API_CALL_TIMEOUT)


def _safe_float(v) -> float | None:
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def percentile_rank(value: float, series: pd.Series) -> float | None:
    """当前值在序列中的百分位 0-100（越低越便宜）。"""
    s = series.dropna()
    if len(s) < 10 or value is None:
        return None
    return float((s <= value).mean() * 100)


def pe_pb_history_percentiles(bundle: OhlcvBundle) -> tuple[float | None, float | None]:
    """用收盘价与当前 PE/PB 估算历史分位（yfinance 无完整历史 PE 时用代理）。"""
    pe_pct = pb_pct = None
    if bundle.pe_ttm is not None and bundle.pe_ttm > 0:
        # 用价格相对 5 年区间作为估值代理分位
        pe_pct = percentile_rank(bundle.close.iloc[-1], bundle.close)
    if bundle.pb is not None and bundle.pb > 0:
        pb_pct = pe_pct
    return pe_pct, pb_pct


def rsi(close: pd.Series, period: int = 14) -> float | None:
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    last_loss = loss.iloc[-1]
    if last_loss == 0:
        return 100.0
    rs = gain.iloc[-1] / last_loss
    return float(100 - (100 / (1 + rs)))


def bollinger(close: pd.Series, window: int = 20, num_std: float = 2.0) -> tuple[float, float, float]:
    ma = close.rolling(window).mean()
    std = close.rolling(window).std()
    mid = float(ma.iloc[-1])
    lower = float((ma - num_std * std).iloc[-1])
    upper = float((ma + num_std * std).iloc[-1])
    return lower, mid, upper


def ma_alignment_score(close: pd.Series) -> float | None:
    if len(close) < 25:
        return None
    ma5 = close.rolling(5).mean().iloc[-1]
    ma10 = close.rolling(10).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    price = close.iloc[-1]
    score = 50.0
    if ma5 > ma10 > ma20:
        score += 30
    elif ma5 < ma10 < ma20:
        score -= 30
    if price > ma20:
        score += 10
    else:
        score -= 10
    return float(np.clip(score, 0, 100))


def technical_levels(bundle: OhlcvBundle) -> dict:
    close = bundle.close
    low_20 = float(close.tail(20).min()) if len(close) >= 20 else float(close.min())
    high_52w = float(bundle.high.tail(252).max()) if len(bundle.high) >= 20 else float(bundle.high.max())
    bb_lower, _, bb_upper = bollinger(close)
    r = rsi(close)
    ma_s = ma_alignment_score(close)
    price = float(close.iloc[-1])
    dist_low = (price - low_20) / low_20 * 100 if low_20 > 0 else 0
    dist_high = (high_52w - price) / high_52w * 100 if high_52w > 0 else 0
    return {
        "low_20d": low_20,
        "high_52w": high_52w,
        "bb_lower": bb_lower,
        "bb_upper": bb_upper,
        "rsi": r,
        "ma_score": ma_s,
        "price": price,
        "dist_from_20d_low_pct": dist_low,
        "dist_from_52w_high_pct": dist_high,
    }
