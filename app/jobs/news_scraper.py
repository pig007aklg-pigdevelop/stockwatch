"""新闻聚合 - 雪球/财联社/Google News RSS

各 RSS 源:
- 雪球个股: https://xueqiu.com/statuses/stock_timeline.json (反爬,改用 Google News)
- Google News 按 ticker: https://news.google.com/rss/search?q={ticker}+stock
- 财联社全局: https://www.cls.cn/nodeapi/telegraphList (有反爬)
- Yahoo Finance per-symbol RSS: https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US

Phase 2 优先级:
1. Yahoo Finance(美股) - 稳定
2. Google News(中文+英文) - 通用
"""
import logging
from datetime import datetime
from time import mktime
import feedparser
from sqlalchemy.exc import IntegrityError

from app.db.models import get_session, Position, Watchlist, News
from app.services.news_filter import filter_news
from app.services.sentiment import analyze_news, SentimentBatchStats

log = logging.getLogger(__name__)


def _yahoo_url(symbol: str) -> str:
    return f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"


def _google_news_url(query: str) -> str:
    import urllib.parse
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=zh-CN&gl=CN&ceid=CN:zh"


def fetch_for_symbol(symbol: str, market: str, name: str = "") -> int:
    """抓某只股票的新闻,返回新增数量"""
    urls = []
    if market == "US":
        urls.append(("Yahoo", _yahoo_url(symbol)))
    query = f"{symbol} {name}".strip() if name else symbol
    urls.append(("Google", _google_news_url(query + " 股票")))

    raw_items: list[dict] = []
    for source, feed_url in urls:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:10]:
                link = entry.get("link", "")
                if not link:
                    continue
                raw_items.append({
                    "url": link,
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", ""),
                    "source": source,
                    "published_parsed": entry.get("published_parsed"),
                })
        except Exception as e:
            log.warning("fetch %s/%s failed: %s", symbol, source, e)

    kept_items, _dropped = filter_news(raw_items)
    stats = SentimentBatchStats()
    new_count = 0
    seen_in_batch: set[str] = set()
    s = get_session()
    try:
        for item in kept_items:
            link_truncated = (item.get("url") or "")[:1000]
            if not link_truncated:
                continue
            if link_truncated in seen_in_batch:
                continue
            if s.query(News).filter_by(url=link_truncated).first():
                continue
            seen_in_batch.add(link_truncated)

            pub = item.get("published_parsed")
            pub_dt = datetime.fromtimestamp(mktime(pub)) if pub else datetime.utcnow()
            title = item.get("title", "") or ""
            analysis = analyze_news(
                title,
                item.get("summary", "") or "",
                symbol,
                stats=stats,
            )
            row = News(
                symbol=symbol,
                title=title[:500],
                url=link_truncated,
                source=item.get("source", ""),
                summary=analysis.get("summary", title[:200]),
                sentiment=analysis.get("sentiment", "neutral"),
                sentiment_type=analysis.get("type", "事实"),
                sentiment_confidence=analysis.get("confidence"),
                published_at=pub_dt,
            )
            try:
                with s.begin_nested():
                    s.add(row)
                    s.flush()
                new_count += 1
            except IntegrityError:
                log.debug(
                    "news duplicate url skipped symbol=%s url=%s",
                    symbol,
                    link_truncated[:80],
                )
                continue
        s.commit()
    finally:
        s.close()

    if stats.total > 0:
        log.info(
            "sentiment.batch total=%s cache_hit=%s llm_call=%s",
            stats.total,
            stats.cache_hit,
            stats.llm_call,
        )
    return new_count


def fetch_all():
    """抓所有持仓与关注名单的新闻"""
    s = get_session()
    try:
        positions = s.query(Position).all()
        watchlist = s.query(Watchlist).all()
    finally:
        s.close()
    total = 0
    for r in list(positions) + list(watchlist):
        n = fetch_for_symbol(r.symbol, r.market, r.name)
        total += n
        log.info("News %s: +%d", r.symbol, n)
    log.info("Total new news: %d", total)
    return total
