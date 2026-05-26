"""Risk officer — rule-based filter (no LLM)."""
from __future__ import annotations

from typing import Any

from app.agents.state import AgentState

TOP_N = {"hk": 3, "us": 5}
MIN_SCORE = 35.0
MAX_SENTIMENT_NEG = -0.55
RSI_OVERBOUGHT = 78.0
MIN_DIST_52W_HIGH_PCT = 3.0


def _reject_reason(pick: dict[str, Any], technical: dict[str, Any] | None) -> str | None:
    score = pick.get("score") or 0
    if score < MIN_SCORE:
        return f"综合分{score:.0f}低于门槛{MIN_SCORE:.0f}"

    sent = pick.get("news_sentiment_avg")
    if sent is not None and sent < MAX_SENTIMENT_NEG:
        return f"新闻情绪{sent:+.2f}过差"

    ind = technical or {}
    rsi = ind.get("rsi")
    if rsi is not None and rsi > RSI_OVERBOUGHT and not ind.get("macd_bullish"):
        return f"RSI{rsi:.0f}超买且MACD未多头"

    dist = ind.get("dist_52w_high_pct")
    if dist is not None and dist < MIN_DIST_52W_HIGH_PCT:
        return f"距52周高仅{dist:.1f}%空间不足"

    return None


def risk_officer_node(state: AgentState) -> dict:
    market = (state.get("market") or "hk").lower()
    top_n = TOP_N.get(market, 3)
    trader_picks = state.get("trader_picks") or []
    technical = state.get("technical") or {}
    market_view = (state.get("market_view") or "").strip()

    assessments: list[dict[str, Any]] = []
    approved: list[dict[str, Any]] = []

    for pick in trader_picks:
        code = pick.get("code") or ""
        ind = technical.get(code)
        reason = _reject_reason(pick, ind)
        entry = {
            "code": code,
            "approved": reason is None,
            "reason": reason or "通过",
            "score": pick.get("score"),
        }
        assessments.append(entry)
        if reason is None:
            approved.append({**pick, "market_view": market_view})

    consensus_picks = approved[:top_n]
    for i, p in enumerate(consensus_picks, start=1):
        p["rank"] = i

    return {
        "risk_assessment": assessments,
        "consensus_picks": consensus_picks,
    }
