from datetime import datetime

from sqlalchemy import text

from app.db.models import Position, Signal, Trade
from app.db.migrate import run_migrations


def test_trade_create_and_link_to_position(session):
    p = Position(symbol="00700", market="HK", cost_price=300.0, quantity=100)
    session.add(p)
    session.commit()

    t = Trade(
        symbol=p.symbol,
        market=p.market,
        side="BUY",
        price=300.0,
        quantity=100,
        traded_at=datetime.utcnow(),
    )
    session.add(t)
    session.flush()
    p.last_trade_id = t.id
    session.commit()

    session.refresh(p)
    assert p.last_trade_id == t.id
    assert session.get(Trade, t.id).symbol == "00700"


def test_trade_link_to_signal(session):
    sig = Signal(
        symbol="NVDA",
        market="US",
        action="TAKE_PROFIT",
        price=150.0,
        cost_price=100.0,
        pnl_pct=50.0,
        reason="test",
    )
    session.add(sig)
    session.commit()

    t = Trade(
        symbol="NVDA",
        market="US",
        side="SELL",
        price=150.0,
        quantity=10,
        realized_pnl=500.0,
        holding_days=30,
        linked_signal_id=sig.id,
        traded_at=datetime.utcnow(),
    )
    session.add(t)
    session.flush()
    sig.acted_trade_id = t.id
    session.commit()

    session.refresh(sig)
    assert sig.acted_trade_id == t.id
    assert session.get(Trade, t.id).linked_signal_id == sig.id


def test_migration_adds_trade_columns(db_engine):
    run_migrations(db_engine)
    with db_engine.connect() as conn:
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        assert "trades" in tables
        pos_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(positions)"))}
        sig_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(signals)"))}
        assert "last_trade_id" in pos_cols
        assert "acted_trade_id" in sig_cols
