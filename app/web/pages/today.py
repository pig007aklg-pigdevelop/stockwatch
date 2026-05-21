"""今日操作建议 — /today"""
from __future__ import annotations

from datetime import datetime

from nicegui import ui
from sqlalchemy import desc

from app.config import config
from app.db.models import get_session, Position, Watchlist, PriceSnapshot, Signal
from app.services.concentration import compute_hhi
from app.ui import render_header, _latest_price, _fmt_score, _is_score_incomplete


def _today_start_utc() -> datetime:
    return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)


def _weight_bar_color(weight: float) -> str:
    if weight > 0.5:
        return "#ef4444"
    if weight >= 0.25:
        return "#f59e0b"
    return "#22c55e"


def _level_badge(level: str) -> str:
    return {"low": "✅ 分散", "mid": "🟡 中等", "high": "🔴 集中"}.get(level, level)


def _mini_radar_option(rec) -> dict:
    dims = [
        ("估值", rec.score_valuation),
        ("资金", rec.score_capital),
        ("技术", rec.score_technical),
        ("基本面", rec.score_fundamental),
        ("新闻", rec.score_news),
    ]
    indicators = [{"name": n, "max": 100} for n, _ in dims]
    values = [v if v is not None else 0 for _, v in dims]
    return {
        "radar": {"indicator": indicators, "radius": "60%"},
        "series": [{"type": "radar", "data": [{"value": values}]}],
        "grid": {"left": 0, "right": 0, "top": 0, "bottom": 0},
    }


def _hhi_bar_option(weights: list[dict]) -> dict:
    codes = [w["code"] for w in weights]
    data = [
        {
            "value": round(w["weight"] * 100, 1),
            "itemStyle": {"color": _weight_bar_color(w["weight"])},
        }
        for w in weights
    ]
    return {
        "tooltip": {"trigger": "axis", "formatter": "{b}: {c}%"},
        "grid": {"left": "28%", "right": "8%", "top": "4%", "bottom": "4%"},
        "xAxis": {"type": "value", "max": 100, "axisLabel": {"formatter": "{value}%"}},
        "yAxis": {"type": "category", "data": list(reversed(codes)), "inverse": True},
        "series": [{"type": "bar", "data": list(reversed(data))}],
    }


def _signal_badge(action: str) -> tuple[str, str]:
    """返回 (显示文本, tailwind 色类)。"""
    mapping = {
        "SCORE_OPPORTUNITY": ("💎 机会", "bg-green-100 text-green-800"),
        "SCORE_RISK": ("⚠️ 风险", "bg-red-100 text-red-800"),
        "STOP_LOSS": ("⛔ 止损", "bg-red-200 text-red-900"),
        "TAKE_PROFIT": ("🎯 止盈", "bg-emerald-100 text-emerald-800"),
        "WATCH_BUY_HINT": ("📥 建仓", "bg-blue-100 text-blue-800"),
        "AUTO_BUY_HINT": ("📥 加仓", "bg-blue-100 text-blue-800"),
        "INTRADAY_MOVE_UP": ("🚀 异动", "bg-amber-100 text-amber-800"),
        "INTRADAY_MOVE_DOWN": ("📉 异动", "bg-amber-100 text-amber-800"),
    }
    return mapping.get(action, (action or "-", "bg-slate-100 text-slate-700"))


def _load_prices(session, records) -> dict[str, float]:
    prices: dict[str, float] = {}
    for r in records:
        lp = _latest_price(session, r.symbol)
        if lp and lp.price and lp.price > 0:
            prices[r.futu_code] = float(lp.price)
        elif hasattr(r, "cost_price") and r.cost_price:
            prices[r.futu_code] = float(r.cost_price)
    return prices


def _watchlist_keys(session) -> set[tuple[str, str]]:
    return {(w.market, w.symbol) for w in session.query(Watchlist).all()}


def _latest_score_risk_reason(session, symbol: str, market: str) -> str:
    sig = (
        session.query(Signal)
        .filter_by(symbol=symbol, market=market, action="SCORE_RISK")
        .order_by(desc(Signal.created_at))
        .first()
    )
    if not sig or not sig.reason:
        return "综合分偏低,关注风险"
    return sig.reason[:80]


