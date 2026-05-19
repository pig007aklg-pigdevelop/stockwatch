"""价格扫描 + 信号生成 + 推送"""
import logging
from datetime import datetime
from app.db.models import get_session, Position, PriceSnapshot, Signal
from app.services.futu_client import futu
from app.services import telegram_bot
from app.jobs.signal_engine import evaluate, evaluate_watch, should_push

log = logging.getLogger(__name__)


def scan_once():
    """单次扫描所有持仓"""
    s = get_session()
    try:
        positions = s.query(Position).all()
        if not positions:
            log.info("No positions to scan.")
            return

        codes = list({p.futu_code for p in positions})
        log.info(f"Scanning {len(codes)} symbols...")
        snap = futu.get_snapshot(codes)
        if not snap:
            log.warning("Empty snapshot from Futu")
            return

        alerts = []
        for pos in positions:
            data = snap.get(pos.futu_code)
            if not data:
                continue
            price = data["price"]
            if price <= 0:
                continue

            # 写价格快照
            s.add(PriceSnapshot(
                symbol=pos.symbol,
                market=pos.market,
                price=price,
                change_pct=data["change_pct"],
                volume=data["volume"],
            ))

            # 评估：止损止盈
            ev = evaluate(pos, price)
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
                alerts.append((pos, ev, price))
                sig.pushed = 1
            s.add(sig)

            # 手工兜底 watch_below / watch_above
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
                    alerts.append((pos, wv, price))
                    wsig.pushed = 1
                s.add(wsig)

        s.commit()

        # 推送告警
        for pos, ev, price in alerts:
            text = (
                f"*{pos.market}.{pos.symbol}* {pos.name}\n"
                f"{ev['reason']}\n"
                f"持仓 {pos.quantity:g} @ {pos.cost_price:.2f}"
            )
            telegram_bot.send(text)
            log.info(f"Pushed alert for {pos.symbol}: {ev['action']}")

    except Exception as e:
        log.exception(f"scan_once error: {e}")
    finally:
        s.close()


def hourly_summary():
    """整点摘要"""
    s = get_session()
    try:
        positions = s.query(Position).all()
        if not positions:
            return
        # 拿每只最新价
        lines = [f"📊 *持仓摘要* {datetime.now().strftime('%m-%d %H:%M')}"]
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
            lines.append(
                f"{emoji} {pos.market}.{pos.symbol}: {latest.price:.2f} "
                f"({pnl_pct:+.2f}%) 日{latest.change_pct:+.2f}%"
            )
        lines.append(f"\n💰 总浮动盈亏: {total_pnl:+.2f}")
        telegram_bot.send("\n".join(lines))
    finally:
        s.close()
