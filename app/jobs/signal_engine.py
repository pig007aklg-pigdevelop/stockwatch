"""信号引擎 - 基于成本/止盈/止损价生成动作建议"""
from datetime import datetime, timedelta
from app.db.models import get_session, Position, PriceSnapshot, Signal
from app.config import config


def evaluate(pos: Position, price: float) -> dict:
    """
    返回 {action, reason, pnl_pct}
    action: HOLD / TAKE_PROFIT / STOP_LOSS / ALERT
    """
    pnl_pct = (price - pos.cost_price) / pos.cost_price * 100

    action = "HOLD"
    reason = f"当前 {price:.2f},成本 {pos.cost_price:.2f},盈亏 {pnl_pct:+.2f}%"

    if pos.stop_loss and price <= pos.stop_loss:
        action = "STOP_LOSS"
        reason = f"⛔️ 触发止损 {pos.stop_loss:.2f},当前 {price:.2f},亏损 {pnl_pct:+.2f}% — 建议离场"
    elif pos.take_profit and price >= pos.take_profit:
        action = "TAKE_PROFIT"
        reason = f"🎯 触达止盈 {pos.take_profit:.2f},当前 {price:.2f},盈利 {pnl_pct:+.2f}% — 建议落袋"
    elif pnl_pct <= -8:
        action = "ALERT"
        reason = f"⚠️ 浮亏已 {pnl_pct:+.2f}%,接近警戒线 — 关注"
    elif pnl_pct >= 20:
        action = "ALERT"
        reason = f"🔥 浮盈已 {pnl_pct:+.2f}% — 考虑分批止盈"

    return {"action": action, "reason": reason, "pnl_pct": pnl_pct}


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
