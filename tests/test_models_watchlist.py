from sqlalchemy import text

from app.db.models import Watchlist
from app.db.migrate import run_migrations


def test_create_watchlist_record(session):
    w = Watchlist(
        symbol="NVDA",
        market="US",
        name="NVIDIA",
        watch_below=100.0,
        watch_above=200.0,
        notes="watch",
    )
    session.add(w)
    session.commit()
    session.refresh(w)
    assert w.id is not None
    assert w.futu_code == "US.NVDA"


def test_watchlist_no_cost_fields():
    assert not hasattr(Watchlist, "cost_price")
    assert not hasattr(Watchlist, "quantity")
    assert not hasattr(Watchlist, "stop_loss")
    assert not hasattr(Watchlist, "take_profit")


def test_migration_creates_watchlist_table(db_engine):
    run_migrations(db_engine)
    with db_engine.connect() as conn:
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        assert "watchlist" in tables
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(watchlist)"))}
        assert "recommended_buy" in cols
        assert "watch_below" in cols
