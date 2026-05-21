import numpy as np
import pandas as pd
import pytest

from datetime import datetime, timedelta

from app.db.models import News
from app.services.scoring import (
    COMPOSITE_FALLBACK,
    CORRECTION_MAX,
    CORRECTION_MIN,
    DimensionScores,
    NEWS_BASELINE,
    WEIGHTS_HK,
    WEIGHTS_US,
    compute_composite,
    correction_factor,
    compute_recommended_prices,
    score_news,
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
    assert buy <= current
    assert sell >= current
    assert sell - buy >= current * 0.05 - 0.01


def _bundle_at_price(current: float) -> market_data.OhlcvBundle:
    n = 60
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    close = pd.Series(np.full(n, current), index=idx)
    return market_data.OhlcvBundle(close=close, high=close + 1, low=close - 1)


def test_recommended_prices_deep_pullback_invariants(monkeypatch):
    """buy_base 高、sell_base 低时,修复后仍满足 buy < current < sell。"""
    current = 100.0

    def fake_levels(_bundle):
        return {
            "price": current,
            "low_20d": 102.0,
            "high_52w": 200.0,
            "bb_lower": 101.0,
            "bb_upper": 95.0,
        }

    monkeypatch.setattr("app.services.scoring.market_data.technical_levels", fake_levels)
    dims = DimensionScores(valuation=80, capital=50, technical=50, fundamental=20, news=NEWS_BASELINE)
    buy, sell = compute_recommended_prices(_bundle_at_price(current), dims)
    assert buy is not None and sell is not None
    assert buy < current < sell
    assert sell - buy >= current * 0.05 - 0.01


def test_recommended_prices_min_five_percent_spread(monkeypatch):
    current = 50.0

    def fake_levels(_bundle):
        return {
            "price": current,
            "low_20d": 50.0,
            "high_52w": 50.0,
            "bb_lower": 50.0,
            "bb_upper": 50.0,
        }

    monkeypatch.setattr("app.services.scoring.market_data.technical_levels", fake_levels)
    dims = DimensionScores(50, 50, 50, 50, NEWS_BASELINE)
    buy, sell = compute_recommended_prices(_bundle_at_price(current), dims)
    assert buy is not None and sell is not None
    assert sell - buy >= current * 0.05 - 0.01


def test_recommended_prices_low_valuation_more_conservative_buy(monkeypatch):
    current = 100.0

    def fake_levels(_bundle):
        return {
            "price": current,
            "low_20d": 99.0,
            "high_52w": 110.0,
            "bb_lower": 98.0,
            "bb_upper": 105.0,
        }

    monkeypatch.setattr("app.services.scoring.market_data.technical_levels", fake_levels)
    dims = DimensionScores(valuation=20, capital=50, technical=50, fundamental=50, news=NEWS_BASELINE)
    buy, _ = compute_recommended_prices(_bundle_at_price(current), dims)
    assert buy is not None
    assert buy <= current * 0.92 + 0.01


def test_recommended_prices_high_fundamental_more_optimistic_sell(monkeypatch):
    current = 100.0

    def fake_levels(_bundle):
        return {
            "price": current,
            "low_20d": 99.0,
            "high_52w": 110.0,
            "bb_lower": 98.0,
            "bb_upper": 105.0,
        }

    monkeypatch.setattr("app.services.scoring.market_data.technical_levels", fake_levels)
    dims = DimensionScores(valuation=50, capital=50, technical=50, fundamental=80, news=NEWS_BASELINE)
    _, sell = compute_recommended_prices(_bundle_at_price(current), dims)
    assert sell is not None
    assert sell >= current * 1.10 - 0.01


def test_score_news_baseline_when_empty(monkeypatch):
    class _Q:
        def filter(self, *a, **k):
            return self

        def all(self):
            return []

    class _S:
        def query(self, *a, **k):
            return _Q()

        def close(self):
            return None

    monkeypatch.setattr("app.services.scoring.get_session", lambda: _S())
    sc, is_base = score_news("NVDA")
    assert sc == 50.0
    assert is_base is True


def test_score_news_bullish_dominant(session, monkeypatch):
    now = datetime.utcnow()
    session.add_all(
        [
            News(symbol="NVDA", title="t1", url=f"u1{now.timestamp()}", source="x", summary="", sentiment="bullish", published_at=now),
            News(symbol="NVDA", title="t2", url=f"u2{now.timestamp()}", source="x", summary="", sentiment="bullish", published_at=now - timedelta(hours=6)),
            News(symbol="NVDA", title="t3", url=f"u3{now.timestamp()}", source="x", summary="", sentiment="neutral", published_at=now - timedelta(days=1)),
        ]
    )
    session.commit()
    monkeypatch.setattr("app.services.scoring.get_session", lambda: session)
    sc, is_base = score_news("NVDA")
    assert is_base is False
    assert sc > 80


def test_score_news_opinion_weighted_lower_than_fact(session, monkeypatch):
    now = datetime.utcnow()
    session.add_all(
        [
            News(
                symbol="NVDA",
                title="f1",
                url=f"uf1{now.timestamp()}",
                source="x",
                summary="",
                sentiment="bullish",
                sentiment_type="事实",
                sentiment_confidence=0.9,
                published_at=now,
            ),
            News(
                symbol="NVDA",
                title="f2",
                url=f"uf2{now.timestamp()}",
                source="x",
                summary="",
                sentiment="bullish",
                sentiment_type="事实",
                sentiment_confidence=0.9,
                published_at=now,
            ),
            News(
                symbol="NVDA",
                title="o1",
                url=f"uo1{now.timestamp()}",
                source="x",
                summary="",
                sentiment="bearish",
                sentiment_type="观点",
                sentiment_confidence=0.9,
                published_at=now,
            ),
        ]
    )
    session.commit()
    monkeypatch.setattr("app.services.scoring.get_session", lambda: session)
    sc_mixed, _ = score_news("NVDA")

    session.query(News).filter(News.title == "o1").delete()
    session.commit()
    session.add(
        News(
            symbol="NVDA",
            title="f3",
            url=f"uf3{now.timestamp()}",
            source="x",
            summary="",
            sentiment="bullish",
            sentiment_type="事实",
            sentiment_confidence=0.9,
            published_at=now,
        )
    )
    session.commit()
    sc_all_fact, _ = score_news("NVDA")
    assert sc_all_fact > sc_mixed


def test_score_news_recent_weighted_higher(session, monkeypatch):
    now = datetime.utcnow()
    session.add_all(
        [
            News(symbol="NVDA", title="old", url=f"uo{now.timestamp()}", source="x", summary="", sentiment="bearish", published_at=now - timedelta(days=7)),
            News(symbol="NVDA", title="new1", url=f"un1{now.timestamp()}", source="x", summary="", sentiment="bullish", published_at=now),
            News(symbol="NVDA", title="new2", url=f"un2{now.timestamp()}", source="x", summary="", sentiment="bullish", published_at=now - timedelta(hours=2)),
        ]
    )
    session.commit()
    monkeypatch.setattr("app.services.scoring.get_session", lambda: session)
    sc, is_base = score_news("NVDA")
    assert is_base is False
    assert sc > 60
