"""LLM 客户端 - 新闻摘要+情绪分析"""
from __future__ import annotations

import logging
from typing import Optional
from app.config import config

log = logging.getLogger(__name__)

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def _client():
    if not config.OPENAI_API_KEY or OpenAI is None:
        return None
    return OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)


def summarize_news(title: str, content: str = "", symbol: str = "") -> dict:
    """返回 {summary, sentiment}"""
    cli = _client()
    if cli is None:
        return {"summary": title[:200], "sentiment": "neutral"}

    prompt = (
        f"以下是关于股票 {symbol} 的新闻。请用中文给出:\n"
        f"1. 一句话摘要(≤40字)\n"
        f"2. 情绪倾向: bullish / bearish / neutral\n\n"
        f"严格按 JSON 输出: {{\"summary\":\"...\",\"sentiment\":\"...\"}}\n\n"
        f"标题: {title}\n内容: {content[:1500]}"
    )
    try:
        resp = cli.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        import json
        data = json.loads(resp.choices[0].message.content)
        return {
            "summary": data.get("summary", title[:200]),
            "sentiment": data.get("sentiment", "neutral"),
        }
    except Exception as e:
        log.warning("LLM summarize failed: %s", e)
        return {"summary": title[:200], "sentiment": "neutral"}


SENTIMENT_MAP = {"bullish": 100.0, "neutral": 50.0, "bearish": 0.0}


def sentiment_to_score(sentiment: str | None) -> float | None:
    """把 bullish/bearish/neutral 映射到 0-100,未知返回 None"""
    if not sentiment:
        return None
    return SENTIMENT_MAP.get(sentiment.strip().lower())
