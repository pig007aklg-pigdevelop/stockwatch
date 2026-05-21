"""LLM 情绪分析结果缓存 — 按 title|summary 的 sha1 去重。"""
from __future__ import annotations

import hashlib
import logging
from typing import Callable

from app.config import config
from app.db.models import NewsSentimentCache, get_session

log = logging.getLogger(__name__)


def content_hash(title: str, summary: str) -> str:
    raw = f"{title}|{summary}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def get_or_compute(
    title: str,
    summary: str,
    llm_call: Callable[[], dict],
    session=None,
) -> tuple[dict, bool]:
    """
    1. hash = sha1(title + "|" + summary)
    2. SELECT from cache → 命中直接返
    3. 未命中 → 调 llm_call(), 写入, 返回

    返回 (result_dict, cache_hit)
    """
    if not config.SENTIMENT_CACHE_ENABLED:
        return llm_call(), False

    h = content_hash(title, summary)
    own_session = session is None
    s = session if session is not None else get_session()
    try:
        row = s.get(NewsSentimentCache, h)
        if row:
            return {
                "type": row.news_type or "事实",
                "sentiment": row.sentiment or "neutral",
                "confidence": row.confidence if row.confidence is not None else 0.5,
                "reason": row.reason or "",
                "summary": row.reason or title[:200],
            }, True

        result = llm_call()
        s.add(
            NewsSentimentCache(
                content_hash=h,
                sentiment=result.get("sentiment", "neutral"),
                news_type=result.get("type", "事实"),
                confidence=float(result.get("confidence", 0.5)),
                reason=result.get("reason", ""),
            )
        )
        s.commit()
        return result, False
    except Exception as e:
        log.warning("sentiment cache error: %s", e)
        s.rollback()
        return llm_call(), False
    finally:
        if own_session:
            s.close()
