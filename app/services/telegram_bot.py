"""Telegram 推送 - 用 httpx 直接调 Bot API,避免长链接复杂度"""
from __future__ import annotations

import logging
from typing import Optional

import httpx
from app.config import config

log = logging.getLogger(__name__)

API = f"https://api.telegram.org/bot{config.TG_TOKEN}"


def _post_message(text: str, parse_mode: Optional[str]) -> httpx.Response:
    payload: dict = {
        "chat_id": config.TG_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return httpx.post(f"{API}/sendMessage", json=payload, timeout=10)


def send(text: str, parse_mode: Optional[str] = None) -> bool:
    if not config.TG_TOKEN or not config.TG_CHAT_ID:
        log.warning("Telegram not configured; printing instead:\n%s", text)
        return False
    try:
        r = _post_message(text, parse_mode)
        if r.status_code == 400 and parse_mode:
            log.warning("Telegram send 400 with parse_mode=%s, retrying plain text", parse_mode)
            r = _post_message(text, None)
        if r.status_code != 200:
            log.error("Telegram send failed: %s %s", r.status_code, r.text)
            return False
        return True
    except Exception as e:
        log.error("Telegram error: %s", e)
        return False
