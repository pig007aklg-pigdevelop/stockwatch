"""Risk officer agent node (Stage 1 stub)."""
from app.agents.state import AgentState


def risk_officer_node(state: AgentState) -> dict:
    # TODO(Stage 2): review trader_picks for concentration, liquidity, and drawdown limits.
    _ = state
    return {"risk_assessment": []}
