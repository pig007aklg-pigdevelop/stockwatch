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
from app.db.models import get_session, Position, News
from app.services.llm_client import summarize_news

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
    # Google News 中英搜索都加上
    query = f"{symbol} {name}".strip() if name else symbol
    urls.append(("Google", _google_news_url(query + " 股票")))

    new_count = 0
    s = get_session()
    try:
        for source, url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:10]:
                    link = entry.get("link", "")
                    if not link:
                        continue
                    exists = s.query(News).filter_by(url=link).first()
                    if exists:
                        continue
                    pub = entry.get("published_parsed")
                    pub_dt = datetime.fromtimestamp(mktime(pub)) if pub else datetime.utcnow()
                    title = entry.get("title", "")
                    # 摘要(LLM 可选)
                    sm = summarize_news(title, entry.get("summary", ""), symbol)
                    s.add(News(
                        symbol=symbol,
                        title=title[:500],
                        url=link[:1000],
                        source=source,
                        summary=sm["summary"],
                        sentiment=sm["sentiment"],
                        published_at=pub_dt,
                    ))
                    new_count += 1
            except Exception as e:
                log.warning("fetch %s/%s failed: %s", symbol, source, e)
        s.commit()
    finally:
        s.close()
    return new_count


def fetch_all():
    """抓所有持仓的新闻"""
    s = get_session()
    try:
        positions = s.query(Position).all()
    finally:
        s.close()
    total = 0
    for p in positions:
        n = fetch_for_symbol(p.symbol, p.market, p.name)
        total += n
        log.info("News %s: +%d", p.symbol, n)
    log.info("Total new news: %d", total)
    return total
