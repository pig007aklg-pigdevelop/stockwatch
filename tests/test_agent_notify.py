from app.agents.notify import format_message


def test_format_message_with_picks():
    result = {
        "market_view": "板块偏多",
        "final_picks": [
            {
                "rank": 1,
                "code": "HK.00700",
                "name": "腾讯",
                "score": 85,
                "price": 400,
                "buy_range_low": 380,
                "buy_range_high": 395,
                "stop_loss": 360,
                "target": 450,
                "tech_view": "MACD金叉",
                "risk_view": "流动性充足",
            }
        ],
    }
    text = format_message("hk", result)
    assert "港股" in text
    assert "腾讯" in text
    assert "380" in text
