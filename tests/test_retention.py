from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import text

from app.db.models import Signal, PriceSnapshot, News
from app.jobs.retention_job import cleanup_old_data, _delete_old_rows


def _insert_signal(session, days_ago: int):
    session.add(
        Signal(
            symbol="T",
            market="US",
            action="HOLD",
            price=1.0,
            cost_price=1.0,
            pnl_pct=0.0,
            reason="t",
            created_at=datetime.utcnow() - timedelta(days=days_ago),
        )
    )


def test_cleanup_deletes_only_rows_older_than_retention(session):
    for d in (100, 95, 30, 1):
        _insert_signal(session, d)
    session.commit()
    assert session.query(Signal).count() == 4

    result = cleanup_old_data(session)
    session.expire_all()

    assert result["signals"] == 2
    assert session.query(Signal).count() == 2
    remaining_days = [
        (datetime.utcnow() - r.created_at).days for r in session.query(Signal).all()
    ]
    assert all(d < 90 for d in remaining_days)


def test_cleanup_empty_tables_no_error(session):
    result = cleanup_old_data(session)
    assert result["signals"] == 0
    assert result["price_snapshots"] == 0
    assert result["news"] == 0
    assert "scores" in result


def test_one_table_failure_does_not_block_others(session):
    old = datetime.utcnow() - timedelta(days=200)
    session.add(
        News(
            symbol="X",
            title="old",
            url="http://old.example/a",
            source="t",
            published_at=old,
            created_at=old,
        )
    )
    session.add(
        PriceSnapshot(
            symbol="Y",
            market="US",
            price=1.0,
            change_pct=0.0,
            timestamp=old,
        )
    )
    session.commit()

    def fail_signals(*args, **kwargs):
        if args[1] == "signals":
            raise RuntimeError("signals delete boom")
        return _delete_old_rows(*args, **kwargs)

    with patch("app.jobs.retention_job._delete_old_rows", side_effect=fail_signals):
        with patch("app.jobs.retention_job._run_vacuum"):
            result = cleanup_old_data(session)

    assert result["signals"] == 0
    assert result["news"] >= 1
    assert result["price_snapshots"] >= 1
    assert session.query(News).count() == 0
    assert session.query(PriceSnapshot).count() == 0
