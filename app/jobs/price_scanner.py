"""价格扫描 + 信号生成 + 推送"""
from __future__ import annotations

import logging
from datetime import datetime
from app.db.models import get_session, Position, Watchlist, PriceSnapshot, Signal
from app.services.quote import snapshot as quote_snapshot
from app.services import telegram_bot
from app.jobs.signal_engine import evaluate, evaluate_watch, evaluate_watchlist_watch, should_push
from app.jobs.constants import ACTIONABLE
from app.config import config

log = logging.getLogger(__name__)


def _compute_weights(positions, snap) -> dict[int, float]:
    """返回 {position.id: weight}; 总市值=0 时返回空 dict (全 None)"""
    market_values: dict[int, float] = {}
    for p in positions:
        data = snap.get(p.futu_code) if snap else None
        px = data.get("price", 0) if data else 0
        price = px if px and px > 0 else p.cost_price
        market_values[p.id] = float(price) * float(p.quantity or 0)
    total = sum(market_values.values())
    if total <= 0:
        return {}
    return {pid: mv / total for pid, mv in market_values.items()}


def _scan_watchlist(session, watchlist, snap, alerts: list) -> None:
    """Watchlist: watch_below/above + recommended_buy → WATCH_BUY_HINT; 无盈亏/异动/止盈止损。"""
    for w in watchlist:
        try:
            _scan_watchlist_item(session, w, snap, alerts)
        except Exception as e:
            log.warning("scan watchlist %s.%s failed: %s", w.market, w.symbol, e)


def _scan_watchlist_item(session, w, snap, alerts: list) -> None:
    data = snap.get(w.futu_code)
    if not data:
        return
    price = data.get("price", 0)
    if price <= 0:
        return

    session.add(PriceSnapshot(
        symbol=w.symbol,
        market=w.market,
        price=price,
        change_pct=data["change_pct"],
        volume=data["volume"],
    ))

    wv = evaluate_watchlist_watch(w, price)
    if wv:
        wsig = Signal(
            symbol=w.symbol,
            market=w.market,
            action=wv["action"],
            price=price,
            cost_price=0.0,
            pnl_pct=0.0,
            reason=wv["reason"],
        )
        if should_push(w.symbol, wv["action"]):
            wsig.pushed = 1
            alerts.append((w, wv, price, wsig))
        session.add(wsig)

    if w.recommended_buy and price <= w.recommended_buy:
        score_txt = f",综合分 {w.composite_score:.0f}" if w.composite_score else ""
        reason = (
            f"🤖 跌至系统推荐买入价 {w.recommended_buy:.2f},"
            f"当前 {price:.2f}{score_txt} — 关注名单,可考虑建仓"
        )
        ev = {"action": "WATCH_BUY_HINT", "reason": reason, "pnl_pct": 0.0}
        hsig = Signal(
            symbol=w.symbol,
            market=w.market,
            action="WATCH_BUY_HINT",
            price=price,
            cost_price=0.0,
            pnl_pct=0.0,
            reason=reason,
        )
        if should_push(w.symbol, "WATCH_BUY_HINT"):
            hsig.pushed = 1
            alerts.append((w, ev, price, hsig))
        session.add(hsig)


def _scan_position(session, pos, snap, weight, alerts: list) -> None:
    data = snap.get(pos.futu_code)
    if not data:
        return
    price = data["price"]
    if price <= 0:
        return

    session.add(PriceSnapshot(
        symbol=pos.symbol,
        market=pos.market,
        price=price,
        change_pct=data["change_pct"],
        volume=data["volume"],
    ))

    ev = evaluate(pos, price, weight=weight)
    sig = Signal(
        symbol=pos.symbol,
        market=pos.market,
        action=ev["action"],
        price=price,
        cost_price=pos.cost_price,
        pnl_pct=ev["pnl_pct"],
        reason=ev["reason"],
    )
    if should_push(pos.symbol, ev["action"]):
        sig.pushed = 1
        alerts.append((pos, ev, price, sig))
    session.add(sig)

    day_change = data.get("change_pct", 0) or 0
    if abs(day_change) >= config.INTRADAY_MOVE_THRESHOLD:
        direction = "UP" if day_change > 0 else "DOWN"
        move_action = f"INTRADAY_MOVE_{direction}"
        emoji = "🚀" if direction == "UP" else "📉"
        move_reason = (
            f"{emoji} 日内异动 {day_change:+.2f}%,当前 {price:.2f} "
            f"— 关注是否有突发消息"
        )
        msig = Signal(
            symbol=pos.symbol,
            market=pos.market,
            action=move_action,
            price=price,
            cost_price=pos.cost_price,
            pnl_pct=ev["pnl_pct"],
            reason=move_reason,
        )
        if should_push(pos.symbol, move_action):
            msig.pushed = 1
            alerts.append((pos, {"action": move_action, "reason": move_reason, "pnl_pct": ev["pnl_pct"]}, price, msig))
        session.add(msig)

    wv = evaluate_watch(pos, price)
    if wv:
        wsig = Signal(
            symbol=pos.symbol,
            market=pos.market,
            action=wv["action"],
            price=price,
            cost_price=pos.cost_price,
            pnl_pct=wv["pnl_pct"],
            reason=wv["reason"],
        )
        if should_push(pos.symbol, wv["action"]):
            wsig.pushed = 1
            alerts.append((pos, wv, price, wsig))
        session.add(wsig)


