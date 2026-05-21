"""入口 - 启动调度器 + NiceGUI 看板"""
import logging
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import config
from app.db.init_db import init_db
from app.jobs.scheduler import build_scheduler, get_scheduler
from app import ui  # 注册路由
from app.web.health import init_version, register_health_routes
from nicegui import ui as nicegui_ui
from nicegui import app as nicegui_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("stockwatch")


def main():
    init_db()
    init_version()
    register_health_routes(nicegui_app, get_scheduler)

    if config.QUOTE_PROVIDER == "futu":
        from app.services.futu_client import futu

        log.info("Connecting to FutuOpenD...")
        try:
            futu.connect()
        except Exception as e:
            log.warning("Futu not available: %s", e)
    else:
        log.info("Quote provider: yfinance (default)")

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
