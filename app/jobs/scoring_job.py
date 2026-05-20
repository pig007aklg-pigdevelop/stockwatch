"""日终综合打分 — 工作日 06:00 更新持仓并 Telegram 推送。"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta

from app.config import config
from app.db.models import get_session, Position, Watchlist, Signal
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
        watchlist = s.query(Watchlist).all()
        all_records = [(p, "POSITION") for p in positions] + [(w, "WATCHLIST") for w in watchlist]
        if not all_records:
            log.info("No records for scoring.")
            return

        updated_pos = []
        updated_watch = []
        for i, (rec, kind) in enumerate(all_records):
            if i > 0:
                time.sleep(INTER_STOCK_SLEEP)

            result = call_with_timeout(
                scoring.score_position,
                SCORE_POSITION_TIMEOUT,
                rec.market,
                rec.symbol,
            )
            if result is None:
                log.warning(
                    "Score skipped %s.%s (timeout or error)",
                    rec.market,
                    rec.symbol,
                )
                continue
            try:
                scoring.apply_result_to_record(rec, result)
                if kind == "POSITION":
                    updated_pos.append(rec)
                else:
                    updated_watch.append(rec)
                log.info(
                    "Scored %s.%s composite=%s",
                    rec.market,
                    rec.symbol,
                    result.composite,
                )
            except Exception as e:
                log.warning(
                    "Score apply failed %s.%s: %s",
                    rec.market,
                    rec.symbol,
                    e,
                )

        s.commit()
        updated = updated_pos + updated_watch
        if updated:
            _send_top5_report(updated)
            _send_score_alerts(s, updated)
    except Exception as e:
        log.exception("run_daily_scoring impl error: %s", e)
        s.rollback()
    finally:
        s.close()


def _record_tag(rec) -> str:
    return "[关]" if isinstance(rec, Watchlist) else "[持]"


def _send_top5_report(records: list) -> None:
    ranked = sorted(
        [r for r in records if r.composite_score is not None],
        key=lambda r: r.composite_score,
        reverse=True,
    )[:5]
    if not ranked:
        return
    lines = [f"📊 *综合打分 Top5* {datetime.now().strftime('%m-%d')}"]
    for r in ranked:
        rb = f"{r.recommended_buy:.2f}" if r.recommended_buy else "-"
        rs = f"{r.recommended_sell:.2f}" if r.recommended_sell else "-"
        lines.append(
            f"• {_record_tag(r)} {r.market}.{r.symbol} {r.name or ''} "
            f"分 *{r.composite_score:.0f}* 买{rb}/卖{rs}"
        )
    telegram_bot.send("\n".join(lines))


def _send_score_alerts(session, records: list) -> None:
    """根据综合分推送两类信号:
       - composite >= OPPORTUNITY_THRESHOLD → SCORE_OPPORTUNITY (💎 低估机会)
       - composite <  RISK_THRESHOLD        → SCORE_RISK         (⚠️ 风险警报)
    """
    opp_thr = config.SCORE_OPPORTUNITY_THRESHOLD
    risk_thr = config.SCORE_RISK_THRESHOLD
    cooldown = timedelta(hours=config.SCORING_ALERT_COOLDOWN_HOURS)
    cutoff = datetime.utcnow() - cooldown

    for rec in records:
        if rec.composite_score is None:
            continue

        is_watch = isinstance(rec, Watchlist)
        cost_price = getattr(rec, "cost_price", None) or 0.0

        if rec.composite_score >= opp_thr:
            action = "SCORE_OPPORTUNITY"
            title = "💎 低估机会"
            verb = "建仓" if is_watch else "加仓"
            extra = (
                f"建议关注买入价 {rec.recommended_buy:.2f}({verb})"
                if rec.recommended_buy
                else ""
            )
        elif rec.composite_score < risk_thr:
            action = "SCORE_RISK"
            title = "⚠️ 风险警报"
            extra = f"建议关注卖出价 {rec.recommended_sell:.2f}" if rec.recommended_sell else ""
        else:
            continue

        recent = (
            session.query(Signal)
            .filter(
                Signal.symbol == rec.symbol,
                Signal.market == rec.market,
                Signal.action == action,
                Signal.created_at >= cutoff,
                Signal.pushed == 1,
            )
            .first()
        )
        if recent:
            continue

        tag = _record_tag(rec)
        text = (
            f"{title} {tag} {rec.market}.{rec.symbol} {rec.name or ''}\n"
            f"综合分 _{rec.composite_score:.0f}_  "
            f"估值{rec.score_valuation or '-'} 基本面{rec.score_fundamental or '-'}\n"
            f"{extra}"
        ).strip()

        telegram_bot.send(text)
        sig = Signal(
            symbol=rec.symbol,
            market=rec.market,
            action=action,
            price=0.0,
            cost_price=cost_price,
            pnl_pct=0.0,
            reason=text,
            pushed=1,
        )
        session.add(sig)
    session.commit()