def scan_once():
    """单次扫描持仓 + 关注名单"""
    s = get_session()
    try:
        positions = s.query(Position).all()
        watchlist = s.query(Watchlist).all()
        codes = list({p.futu_code for p in positions} | {w.futu_code for w in watchlist})
        if not codes:
            log.info("No positions or watchlist to scan.")
            return

        log.info(f"Scanning {len(codes)} symbols...")
        snap = quote_snapshot(codes)
        if not snap:
            log.warning("Empty snapshot from Futu")
            return

        weights = _compute_weights(positions, snap)
        alerts = []

        for pos in positions:
            try:
                _scan_position(s, pos, snap, weights.get(pos.id), alerts)
            except Exception as e:
                log.warning("scan position %s.%s failed: %s", pos.market, pos.symbol, e)

        _scan_watchlist(s, watchlist, snap, alerts)

        s.flush()
        s.commit()

        for rec, ev, price, sig in alerts:
            is_watch = isinstance(rec, Watchlist)
            prefix = "🔭 [关注] " if is_watch else ""
            text = (
                f"{prefix}*{rec.market}.{rec.symbol}* {rec.name}\n"
                f"{ev['reason']}"
            )
            if not is_watch:
                text += f"\n持仓 {rec.quantity:g} @ {rec.cost_price:.2f}"
            if ev["action"] in ACTIONABLE and sig.id:
                text += f"\n📝 用 UI 交易日志记录此次操作 (signal_id={sig.id})"
            telegram_bot.send(text)
            log.info(f"Pushed alert for {rec.symbol}: {ev['action']}")

    except Exception as e:
        log.exception(f"scan_once error: {e}")
    finally:
        s.close()


def hourly_summary(market_hint: str | None = None, phase: str = "open"):
    """
    market_hint: None=全部, "HK"=仅港股, "US"=仅美股
    phase: "open" 简短概览 / "close" 加上当日 P&L
    """
    s = get_session()
    try:
        q = s.query(Position)
        if market_hint:
            q = q.filter(Position.market == market_hint)
        positions = q.all()
        if not positions:
            return
        title_map = {
            ("HK", "open"): "🌅 港股开盘后摘要",
            ("HK", "close"): "🌇 港股收盘前摘要",
            ("US", "open"): "🌃 美股开盘后摘要",
            ("US", "close"): "🌄 美股收盘前摘要",
        }
        title = title_map.get((market_hint, phase), "📊 持仓摘要")
        lines = [f"{title} {datetime.now().strftime('%m-%d %H:%M')}"]
        total_pnl = 0.0
        for pos in positions:
            latest = (
                s.query(PriceSnapshot)
                .filter_by(symbol=pos.symbol)
                .order_by(PriceSnapshot.timestamp.desc())
                .first()
            )
            if not latest:
                continue
            pnl_pct = (latest.price - pos.cost_price) / pos.cost_price * 100
            pnl_abs = (latest.price - pos.cost_price) * pos.quantity
            total_pnl += pnl_abs
            emoji = "🟢" if pnl_pct >= 0 else "🔴"
            if phase == "close":
                lines.append(
                    f"{emoji} {pos.market}.{pos.symbol}: {latest.price:.2f} "
                    f"({pnl_pct:+.2f}%) 日{latest.change_pct:+.2f}%"
                )
            else:
                lines.append(
                    f"{emoji} {pos.market}.{pos.symbol}: {latest.price:.2f} "
                    f"({pnl_pct:+.2f}%)"
                )
        if phase == "close":
            lines.append(f"\n💰 总浮动盈亏: {total_pnl:+.2f}")
        telegram_bot.send("\n".join(lines))
    finally:
        s.close()
