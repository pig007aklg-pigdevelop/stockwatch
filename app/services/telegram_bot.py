"""Telegram 推送 - 用 httpx 直接调 Bot API,避免长链接复杂度"""
import logging
import httpx
from app.config import config

log = logging.getLogger(__name__)

API = f"https://api.telegram.org/bot{config.TG_TOKEN}"


def send(text: str, parse_mode: str = "Markdown") -> bool:
    if not config.TG_TOKEN or not config.TG_CHAT_ID:
        log.warning("Telegram not configured; printing instead:\n%s", text)
        return False
    try:
        r = httpx.post(
            f"{API}/sendMessage",
            json={
                "chat_id": config.TG_CHAT_ID,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        if r.status_code != 200:
            log.error("Telegram send failed: %s %s", r.status_code, r.text)
            return False
        return True
    except Exception as e:
        log.error("Telegram error: %s", e)
        return False
