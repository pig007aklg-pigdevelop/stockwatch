"""Persist agent pipeline results to SQLite."""
from __future__ import annotations

import json
import logging
from datetime import datetime

from app.db.models import AgentPick, get_session

log = logging.getLogger(__name__)


def save_agent_picks(
    market: str,
    final_picks: list[dict],
    *,
    run_at: datetime | None = None,
) -> int:
    """Insert one row per pick. Returns number of rows written."""
    if not final_picks:
        return 0

    ts = run_at or datetime.utcnow()
    mkt = (market or "hk").lower()
    session = get_session()
    try:
        for pick in final_picks:
            row = AgentPick(
                market=mkt,
                run_at=ts,
                rank=int(pick.get("rank") or 0),
                code=str(pick.get("code") or ""),
                name=str(pick.get("name") or ""),
                price=pick.get("price"),
                score=pick.get("score"),
                buy_range_low=pick.get("buy_range_low"),
                buy_range_high=pick.get("buy_range_high"),
                stop_loss=pick.get("stop_loss"),
                target=pick.get("target"),
                tech_view=str(pick.get("tech_view") or ""),
                risk_view=str(pick.get("risk_view") or ""),
                market_view=str(pick.get("market_view") or ""),
                news_sentiment_avg=pick.get("news_sentiment_avg"),
                raw_json=json.dumps(pick, ensure_ascii=False, default=str),
            )
            session.add(row)
        session.commit()
        log.info("save_agent_picks: market=%s rows=%d", mkt, len(final_picks))
        return len(final_picks)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
