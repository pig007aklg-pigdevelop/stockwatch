from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.web.health import build_health_response, register_health_routes


def _mock_scheduler(job_count: int = 5, next_run=None):
    sched = MagicMock()
    if job_count <= 0:
        sched.get_jobs.return_value = []
        return sched
    job = MagicMock()
    job.next_run_time = next_run or datetime.utcnow() + timedelta(hours=1)
    sched.get_jobs.return_value = [job] * job_count
    return sched


def test_health_ok_returns_200():
    sched = _mock_scheduler(5)
    with patch("app.web.health._check_db", return_value={"ok": True, "latency_ms": 2.0}):
        with patch("app.web.health._check_disk", return_value={"ok": True, "db_size_mb": 1.0, "free_mb": 8000.0}):
            with patch(
                "app.web.health._check_quote",
                return_value={"ok": True, "provider": "akshare", "sample_price": 110.0},
            ):
                body, code = build_health_response(sched)
    assert code == 200
    assert body["status"] == "ok"
    assert body["checks"]["db"]["ok"] is True
    assert body["checks"]["scheduler"]["jobs"] == 5
    assert body["checks"]["quote"]["ok"] is True


def test_health_db_failure_returns_503_down():
    sched = _mock_scheduler(5)
    with patch("app.web.health._check_db", return_value={"ok": False, "latency_ms": None}):
        with patch("app.web.health._check_disk", return_value={"ok": True, "db_size_mb": 1.0, "free_mb": 8000.0}):
            with patch("app.web.health._check_quote", return_value={"ok": True, "provider": "akshare"}):
                body, code = build_health_response(sched)
    assert code == 503
    assert body["status"] == "down"


def test_health_no_scheduler_jobs_returns_degraded():
    sched = _mock_scheduler(0)
    with patch("app.web.health._check_db", return_value={"ok": True, "latency_ms": 1.0}):
        with patch("app.web.health._check_disk", return_value={"ok": True, "db_size_mb": 1.0, "free_mb": 8000.0}):
            with patch("app.web.health._check_quote", return_value={"ok": True, "provider": "akshare"}):
                body, code = build_health_response(sched)
    assert code == 200
    assert body["status"] == "degraded"
    assert body["checks"]["scheduler"]["ok"] is False


def test_health_quote_failure_returns_degraded():
    sched = _mock_scheduler(5)
    with patch("app.web.health._check_db", return_value={"ok": True, "latency_ms": 1.0}):
        with patch("app.web.health._check_disk", return_value={"ok": True, "db_size_mb": 1.0, "free_mb": 8000.0}):
            with patch(
                "app.web.health._check_quote",
                return_value={"ok": False, "provider": "akshare", "error": "empty"},
            ):
                body, code = build_health_response(sched)
    assert code == 200
    assert body["status"] == "degraded"
    assert body["checks"]["quote"]["ok"] is False


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("nicegui"),
    reason="nicegui not installed",
)
def test_health_route_registered():
    from nicegui import app

    register_health_routes(app, lambda: _mock_scheduler(3))
    paths = [getattr(r, "path", None) for r in app.routes]
    assert "/health" in paths
