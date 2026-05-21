from app.db.models import Position
from app.jobs.signal_engine import (
    classify_tier,
    evaluate_watch,
    evaluate,
)


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


def test_classify_tier_heavy():
    assert classify_tier(0.50) == "HEAVY"


def test_classify_tier_light():
    assert classify_tier(0.05) == "LIGHT"


def test_classify_tier_normal():
    assert classify_tier(0.20) == "NORMAL"


def test_classify_tier_none_defaults_normal():
    assert classify_tier(None) == "NORMAL"


def test_heavy_position_triggers_alert_at_minus_5():
    pos = make_pos(cost_price=100)
    r = evaluate(pos, 94, weight=0.5)  # -6% on heavy
    assert r["action"] == "ALERT"
    assert r["tier"] == "HEAVY"


def test_light_position_no_alert_at_minus_8():
    pos = make_pos(cost_price=100)
    r = evaluate(pos, 92, weight=0.05)  # -8% on light: 阈值是 -12%
    assert r["action"] == "HOLD"
    assert r["tier"] == "LIGHT"


def test_stop_loss_independent_of_tier():
    pos = make_pos(cost_price=100, stop_loss=95)
    r = evaluate(pos, 94, weight=0.5)
    assert r["action"] == "STOP_LOSS"


def test_evaluate_zero_cost_returns_hold():
    pos = make_pos(cost_price=0)
    r = evaluate(pos, 100.0)
    assert r["action"] == "HOLD"
    assert r["pnl_pct"] == 0.0


def test_evaluate_watch_zero_cost_returns_none():
    pos = make_pos(cost_price=0, watch_below=90)
    assert evaluate_watch(pos, 85) is None
