"""日终综合打分 — 工作日 06:00 更新持仓并 Telegram 推送。"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta

from app.config import config
from app.db.models import get_session, Position, Signal
from app.services import scoring, telegram_bot
from app.services.external_call import (
    INTER_STOCK_SLEEP,
    SCORE_POSITION_TIMEOUT,
    call_with_timeout,
)

log = logging.getLogger(__name__)

_scoring_lock = threading.Lock()


def scoring_in_progress() -> bool:
    return _scoring_lock.locked()


def run_daily_scoring() -> bool:
    """
    批量打分。全局锁保证同一时间仅一个任务。
    返回 True 表示本次执行完成，False 表示已有任务在跑而跳过。
    """
    if not _scoring_lock.acquire(blocking=False):
        log.warning("Scoring task already running, skipped")
        return False
    try:
        _run_daily_scoring_impl()
        return True
    except Exception as e:
        log.exception("run_daily_scoring error: %s", e)
        return False
    finally:
        _scoring_lock.release()


def _run_daily_scoring_impl() -> None:
    s = get_session()
    try:
        positions = s.query(Position).all()
        if not positions:
            log.info("No positions for scoring.")
            return

        updated = []
        for i, pos in enumerate(positions):
            if i > 0:
                time.sleep(INTER_STOCK_SLEEP)

            result = call_with_timeout(
                scoring.score_position,
                SCORE_POSITION_TIMEOUT,
                pos.market,
                pos.symbol,
            )
            if result is None:
                log.warning(
                    "Score skipped %s.%s (timeout or error)",
                    pos.market,
                    pos.symbol,
                )
                continue
            try:
                scoring.apply_result_to_position(pos, result)
                updated.append(pos)
                log.info(
                    "Scored %s.%s composite=%s",
                    pos.market,
                    pos.symbol,
                    result.composite,
                )
            except Exception as e:
                log.warning(
                    "Score apply failed %s.%s: %s",
                    pos.market,
                    pos.symbol,
                    e,
                )

        s.commit()
        if updated:
            _send_top5_report(updated)
            _send_opportunity_alerts(s, updated)
    except Exception as e:
        log.exception("run_daily_scoring impl error: %s", e)
        s.rollback()
    finally:
        s.close()


def _send_top5_report(positions: list) -> None:
    ranked = sorted(
        [p for p in positions if p.composite_score is not None],
        key=lambda p: p.composite_score,
        reverse=True,
    )[:5]
    if not ranked:
        return
    lines = [f"📊 *综合打分 Top5* {datetime.now().strftime('%m-%d')}"]
    for p in ranked:
        rb = f"{p.recommended_buy:.2f}" if p.recommended_buy else "-"
        rs = f"{p.recommended_sell:.2f}" if p.recommended_sell else "-"
        lines.append(
            f"• {p.market}.{p.symbol} {p.name or ''} "
            f"分 *{p.composite_score:.0f}* 买{rb}/卖{rs}"
        )
    telegram_bot.send("\n".join(lines))


def _send_opportunity_alerts(session, positions: list) -> None:
    threshold = config.SCORE_OPPORTUNITY_THRESHOLD
    cooldown = timedelta(hours=config.SCORING_ALERT_COOLDOWN_HOURS)
    cutoff = datetime.utcnow() - cooldown

    for pos in positions:
        if pos.composite_score is None or pos.composite_score >= threshold:
            continue
        recent = (
            session.query(Signal)
            .filter(
                Signal.symbol == pos.symbol,
                Signal.market == pos.market,
                Signal.action == "SCORE_OPPORTUNITY",
                Signal.created_at >= cutoff,
                Signal.pushed == 1,
            )
            .first()
        )
        if recent:
            continue
        text = (
            f"💎 *低估机会* {pos.market}.{pos.symbol} {pos.name or ''}\n"
            f"综合分 *{pos.composite_score:.0f}* < {threshold:.0f}\n"
            f"推荐买 {pos.recommended_buy or '-'} / 卖 {pos.recommended_sell or '-'}"
        )
        telegram_bot.send(text)
        session.add(
            Signal(
                symbol=pos.symbol,
                market=pos.market,
                action="SCORE_OPPORTUNITY",
                price=0,
                cost_price=pos.cost_price,
                pnl_pct=0,
                reason=f"综合分 {pos.composite_score:.0f} 跌破 {threshold:.0f}",
                pushed=1,
            )
        )
    session.commit()
