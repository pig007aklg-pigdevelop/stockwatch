"""入口"""
import logging
from app.db.init_db import init_db
from app.jobs.scheduler import build_scheduler
from app.services.futu_client import futu

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("stockwatch")


def main():
    init_db()
    log.info("Connecting to FutuOpenD...")
    try:
        futu.connect()
    except Exception as e:
        log.error("Futu connect failed: %s — continuing, will retry on first scan", e)

    sched = build_scheduler()
    log.info("Scheduler starting. Press Ctrl+C to stop.")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down...")
        futu.close()


if __name__ == "__main__":
    main()
