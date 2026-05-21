"""yfinance / akshare 历史行情 + 估值/技术指标。"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.services.external_call import API_CALL_TIMEOUT, call_with_timeout
from app.services.ticker import normalize_symbol, to_yfinance_symbol

log = logging.getLogger(__name__)


@dataclass
class OhlcvBundle:
    close: pd.Series
    high: pd.Series
    low: pd.Series
    pe_ttm: float | None = None
    pb: float | None = None


def _series_from_df(df: pd.DataFrame, col_candidates: list[str]) -> pd.Series | None:
    col = None
    for c in col_candidates:
        if c in df.columns:
            col = c
            break
    if col is None:
        return None
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    return s if len(s) > 0 else None


def _bundle_from_frames(close: pd.Series, high: pd.Series, low: pd.Series) -> OhlcvBundle | None:
    if close is None or high is None or low is None:
        return None
    if len(close) < 30:
        return None
    close = close.reset_index(drop=True)
    high = high.reset_index(drop=True)
    low = low.reset_index(drop=True)
    return OhlcvBundle(close=close, high=high, low=low)


def _fetch_yfinance_single(yf_sym: str, years: int = 5) -> OhlcvBundle | None:
    def _fetch() -> OhlcvBundle | None:
        import yfinance as yf

        t = yf.Ticker(yf_sym)
        hist = t.history(period=f"{years}y", auto_adjust=True)
        if hist is None or hist.empty or len(hist) < 30:
            return None
        if "Close" not in hist.columns:
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

    return call_with_timeout(_fetch, API_CALL_TIMEOUT)


def _fetch_akshare_hk(symbol: str) -> OhlcvBundle | None:
    code = normalize_symbol("HK", symbol)

    def _fetch() -> OhlcvBundle | None:
        import akshare as ak

        df = ak.stock_hk_hist(symbol=code, period="daily", adjust="qfq")
        if df is None or df.empty:
            return None
        close = _series_from_df(df, ["收盘", "close", "Close"])
        high = _series_from_df(df, ["最高", "high", "High"])
        low = _series_from_df(df, ["最低", "low", "Low"])
        return _bundle_from_frames(close, high, low)

    try:
        bundle = call_with_timeout(_fetch, API_CALL_TIMEOUT)
        if bundle:
            log.info("fetch_ohlcv HK %s via akshare (%d bars)", code, len(bundle.close))
        return bundle
    except Exception as e:
        log.warning("fetch_akshare_hk %s: %s", code, e)
        return None


def fetch_ohlcv(market: str, symbol: str, years: int = 5) -> OhlcvBundle | None:
    mkt = (market or "").upper()

    try:
        import yfinance  # noqa: F401
    except ImportError:
        yfinance_ok = False
    else:
        yfinance_ok = True

    if mkt == "HK":
        if yfinance_ok:
            yf_sym = to_yfinance_symbol("HK", symbol)
            bundle = _fetch_yfinance_single(yf_sym, years)
            if bundle:
                return bundle
            log.warning("yfinance HK empty for %s (%s), fallback akshare", symbol, yf_sym)
        return _fetch_akshare_hk(symbol)

    if not yfinance_ok:
        log.warning("yfinance not installed")
        return None

    yf_sym = to_yfinance_symbol(market, symbol)
    return _fetch_yfinance_single(yf_sym, years)


def _safe_float(v) -> float | None:
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        f = float(v)
        return None if np.isnan(f) or np.isinf(f) else f
    except (TypeError, ValueError):
        return None


def percentile_rank(value: float, series: pd.Series) -> float | None:
    s = series.dropna()
    if len(s) < 10 or value is None:
        return None
    return float((s <= value).mean() * 100)


def pe_pb_history_percentiles(bundle: OhlcvBundle) -> tuple[float | None, float | None]:
    pe_pct = pb_pct = None
    if bundle.pe_ttm is not None and bundle.pe_ttm > 0:
        pe_pct = percentile_rank(float(bundle.close.iloc[-1]), bundle.close)
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
    if pd.isna(last_loss) or last_loss == 0:
        return 100.0 if not pd.isna(gain.iloc[-1]) else None
    rs = gain.iloc[-1] / last_loss
    if pd.isna(rs):
        return None
    return float(100 - (100 / (1 + rs)))


def bollinger(close: pd.Series, window: int = 20, num_std: float = 2.0) -> tuple[float, float, float]:
    ma = close.rolling(window).mean()
    std = close.rolling(window).std()
    mid = float(ma.iloc[-1]) if pd.notna(ma.iloc[-1]) else float(close.iloc[-1])
    lower = float((ma - num_std * std).iloc[-1])
    upper = float((ma + num_std * std).iloc[-1])
    if pd.isna(lower):
        lower = mid
    if pd.isna(upper):
        upper = mid
    return lower, mid, upper


def ma_alignment_score(close: pd.Series) -> float | None:
    if len(close) < 25:
        return None
    ma5 = close.rolling(5).mean().iloc[-1]
    ma10 = close.rolling(10).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    price = close.iloc[-1]
    if any(pd.isna(x) for x in (ma5, ma10, ma20, price)):
        return None
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
    if pd.isna(price) or price <= 0:
        price = float(close.dropna().iloc[-1]) if len(close.dropna()) else 0.0
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
