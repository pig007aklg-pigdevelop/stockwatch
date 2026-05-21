"""数据保留 — 定期清理历史 signals / snapshots / news / scores。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from app.config import config
from app.db.models import Signal, PriceSnapshot, News, engine

log = logging.getLogger(__name__)

_TABLE_SPECS = (
    ("signals", Signal, "created_at", config.RETENTION_SIGNALS_DAYS),
    ("price_snapshots", PriceSnapshot, "timestamp", config.RETENTION_PRICE_SNAPSHOTS_DAYS),
    ("news", News, "created_at", config.RETENTION_NEWS_DAYS),
    ("scores", None, "created_at", config.RETENTION_SCORES_DAYS),
)


def _table_exists(session: Session, name: str) -> bool:
    row = session.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": name},
    ).first()
    return row is not None


def _delete_old_rows(session: Session, table: str, model, date_col: str, days: int) -> int:
    cutoff = datetime.utcnow() - timedelta(days=days)
    if model is None:
        if not _table_exists(session, table):
            log.info(
                "retention.cleanup table=%s deleted=0 cutoff=%s (table missing)",
                table,
                cutoff.isoformat(),
            )
            return 0
        result = session.execute(
            text(f"DELETE FROM {table} WHERE {date_col} < :cutoff"),
            {"cutoff": cutoff},
        )
    else:
        col = getattr(model, date_col)
        result = session.execute(delete(model).where(col < cutoff))
    deleted = result.rowcount if result.rowcount is not None else 0
    log.info(
        "retention.cleanup table=%s deleted=%s cutoff=%s",
        table,
        deleted,
        cutoff.isoformat(),
    )
    return deleted


def _run_vacuum() -> None:
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("VACUUM"))
    log.info("retention.vacuum completed")


def cleanup_old_data(db: Session) -> dict:
    """
    清理 N 天前的数据,返回各表删除行数。
    返回: {"signals": 123, "price_snapshots": 456, "news": 78, "scores": 0}
    """
    counts: dict[str, int] = {}
    for table, model, date_col, days in _TABLE_SPECS:
        try:
            counts[table] = _delete_old_rows(db, table, model, date_col, days)
        except Exception as e:
            log.exception(
                "retention.cleanup table=%s failed: %s",
                table,
                e,
            )
            counts[table] = 0

    try:
        db.commit()
    except Exception as e:
        log.exception("retention.commit failed: %s", e)
        db.rollback()
        raise

    if config.RETENTION_VACUUM:
        try:
            _run_vacuum()
        except Exception as e:
            log.exception("retention.vacuum failed: %s", e)

    return counts


def run_retention_cleanup() -> dict:
    """调度入口: 自建 session 执行清理。"""
    from app.db.models import get_session

    s = get_session()
    try:
        return cleanup_old_data(s)
    finally:
        s.close()
