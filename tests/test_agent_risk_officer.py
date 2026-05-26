from app.agents.risk_officer import TOP_N, risk_officer_node


def test_risk_officer_hk_top3():
    state = {
        "market": "hk",
        "market_view": "大盘中性",
        "trader_picks": [
            {"code": f"HK.{i:05d}", "score": 90 - i, "news_sentiment_avg": 0.2}
            for i in range(6)
        ],
        "technical": {
            f"HK.{i:05d}": {
                "rsi": 50,
                "macd_bullish": True,
                "dist_52w_high_pct": 12,
            }
            for i in range(6)
        },
    }
    out = risk_officer_node(state)
    assert len(out["consensus_picks"]) == TOP_N["hk"]
    assert out["consensus_picks"][0]["rank"] == 1


def test_risk_officer_rejects_low_score():
    state = {
        "market": "us",
        "market_view": "",
        "trader_picks": [{"code": "US.AAPL", "score": 20, "news_sentiment_avg": 0.1}],
        "technical": {"US.AAPL": {"rsi": 50, "macd_bullish": True, "dist_52w_high_pct": 20}},
    }
    out = risk_officer_node(state)
    assert out["consensus_picks"] == []
    assert out["risk_assessment"][0]["approved"] is False
