import sys
from datetime import datetime
from unittest.mock import MagicMock

# feedparser 可能未装在本地 pytest 环境
sys.modules.setdefault("feedparser", MagicMock())

from app.db.models import News
from app.jobs.news_scraper import fetch_for_symbol


def _fake_entry(link: str, title: str = "t"):
    return {
        "link": link,
        "title": title,
        "summary": "",
        "published_parsed": datetime.utcnow().timetuple(),
    }


def test_two_same_urls_in_batch_inserts_one_no_exception(session, monkeypatch):
    """同批内 2 条相同 URL,只入库 1 条,commit 不抛 UNIQUE。"""
    dup_url = "https://finance.yahoo.com/article/same-story-batch"
    feed_yahoo = MagicMock(entries=[_fake_entry(dup_url, "Yahoo")])
    feed_google = MagicMock(entries=[_fake_entry(dup_url, "Google")])

    monkeypatch.setattr(
        "app.jobs.news_scraper.feedparser.parse",
        lambda url: feed_yahoo if "yahoo" in url else feed_google,
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

    n = fetch_for_symbol("NVDA", "US", name="")
    assert n == 1
    assert session.query(News).filter_by(url=dup_url[:1000]).count() == 1
    session.commit()


def test_expunge_after_integrity_error_allows_commit(session):
    """savepoint 回滚后 expunge,避免失败对象在 commit 时再次 flush。"""
    from sqlalchemy.exc import IntegrityError

    url = "https://dup.test/existing"
    session.add(
        News(
            symbol="OLD",
            title="seed",
            url=url,
            source="x",
            summary="",
            published_at=datetime.utcnow(),
        )
    )
    session.commit()

    dup_obj = News(
        symbol="NEW",
        title="dup",
        url=url,
        source="x",
        summary="",
        published_at=datetime.utcnow(),
    )
    ok_obj = News(
        symbol="NEW",
        title="ok",
        url="https://dup.test/other",
        source="x",
        summary="",
        published_at=datetime.utcnow(),
    )
    try:
        with session.begin_nested():
            session.add(dup_obj)
    except IntegrityError:
        if dup_obj in session:
            session.expunge(dup_obj)
    session.add(ok_obj)
    session.commit()
    assert session.query(News).filter_by(symbol="NEW").count() == 1


def test_fetch_dedups_same_url_within_batch(session, monkeypatch):
    dup_url = "https://finance.yahoo.com/article/same-story"
    feed_yahoo = MagicMock(entries=[_fake_entry(dup_url, "Yahoo")])
    feed_google = MagicMock(entries=[_fake_entry(dup_url, "Google")])

    monkeypatch.setattr(
        "app.jobs.news_scraper.feedparser.parse",
        lambda url: feed_yahoo if "yahoo" in url else feed_google,
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

    n = fetch_for_symbol("NVDA", "US", name="")
    assert n == 1
    assert session.query(News).filter_by(url=dup_url[:1000]).count() == 1


def test_fetch_integrity_error_skips_row_and_continues(session, monkeypatch):
    url1 = "https://finance.yahoo.com/a/one"
    url2 = "https://finance.yahoo.com/a/two"
    session.add(
        News(
            symbol="OLD",
            title="existing",
            url=url1[:1000],
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
    monkeypatch.setattr("app.jobs.news_scraper.feedparser.parse", lambda url: feed)
    monkeypatch.setattr("app.jobs.news_scraper.filter_news", lambda items: (items, 0))
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

    n = fetch_for_symbol("NVDA", "US")
    assert n == 1
    assert session.query(News).filter_by(symbol="NVDA", url=url2[:1000]).count() == 1
