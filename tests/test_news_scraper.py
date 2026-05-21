import sys
from datetime import datetime
from unittest.mock import MagicMock

# feedparser 可能未装在本地 pytest 环境
sys.modules.setdefault("feedparser", MagicMock())

from app.db.models import News
from app.jobs.news_scraper import URL_MAX_LEN, fetch_for_symbol


def _fake_entry(link: str, title: str = "t"):
    return {
        "link": link,
        "title": title,
        "summary": "",
        "published_parsed": datetime.utcnow().timetuple(),
    }


def _patch_fetch(monkeypatch, session, feed_yahoo, feed_google=None):
    monkeypatch.setattr(
        "app.jobs.news_scraper.feedparser.parse",
        lambda url: feed_yahoo if "yahoo" in url else (feed_google or feed_yahoo),
    )
    monkeypatch.setattr(
        "app.jobs.news_scraper.filter_news",
        lambda items: (items, 0),
    )
    monkeypatch.setattr(
        "app.jobs.news_scraper.analyze_news",
        lambda title, summary, symbol, stats=None: {
            "summary": title,
            "sentiment": "neutral",
            "type": "事实",
            "confidence": 0.5,
        },
    )
    monkeypatch.setattr("app.jobs.news_scraper.get_session", lambda: session)


def test_two_same_urls_in_batch_inserts_one_no_exception(session, monkeypatch):
    """同批内 2 条相同 URL,只入库 1 条,commit 不抛 UNIQUE。"""
    dup_url = "https://finance.yahoo.com/article/same-story-batch"
    feed_yahoo = MagicMock(entries=[_fake_entry(dup_url, "Yahoo")])
    feed_google = MagicMock(entries=[_fake_entry(dup_url, "Google")])
    _patch_fetch(monkeypatch, session, feed_yahoo, feed_google)

    n = fetch_for_symbol("NVDA", "US", name="")
    assert n == 1
    assert session.query(News).filter_by(url=dup_url[:URL_MAX_LEN]).count() == 1


def test_long_url_truncated_on_insert(session, monkeypatch):
    long_url = "https://finance.yahoo.com/" + ("x" * 2000)
    feed = MagicMock(entries=[_fake_entry(long_url)])
    _patch_fetch(monkeypatch, session, feed)

    fetch_for_symbol("NVDA", "US")
    row = session.query(News).filter_by(symbol="NVDA").first()
    assert row is not None
    assert len(row.url) == URL_MAX_LEN
    assert row.url == long_url[:URL_MAX_LEN]


def test_duplicate_url_in_db_skips_without_error(session, monkeypatch):
    url1 = "https://finance.yahoo.com/a/one"
    url2 = "https://finance.yahoo.com/a/two"
    session.add(
        News(
            symbol="OLD",
            title="existing",
            url=url1[:URL_MAX_LEN],
            source="x",
            summary="",
            published_at=datetime.utcnow(),
        )
    )
    session.commit()

    feed = MagicMock(
        entries=[
            _fake_entry(url1, "dup in db"),
            _fake_entry(url2, "new"),
        ]
    )
    _patch_fetch(monkeypatch, session, feed)

    n = fetch_for_symbol("NVDA", "US")
    assert n == 1
    assert session.query(News).filter_by(symbol="NVDA", url=url2[:URL_MAX_LEN]).count() == 1
