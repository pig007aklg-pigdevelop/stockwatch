"""Run the full agent pipeline (CLI / scheduled jobs)."""
from __future__ import annotations

import logging
import traceback

from app.agents.graph import build_graph
from app.agents.notify import send_alert, send_pipeline_message
from app.agents.repository import save_agent_picks

log = logging.getLogger(__name__)

MARKET_LABELS = {"hk": "港股", "us": "美股"}


def run_agent_pipeline(
    market: str,
    *,
    notify: bool = False,
    dry_run: bool = False,
) -> dict:
    from app.services.futu_client import futu

    mkt = (market or "hk").lower()
    initial = {
        "market": mkt,
        "candidates": [],
        "news": {},
        "technical": {},
        "market_view": "",
        "trader_picks": [],
        "risk_assessment": [],
        "consensus_picks": [],
        "final_picks": [],
    }

    futu.connect()
    try:
        graph = build_graph()
        result = graph.invoke(
            initial,
            config={"configurable": {"dry_run": dry_run}},
        )
        if notify and not dry_run:
            send_pipeline_message(mkt, result)
        save_agent_picks(mkt, result.get("final_picks") or [])
        return result
    except Exception as e:
        label = MARKET_LABELS.get(mkt, mkt)
        msg = f"{label} pipeline 失败: {e}\n{traceback.format_exc()[-800:]}"
        log.exception("run_agent_pipeline failed: %s", e)
        if notify:
            send_alert(msg)
        raise
    finally:
        futu.close()
