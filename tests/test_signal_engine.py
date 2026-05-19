from app.db.models import Position
from app.jobs.signal_engine import evaluate_watch, evaluate


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
