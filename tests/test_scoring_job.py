from unittest.mock import patch, MagicMock
from datetime import datetime

from app.jobs.scoring_job import run_daily_scoring, _send_top5_report
from app.services.scoring import ScoreResult, DimensionScores, NEWS_BASELINE


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
                with patch("app.jobs.scoring_job._send_opportunity_alerts"):
                    with patch("app.jobs.scoring_job.get_session", return_value=session):
                        with patch.object(session, "close"):
                            with patch("app.jobs.scoring_job.time.sleep"):
                                assert run_daily_scoring() is True
    p = session.query(type(sample_position)).filter_by(symbol="00700").first()
    assert p.composite_score == 75.0
    assert p.recommended_buy == 290.0
