"""新闻源白名单过滤。"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from app.config import config

log = logging.getLogger(__name__)

NEWS_WHITELIST_HK_US = {
    "reuters.com",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "cnbc.com",
    "marketwatch.com",
    "seekingalpha.com",
    "barrons.com",
    "investors.com",
    "cls.cn",
    "stcn.com",
    "yicai.com",
    "caixin.com",
    "21jingji.com",
    "jiemian.com",
    "hkej.com",
    "scmp.com",
}

_whitelist_cache: set[str] | None = None


def _build_whitelist() -> set[str]:
    domains = set(NEWS_WHITELIST_HK_US)
    extra = (config.NEWS_WHITELIST_EXTRA or "").strip()
    if extra:
        for part in extra.split(","):
            d = part.strip().lower()
            if d.startswith("www."):
                d = d[4:]
            if d:
                domains.add(d)
    return domains


def get_whitelist_domains() -> set[str]:
    global _whitelist_cache
    if _whitelist_cache is None:
        _whitelist_cache = _build_whitelist()
    return _whitelist_cache


def reset_whitelist_cache() -> None:
    """测试用: 配置变更后重建白名单。"""
    global _whitelist_cache
    _whitelist_cache = None


def extract_domain(url: str) -> str | None:
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return None
    try:
        host = urlparse(url).netloc or urlparse(url).path
        if not host:
            return None
        host = host.lower().split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        return host or None
    except Exception:
        return None


def is_whitelisted(url: str) -> bool:
    """从 url 提取 domain,去掉 www. 前缀,匹配白名单。"""
    if not config.NEWS_WHITELIST_ENABLED:
        return True
    domain = extract_domain(url)
    if not domain:
        return False
    allowed = get_whitelist_domains()
    for w in allowed:
        if domain == w or domain.endswith("." + w):
            return True
    return False


def filter_news(items: list[dict]) -> tuple[list[dict], int]:
    """返回 (保留的, 丢弃数)。item 需含 url 字段。"""
    if not config.NEWS_WHITELIST_ENABLED:
        return items, 0
    kept: list[dict] = []
    dropped = 0
    for item in items:
        url = item.get("url") or item.get("link") or ""
        if is_whitelisted(url):
            kept.append(item)
        else:
            dropped += 1
    if dropped or kept:
        log.info("news.filter dropped=%s kept=%s", dropped, len(kept))
    return kept, dropped
