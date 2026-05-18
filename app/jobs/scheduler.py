"""APScheduler 调度配置"""
import logging
from datetime import datetime
import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from app.config import config
from app.jobs.price_scanner import scan_once, hourly_summary

log = logging.getLogger(__name__)
TZ = pytz.timezone(config.TZ)


def in_hk_session() -> bool:
    """港股交易时段 (北京时间): 9:30-12:00, 13:00-16:00, 周一到五"""
    now = datetime.now(TZ)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (
        (t >= datetime.strptime("09:30", "%H:%M").time() and t <= datetime.strptime("12:00", "%H:%M").time())
        or (t >= datetime.strptime("13:00", "%H:%M").time() and t <= datetime.strptime("16:00", "%H:%M").time())
    )


def in_us_session() -> bool:
    """美股盘前+盘中 (北京时间): 大致 21:00-次日 05:00 (考虑夏令时简化)"""
    now = datetime.now(TZ)
    weekday = now.weekday()
    t = now.time()
    # 北京时间周一21:00 - 周六05:00 大致都覆盖
    if weekday == 0 and t < datetime.strptime("21:00", "%H:%M").time():
        return False
    if weekday == 5 and t > datetime.strptime("05:00", "%H:%M").time():
        return False
    if weekday == 6:
        return False
    if weekday in (1, 2, 3, 4):
        return t >= datetime.strptime("21:00", "%H:%M").time() or t <= datetime.strptime("05:00", "%H:%M").time()
    if weekday == 0:
        return t >= datetime.strptime("21:00", "%H:%M").time()
    if weekday == 5:
        return t <= datetime.strptime("05:00", "%H:%M").time()
    return False


def scan_job():
    if in_hk_session() or in_us_session():
        log.info("⏱  Scan tick — in trading session")
        scan_once()
    else:
        log.debug("Skip scan — out of session")


def summary_job():
    if config.HOURLY_SUMMARY and (in_hk_session() or in_us_session()):
        hourly_summary()


def build_scheduler() -> BlockingScheduler:
    sched = BlockingScheduler(timezone=TZ)
    # 每 N 分钟扫描
    sched.add_job(
        scan_job,
        CronTrigger(minute=f"*/{config.SCAN_INTERVAL}", timezone=TZ),
        id="scan",
        max_instances=1,
        coalesce=True,
    )
    # 整点摘要
    sched.add_job(
        summary_job,
        CronTrigger(minute=0, timezone=TZ),
        id="summary",
        max_instances=1,
    )
    return sched
