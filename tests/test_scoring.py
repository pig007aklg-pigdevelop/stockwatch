import numpy as np
import pandas as pd
import pytest

from app.services.scoring import (
    COMPOSITE_FALLBACK,
    CORRECTION_MAX,
    CORRECTION_MIN,
    PRICE_DEVIATION_MAX,
    DimensionScores,
    NEWS_BASELINE,
    WEIGHTS_HK,
    WEIGHTS_US,
    compute_composite,
    correction_factor,
    compute_recommended_prices,
    substantive_dims_all_missing,
    weights_for_market,
)
from app.services import market_data


def test_weights_us_no_capital():
    w = weights_for_market("US")
    assert w["capital"] == 0
    assert abs(sum(w.values()) - 1.0) < 1e-6


def test_compute_composite_hk_all_dims():
    dims = DimensionScores(80, 70, 60, 50, NEWS_BASELINE)
    c, incomplete = compute_composite("HK", dims)
    assert incomplete is False
    expected = (
        80 * WEIGHTS_HK["valuation"]
        + 70 * WEIGHTS_HK["capital"]
        + 60 * WEIGHTS_HK["technical"]
        + 50 * WEIGHTS_HK["fundamental"]
        + NEWS_BASELINE * WEIGHTS_HK["news"]
    )
    assert c == round(expected, 2)


def test_compute_composite_us_skips_capital():
    dims = DimensionScores(80, None, 60, 50, NEWS_BASELINE)
    c, _ = compute_composite("US", dims)
    w = WEIGHTS_US
    expected = (
        80 * w["valuation"]
        + 60 * w["technical"]
        + 50 * w["fundamental"]
        + NEWS_BASELINE * w["news"]
    ) / (w["valuation"] + w["technical"] + w["fundamental"] + w["news"])
    assert c == round(expected, 2)


def test_compute_composite_renormalize_missing():
    dims = DimensionScores(80, None, None, 50, NEWS_BASELINE)
    c, _ = compute_composite("HK", dims)
    assert c is not None
    assert 0 <= c <= 100


def test_compute_composite_all_substantive_none_fallback():
    dims = DimensionScores(None, None, None, None, NEWS_BASELINE)
    assert substantive_dims_all_missing(dims) is True
    c, incomplete = compute_composite("HK", dims)
    assert c == COMPOSITE_FALLBACK
    assert incomplete is True


def test_compute_composite_nan_dimension_sanitized():
    dims = DimensionScores(float("nan"), None, None, None, NEWS_BASELINE)
    c, incomplete = compute_composite("HK", dims)
    assert c == COMPOSITE_FALLBACK
    assert incomplete is True


def test_correction_factor():
    assert correction_factor(None) == 1.0
    mid = CORRECTION_MIN + 0.5 * (CORRECTION_MAX - CORRECTION_MIN)
    assert correction_factor(50) == pytest.approx(mid)
    assert correction_factor(100) == pytest.approx(CORRECTION_MAX)
    assert correction_factor(0) == pytest.approx(CORRECTION_MIN)


def test_correction_factor_clamped():
    assert CORRECTION_MIN == 0.85
    assert CORRECTION_MAX == 1.10
    assert correction_factor(1000) <= CORRECTION_MAX
    assert correction_factor(-100) >= CORRECTION_MIN


def test_recommended_prices():
    n = 60
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    close = pd.Series(np.linspace(100, 120, n), index=idx)
    high = close + 2
    low = close - 2
    bundle = market_data.OhlcvBundle(close=close, high=high, low=low, pe_ttm=20, pb=3)
    dims = DimensionScores(80, 70, 60, 50, NEWS_BASELINE)
    buy, sell = compute_recommended_prices(bundle, dims)
    assert buy is not None and sell is not None
    current = float(close.iloc[-1])
    assert current * (1 - PRICE_DEVIATION_MAX) <= buy <= current * (1 + PRICE_DEVIATION_MAX)
    assert current * (1 - PRICE_DEVIATION_MAX) <= sell <= current * (1 + PRICE_DEVIATION_MAX)
