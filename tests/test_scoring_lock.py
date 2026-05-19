import threading

from app.jobs import scoring_job


def test_run_daily_scoring_global_lock():
    scoring_job._scoring_lock.acquire()
    try:
        assert scoring_job.scoring_in_progress() is True
        assert scoring_job.run_daily_scoring() is False
    finally:
        scoring_job._scoring_lock.release()
