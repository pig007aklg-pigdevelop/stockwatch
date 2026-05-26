"""News collection and batch sentiment analysis for the agent pipeline."""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from time import mktime
from typing import TYPE_CHECKING

import feedparser
from langchain_core.messages import HumanMessage

from app.agents.llm import get_llm
from app.agents.state import StockNews

if TYPE_CHECKING:
    from app.services.futu_client import FutuClient

log = logging.getLogger(__name__)

YAHOO_FALLBACK_LIMIT = 3
MAX_NEWS_PER_STOCK = 5

SENTIMENT_BATCH_PROMPT = """你是金融新闻情绪分析助手。给定以下新闻标题和摘要,对每条返回情绪分(-1=极负面,0=中性,1=极正面)和简短理由。

返回 JSON list,不要其它文字:
[{{"idx":0,"sentiment":0.7,"reason":"..."}}]

股票代码: {code}

新闻列表:
{news_block}
"""


def _parse_futu_code(futu_code: str) -> tuple[str, str] | None:
    if "." not in futu_code:
        return None
    market, symbol = futu_code.split(".", 1)
    return market.upper(), symbol


def _yahoo_rss_url(futu_code: str) -> str | None:
    parsed = _parse_futu_code(futu_code)
    if not parsed:
        return None
    market, symbol = parsed
    if market == "HK":
        num = symbol.lstrip("0") or "0"
        return (
            f"https://feeds.finance.yahoo.com/rss/2.0/headline"
            f"?s={num}.HK&region=HK&lang=zh-Hant-HK"
        )
    if market == "US":
        return (
            f"https://feeds.finance.yahoo.com/rss/2.0/headline"
            f"?s={symbol}&region=US&lang=en-US"
        )
    return None


