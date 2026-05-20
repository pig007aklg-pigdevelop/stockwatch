from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from app.config import config
from app.db.models import Position, Watchlist, Signal, PriceSnapshot
from app.jobs.price_scanner import _compute_weights, scan_once, hourly_summary


def _pos(pid: int, futu_code: str, cost: float, qty: float) -> Position:
    p = Position(symbol="X", market="US", cost_price=cost, quantity=qty)
    p.id = pid
    # models.Position.futu_code uses market/symbol; we override for tests
    p.market = futu_code.split(".", 1)[0]
    p.symbol = futu_code.split(".", 1)[1]
    return p


def test_compute_weights_basic():
    p1 = _pos(1, "US.AAA", 10.0, 10)  # mv 100
    p2 = _pos(2, "US.BBB", 10.0, 10)  # mv 100
    snap = {
        "US.AAA": {"price": 10.0},
        "US.BBB": {"price": 10.0},
    }
    weights = _compute_weights([p1, p2], snap)
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    assert abs(weights[1] - 0.5) < 1e-6
    assert abs(weights[2] - 0.5) < 1e-6


def test_compute_weights_empty_snap_falls_back_to_cost():
    p1 = _pos(1, "US.AAA", 10.0, 10)  # 100
    p2 = _pos(2, "US.BBB", 30.0, 10)  # 300
    weights = _compute_weights([p1, p2], snap={})
    assert abs(weights[1] - 0.25) < 1e-6
    assert abs(weights[2] - 0.75) < 1e-6


def test_compute_weights_zero_total_returns_empty():
    p1 = _pos(1, "US.AAA", 10.0, 0)
    p2 = _pos(2, "US.BBB", 30.0, 0)
    weights = _compute_weights([p1, p2], snap={})
    assert weights == {}


def _mk_session_factory(session):
    Session = sessionmaker(bind=session.get_bind())

    def _get_session():
        return Session()

    return _get_session


def test_intraday_move_up_triggers_signal(session, monkeypatch):
    p = Position(symbol="AAA", market="US", cost_price=100.0, quantity=1)
    session.add(p)
    session.commit()

    snap = {
        p.futu_code: {"price": 100.0, "change_pct": 3.5, "volume": 1},
    }

    monkeypatch.setattr("app.jobs.price_scanner.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.signal_engine.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.price_scanner.futu.get_snapshot", lambda codes: snap)
    monkeypatch.setattr("app.jobs.price_scanner.telegram_bot.send", lambda text: True)

    scan_once()
    s2 = sessionmaker(bind=session.get_bind())()
    try:
        sig = s2.query(Signal).filter_by(action="INTRADAY_MOVE_UP", symbol="AAA").first()
        assert sig is not None
    finally:
        s2.close()


def test_intraday_move_down_triggers_signal(session, monkeypatch):
    p = Position(symbol="BBB", market="US", cost_price=100.0, quantity=1)
    session.add(p)
    session.commit()

    snap = {
        p.futu_code: {"price": 100.0, "change_pct": -4.0, "volume": 1},
    }

    monkeypatch.setattr("app.jobs.price_scanner.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.signal_engine.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.price_scanner.futu.get_snapshot", lambda codes: snap)
    monkeypatch.setattr("app.jobs.price_scanner.telegram_bot.send", lambda text: True)

    scan_once()
    s2 = sessionmaker(bind=session.get_bind())()
    try:
        sig = s2.query(Signal).filter_by(action="INTRADAY_MOVE_DOWN", symbol="BBB").first()
        assert sig is not None
    finally:
        s2.close()


def test_intraday_move_below_threshold_no_signal(session, monkeypatch):
    p = Position(symbol="CCC", market="US", cost_price=100.0, quantity=1)
    session.add(p)
    session.commit()

    snap = {
        p.futu_code: {"price": 100.0, "change_pct": 2.0, "volume": 1},
    }

    monkeypatch.setattr("app.jobs.price_scanner.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.signal_engine.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.price_scanner.futu.get_snapshot", lambda codes: snap)
    monkeypatch.setattr("app.jobs.price_scanner.telegram_bot.send", lambda text: True)

    scan_once()
    s2 = sessionmaker(bind=session.get_bind())()
    try:
        sig = s2.query(Signal).filter(Signal.action.like("INTRADAY_MOVE_%")).first()
        assert sig is None
    finally:
        s2.close()


def test_intraday_move_respects_cooldown(session, monkeypatch):
    p = Position(symbol="DDD", market="US", cost_price=100.0, quantity=1)
    session.add(p)
    session.commit()

    # Seed a recent pushed signal within cooldown window
    session.add(
        Signal(
            symbol="DDD",
            market="US",
            action="INTRADAY_MOVE_UP",
            price=100.0,
            cost_price=100.0,
            pnl_pct=0.0,
            reason="prev",
            pushed=1,
            created_at=datetime.utcnow() - timedelta(minutes=config.ALERT_COOLDOWN) + timedelta(minutes=1),
        )
    )
    session.commit()

    snap = {
        p.futu_code: {"price": 100.0, "change_pct": 3.5, "volume": 1},
    }

    monkeypatch.setattr("app.jobs.price_scanner.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.signal_engine.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.price_scanner.futu.get_snapshot", lambda codes: snap)
    sent = {"count": 0}
    monkeypatch.setattr(
        "app.jobs.price_scanner.telegram_bot.send",
        lambda text: sent.__setitem__("count", sent["count"] + 1) or True,
    )

    scan_once()
    assert sent["count"] == 0


