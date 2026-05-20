"""信号引擎 - 基于成本/止盈/止损价生成动作建议"""
from __future__ import annotations

from datetime import datetime, timedelta
from app.db.models import get_session, Position, PriceSnapshot, Signal
from app.config import config


TIER_THRESHOLDS: dict[str, tuple[float, float]] = {
    "HEAVY": (-5.0, 15.0),
    "NORMAL": (-8.0, 20.0),
    "LIGHT": (-12.0, 30.0),
}


def classify_tier(weight: float | None) -> str:
    """根据仓位市值权重返回档位名。weight 为 None 时按 NORMAL 处理。"""
    if weight is None:
        return "NORMAL"
    if weight >= config.HEAVY_POSITION_THRESHOLD:
        return "HEAVY"
    if weight < config.LIGHT_POSITION_THRESHOLD:
        return "LIGHT"
    return "NORMAL"


def evaluate(pos: Position, price: float, weight: float | None = None) -> dict:
    """
    返回 {action, reason, pnl_pct, tier}
    action: HOLD / TAKE_PROFIT / STOP_LOSS / ALERT

    weight: 仓位市值占总持仓市值的比例 (0-1),用于分档兜底阈值
    """
    pnl_pct = (price - pos.cost_price) / pos.cost_price * 100
    tier = classify_tier(weight)
    loss_thr, gain_thr = TIER_THRESHOLDS[tier]

    action = "HOLD"
    reason = f"当前 {price:.2f},成本 {pos.cost_price:.2f},盈亏 {pnl_pct:+.2f}%"

    if pos.stop_loss and price <= pos.stop_loss:
        action = "STOP_LOSS"
        reason = f"⛔️ 触发止损 {pos.stop_loss:.2f},当前 {price:.2f},亏损 {pnl_pct:+.2f}% — 建议离场"
    elif pos.take_profit and price >= pos.take_profit:
        action = "TAKE_PROFIT"
        reason = f"🎯 触达止盈 {pos.take_profit:.2f},当前 {price:.2f},盈利 {pnl_pct:+.2f}% — 建议落袋"
    elif pnl_pct <= loss_thr:
        action = "ALERT"
        reason = (
            f"⚠️ [{tier}] 浮亏已 {pnl_pct:+.2f}%(档位线 {loss_thr:.0f}%) "
            f"— 关注"
        )
    elif pnl_pct >= gain_thr:
        action = "ALERT"
        reason = (
            f"🔥 [{tier}] 浮盈已 {pnl_pct:+.2f}%(档位线 +{gain_thr:.0f}%) "
            f"— 考虑分批止盈"
        )

    return {"action": action, "reason": reason, "pnl_pct": pnl_pct, "tier": tier}


def evaluate_watch(pos: Position, price: float) -> dict | None:
    """
    手工兜底 + 系统推荐价兜底。
    优先级: watch_below/above (手填) > recommended_buy/sell (系统算)
    """
    pnl_pct = (price - pos.cost_price) / pos.cost_price * 100 if pos.cost_price else 0

    if pos.watch_below is not None and price <= pos.watch_below:
        return {
            "action": "WATCH_BUY",
            "reason": (
                f"📉 跌破关注下限 {pos.watch_below:.2f},当前 {price:.2f} — 手工兜底买入关注"
            ),
            "pnl_pct": pnl_pct,
        }
    if pos.watch_above is not None and price >= pos.watch_above:
        return {
            "action": "WATCH_SELL",
            "reason": (
                f"📈 突破关注上限 {pos.watch_above:.2f},当前 {price:.2f} — 手工兜底卖出关注"
            ),
            "pnl_pct": pnl_pct,
        }

    if pos.watch_below is None and pos.recommended_buy and price <= pos.recommended_buy:
        score_txt = f",综合分 {pos.composite_score:.0f}" if pos.composite_score else ""
        return {
            "action": "AUTO_BUY_HINT",
            "reason": (
                f"🤖 跌至系统推荐买入价 {pos.recommended_buy:.2f},"
                f"当前 {price:.2f}{score_txt} — 可考虑分批吸纳"
            ),
            "pnl_pct": pnl_pct,
        }
    if pos.watch_above is None and pos.recommended_sell and price >= pos.recommended_sell:
        score_txt = f",综合分 {pos.composite_score:.0f}" if pos.composite_score else ""
        return {
            "action": "AUTO_SELL_HINT",
            "reason": (
                f"🤖 涨至系统推荐卖出价 {pos.recommended_sell:.2f},"
                f"当前 {price:.2f}{score_txt} — 可考虑分批减仓"
            ),
            "pnl_pct": pnl_pct,
        }
    return None


def should_push(symbol: str, action: str) -> bool:
    """避免刷屏: 同 symbol 同 action 在冷却期内不重复推"""
    if action == "HOLD":
        return False
    s = get_session()
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=config.ALERT_COOLDOWN)
        recent = (
            s.query(Signal)
            .filter(
                Signal.symbol == symbol,
                Signal.action == action,
                Signal.created_at >= cutoff,
                Signal.pushed == 1,
            )
            .first()
        )
        return recent is None
    finally:
        s.close()