def _parse_published_at(raw: str) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%b %d, %Y",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
    ):
        try:
            dt = datetime.strptime(raw.replace("Z", "+0000"), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _within_hours(published_at: str, hours: int) -> bool:
    if not published_at:
        return True
    dt = _parse_published_at(published_at)
    if dt is None:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return dt >= cutoff


def fetch_yahoo_rss_news(futu_code: str, limit: int = YAHOO_FALLBACK_LIMIT) -> list[dict]:
    """Yahoo Finance RSS fallback (used by NewsCollector and CLI --check)."""
    url = _yahoo_rss_url(futu_code)
    if not url:
        return []
    try:
        feed = feedparser.parse(
            url,
            agent="Mozilla/5.0 (compatible; StockWatch/1.0)",
            request_headers={"User-Agent": "Mozilla/5.0 (compatible; StockWatch/1.0)"},
        )
        if getattr(feed, "bozo", False) and not feed.entries:
            return []

        items: list[dict] = []
        for entry in feed.entries[:limit]:
            title = (entry.get("title") or "").strip()
            if not title:
                continue
            summary = (entry.get("description") or entry.get("summary") or "").strip()
            published_at = (entry.get("published") or entry.get("pubDate") or "").strip()
            pub_parsed = entry.get("published_parsed")
            if pub_parsed:
                try:
                    published_at = datetime.fromtimestamp(
                        mktime(pub_parsed), tz=timezone.utc
                    ).isoformat()
                except (OverflowError, OSError, ValueError):
                    pass
            items.append(
                {
                    "title": title[:500],
                    "summary": summary[:1500],
                    "published_at": published_at,
                    "url": (entry.get("link") or "")[:1000],
                    "source": "yahoo_rss",
                }
            )
        return items[:limit]
    except Exception as e:
        log.debug("Yahoo RSS fetch failed for %s: %s", futu_code, e)
        return []


def _fetch_futu_news(ctx, futu_code: str) -> list[dict]:
    # TODO: Futu OpenQuoteContext has no stock-news API in futu-api; wire here if added.
    for method_name in ("get_stock_news", "request_news", "get_news"):
        method = getattr(ctx, method_name, None)
        if not callable(method):
            continue
        try:
            ret, data = method(futu_code)
            from futu import RET_OK

            if ret != RET_OK or data is None:
                continue
            rows = data.to_dict("records") if hasattr(data, "to_dict") else list(data)
            out = []
            for row in rows:
                out.append(
                    {
                        "title": str(row.get("title") or row.get("news_title") or "")[:500],
                        "summary": str(row.get("summary") or row.get("content") or "")[:1500],
                        "published_at": str(
                            row.get("published_at") or row.get("time") or row.get("timestamp") or ""
                        ),
                        "source": "futu",
                    }
                )
            return out
        except Exception as e:
            log.debug("Futu %s failed for %s: %s", method_name, futu_code, e)
    return []


def _extract_json_list(text: str) -> list:
    text = (text or "").strip()
    if not text:
        return []
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


class NewsCollector:
    def __init__(self, futu_client: "FutuClient"):
        self.futu_client = futu_client

    def get_news(self, code: str, hours: int = 24) -> list[dict]:
        items: list[dict] = []
        try:
            self.futu_client.connect()
            if self.futu_client.ctx is not None:
                items = _fetch_futu_news(self.futu_client.ctx, code)
        except Exception as e:
            log.debug("Futu news unavailable for %s: %s", code, e)

        if not items:
            items = fetch_yahoo_rss_news(code)

        filtered = [n for n in items if _within_hours(n.get("published_at", ""), hours)]
        return filtered[:MAX_NEWS_PER_STOCK]

    def analyze_sentiment(
        self,
        news_items: list[dict],
        code: str,
        *,
        dry_run: bool = False,
    ) -> list[StockNews]:
        if not news_items:
            return []

        if dry_run:
            return [
                StockNews(
                    code=code,
                    title=item.get("title", ""),
                    summary=item.get("summary", ""),
                    sentiment=0.25,
                    published_at=item.get("published_at", ""),
                )
                for item in news_items
            ]

        lines = []
        for i, item in enumerate(news_items):
            lines.append(
                f"[{i}] 标题:{item.get('title', '')}\n摘要:{item.get('summary', '') or '(无)'}"
            )
        prompt = SENTIMENT_BATCH_PROMPT.format(code=code, news_block="\n\n".join(lines))

        scores: dict[int, float] = {}
        try:
            resp = get_llm().invoke([HumanMessage(content=prompt)])
            content = resp.content if hasattr(resp, "content") else str(resp)
            for row in _extract_json_list(content):
                try:
                    idx = int(row.get("idx"))
                    scores[idx] = max(-1.0, min(1.0, float(row.get("sentiment", 0))))
                except (TypeError, ValueError):
                    continue
        except Exception as e:
            log.warning("sentiment batch failed for %s: %s", code, e)

        result: list[StockNews] = []
        for i, item in enumerate(news_items):
            result.append(
                StockNews(
                    code=code,
                    title=item.get("title", ""),
                    summary=item.get("summary", ""),
                    sentiment=scores.get(i, 0.0),
                    published_at=item.get("published_at", ""),
                )
            )
        return result

    def collect_all(
        self,
        codes: list[str],
        *,
        dry_run: bool = False,
    ) -> dict[str, list[StockNews]]:
        if dry_run:
            out: dict[str, list[StockNews]] = {}
            for code in codes:
                mocks = [
                    {
                        "title": f"[dry-run] {code} 市场动态样例",
                        "summary": "用于验证数据流,不调用 LLM。",
                        "published_at": datetime.now(timezone.utc).isoformat(),
                    }
                ]
                out[code] = self.analyze_sentiment(mocks, code, dry_run=True)
            return out

        result: dict[str, list[StockNews]] = {}

        def work(stock_code: str) -> tuple[str, list[StockNews]]:
            raw = self.get_news(stock_code, hours=24)
            return stock_code, self.analyze_sentiment(raw, stock_code)

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(work, c) for c in codes]
            for fut in as_completed(futures):
                try:
                    code, analyzed = fut.result()
                    result[code] = analyzed
                except Exception as e:
                    log.warning("collect_all task failed: %s", e)

        return result
