"""五维综合打分 + 推荐买卖价。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import or_

from app.db.models import News, get_session
from app.services import data_sources, market_data
from app.services.llm_client import sentiment_to_score
from app.services.ticker import is_us_market, normalize_symbol

log = logging.getLogger(__name__)

NEWS_BASELINE = 50.0
NEWS_LOOKBACK_DAYS = 7
NEWS_MIN_COUNT = 2
COMPOSITE_FALLBACK = 50.0
CORRECTION_MIN = 0.85
CORRECTION_MAX = 1.10
PRICE_DEVIATION_MAX = 0.20
SUBSTANTIVE_DIMS = ("valuation", "capital", "technical", "fundamental")

WEIGHTS_HK = {
    "valuation": 0.25,
    "capital": 0.25,
    "technical": 0.20,
    "fundamental": 0.20,
    "news": 0.10,
}

WEIGHTS_US = {
    "valuation": 0.33,
    "capital": 0.0,
    "technical": 0.27,
    "fundamental": 0.27,
    "news": 0.13,
}


@dataclass
class DimensionScores:
    valuation: float | None
    capital: float | None
    technical: float | None
    fundamental: float | None
    news: float

    def as_dict(self) -> dict[str, float | None]:
        return {
            "valuation": self.valuation,
            "capital": self.capital,
            "technical": self.technical,
            "fundamental": self.fundamental,
            "news": self.news,
        }


@dataclass
class ScoreResult:
    composite: float | None
    dimensions: DimensionScores
    recommended_buy: float | None
    recommended_sell: float | None
    updated_at: datetime
    data_incomplete: bool = False


def _sanitize_score(v: float | None) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _safe_mean(parts: list[float]) -> float | None:
    clean = [_sanitize_score(x) for x in parts]
    clean = [x for x in clean if x is not None]
    if not clean:
        return None
    return float(np.mean(clean))


def weights_for_market(market: str) -> dict[str, float]:
    return WEIGHTS_US if is_us_market(market) else WEIGHTS_HK


def score_valuation(bundle: market_data.OhlcvBundle | None) -> float | None:
    if bundle is None:
        return None
    pe_pct, pb_pct = market_data.pe_pb_history_percentiles(bundle)
    parts = []
    if pe_pct is not None:
        parts.append(100 - pe_pct)
    if pb_pct is not None and pb_pct != pe_pct:
        parts.append(100 - pb_pct)
    if not parts:
        pct = market_data.percentile_rank(float(bundle.close.iloc[-1]), bundle.close)
        if pct is not None:
            return float(np.clip(100 - pct, 0, 100))
        return None
    return _sanitize_score(float(np.clip(np.mean(parts), 0, 100)))


def score_capital(market: str, symbol: str) -> float | None:
    if is_us_market(market):
        return None
    hsgt = data_sources.fetch_hsgt_holdings(market, symbol)
    flow = data_sources.fetch_fund_flow(market, symbol)
    parts = []
    if hsgt and hsgt.hold_change_5d is not None:
        ch = hsgt.hold_change_5d
        parts.append(float(np.clip(50 + np.sign(ch) * min(abs(ch) / 1e6, 50), 0, 100)))
    elif hsgt and hsgt.hold_ratio is not None:
        parts.append(float(np.clip(hsgt.hold_ratio * 5, 0, 100)))
    if flow and flow.net_inflow_5d is not None:
        v = flow.net_inflow_5d
        parts.append(float(np.clip(50 + np.tanh(v / 1e8) * 50, 0, 100)))
    if flow and flow.main_net_pct is not None:
        parts.append(float(np.clip(50 + flow.main_net_pct, 0, 100)))
    return _safe_mean(parts)


def score_technical(bundle: market_data.OhlcvBundle | None) -> float | None:
    if bundle is None:
        return None
    t = market_data.technical_levels(bundle)
    parts = []
    if t["rsi"] is not None:
        rsi_val = t["rsi"]
        if rsi_val < 30:
            parts.append(80)
        elif rsi_val > 70:
            parts.append(30)
        else:
            parts.append(50 + (50 - rsi_val) * 0.5)
    if t["ma_score"] is not None:
        parts.append(t["ma_score"])
    dist = t.get("dist_from_52w_high_pct", 0)
    parts.append(float(np.clip(50 + dist * 0.5, 0, 100)))
    return _safe_mean(parts)


def score_fundamental(market: str, symbol: str) -> float | None:
    snap = data_sources.fetch_financial_abstract(market, symbol)
    if snap is None:
        return None
    parts = []

    def metric_score(val: float | None, trend: float | None, good_high: bool = True) -> float | None:
        if val is None:
            return None
        base = float(np.clip(val, -50, 50)) if good_high else float(np.clip(-val, -50, 50))
        s = 50 + base
        if trend is not None:
            s += float(np.clip(trend, -20, 20))
        return float(np.clip(s, 0, 100))

    for val, trend in (
        (snap.roe, snap.roe_trend),
        (snap.revenue_growth, snap.revenue_trend),
        (snap.net_margin, snap.margin_trend),
    ):
        m = metric_score(val, trend)
        if m is not None:
            parts.append(m)
    return _safe_mean(parts)


def score_news(symbol: str) -> tuple[float, bool]:
    """
    基于近 NEWS_LOOKBACK_DAYS 天 News.sentiment 的加权得分(越新权重越大)。
    返回 (score, is_baseline) — is_baseline=True 表示数据不足回落 50。
    """
    cutoff = datetime.utcnow() - timedelta(days=NEWS_LOOKBACK_DAYS)
    s = get_session()
    try:
        rows = (
            s.query(News.sentiment, News.published_at)
            .filter(
                or_(News.symbol == symbol, News.symbol.is_(None)),
                News.published_at >= cutoff,
                News.sentiment != "",
            )
            .all()
        )
    finally:
        s.close()

    pairs = [(sentiment_to_score(sent), ts) for sent, ts in rows]
    pairs = [(sc, ts) for sc, ts in pairs if sc is not None and ts is not None]
    if len(pairs) < NEWS_MIN_COUNT:
        return NEWS_BASELINE, True

    now = datetime.utcnow()
    weighted: list[tuple[float, float]] = []
    for sc, ts in pairs:
        age_days = max(0.0, (now - ts).total_seconds() / 86400.0)
        w = max(0.5, 1.0 - 0.5 * age_days / NEWS_LOOKBACK_DAYS)
        weighted.append((float(sc), float(w)))

    total_w = sum(w for _, w in weighted)
    score = (
        sum(sc * w for sc, w in weighted) / total_w
        if total_w > 0
        else NEWS_BASELINE
    )
    return float(np.clip(score, 0, 100)), False


def substantive_dims_all_missing(dims: DimensionScores) -> bool:
    scores = dims.as_dict()
    return all(_sanitize_score(scores.get(k)) is None for k in SUBSTANTIVE_DIMS)


def compute_composite(market: str, dims: DimensionScores) -> tuple[float, bool]:
    """
    返回 (composite, data_incomplete)。
    四维全无有效数据时保底 50 分并标记 incomplete。
    """
    if substantive_dims_all_missing(dims):
        log.warning(
            "Scoring incomplete for market=%s: all substantive dimensions missing, fallback=%s",
            market,
            COMPOSITE_FALLBACK,
        )
        return COMPOSITE_FALLBACK, True

    weights = weights_for_market(market)
    scores = {k: _sanitize_score(v) for k, v in dims.as_dict().items()}
    active = {k: v for k, v in scores.items() if v is not None and weights.get(k, 0) > 0}
    if not active:
        log.warning("Scoring no active dimensions, fallback=%s", COMPOSITE_FALLBACK)
        return COMPOSITE_FALLBACK, True

    total_w = sum(weights[k] for k in active)
    if total_w <= 0:
        return COMPOSITE_FALLBACK, True

    composite = sum(scores[k] * weights[k] for k in active) / total_w
    composite = _sanitize_score(composite)
    if composite is None:
        log.warning("Scoring composite is NaN, fallback=%s", COMPOSITE_FALLBACK)
        return COMPOSITE_FALLBACK, True

    missing_count = sum(1 for k in SUBSTANTIVE_DIMS if scores.get(k) is None)
    incomplete = missing_count >= len(SUBSTANTIVE_DIMS) or missing_count >= 3
    return round(float(composite), 2), incomplete


def correction_factor(score: float | None) -> float:
    if score is None:
        return 1.0
    raw = CORRECTION_MIN + (float(score) / 100.0) * (CORRECTION_MAX - CORRECTION_MIN)
    return float(np.clip(raw, CORRECTION_MIN, CORRECTION_MAX))


def _clamp_to_current_price(price: float, target: float) -> float:
    lo = price * (1 - PRICE_DEVIATION_MAX)
    hi = price * (1 + PRICE_DEVIATION_MAX)
    return float(np.clip(target, lo, hi))


def compute_recommended_prices(
    bundle: market_data.OhlcvBundle | None,
    dims: DimensionScores,
) -> tuple[float | None, float | None]:
    if bundle is None:
        return None, None
    t = market_data.technical_levels(bundle)
    current = t["price"]
    if current <= 0 or np.isnan(current):
        return None, None
    buy_base = max(t["low_20d"], t["bb_lower"])
    sell_base = min(t["high_52w"], t["bb_upper"])
    if np.isnan(buy_base) or np.isnan(sell_base):
        buy_base = current * 0.95
        sell_base = current * 1.05
    buy = buy_base * correction_factor(dims.valuation)
    sell = sell_base * correction_factor(dims.fundamental)
    buy = _clamp_to_current_price(current, buy)
    sell = _clamp_to_current_price(current, sell)
    if buy <= 0 or sell <= 0 or np.isnan(buy) or np.isnan(sell):
        return None, None
    return round(float(buy), 2), round(float(sell), 2)


def score_position(market: str, symbol: str) -> ScoreResult:
    sym = normalize_symbol(market, symbol)
    bundle = market_data.fetch_ohlcv(market, sym)
    news_score, _news_is_baseline = score_news(sym)
    dims = DimensionScores(
        valuation=score_valuation(bundle),
        capital=score_capital(market, sym),
        technical=score_technical(bundle),
        fundamental=score_fundamental(market, sym),
        news=news_score,
    )
    composite, incomplete = compute_composite(market, dims)
    buy, sell = compute_recommended_prices(bundle, dims)
    if buy is None and bundle is not None:
        log.warning("recommended_buy missing %s.%s despite OHLCV bundle", market, sym)
    return ScoreResult(
        composite=composite,
        dimensions=dims,
        recommended_buy=buy,
        recommended_sell=sell,
        updated_at=datetime.utcnow(),
        data_incomplete=incomplete,
    )


def apply_result_to_record(record, result: ScoreResult) -> None:
    """通用版: Position / Watchlist 都适用。"""
    record.composite_score = result.composite
    record.score_valuation = result.dimensions.valuation
    record.score_capital = result.dimensions.capital
    record.score_technical = result.dimensions.technical
    record.score_fundamental = result.dimensions.fundamental
    record.score_news = result.dimensions.news
    record.recommended_buy = result.recommended_buy
    record.recommended_sell = result.recommended_sell
    record.score_updated_at = result.updated_at


apply_result_to_position = apply_result_to_record
