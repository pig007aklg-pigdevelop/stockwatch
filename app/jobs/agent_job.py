"""Scheduled multi-agent analysis jobs."""
from __future__ import annotations

import logging

from app.agents.runner import run_agent_pipeline

log = logging.getLogger(__name__)


def run_hk_premarket() -> None:
    log.info("Agent job: HK premarket (08:30)")
    run_agent_pipeline("hk", notify=True)


def run_hk_midday() -> None:
    log.info("Agent job: HK midday (12:30)")
    run_agent_pipeline("hk", notify=True)


def run_us_premarket() -> None:
    log.info("Agent job: US premarket (21:00)")
    run_agent_pipeline("us", notify=True)
