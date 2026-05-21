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
    SCORE_OPPORTUNITY_THRESHOLD = float(os.getenv("SCORE_OPPORTUNITY_THRESHOLD", "70"))
    SCORE_RISK_THRESHOLD = float(os.getenv("SCORE_RISK_THRESHOLD", "30"))
    SCORING_ALERT_COOLDOWN_HOURS = int(os.getenv("SCORING_ALERT_COOLDOWN_HOURS", "24"))

    # Position weight tiers (Phase 4.2)
    HEAVY_POSITION_THRESHOLD = float(os.getenv("HEAVY_POSITION_THRESHOLD", "0.30"))
    LIGHT_POSITION_THRESHOLD = float(os.getenv("LIGHT_POSITION_THRESHOLD", "0.10"))

    # Intraday move alert (Phase 4.3)
    INTRADAY_MOVE_THRESHOLD = float(os.getenv("INTRADAY_MOVE_THRESHOLD", "3.0"))  # 百分比

    # Concentration / FX (P3-1)
    FX_USD_CNY = float(os.getenv("FX_USD_CNY", "7.2"))
    FX_HKD_CNY = float(os.getenv("FX_HKD_CNY", "0.93"))
    HHI_HIGH_THRESHOLD = float(os.getenv("HHI_HIGH_THRESHOLD", "0.25"))
    HHI_MID_THRESHOLD = float(os.getenv("HHI_MID_THRESHOLD", "0.15"))
    TOP1_WARN_THRESHOLD = float(os.getenv("TOP1_WARN_THRESHOLD", "0.5"))

    # Data retention (P3-2)
    RETENTION_SIGNALS_DAYS = int(os.getenv("RETENTION_SIGNALS_DAYS", "90"))
    RETENTION_PRICE_SNAPSHOTS_DAYS = int(os.getenv("RETENTION_PRICE_SNAPSHOTS_DAYS", "90"))
    RETENTION_NEWS_DAYS = int(os.getenv("RETENTION_NEWS_DAYS", "180"))
    RETENTION_SCORES_DAYS = int(os.getenv("RETENTION_SCORES_DAYS", "180"))
    RETENTION_VACUUM = os.getenv("RETENTION_VACUUM", "true").lower() == "true"

    # Quote provider (akshare | futu)
    QUOTE_PROVIDER = os.getenv("QUOTE_PROVIDER", "akshare").lower()

    # News whitelist (P4-1)
    NEWS_WHITELIST_ENABLED = os.getenv("NEWS_WHITELIST_ENABLED", "true").lower() == "true"
    NEWS_WHITELIST_EXTRA = os.getenv("NEWS_WHITELIST_EXTRA", "")

    # Sentiment LLM cache (P4-1)
    SENTIMENT_CACHE_ENABLED = os.getenv("SENTIMENT_CACHE_ENABLED", "true").lower() == "true"


config = Config()
