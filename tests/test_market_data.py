import pandas as pd
from unittest.mock import patch

from app.services import market_data
from app.services.scoring import NEWS_BASELINE, DimensionScores, compute_recommended_prices


def _sample_bundle():
    n = 40
    idx = range(n)
    close = pd.Series([10.0 + i * 0.1 for i in idx])
    high = close + 0.5
    low = close - 0.5
    return market_data.OhlcvBundle(close=close, high=high, low=low)


def test_fetch_ohlcv_hk_fallback_to_akshare():
    bundle = _sample_bundle()
    with patch("app.services.market_data._fetch_yfinance_single", return_value=None):
        with patch("app.services.market_data._fetch_akshare_hk", return_value=bundle):
            result = market_data.fetch_ohlcv("HK", "00883")
    assert result is not None
    assert len(result.close) >= 30


def test_recommended_prices_from_hk_bundle():
    bundle = _sample_bundle()
    dims = DimensionScores(50, None, 50, None, NEWS_BASELINE)
    buy, sell = compute_recommended_prices(bundle, dims)
    assert buy is not None and sell is not None
    current = float(bundle.close.iloc[-1])
    assert current * 0.8 <= buy <= current * 1.2
    assert current * 0.8 <= sell <= current * 1.2
