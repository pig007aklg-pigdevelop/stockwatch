"""SQLite 增量迁移 — 对已有库 ADD COLUMN，幂等可重复执行。"""
import logging
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

# (table, column, sqlite_type)
MIGRATION_COLUMNS = [
    ("positions", "watch_below", "REAL"),
    ("positions", "watch_above", "REAL"),
    ("positions", "composite_score", "REAL"),
    ("positions", "score_valuation", "REAL"),
    ("positions", "score_capital", "REAL"),
    ("positions", "score_technical", "REAL"),
    ("positions", "score_fundamental", "REAL"),
    ("positions", "score_news", "REAL"),
    ("positions", "score_updated_at", "DATETIME"),
    ("positions", "recommended_buy", "REAL"),
    ("positions", "recommended_sell", "REAL"),
    ("positions", "last_trade_id", "INTEGER"),
    ("signals", "acted_trade_id", "INTEGER"),
    ("news", "sentiment_type", "TEXT"),
    ("news", "sentiment_confidence", "REAL"),
]

# 向后兼容
POSITION_COLUMNS = MIGRATION_COLUMNS


def _existing_columns(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {r[1] for r in rows}


def run_migrations(engine: Engine) -> None:
    with engine.begin() as conn:
        for table, column, col_type in MIGRATION_COLUMNS:
            existing = _existing_columns(conn, table)
            if column in existing:
                continue
            sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
            conn.execute(text(sql))
            log.info("Migration: added %s.%s", table, column)

    from app.db.models import Base

    Base.metadata.create_all(engine)
