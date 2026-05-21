"""新闻情绪分析 — Prompt + 缓存封装。"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.llm_client import llm_analyze_sentiment_raw
from app.services.sentiment_cache import get_or_compute


@dataclass
class SentimentBatchStats:
    total: int = 0
    cache_hit: int = 0
    llm_call: int = 0


def analyze_news(
    title: str,
    summary: str = "",
    symbol: str = "",
    stats: SentimentBatchStats | None = None,
) -> dict:
    """分析单条新闻情绪,走缓存。"""

    def _call():
        return llm_analyze_sentiment_raw(title, summary, symbol)

    result, hit = get_or_compute(title, summary, _call)

    if stats is not None:
        stats.total += 1
        if hit:
            stats.cache_hit += 1
        else:
            stats.llm_call += 1

    if not result:
        return {
            "type": "事实",
            "sentiment": "neutral",
            "confidence": 0.3,
            "reason": "无LLM",
            "summary": title[:200],
        }
    if "summary" not in result:
        result["summary"] = result.get("reason") or title[:200]
    return result
