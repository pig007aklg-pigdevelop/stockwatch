from app.db.models import Position
from app.services.concentration import compute_hhi


def test_single_position_full_concentration():
    p = Position(symbol="BABA", market="US", cost_price=100.0, quantity=1000)
    prices = {"US.BABA": 100.0}
    r = compute_hhi([p], prices)
    assert r["hhi"] == 1.0
    assert r["level"] == "high"
    assert r["top1_weight"] == 1.0
    assert "严重集中" in r["advice"]


def test_five_equal_positions_low_concentration():
    positions = [
        Position(symbol=f"S{i}", market="US", cost_price=10.0, quantity=100)
        for i in range(5)
    ]
    prices = {p.futu_code: 10.0 for p in positions}
    r = compute_hhi(positions, prices)
    assert abs(r["hhi"] - 0.2) < 1e-6
    assert r["level"] == "mid"
    assert abs(r["top1_weight"] - 0.2) < 1e-6
    assert r["advice"] == "✅ 分散度尚可"


def test_baba_heavy_portfolio_triggers_top1_warning():
    """BABA 1800 股 @ $110 — 单票占组合绝大部分。"""
    baba = Position(symbol="BABA", market="US", cost_price=110.0, quantity=1800)
    other = Position(symbol="NVDA", market="US", cost_price=500.0, quantity=10)
    prices = {"US.BABA": 110.0, "US.NVDA": 500.0}
    r = compute_hhi([baba, other], prices)
    baba_value = 110.0 * 1800 * 7.2
    nvda_value = 500.0 * 10 * 7.2
    expected_top1 = baba_value / (baba_value + nvda_value)
    assert expected_top1 >= 0.65
    assert r["top1_weight"] >= 0.65
    assert "BABA" in r["advice"]
    assert "严重集中" in r["advice"]
