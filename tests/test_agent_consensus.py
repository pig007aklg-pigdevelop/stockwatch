from app.agents.consensus import _rule_prices, consensus_node


def test_rule_prices_sane():
    prices = _rule_prices({"price": 100}, {"low_20d": 90, "high_52w": 120})
    assert prices["buy_range_low"] < prices["buy_range_high"]
    assert prices["stop_loss"] < prices["buy_range_low"]
    assert prices["target"] > 100


def test_consensus_dry_run_final_picks():
    state = {
        "consensus_picks": [
            {
                "rank": 1,
                "code": "HK.00700",
                "score": 80,
                "price": 400,
                "tech_view": "MACD金叉",
            }
        ],
        "technical": {
            "HK.00700": {
                "low_20d": 380,
                "high_52w": 450,
                "price": 400,
                "tech_view": "MACD金叉",
            }
        },
        "news": {},
        "market_view": "中性",
    }
    out = consensus_node(state, config={"configurable": {"dry_run": True}})
    picks = out["final_picks"]
    assert len(picks) == 1
    assert picks[0]["buy_range_low"] is not None
    assert picks[0]["target"] is not None
