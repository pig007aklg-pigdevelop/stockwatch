"""Trader analyst agent node (Stage 1 stub)."""
from app.agents.state import AgentState


def trader_node(state: AgentState) -> dict:
    # TODO(Stage 2): rank candidates by news sentiment + market_view, output trade ideas.
    _ = state
    return {"trader_picks": []}
