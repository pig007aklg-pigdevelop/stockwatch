"""Golden tests for agent EMA/MACD (通达信-style seed + 9-day DEA)."""
import numpy as np
import pandas as pd
import pytest

from app.agents.technical import (
    DEA_PERIOD,
    EMA_FAST,
    EMA_SLOW,
    compute_indicators,
    ema_series,
    macd_series,
)
from app.services.market_data import OhlcvBundle


def _reference_ema(close: np.ndarray, period: int) -> np.ndarray:
    n = len(close)
    out = np.full(n, np.nan)
    if n < period:
        return out
    alpha = 2.0 / (period + 1)
    out[period - 1] = close[:period].mean()
    prev = out[period - 1]
    for i in range(period, n):
        prev = alpha * close[i] + (1.0 - alpha) * prev
        out[i] = prev
    return out


def _reference_macd(close: np.ndarray) -> tuple[float, float, float]:
    ema12 = _reference_ema(close, EMA_FAST)
    ema26 = _reference_ema(close, EMA_SLOW)
    dif = ema12 - ema26
    first = int(np.argmax(~np.isnan(dif)))
    dif_tail = dif[first:]
    dea_tail = _reference_ema(dif_tail, DEA_PERIOD)
    last = len(close) - 1
    dea_idx = first + int(np.argmax(~np.isnan(dea_tail)))
    d = dif[last]
    dea = dea_tail[-1] if not np.isnan(dea_tail[-1]) else np.nan
    hist = 2.0 * (d - dea)
    return float(d), float(dea), float(hist)


# 35 bars: deterministic ramp — enough for MACD(12,26,9)
_GOLDEN_CLOSE = np.array([10.0 + i * 0.15 for i in range(35)], dtype=float)


def test_ema_series_seed_is_sma_of_first_n():
    close = pd.Series(_GOLDEN_CLOSE)
    ema12 = ema_series(close, 12)
    expected_seed = close.iloc[:12].mean()
    assert ema12.iloc[11] == pytest.approx(expected_seed)
    ref = _reference_ema(_GOLDEN_CLOSE, 12)
    for i in range(11, len(close)):
        assert ema12.iloc[i] == pytest.approx(ref[i], rel=1e-9, abs=1e-9)


def test_ema_series_too_short_returns_all_nan():
    close = pd.Series([1.0, 2.0, 3.0])
    ema = ema_series(close, 12)
    assert ema.isna().all()


def test_macd_dea_is_9day_ema_of_dif():
    close = pd.Series(_GOLDEN_CLOSE)
    dif, dea, hist = macd_series(close)
    ref_dif, ref_dea, ref_hist = _reference_macd(_GOLDEN_CLOSE)
    assert dif.iloc[-1] == pytest.approx(ref_dif, rel=1e-9, abs=1e-9)
    assert dea.iloc[-1] == pytest.approx(ref_dea, rel=1e-9, abs=1e-9)
    assert hist.iloc[-1] == pytest.approx(ref_hist, rel=1e-9, abs=1e-9)
    assert hist.iloc[-1] == pytest.approx(2.0 * (dif.iloc[-1] - dea.iloc[-1]), rel=1e-9)


def test_macd_first_valid_dif_at_slow_period_bar():
    close = pd.Series(_GOLDEN_CLOSE)
    dif, dea, _ = macd_series(close)
    # First non-NaN DIF when both EMA12 and EMA26 exist (index 25 = bar 26)
    first_dif = dif.first_valid_index()
    assert first_dif == EMA_SLOW - 1
    # DEA needs 9 valid DIF values after first DIF
    first_dea = dea.first_valid_index()
    assert first_dea == EMA_SLOW - 1 + DEA_PERIOD - 1


def test_compute_indicators_bundle_min_bars():
    n = 40
    close = pd.Series([10.0 + i * 0.1 for i in range(n)])
    bundle = OhlcvBundle(close=close, high=close + 0.5, low=close - 0.5)
    ind = compute_indicators(bundle)
    assert ind is not None
    assert ind["price"] == pytest.approx(float(close.iloc[-1]))
    assert ind["dif"] is not None
    assert ind["dea"] is not None
    assert ind["rsi"] is not None


def test_compute_indicators_rejects_short_series():
    close = pd.Series([10.0] * 20)
    bundle = OhlcvBundle(close=close, high=close, low=close)
    assert compute_indicators(bundle) is None
