from app.jobs.price_scanner import _compute_weights
from app.db.models import Position


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

