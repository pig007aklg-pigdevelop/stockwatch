import pytest

from app.config import config
from app.services import news_filter


@pytest.fixture(autouse=True)
def reset_whitelist():
    news_filter.reset_whitelist_cache()
    yield
    news_filter.reset_whitelist_cache()


def test_reuters_variants_whitelisted():
    for url in (
        "https://reuters.com/article/1",
        "https://www.reuters.com/markets/1",
        "https://m.reuters.com/world/1",
    ):
        assert news_filter.is_whitelisted(url) is True


def test_toutiao_dropped():
    assert news_filter.is_whitelisted("https://www.toutiao.com/article/123") is False


def test_invalid_url_dropped_not_crash():
    assert news_filter.is_whitelisted("") is False
    assert news_filter.is_whitelisted("not-a-url") is False
    items = [{"url": ""}, {"url": "ftp://bad"}, {"title": "no url"}]
    kept, dropped = news_filter.filter_news(items)
    assert kept == []
    assert dropped == 3


def test_whitelist_disabled_passes_all(monkeypatch):
    monkeypatch.setattr(config, "NEWS_WHITELIST_ENABLED", False)
    news_filter.reset_whitelist_cache()
    items = [
        {"url": "https://xxx.toutiao.com/x"},
        {"url": "https://reuters.com/x"},
    ]
    kept, dropped = news_filter.filter_news(items)
    assert len(kept) == 2
    assert dropped == 0
