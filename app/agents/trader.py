"""Trader analyst — rule-based scoring (no LLM)."""
from __future__ import annotations

from typing import Any

from app.agents.state import AgentState, StockNews

# 7 条可解释规则 (满分各档加总后 cap 100)
RULE_NEWS_SENTIMENT = "news_sentiment"  # 1. 新闻情绪均分 → 0~20
RULE_MACD_BULL = "macd_bullish"  # 2. DIF>DEA → +15
RULE_MACD_HIST = "macd_hist_expand"  # 3. 红柱且柱放大 → +10
RULE_RSI_ZONE = "rsi_healthy"  # 4. RSI 35~65 → +15
RULE_ABOVE_MA20 = "price_above_ma20"  # 5. 站上 MA20 → +15
RULE_MA_ALIGN = "ma_bull_align"  # 6. MA5>MA10>MA20 → +15
RULE_ROOM_52W = "room_below_52w_high"  # 7. 距 52 周高 >10% → +10


def _avg_sentiment(items: list[StockNews]) -> float | None:
    if not items:
        return None
    return sum(n["sentiment"] for n in items) / len(items)


def _sector_avg_sentiment(news: dict[str, list[StockNews]]) -> float | None:
    scores: list[float] = []
    for items in news.values():
        avg = _avg_sentiment(items)
        if avg is not None:
            scores.append(avg)
    if not scores:
        return None
    return sum(scores) / len(scores)


def score_stock(
    code: str,
    *,
    news_items: list[StockNews],
    technical: dict[str, Any] | None,
    sector_avg: float | None,
) -> dict[str, Any]:
    """Return pick dict with score and per-rule breakdown."""
    rule_scores: dict[str, float] = {}
    total = 0.0

    sent_avg = _avg_sentiment(news_items)
    # Rule 1: map [-1,1] → [0,20]; neutral news → 10
    if sent_avg is not None:
        pts = max(0.0, min(20.0, (sent_avg + 1.0) * 10.0))
        if sector_avg is not None and sent_avg >= sector_avg:
            pts = min(20.0, pts + 2.0)
        rule_scores[RULE_NEWS_SENTIMENT] = round(pts, 1)
        total += pts
    else:
        rule_scores[RULE_NEWS_SENTIMENT] = 10.0
        total += 10.0

    ind = technical or {}

    if ind.get("macd_bullish"):
        rule_scores[RULE_MACD_BULL] = 15.0
        total += 15.0
    else:
        rule_scores[RULE_MACD_BULL] = 0.0

    hist = ind.get("macd_hist")
    prev_hist = ind.get("macd_hist_prev")
    if hist is not None and hist > 0 and (prev_hist is None or hist > prev_hist):
        rule_scores[RULE_MACD_HIST] = 10.0
        total += 10.0
    else:
        rule_scores[RULE_MACD_HIST] = 0.0

    rsi = ind.get("rsi")
    if rsi is not None:
        if 35 <= rsi <= 65:
            rule_scores[RULE_RSI_ZONE] = 15.0
            total += 15.0
        elif rsi > 75:
            rule_scores[RULE_RSI_ZONE] = -5.0
            total -= 5.0
        elif rsi < 30:
            rule_scores[RULE_RSI_ZONE] = 8.0
            total += 8.0
        else:
            rule_scores[RULE_RSI_ZONE] = 5.0
            total += 5.0
    else:
        rule_scores[RULE_RSI_ZONE] = 0.0

    if ind.get("price_above_ma20"):
        rule_scores[RULE_ABOVE_MA20] = 15.0
        total += 15.0
    else:
        rule_scores[RULE_ABOVE_MA20] = 0.0

    if ind.get("ma_bull_align"):
        rule_scores[RULE_MA_ALIGN] = 15.0
        total += 15.0
    else:
        rule_scores[RULE_MA_ALIGN] = 0.0

    dist = ind.get("dist_52w_high_pct")
    if dist is not None:
        if dist >= 10.0:
            rule_scores[RULE_ROOM_52W] = 10.0
            total += 10.0
        elif dist < 5.0:
            rule_scores[RULE_ROOM_52W] = -5.0
            total -= 5.0
        else:
            rule_scores[RULE_ROOM_52W] = 5.0
            total += 5.0
    else:
        rule_scores[RULE_ROOM_52W] = 0.0

    score = round(max(0.0, min(100.0, total)), 1)
    return {
        "code": code,
        "score": score,
        "news_sentiment_avg": sent_avg,
        "rule_scores": rule_scores,
        "tech_view": ind.get("tech_view") or "",
        "price": ind.get("price"),
    }


def trader_node(state: AgentState) -> dict:
    news = state.get("news") or {}
    technical = state.get("technical") or {}
    candidates = state.get("candidates") or list(news.keys())
    sector_avg = _sector_avg_sentiment(news)

    picks: list[dict[str, Any]] = []
    for code in candidates:
        pick = score_stock(
            code,
            news_items=news.get(code) or [],
            technical=technical.get(code),
            sector_avg=sector_avg,
        )
        picks.append(pick)

    picks.sort(key=lambda p: p["score"], reverse=True)
    return {"trader_picks": picks}
