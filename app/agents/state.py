"""LangGraph shared state types."""
from typing import TypedDict


class StockNews(TypedDict):
    code: str
    title: str
    summary: str
    sentiment: float  # -1.0 ~ 1.0
    published_at: str


class AgentState(TypedDict):
    market: str  # "hk" or "us"
    candidates: list[str]  # ["HK.09988", ...]
    news: dict[str, list[StockNews]]  # code -> list of news with sentiment
    technical: dict[str, dict]  # code -> indicators (dif/dea/rsi/ma/tech_view...)
    market_view: str  # 市场分析师输出
    trader_picks: list[dict]  # rule-scored candidates
    risk_assessment: list[dict]  # per-pick risk review
    consensus_picks: list[dict]  # top N after risk, before LLM consensus
    final_picks: list[dict]  # consensus output with prices & views
