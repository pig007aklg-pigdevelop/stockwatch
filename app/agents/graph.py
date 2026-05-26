"""LangGraph pipeline for multi-agent stock analysis (Stage 1)."""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from app.agents.market_analyst import market_analyst_node
from app.agents.news import NewsCollector
from app.agents.risk_officer import risk_officer_node
from app.agents.state import AgentState
from app.agents.technical import scan_candidates
from app.agents.trader import trader_node
from app.services.futu_client import futu
from app.services.index_constituents import (
    get_hk_tech_constituents,
    get_us_nasdaq100_constituents,
)

log = logging.getLogger(__name__)


def _dry_run_from_config(config: RunnableConfig) -> bool:
    return bool((config.get("configurable") or {}).get("dry_run"))


def fetch_candidates_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    _ = config
    market = (state.get("market") or "hk").lower()
    if market == "us":
        candidates = get_us_nasdaq100_constituents()
    else:
        candidates = get_hk_tech_constituents()
    log.info("fetch_candidates: market=%s count=%d", market, len(candidates))
    return {"candidates": candidates}


def collect_news_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    candidates = state.get("candidates") or []
    dry_run = _dry_run_from_config(config)
    collector = NewsCollector(futu)
    news = collector.collect_all(candidates, dry_run=dry_run)
    total_items = sum(len(v) for v in news.values())
    log.info("collect_news: stocks=%d news_items=%d dry_run=%s", len(news), total_items, dry_run)
    return {"news": news}


def technical_scan_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    _ = config
    market = (state.get("market") or "hk").lower()
    candidates = state.get("candidates") or []
    technical = scan_candidates(market, candidates)
    log.info("technical_scan: market=%s scanned=%d", market, len(technical))
    return {"technical": technical}


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("fetch_candidates", fetch_candidates_node)
    graph.add_node("collect_news", collect_news_node)
    graph.add_node("technical_scan", technical_scan_node)
    graph.add_node("market_analyst", market_analyst_node)
    graph.add_node("trader", trader_node)
    graph.add_node("risk_officer", risk_officer_node)

    graph.set_entry_point("fetch_candidates")
    graph.add_edge("fetch_candidates", "collect_news")
    graph.add_edge("collect_news", "technical_scan")
    graph.add_edge("technical_scan", "market_analyst")
    graph.add_edge("market_analyst", "trader")
    graph.add_edge("trader", "risk_officer")
    graph.add_edge("risk_officer", END)

    return graph.compile()
