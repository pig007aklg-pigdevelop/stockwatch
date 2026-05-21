"""持仓集中度 — HHI 与权重建议。"""
from __future__ import annotations

from app.config import config
from app.db.models import Position


def _fx_rate(market: str) -> float:
    if market == "US":
        return config.FX_USD_CNY
    if market == "HK":
        return config.FX_HKD_CNY
    return 1.0


def _hhi_level(hhi: float) -> str:
    if hhi > config.HHI_HIGH_THRESHOLD:
        return "high"
    if hhi >= config.HHI_MID_THRESHOLD:
        return "mid"
    return "low"


def compute_hhi(positions: list[Position], prices: dict[str, float]) -> dict:
    """
    prices: futu_code → 现价 (如 {"US.BABA": 110.0})

    返回 hhi, level, total_value_cny, weights, top1_weight, top3_weight, advice
    """
    empty = {
        "hhi": 0.0,
        "level": "low",
        "total_value_cny": 0.0,
        "weights": [],
        "top1_weight": 0.0,
        "top3_weight": 0.0,
        "advice": "✅ 分散度尚可",
    }
    if not positions:
        return empty

    rows: list[dict] = []
    for p in positions:
        price = prices.get(p.futu_code) or prices.get(p.symbol) or p.cost_price
        if not price or price <= 0:
            price = p.cost_price
        value_native = float(price) * float(p.quantity or 0)
        value_cny = value_native * _fx_rate(p.market)
        code = f"{p.market}.{p.symbol}"
        rows.append({"code": code, "value_cny": value_cny})

    total = sum(r["value_cny"] for r in rows)
    if total <= 0:
        return empty

    for r in rows:
        r["weight"] = r["value_cny"] / total

    rows.sort(key=lambda x: x["weight"], reverse=True)
    weights = [
        {"code": r["code"], "weight": r["weight"], "value_cny": r["value_cny"]}
        for r in rows
    ]
    hhi = sum(r["weight"] ** 2 for r in rows)
    top1_weight = rows[0]["weight"]
    top3_weight = sum(r["weight"] for r in rows[:3])
    top1_code = rows[0]["code"]

    if top1_weight > config.TOP1_WARN_THRESHOLD:
        pct = int(round(top1_weight * 100))
        advice = (
            f"⚠️ {top1_code} 占比 {pct}%,严重集中,建议拆分到 3-5 只"
        )
    elif hhi > config.HHI_HIGH_THRESHOLD:
        advice = f"🟡 组合偏集中(HHI={hhi:.2f})"
    else:
        advice = "✅ 分散度尚可"

    return {
        "hhi": round(hhi, 4),
        "level": _hhi_level(hhi),
        "total_value_cny": round(total, 2),
        "weights": weights,
        "top1_weight": round(top1_weight, 4),
        "top3_weight": round(top3_weight, 4),
        "advice": advice,
    }
