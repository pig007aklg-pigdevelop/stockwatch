import json
from datetime import datetime

import pytest
from sqlalchemy.orm import sessionmaker

from app.agents.repository import save_agent_picks
from app.db.models import AgentPick, Base


def test_save_agent_picks_writes_rows(db_engine, monkeypatch):
    Session = sessionmaker(bind=db_engine)
    monkeypatch.setattr("app.agents.repository.get_session", lambda: Session())

    picks = [
        {
            "rank": 1,
            "code": "HK.00700",
            "name": "腾讯",
            "price": 400.0,
            "score": 80.0,
            "buy_range_low": 380.0,
            "buy_range_high": 395.0,
            "stop_loss": 360.0,
            "target": 450.0,
            "tech_view": "MACD金叉",
            "risk_view": "通过",
            "market_view": "中性",
            "news_sentiment_avg": 0.2,
        }
    ]
    n = save_agent_picks("hk", picks, run_at=datetime(2026, 5, 26, 8, 30))
    assert n == 1

    s = Session()
    try:
        rows = s.query(AgentPick).all()
        assert len(rows) == 1
        assert rows[0].code == "HK.00700"
        raw = json.loads(rows[0].raw_json)
        assert raw["name"] == "腾讯"
    finally:
        s.close()