@ui.page("/today")
def today_page():
    render_header()
    content = ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-4")

    with content:
        with ui.row().classes("w-full items-center"):
            ui.label("📌 今日操作").classes("text-2xl font-bold")
            ui.space()
            refresh_btn = ui.button("🔄 刷新").props("color=primary flat")

        health_box = ui.column().classes("w-full gap-2")
        buy_box = ui.column().classes("w-full gap-2")
        sell_box = ui.column().classes("w-full gap-2")
        signals_box = ui.column().classes("w-full gap-2")

    def refresh():
        health_box.clear()
        buy_box.clear()
        sell_box.clear()
        signals_box.clear()

        s = get_session()
        try:
            positions = s.query(Position).all()
            watchlist = s.query(Watchlist).all()
            prices = _load_prices(s, positions)
            hhi_data = compute_hhi(positions, prices)
            watched = _watchlist_keys(s)
            opp_thr = config.SCORE_OPPORTUNITY_THRESHOLD
            risk_thr = config.SCORE_RISK_THRESHOLD
            today_start = _today_start_utc()

            # ── 卡片 1: 组合健康度 ──
            with health_box:
                with ui.card().classes("w-full"):
                    ui.label("📊 组合健康度").classes("text-lg font-bold mb-2")
                    if not positions:
                        ui.label("暂无持仓,无法计算集中度").classes("text-slate-500")
                    else:
                        with ui.row().classes("gap-6 flex-wrap items-center"):
                            ui.label(
                                f"总市值 ¥{hhi_data['total_value_cny']:,.0f}"
                            ).classes("text-xl font-semibold")
                            ui.label(f"HHI {hhi_data['hhi']:.2f}").classes("text-lg")
                            level_cls = {
                                "low": "bg-green-100 text-green-800",
                                "mid": "bg-amber-100 text-amber-800",
                                "high": "bg-red-100 text-red-800",
                            }.get(hhi_data["level"], "bg-slate-100")
                            ui.badge(_level_badge(hhi_data["level"])).classes(level_cls)
                            ui.label(
                                f"Top1 {hhi_data['top1_weight']*100:.0f}% · "
                                f"Top3 {hhi_data['top3_weight']*100:.0f}%"
                            ).classes("text-sm text-slate-600")
                        if hhi_data["weights"]:
                            ui.echart(_hhi_bar_option(hhi_data["weights"])).classes(
                                "w-full h-64"
                            )
                        ui.label(hhi_data["advice"]).classes(
                            "text-base mt-2 font-medium"
                        )

            # ── 卡片 2: 建议买入 ──
            with buy_box:
                with ui.card().classes("w-full"):
                    ui.label("📥 今日建议买入 (Top 3)").classes("text-lg font-bold mb-2")
                    candidates = [
                        w for w in watchlist
                        if w.composite_score is not None
                        and w.composite_score >= opp_thr
                    ]
                    candidates.sort(key=lambda x: x.composite_score, reverse=True)
                    picks = candidates[:3]
                    if not picks:
                        ui.label("今日无建议").classes("text-slate-500")
                    else:
                        for w in picks:
                            lp = _latest_price(s, w.symbol)
                            price = lp.price if lp else 0
                            in_list = (w.market, w.symbol) in watched
                            with ui.row().classes(
                                "w-full items-center gap-2 flex-wrap border-b py-2"
                            ):
                                ui.label(f"{w.market}.{w.symbol}").classes(
                                    "font-bold w-24"
                                )
                                ui.label(w.name or "-").classes("w-20 text-sm")
                                ui.label(
                                    f"现价 {price:.2f}" if price else "现价 -"
                                ).classes("w-24 text-sm")
                                ui.label(
                                    f"综合 {_fmt_score(w.composite_score, incomplete=_is_score_incomplete(w))}"
                                ).classes("w-20 text-sm")
                                ui.echart(_mini_radar_option(w)).classes("w-28 h-28")
                                rb = (
                                    f"{w.recommended_buy:.2f}"
                                    if w.recommended_buy
                                    else "-"
                                )
                                ui.label(f"建议买 {rb}").classes("w-24 text-sm")

                                def add_watch(
                                    sym=w.symbol,
                                    mkt=w.market,
                                    nm=w.name,
                                    btn_ref=None,
                                ):
                                    ss = get_session()
                                    try:
                                        if ss.query(Watchlist).filter_by(
                                            symbol=sym, market=mkt
                                        ).first():
                                            ui.notify("已在关注名单", color="info")
                                            return
                                        ss.add(
                                            Watchlist(
                                                symbol=sym,
                                                market=mkt,
                                                name=nm or "",
                                            )
                                        )
                                        ss.commit()
                                        ui.notify(
                                            f"已加入关注 {mkt}.{sym}",
                                            color="positive",
                                        )
                                        refresh()
                                    finally:
                                        ss.close()

                                if in_list:
                                    ui.label("已关注").classes(
                                        "text-sm text-green-600"
                                    )
                                else:
                                    ui.button(
                                        "加自选",
                                        on_click=add_watch,
                                    ).props("size=sm color=primary outline")

            # ── 卡片 3: 建议减仓 ──
            with sell_box:
                with ui.card().classes("w-full"):
                    ui.label("📤 今日建议减仓 (Top 3)").classes("text-lg font-bold mb-2")
                    risk_pos = [
                        p for p in positions
                        if p.composite_score is not None
                        and p.composite_score < risk_thr
                    ]
                    risk_pos.sort(key=lambda x: x.composite_score)
                    sells = risk_pos[:3]
                    if not sells:
                        ui.label("今日无建议").classes("text-slate-500")
                    else:
                        for p in sells:
                            lp = _latest_price(s, p.symbol)
                            price = lp.price if lp else 0
                            pnl_pct = (
                                (price - p.cost_price) / p.cost_price * 100
                                if price and p.cost_price
                                else 0
                            )
                            pnl_abs = (price - p.cost_price) * p.quantity if price else 0
                            reason = _latest_score_risk_reason(s, p.symbol, p.market)
                            rs = (
                                f"{p.recommended_sell:.2f}"
                                if p.recommended_sell
                                else "-"
                            )
                            with ui.row().classes(
                                "w-full items-start gap-2 flex-wrap border-b py-2"
                            ):
                                ui.label(f"{p.market}.{p.symbol}").classes(
                                    "font-bold w-24"
                                )
                                ui.label(f"持仓 {p.quantity:g}").classes("w-20 text-sm")
                                ui.label(
                                    f"浮盈 {pnl_pct:+.1f}% ({pnl_abs:+,.0f})"
                                ).classes("w-32 text-sm")
                                ui.label(
                                    f"综合 {_fmt_score(p.composite_score)}"
                                ).classes("w-16 text-sm")
                                ui.label(reason).classes(
                                    "flex-1 text-sm text-slate-600 min-w-48"
                                )
                                ui.label(f"建议卖 {rs}").classes("w-24 text-sm")

            # ── 卡片 4: 今日信号 ──
            with signals_box:
                with ui.card().classes("w-full"):
                    ui.label("🔔 今日已触发信号").classes("text-lg font-bold mb-2")
                    today_sigs = (
                        s.query(Signal)
                        .filter(Signal.created_at >= today_start)
                        .order_by(desc(Signal.created_at))
                        .limit(10)
                        .all()
                    )
                    if not today_sigs:
                        ui.label("今日无建议").classes("text-slate-500")
                    else:
                        with ui.element("table").classes(
                            "w-full text-sm border-collapse"
                        ):
                            with ui.element("thead"):
                                with ui.element("tr").classes("border-b"):
                                    for h in [
                                        "时间",
                                        "代码",
                                        "类型",
                                        "摘要",
                                        "状态",
                                    ]:
                                        el = ui.element("th").classes(
                                            "text-left p-2 font-semibold"
                                        )
                                        el.text = h
                            with ui.element("tbody"):
                                for sig in today_sigs:
                                    badge_txt, badge_cls = _signal_badge(sig.action)
                                    reason = (sig.reason or "")[:30]
                                    acted = (
                                        "✅ 已记"
                                        if sig.acted_trade_id
                                        else "⏳ 待记"
                                    )
                                    with ui.element("tr").classes(
                                        "border-b hover:bg-slate-50"
                                    ):
                                        ui.element("td").classes("p-2").text = (
                                            sig.created_at.strftime("%H:%M")
                                        )
                                        ui.element("td").classes("p-2").text = (
                                            f"{sig.market}.{sig.symbol}"
                                        )
                                        td_type = ui.element("td").classes("p-2")
                                        with td_type:
                                            ui.label(badge_txt).classes(
                                                f"px-2 py-0.5 rounded text-xs {badge_cls}"
                                            )
                                        ui.element("td").classes(
                                            "p-2 text-slate-600"
                                        ).text = reason
                                        ui.element("td").classes("p-2").text = acted
        finally:
            s.close()

    refresh()
    refresh_btn.on_click(refresh)