def test_hourly_summary_filters_by_market(session, monkeypatch):
    hk = Position(symbol="00700", market="HK", cost_price=300.0, quantity=1)
    us = Position(symbol="NVDA", market="US", cost_price=100.0, quantity=1)
    session.add_all([hk, us])
    session.commit()

    session.add_all(
        [
            PriceSnapshot(symbol="00700", market="HK", price=310.0, change_pct=1.0, volume=1),
            PriceSnapshot(symbol="NVDA", market="US", price=110.0, change_pct=2.0, volume=1),
        ]
    )
    session.commit()

    monkeypatch.setattr("app.jobs.price_scanner.get_session", _mk_session_factory(session))
    captured = {"text": ""}
    monkeypatch.setattr("app.jobs.price_scanner.telegram_bot.send", lambda text: captured.__setitem__("text", text) or True)

    hourly_summary(market_hint="HK", phase="open")
    assert "HK.00700" in captured["text"]
    assert "US.NVDA" not in captured["text"]


def test_actionable_signal_has_trade_log_hint(session, monkeypatch):
    p = Position(symbol="AAA", market="US", cost_price=100.0, quantity=1, stop_loss=95.0)
    session.add(p)
    session.commit()

    snap = {p.futu_code: {"price": 94.0, "change_pct": 0.5, "volume": 1}}
    sent_texts = []

    monkeypatch.setattr("app.jobs.price_scanner.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.signal_engine.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.price_scanner.futu.get_snapshot", lambda codes: snap)
    monkeypatch.setattr(
        "app.jobs.price_scanner.telegram_bot.send",
        lambda text: sent_texts.append(text) or True,
    )

    scan_once()
    assert any("交易日志" in t for t in sent_texts)
    assert any("signal_id=" in t for t in sent_texts)


def test_intraday_move_no_trade_log_hint(session, monkeypatch):
    p = Position(symbol="EEE", market="US", cost_price=100.0, quantity=1)
    session.add(p)
    session.commit()

    snap = {p.futu_code: {"price": 100.0, "change_pct": 4.0, "volume": 1}}
    sent_texts = []

    monkeypatch.setattr("app.jobs.price_scanner.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.signal_engine.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.price_scanner.futu.get_snapshot", lambda codes: snap)
    monkeypatch.setattr(
        "app.jobs.price_scanner.telegram_bot.send",
        lambda text: sent_texts.append(text) or True,
    )

    scan_once()
    assert sent_texts
    assert not any("交易日志" in t for t in sent_texts)


def test_watchlist_recommended_buy_triggers_watch_buy_hint(session, monkeypatch):
    w = Watchlist(symbol="WATCH", market="US", name="W", recommended_buy=50.0)
    session.add(w)
    session.commit()

    snap = {w.futu_code: {"price": 48.0, "change_pct": 0.5, "volume": 1}}
    sent_texts = []

    monkeypatch.setattr("app.jobs.price_scanner.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.signal_engine.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.price_scanner.futu.get_snapshot", lambda codes: snap)
    monkeypatch.setattr(
        "app.jobs.price_scanner.telegram_bot.send",
        lambda text: sent_texts.append(text) or True,
    )

    scan_once()
    sig = session.query(Signal).filter_by(symbol="WATCH", action="WATCH_BUY_HINT").first()
    assert sig is not None
    assert any("建仓" in t or "WATCH_BUY_HINT" in str(sent_texts) or "交易日志" in t for t in sent_texts)


def test_watchlist_does_not_emit_intraday_move(session, monkeypatch):
    w = Watchlist(symbol="MOVE", market="US", name="M")
    session.add(w)
    session.commit()

    snap = {w.futu_code: {"price": 10.0, "change_pct": 5.0, "volume": 1}}

    monkeypatch.setattr("app.jobs.price_scanner.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.signal_engine.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.price_scanner.futu.get_snapshot", lambda codes: snap)
    monkeypatch.setattr("app.jobs.price_scanner.telegram_bot.send", lambda text: True)

    scan_once()
    assert session.query(Signal).filter_by(symbol="MOVE", action="INTRADAY_MOVE_UP").first() is None


def test_watchlist_does_not_emit_stop_loss(session, monkeypatch):
    w = Watchlist(symbol="SAFE", market="US", name="S", watch_below=5.0)
    session.add(w)
    session.commit()

    snap = {w.futu_code: {"price": 100.0, "change_pct": 0.0, "volume": 1}}

    monkeypatch.setattr("app.jobs.price_scanner.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.signal_engine.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.price_scanner.futu.get_snapshot", lambda codes: snap)
    monkeypatch.setattr("app.jobs.price_scanner.telegram_bot.send", lambda text: True)

    scan_once()
    assert session.query(Signal).filter_by(symbol="SAFE", action="STOP_LOSS").first() is None


def test_position_and_watchlist_share_snapshot_table(session, monkeypatch):
    p = Position(symbol="POS", market="US", cost_price=10.0, quantity=1)
    w = Watchlist(symbol="WL", market="US", name="WL")
    session.add_all([p, w])
    session.commit()

    snap = {
        p.futu_code: {"price": 10.0, "change_pct": 0.0, "volume": 1},
        w.futu_code: {"price": 20.0, "change_pct": 0.0, "volume": 1},
    }

    monkeypatch.setattr("app.jobs.price_scanner.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.signal_engine.get_session", _mk_session_factory(session))
    monkeypatch.setattr("app.jobs.price_scanner.futu.get_snapshot", lambda codes: snap)
    monkeypatch.setattr("app.jobs.price_scanner.telegram_bot.send", lambda text: True)

    scan_once()
    assert session.query(PriceSnapshot).filter_by(symbol="POS").count() >= 1
    assert session.query(PriceSnapshot).filter_by(symbol="WL").count() >= 1

