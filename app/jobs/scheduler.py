"""APScheduler 调度配置 - 后台模式(给 NiceGUI 用)"""
from __future__ import annotations

import logging
from datetime import datetime
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.config import config
from app.jobs.price_scanner import scan_once, hourly_summary
from app.jobs.news_scraper import fetch_all as fetch_news_all
from app.jobs.scoring_job import run_daily_scoring
from app.jobs.retention_job import run_retention_cleanup

log = logging.getLogger(__name__)
TZ = pytz.timezone(config.TZ)

_scheduler: BackgroundScheduler | None = None


def in_hk_session() -> bool:
    now = datetime.now(TZ)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (
        (t >= datetime.strptime("09:30", "%H:%M").time() and t <= datetime.strptime("12:00", "%H:%M").time())
        or (t >= datetime.strptime("13:00", "%H:%M").time() and t <= datetime.strptime("16:00", "%H:%M").time())
    )


def in_us_session() -> bool:
    now = datetime.now(TZ)
    weekday = now.weekday()
    t = now.time()
    if weekday in (1, 2, 3, 4):
        return t >= datetime.strptime("21:00", "%H:%M").time() or t <= datetime.strptime("05:00", "%H:%M").time()
    if weekday == 0:
        return t >= datetime.strptime("21:00", "%H:%M").time()
    if weekday == 5:
        return t <= datetime.strptime("05:00", "%H:%M").time()
    return False


def scan_job():
    if in_hk_session() or in_us_session():
        log.info("⏱  Scan — in session")
        scan_once()


def hk_open_summary_job():
    if in_hk_session():
        hourly_summary(market_hint="HK", phase="open")


def hk_close_summary_job():
    hourly_summary(market_hint="HK", phase="close")


def us_open_summary_job():
    if in_us_session():
        hourly_summary(market_hint="US", phase="open")


def us_close_summary_job():
    hourly_summary(market_hint="US", phase="close")


def news_job():
    try:
        fetch_news_all()
    except Exception as e:
        log.exception("news_job error: %s", e)


def scoring_job():
    try:
        log.info("⏱  Daily scoring job")
        run_daily_scoring()
    except Exception as e:
        log.exception("scoring_job error: %s", e)


def retention_cleanup_job():
    try:
        log.info("⏱  Retention cleanup job")
        result = run_retention_cleanup()
        log.info("Retention cleanup result: %s", result)
    except Exception as e:
        log.exception("retention_cleanup_job error: %s", e)


def get_scheduler() -> BackgroundScheduler | None:
    return _scheduler


def build_scheduler() -> BackgroundScheduler:
    global _scheduler
    sched = BackgroundScheduler(timezone=TZ)
    _scheduler = sched
    sched.add_job(scan_job, CronTrigger(minute=f"*/{config.SCAN_INTERVAL}", timezone=TZ),
                  id="scan", max_instances=1, coalesce=True)
    # 摘要推送：开盘/收盘前各一次（Asia/Shanghai）
    sched.add_job(
        hk_open_summary_job,
        CronTrigger(hour=10, minute=0, day_of_week="mon-fri", timezone=TZ),
        id="summary_hk_open",
        max_instances=1,
        coalesce=True,
    )
    sched.add_job(
        hk_close_summary_job,
        CronTrigger(hour=15, minute=30, day_of_week="mon-fri", timezone=TZ),
        id="summary_hk_close",
        max_instances=1,
        coalesce=True,
    )
    sched.add_job(
        us_open_summary_job,
        CronTrigger(hour=22, minute=0, day_of_week="mon-fri", timezone=TZ),
        id="summary_us_open",
        max_instances=1,
        coalesce=True,
    )
    # 美股收盘前 04:30 (Asia/Shanghai) 属于次日
    sched.add_job(
        us_close_summary_job,
        CronTrigger(hour=4, minute=30, day_of_week="tue-sat", timezone=TZ),
        id="summary_us_close",
        max_instances=1,
        coalesce=True,
    )
    sched.add_job(news_job, CronTrigger(minute=f"*/{config.NEWS_INTERVAL}", timezone=TZ),
                  id="news", max_instances=1, coalesce=True)
    # 工作日 06:00 综合打分 (Mon-Fri)
    sched.add_job(
        scoring_job,
        CronTrigger(day_of_week="mon-fri", hour=6, minute=0, timezone=TZ),
        id="scoring",
        max_instances=1,
        coalesce=True,
    )
    sched.add_job(
        retention_cleanup_job,
        CronTrigger(day_of_week="sun", hour=3, minute=0, timezone=TZ),
        id="retention_cleanup",
        max_instances=1,
        coalesce=True,
    )
    return sched
