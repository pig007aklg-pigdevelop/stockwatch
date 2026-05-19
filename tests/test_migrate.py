from app.db.migrate import run_migrations
from sqlalchemy import text


def test_migrations_idempotent(db_engine):
    run_migrations(db_engine)
    run_migrations(db_engine)
    with db_engine.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(positions)"))}
    assert "composite_score" in cols
    assert "watch_below" in cols
    assert "recommended_sell" in cols
