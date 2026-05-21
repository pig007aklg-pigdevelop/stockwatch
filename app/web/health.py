"""健康检查 — GET /health (FastAPI, 不走 NiceGUI 页面)。"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from datetime import datetime
from typing import Callable

import pytz
from sqlalchemy import text

from app.config import config
from app.db.models import get_session

log = logging.getLogger(__name__)

VERSION = "unknown"
_START_MONOTONIC = time.monotonic()
_TZ = pytz.timezone(config.TZ)

DISK_FREE_DEGRADED_MB = 500


def init_version() -> None:
    global VERSION
    try:
        VERSION = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).strip()
    except Exception:
        VERSION = "unknown"


def _iso_timestamp() -> str:
    return datetime.now(_TZ).isoformat(timespec="seconds")


def _check_db() -> dict:
    try:
        t0 = time.perf_counter()
        s = get_session()
        try:
            s.execute(text("SELECT 1"))
            s.commit()
        finally:
            s.close()
        ms = (time.perf_counter() - t0) * 1000
        return {"ok": True, "latency_ms": round(ms, 1)}
    except Exception as e:
        log.warning("health db check failed: %s", e)
        return {"ok": False, "latency_ms": None}


def _check_scheduler(scheduler) -> dict:
    if scheduler is None:
        return {"ok": False, "jobs": 0, "next_run": None}
    try:
        jobs = scheduler.get_jobs()
        if not jobs:
            return {"ok": False, "jobs": 0, "next_run": None}
        next_times = [j.next_run_time for j in jobs if j.next_run_time]
        next_run = None
        if next_times:
            earliest = min(next_times)
            if earliest.tzinfo is None:
                earliest = _TZ.localize(earliest)
            next_run = earliest.astimezone(_TZ).isoformat(timespec="seconds")
        return {"ok": True, "jobs": len(jobs), "next_run": next_run}
    except Exception as e:
        log.warning("health scheduler check failed: %s", e)
        return {"ok": False, "jobs": 0, "next_run": None}


def _check_disk() -> dict:
    try:
        db_path = config.DB_PATH
        db_size_mb = 0.0
        if os.path.isfile(db_path):
            db_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 1)
        parent = os.path.dirname(os.path.abspath(db_path)) or "."
        usage = shutil.disk_usage(parent)
        free_mb = round(usage.free / (1024 * 1024), 1)
        ok = free_mb >= DISK_FREE_DEGRADED_MB
        return {"ok": ok, "db_size_mb": db_size_mb, "free_mb": free_mb}
    except Exception as e:
        log.warning("health disk check failed: %s", e)
        return {"ok": False, "db_size_mb": 0.0, "free_mb": 0.0}


def build_health_response(scheduler) -> tuple[dict, int]:
    checks = {
        "db": _check_db(),
        "scheduler": _check_scheduler(scheduler),
        "disk": _check_disk(),
    }

    if not checks["db"]["ok"]:
        status = "down"
    elif not checks["scheduler"]["ok"] or not checks["disk"]["ok"]:
        status = "degraded"
    else:
        status = "ok"

    body = {
        "status": status,
        "timestamp": _iso_timestamp(),
        "version": VERSION,
        "uptime_seconds": int(time.monotonic() - _START_MONOTONIC),
        "checks": checks,
    }
    code = 503 if status == "down" else 200
    return body, code


def register_health_routes(app, scheduler_getter: Callable):
    """在 NiceGUI / FastAPI app 上注册 GET /health。"""

    @app.get("/health")
    async def health_endpoint():
        from fastapi.responses import JSONResponse

        sched = scheduler_getter() if scheduler_getter else None
        body, code = build_health_response(sched)
        return JSONResponse(content=body, status_code=code)
