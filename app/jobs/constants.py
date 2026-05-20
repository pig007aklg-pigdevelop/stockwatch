"""信号/推送相关常量 — 供 price_scanner 与 UI 共用。"""

ACTIONABLE = frozenset({
    "STOP_LOSS",
    "TAKE_PROFIT",
    "AUTO_BUY_HINT",
    "AUTO_SELL_HINT",
    "WATCH_BUY",
    "WATCH_SELL",
})
