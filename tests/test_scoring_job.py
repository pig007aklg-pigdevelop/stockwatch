from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from app.jobs.scoring_job import run_daily_scoring, _send_top5_report, _send_score_alerts
from app.services.scoring import ScoreResult, DimensionScores, NEWS_BASELINE
from app.db.models import Signal
from app.config import config


def test_send_top5_report_no_crash():
  positions = []
  for i, score in enumerate([90, 80, 70, 60, 50, 40]):
    p = MagicMock()
    p.market = "US"
    p.symbol = f"S{i}"
    p.name = ""
    p.composite_score = score
    p.recommended_buy = 10.0
    p.recommended_sell = 20.0
    positions.append(p)
  with patch("app.jobs.scoring_job.telegram_bot.send") as mock_send:
    _send_top5_report(positions)
    mock_send.assert_called_once()


def test_run_daily_scoring_updates_db(session, sample_position):
    result = ScoreResult(
        composite=75.0,
        dimensions=DimensionScores(70, 60, 65, 55, NEWS_BASELINE),
        recommended_buy=290.0,
        recommended_sell=380.0,
        updated_at=datetime.utcnow(),
    )
    with patch("app.jobs.scoring_job.scoring.score_position", return_value=result):
        with patch("app.jobs.scoring_job.call_with_timeout", side_effect=lambda fn, *a, **k: fn(*a)):
            with patch("app.jobs.scoring_job._send_top5_report"):
                with patch("app.jobs.scoring_job._send_score_alerts"):
                    with patch("app.jobs.scoring_job.get_session", return_value=session):
                        with patch.object(session, "close"):
                            with patch("app.jobs.scoring_job.time.sleep"):
                                assert run_daily_scoring() is True
    p = session.query(type(sample_position)).filter_by(symbol="00700").first()
    assert p.composite_score == 75.0
    assert p.recommended_buy == 290.0


def _mk_pos(score: float, **kwargs):
    p = MagicMock()
    p.market = kwargs.get("market", "HK")
    p.symbol = kwargs.get("symbol", "00700")
    p.name = kwargs.get("name", "")
    p.cost_price = kwargs.get("cost_price", 100.0)
    p.composite_score = score
    p.recommended_buy = kwargs.get("recommended_buy", None)
    p.recommended_sell = kwargs.get("recommended_sell", None)
    p.score_valuation = kwargs.get("score_valuation", None)
    p.score_fundamental = kwargs.get("score_fundamental", None)
    return p


def test_high_score_triggers_opportunity(session):
    pos = _mk_pos(75.0, recommended_buy=9.2)
    with patch("app.jobs.scoring_job.telegram_bot.send") as mock_send:
        _send_score_alerts(session, [pos])
        mock_send.assert_called_once()
    sig = session.query(Signal).filter_by(action="SCORE_OPPORTUNITY", symbol=pos.symbol).first()
    assert sig is not None


def test_low_score_triggers_risk(session):
    pos = _mk_pos(20.0, recommended_sell=12.0)
    with patch("app.jobs.scoring_job.telegram_bot.send") as mock_send:
        _send_score_alerts(session, [pos])
        mock_send.assert_called_once()
    sig = session.query(Signal).filter_by(action="SCORE_RISK", symbol=pos.symbol).first()
    assert sig is not None


def test_mid_score_no_alert(session):
    pos = _mk_pos(50.0)
    with patch("app.jobs.scoring_job.telegram_bot.send") as mock_send:
        _send_score_alerts(session, [pos])
        mock_send.assert_not_called()
    assert session.query(Signal).count() == 0


def test_cooldown_blocks_repeated_alert(session):
    pos = _mk_pos(75.0, recommended_buy=9.2)
    session.add(
        Signal(
            symbol=pos.symbol,
            market=pos.market,
            action="SCORE_OPPORTUNITY",
            price=0.0,
            cost_price=pos.cost_price,
            pnl_pct=0.0,
            reason="prev",
            pushed=1,
            created_at=datetime.utcnow() - timedelta(hours=config.SCORING_ALERT_COOLDOWN_HOURS) + timedelta(minutes=1),
        )
    )
    session.commit()
    with patch("app.jobs.scoring_job.telegram_bot.send") as mock_send:
        _send_score_alerts(session, [pos])
        mock_send.assert_not_called()
