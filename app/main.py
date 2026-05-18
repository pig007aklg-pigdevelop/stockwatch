"""入口 - 启动调度器 + NiceGUI 看板"""
import logging
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import config
from app.db.init_db import init_db
from app.jobs.scheduler import build_scheduler
from app.services.futu_client import futu
from app import ui  # 注册路由
from nicegui import ui as nicegui_ui

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("stockwatch")


def main():
    init_db()
    log.info("Connecting to FutuOpenD (best-effort)...")
    try:
        futu.connect()
    except Exception as e:
        log.warning("Futu not available: %s", e)

    sched = build_scheduler()
    sched.start()
    log.info("Scheduler started.")
    log.info(f"Web dashboard: http://{config.WEB_HOST}:{config.WEB_PORT}")

    nicegui_ui.run(
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        title="StockWatch",
        reload=False,
        show=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
