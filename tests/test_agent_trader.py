from app.agents.trader import (
    RULE_MACD_BULL,
    RULE_NEWS_SENTIMENT,
    score_stock,
    trader_node,
)


def test_score_stock_news_and_macd_rules():
    news = [{"code": "HK.00700", "title": "t", "summary": "", "sentiment": 0.5, "published_at": ""}]
    tech = {
        "macd_bullish": True,
        "macd_hist": 0.2,
        "macd_hist_prev": 0.1,
        "rsi": 50.0,
        "price_above_ma20": True,
        "ma_bull_align": True,
        "dist_52w_high_pct": 15.0,
        "tech_view": "test",
        "price": 400.0,
    }
    pick = score_stock("HK.00700", news_items=news, technical=tech, sector_avg=0.0)
    assert pick["score"] > 70
    assert pick["rule_scores"][RULE_NEWS_SENTIMENT] >= 15
    assert pick["rule_scores"][RULE_MACD_BULL] == 15.0


def test_trader_node_sorts_by_score():
    state = {
        "market": "hk",
        "candidates": ["HK.A", "HK.B"],
        "news": {
            "HK.A": [{"code": "HK.A", "title": "", "summary": "", "sentiment": 0.8, "published_at": ""}],
            "HK.B": [{"code": "HK.B", "title": "", "summary": "", "sentiment": -0.5, "published_at": ""}],
        },
        "technical": {
            "HK.A": {
                "macd_bullish": True,
                "macd_hist": 1,
                "macd_hist_prev": 0,
                "rsi": 55,
                "price_above_ma20": True,
                "ma_bull_align": True,
                "dist_52w_high_pct": 20,
                "tech_view": "A",
                "price": 10,
            },
            "HK.B": {
                "macd_bullish": False,
                "macd_hist": -1,
                "macd_hist_prev": 0,
                "rsi": 80,
                "price_above_ma20": False,
                "ma_bull_align": False,
                "dist_52w_high_pct": 2,
                "tech_view": "B",
                "price": 10,
            },
        },
    }
    out = trader_node(state)
    picks = out["trader_picks"]
    assert picks[0]["code"] == "HK.A"
    assert picks[0]["score"] > picks[1]["score"]
