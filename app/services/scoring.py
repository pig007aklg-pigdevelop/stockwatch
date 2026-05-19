"""五维综合打分 + 推荐买卖价。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from app.services import data_sources, market_data
from app.services.ticker import is_us_market, normalize_symbol

NEWS_BASELINE = 50.0
CORRECTION_MIN = 0.85
CORRECTION_MAX = 1.10
PRICE_DEVIATION_MAX = 0.20  # 推荐价相对现价 ±20%

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


def weights_for_market(market: str) -> dict[str, float]:
    return WEIGHTS_US if is_us_market(market) else WEIGHTS_HK


def score_valuation(bundle: market_data.OhlcvBundle | None) -> float | None:
    if bundle is None:
        return None
    pe_pct, pb_pct = market_data.pe_pb_history_percentiles(bundle)
    parts = []
    if pe_pct is not None:
        parts.append(100 - pe_pct)  # 分位越低越便宜 → 分越高
    if pb_pct is not None and pb_pct != pe_pct:
        parts.append(100 - pb_pct)
    if not parts:
        # 仅有价格序列：相对 5 年收盘价分位
        pct = market_data.percentile_rank(float(bundle.close.iloc[-1]), bundle.close)
        if pct is not None:
            return float(np.clip(100 - pct, 0, 100))
        return None
    return float(np.clip(np.mean(parts), 0, 100))


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
    if not parts:
        return None
    return float(np.mean(parts))


def score_technical(bundle: market_data.OhlcvBundle | None) -> float | None:
    if bundle is None:
        return None
    t = market_data.technical_levels(bundle)
    parts = []
    if t["rsi"] is not None:
        rsi = t["rsi"]
        # 30-70 中性偏高，超卖加分
        if rsi < 30:
            parts.append(80)
        elif rsi > 70:
            parts.append(30)
        else:
            parts.append(50 + (50 - rsi) * 0.5)
    if t["ma_score"] is not None:
        parts.append(t["ma_score"])
    # 距 52 周高点越远（回调多）略加分
    dist = t.get("dist_from_52w_high_pct", 0)
    parts.append(float(np.clip(50 + dist * 0.5, 0, 100)))
    if not parts:
        return None
    return float(np.clip(np.mean(parts), 0, 100))


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
    if not parts:
        return None
    return float(np.mean(parts))


def compute_composite(market: str, dims: DimensionScores) -> float | None:
    weights = weights_for_market(market)
    scores = dims.as_dict()
    active = {k: v for k, v in scores.items() if v is not None and weights.get(k, 0) > 0}
    if not active:
        return None
    total_w = sum(weights[k] for k in active)
    if total_w <= 0:
        return None
    composite = sum(scores[k] * weights[k] for k in active) / total_w
    return round(float(composite), 2)


def correction_factor(score: float | None) -> float:
    """估值/基本面对推荐价的修正系数，线性映射并 clamp [0.85, 1.10]。"""
    if score is None:
        return 1.0
    raw = CORRECTION_MIN + (float(score) / 100.0) * (CORRECTION_MAX - CORRECTION_MIN)
    return float(np.clip(raw, CORRECTION_MIN, CORRECTION_MAX))


def _clamp_to_current_price(price: float, target: float) -> float:
    """推荐价相对现价不超过 ±20%。"""
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
    if current <= 0:
        return None, None
    buy_base = max(t["low_20d"], t["bb_lower"])
    sell_base = min(t["high_52w"], t["bb_upper"])
    buy = buy_base * correction_factor(dims.valuation)
    sell = sell_base * correction_factor(dims.fundamental)
    buy = _clamp_to_current_price(current, buy)
    sell = _clamp_to_current_price(current, sell)
    if buy <= 0 or sell <= 0:
        return None, None
    return round(buy, 2), round(sell, 2)


def score_position(market: str, symbol: str) -> ScoreResult:
    sym = normalize_symbol(market, symbol)
    bundle = market_data.fetch_ohlcv(market, sym)
    dims = DimensionScores(
        valuation=score_valuation(bundle),
        capital=score_capital(market, sym),
        technical=score_technical(bundle),
        fundamental=score_fundamental(market, sym),
        news=NEWS_BASELINE,
    )
    composite = compute_composite(market, dims)
    buy, sell = compute_recommended_prices(bundle, dims)
    return ScoreResult(
        composite=composite,
        dimensions=dims,
        recommended_buy=buy,
        recommended_sell=sell,
        updated_at=datetime.utcnow(),
    )


def apply_result_to_position(pos, result: ScoreResult) -> None:
    pos.composite_score = result.composite
    pos.score_valuation = result.dimensions.valuation
    pos.score_capital = result.dimensions.capital
    pos.score_technical = result.dimensions.technical
    pos.score_fundamental = result.dimensions.fundamental
    pos.score_news = result.dimensions.news
    pos.recommended_buy = result.recommended_buy
    pos.recommended_sell = result.recommended_sell
    pos.score_updated_at = result.updated_at
