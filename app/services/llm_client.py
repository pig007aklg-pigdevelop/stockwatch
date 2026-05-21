"""LLM 客户端 - 新闻摘要+情绪分析"""
from __future__ import annotations

import json
import logging
from typing import Optional
from app.config import config

log = logging.getLogger(__name__)

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

SENTIMENT_PROMPT = """你是港股/美股新闻情绪分析助手。给定一条新闻标题+摘要,判断它对该股票的影响。

严格按以下步骤:

1. 先判断**类型**:
   - "事实"(财报/公告/数据/政策/收并购/裁员/产品发布)
   - "观点"(分析师评级/媒体评论/小道消息/股吧风向)

2. 再判断**情绪**:bullish / neutral / bearish

3. 输出 JSON,字段固定:
{{
  "type": "事实" | "观点",
  "sentiment": "bullish" | "neutral" | "bearish",
  "confidence": 0.0-1.0,
  "reason": "≤30字中文,说明判断依据",
  "summary": "≤40字中文一句话摘要"
}}

判定规则(关键):
- 类型="观点" 时,confidence ≤ 0.6,除非有具体数字/事件支撑
- 财报超预期/低于预期 → 事实+对应情绪,confidence ≥ 0.8
- 标题含"传"、"或将"、"有望"、"恐"、"猜测" → 多半是观点,情绪取 neutral 除非很确定
- 无法判断 → type=事实,sentiment=neutral,confidence=0.3

新闻:
标题:{title}
摘要:{summary}
"""


def _client():
    if not config.OPENAI_API_KEY or OpenAI is None:
        return None
    return OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)


def _normalize_sentiment_result(data: dict, title: str) -> dict:
    sent = (data.get("sentiment") or "neutral").strip().lower()
    if sent not in ("bullish", "neutral", "bearish"):
        sent = "neutral"
    news_type = data.get("type") or "事实"
    if news_type not in ("事实", "观点"):
        news_type = "事实"
    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    if news_type == "观点" and confidence > 0.6:
        reason = (data.get("reason") or "")
        has_numbers = any(c.isdigit() for c in reason + title)
        if not has_numbers:
            confidence = 0.6
    reason = (data.get("reason") or "")[:80]
    summary = (data.get("summary") or reason or title)[:200]
    return {
        "type": news_type,
        "sentiment": sent,
        "confidence": confidence,
        "reason": reason,
        "summary": summary,
    }


def llm_analyze_sentiment_raw(title: str, content: str = "", symbol: str = "") -> dict:
    """调用 LLM 分析情绪(不经缓存)。"""
    cli = _client()
    if cli is None:
        return {
            "type": "事实",
            "sentiment": "neutral",
            "confidence": 0.3,
            "reason": "无LLM",
            "summary": title[:200],
        }

    summary_text = (content or "")[:1500]
    prompt = SENTIMENT_PROMPT.format(title=title, summary=summary_text)
    try:
        resp = cli.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        return _normalize_sentiment_result(data, title)
    except Exception as e:
        log.warning("LLM sentiment analyze failed: %s", e)
        return {
            "type": "事实",
            "sentiment": "neutral",
            "confidence": 0.3,
            "reason": "分析失败",
            "summary": title[:200],
        }


def summarize_news(title: str, content: str = "", symbol: str = "") -> dict:
    """返回 {summary, sentiment, type, confidence, reason} — 兼容旧调用。"""
    from app.services.sentiment import analyze_news

    return analyze_news(title, content, symbol)


SENTIMENT_MAP = {"bullish": 100.0, "neutral": 50.0, "bearish": 0.0}


def sentiment_to_score(sentiment: str | None) -> float | None:
    """把 bullish/bearish/neutral 映射到 0-100,未知返回 None"""
    if not sentiment:
        return None
    return SENTIMENT_MAP.get(sentiment.strip().lower())
