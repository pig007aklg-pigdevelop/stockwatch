"""Telegram message formatting for agent pipeline (uses telegram_bot.send)."""
from __future__ import annotations

from app.services import telegram_bot

MARKET_LABELS = {"hk": "港股", "us": "美股"}


def format_message(market: str, result: dict) -> str:
    label = MARKET_LABELS.get((market or "hk").lower(), market)
    market_view = (result.get("market_view") or "").strip()
    final_picks = result.get("final_picks") or []

    lines = [f"📊 StockWatch 多智能体 | {label}", ""]
    if market_view:
        lines.append("🌐 大盘观察")
        lines.append(market_view[:600])
        lines.append("")

    if not final_picks:
        lines.append("今日无通过风控的推荐标的。")
        return "\n".join(lines)

    lines.append(f"✅ 推荐 {len(final_picks)} 只")
    for p in final_picks:
        rank = p.get("rank", "?")
        code = p.get("code", "")
        name = p.get("name") or code
        score = p.get("score")
        price = p.get("price")
        bl = p.get("buy_range_low")
        bh = p.get("buy_range_high")
        sl = p.get("stop_loss")
        tg = p.get("target")
        lines.append("")
        lines.append(f"{rank}. {name} ({code}) 分{score:.0f}" if score is not None else f"{rank}. {name} ({code})")
        if price is not None:
            lines.append(f"   现价 {price:.2f}")
        if bl is not None and bh is not None:
            lines.append(f"   买入 {bl:.2f} ~ {bh:.2f}")
        if sl is not None:
            lines.append(f"   止损 {sl:.2f}")
        if tg is not None:
            lines.append(f"   目标 {tg:.2f}")
        tv = (p.get("tech_view") or "").strip()
        rv = (p.get("risk_view") or "").strip()
        if tv:
            lines.append(f"   技术: {tv[:120]}")
        if rv:
            lines.append(f"   风控: {rv[:120]}")

    return "\n".join(lines)


def send_pipeline_message(market: str, result: dict) -> bool:
    text = format_message(market, result)
    return telegram_bot.send(text)


def send_alert(text: str) -> bool:
    return telegram_bot.send(f"🚨 Agent pipeline\n{text}")
