from app.db.models import Position
from app.jobs.signal_engine import evaluate_watch, evaluate


def make_pos(**kwargs) -> Position:
    base = dict(symbol="NVDA", market="US", cost_price=100)
    base.update(kwargs)
    return Position(**base)


def test_evaluate_watch_below():
    pos = Position(
        symbol="NVDA", market="US", cost_price=100,
        watch_below=90, watch_above=None,
    )
    r = evaluate_watch(pos, 85)
    assert r["action"] == "WATCH_BUY"


def test_evaluate_watch_above():
    pos = Position(
        symbol="NVDA", market="US", cost_price=100,
        watch_below=None, watch_above=150,
    )
    r = evaluate_watch(pos, 160)
    assert r["action"] == "WATCH_SELL"


def test_evaluate_watch_no_trigger():
    pos = Position(symbol="NVDA", market="US", cost_price=100, watch_below=80)
    assert evaluate_watch(pos, 100) is None


def test_evaluate_stop_loss_unchanged():
    pos = Position(symbol="X", market="US", cost_price=100, stop_loss=90)
    r = evaluate(pos, 85)
    assert r["action"] == "STOP_LOSS"


def test_auto_buy_hint_when_no_manual_watch():
    pos = make_pos(recommended_buy=92, watch_below=None)
    r = evaluate_watch(pos, 91)
    assert r["action"] == "AUTO_BUY_HINT"


def test_auto_sell_hint_when_no_manual_watch():
    pos = make_pos(recommended_sell=120, watch_above=None)
    r = evaluate_watch(pos, 121)
    assert r["action"] == "AUTO_SELL_HINT"


def test_manual_watch_takes_priority_over_recommended():
    pos = make_pos(recommended_buy=92, watch_below=95)
    r = evaluate_watch(pos, 94)
    assert r["action"] == "WATCH_BUY"


def test_no_signal_when_neither_set():
    pos = make_pos(recommended_buy=None, watch_below=None)
    assert evaluate_watch(pos, 80) is None
