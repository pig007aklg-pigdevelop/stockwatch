from unittest.mock import MagicMock

import pytest

from app.config import config
from app.db.models import NewsSentimentCache
from app.services.sentiment_cache import content_hash, get_or_compute


def test_first_call_miss_invokes_llm(session, monkeypatch):
    monkeypatch.setattr(config, "SENTIMENT_CACHE_ENABLED", True)
    calls = []

    def llm_call():
        calls.append(1)
        return {
            "type": "事实",
            "sentiment": "bullish",
            "confidence": 0.9,
            "reason": "业绩好",
            "summary": "业绩增长",
        }

    result, hit = get_or_compute("标题A", "摘要B", llm_call, session=session)
    assert hit is False
    assert len(calls) == 1
    assert result["sentiment"] == "bullish"
    h = content_hash("标题A", "摘要B")
    row = session.get(NewsSentimentCache, h)
    assert row is not None
    assert row.sentiment == "bullish"


def test_second_call_hit_skips_llm(session, monkeypatch):
    monkeypatch.setattr(config, "SENTIMENT_CACHE_ENABLED", True)
    payload = {
        "type": "观点",
        "sentiment": "neutral",
        "confidence": 0.5,
        "reason": "评级调整",
        "summary": "分析师中性",
    }

    get_or_compute("同标题", "同摘要", lambda: payload, session=session)
    calls = []

    result, hit = get_or_compute(
        "同标题", "同摘要", lambda: calls.append(1) or payload, session=session
    )
    assert hit is True
    assert calls == []
    assert result["sentiment"] == "neutral"


def test_title_change_misses_cache(session, monkeypatch):
    monkeypatch.setattr(config, "SENTIMENT_CACHE_ENABLED", True)
    base = {"type": "事实", "sentiment": "bearish", "confidence": 0.8, "reason": "x", "summary": "y"}

    get_or_compute("标题一", "摘要", lambda: base, session=session)
    calls = []
    get_or_compute("标题二", "摘要", lambda: calls.append(1) or base, session=session)
    assert len(calls) == 1
