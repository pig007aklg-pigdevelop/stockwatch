"""配置加载"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).parent.parent


class Config:
    # Telegram
    TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    # Futu
    FUTU_HOST = os.getenv("FUTU_HOST", "127.0.0.1")
    FUTU_PORT = int(os.getenv("FUTU_PORT", "11111"))

    # DB
    DB_PATH = os.getenv("DB_PATH", str(ROOT / "data" / "stockwatch.db"))

    # 推送策略
    HOURLY_SUMMARY = os.getenv("HOURLY_SUMMARY", "true").lower() == "true"
    SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))
    ALERT_COOLDOWN = int(os.getenv("ALERT_COOLDOWN_MINUTES", "60"))
    TZ = os.getenv("TZ", "Asia/Shanghai")

    # Web
    WEB_PORT = int(os.getenv("WEB_PORT", "8080"))
    WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")

    # LLM
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # News
    NEWS_INTERVAL = int(os.getenv("NEWS_INTERVAL_MINUTES", "30"))

    # Scoring (Phase 4.1)
    SCORE_OPPORTUNITY_THRESHOLD = float(os.getenv("SCORE_OPPORTUNITY_THRESHOLD", "30"))
    SCORING_ALERT_COOLDOWN_HOURS = int(os.getenv("SCORING_ALERT_COOLDOWN_HOURS", "24"))


config = Config()
