"""NiceGUI 看板 - 总览/持仓/新闻/信号"""
import math
from datetime import datetime, timedelta
from nicegui import ui, run, app as nicegui_app
from sqlalchemy import desc
from app.db.models import get_session, Position, PriceSnapshot, Signal, News, Trade
from app.jobs.constants import ACTIONABLE
from app.services.futu_client import futu
from app.jobs.price_scanner import scan_once
from app.jobs.news_scraper import fetch_for_symbol
from app.jobs.scoring_job import run_daily_scoring


def _latest_price(s, symbol):
    row = (s.query(PriceSnapshot).filter_by(symbol=symbol)
           .order_by(desc(PriceSnapshot.timestamp)).first())
    return row


def _is_score_incomplete(p) -> bool:
    return all(
        getattr(p, f"score_{d}", None) is None
        for d in ("valuation", "capital", "technical", "fundamental")
    )


def _fmt_score(v, incomplete: bool = False):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "-"
    text = f"{v:.0f}"
    return f"⚠️{text}" if incomplete else text


def _score_color(v):
    if v is None:
        return "slate"
    if v < 30:
        return "red"
    if v < 60:
        return "amber"
    return "green"


def _wire_scoring_button(btn, label: str, on_success=None):
    """立即打分：disable + 全局锁，后台线程执行。"""

    async def _run_scoring():
        btn.disable()
        btn.set_text("打分中...")
        try:
            ok = await run.io_bound(run_daily_scoring)
            if ok:
                if on_success:
                    on_success()
                ui.notify("打分完成", color="positive")
            else:
                ui.notify("打分任务进行中，请稍候", color="warning")
        finally:
            btn.enable()
            btn.set_text(label)

    btn.on_click(_run_scoring)


def render_header():
    with ui.header(elevated=True).classes("bg-slate-800 text-white"):
        ui.label("📈 StockWatch").classes("text-xl font-bold")
        ui.space()
        ui.link("总览", "/").classes("text-white mx-2")
        ui.link("持仓", "/positions").classes("text-white mx-2")
        ui.link("新闻", "/news").classes("text-white mx-2")
        ui.link("信号", "/signals").classes("text-white mx-2")
        ui.link("交易日志", "/trades").classes("text-white mx-2")


# ────────── 总览 ──────────
@ui.page("/")
def dashboard():
    render_header()
    with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-4"):
        ui.label("📊 总览").classes("text-2xl font-bold")

        stats_row = ui.row().classes("gap-4 w-full")

        def refresh():
            stats_row.clear()
            s = get_session()
            try:
                positions = s.query(Position).all()
                total_cost = sum(p.cost_price * p.quantity for p in positions)
                total_mv = 0.0
                signals_24h = (s.query(Signal)
                               .filter(Signal.created_at >= datetime.utcnow() - timedelta(hours=24))
                               .filter(Signal.action != "HOLD").count())
                for p in positions:
                    lp = _latest_price(s, p.symbol)
                    if lp:
                        total_mv += lp.price * p.quantity
                pnl = total_mv - total_cost
                pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else 0

                def card(title, value, color="slate"):
                    with stats_row:
                        with ui.card().classes(f"flex-1 bg-{color}-50"):
                            ui.label(title).classes("text-sm text-slate-600")
                            ui.label(value).classes("text-2xl font-bold")

                card("持仓数", f"{len(positions)}")
                card("总成本", f"{total_cost:,.2f}")
                card("总市值", f"{total_mv:,.2f}")
                card("浮动盈亏", f"{pnl:+,.2f} ({pnl_pct:+.2f}%)",
                     "green" if pnl >= 0 else "red")
                card("24h 信号", f"{signals_24h}", "amber")
            finally:
                s.close()

        refresh()

        with ui.row().classes("gap-2"):
            ui.button("🔄 刷新", on_click=refresh).props("color=primary")
            ui.button("⏱ 立即扫描", on_click=lambda: (scan_once(), refresh(),
                                                  ui.notify("扫描完成", color="positive")))
            score_btn = ui.button("📐 立即打分").props("color=secondary")
            _wire_scoring_button(
                score_btn,
                "📐 立即打分",
                on_success=lambda: (refresh(), refresh_holdings()),
            )

        ui.label("📋 持仓概览").classes("text-xl font-bold mt-4")
        holdings_table = ui.element("div").classes("w-full")

        def refresh_holdings():
            holdings_table.clear()
            s = get_session()
            try:
                positions = s.query(Position).all()
                rows = []
                for p in positions:
                    lp = _latest_price(s, p.symbol)
                    price = lp.price if lp else 0
                    change_pct = lp.change_pct if lp else 0
                    pnl_pct = ((price - p.cost_price) / p.cost_price * 100) if p.cost_price > 0 else 0
                    pnl_abs = (price - p.cost_price) * p.quantity
                    rows.append({
                        "symbol": f"{p.market}.{p.symbol}",
                        "name": p.name or "-",
                        "composite": _fmt_score(
                            p.composite_score, incomplete=_is_score_incomplete(p)
                        ),
                        "cost": f"{p.cost_price:.2f}",
                        "price": f"{price:.2f}" if price else "-",
                        "day_chg": f"{change_pct:+.2f}%",
                        "pnl_pct": f"{pnl_pct:+.2f}%",
                        "pnl_abs": f"{pnl_abs:+.2f}",
                        "qty": f"{p.quantity:g}",
                        "rec_buy": f"{p.recommended_buy:.2f}" if p.recommended_buy else "-",
                        "rec_sell": f"{p.recommended_sell:.2f}" if p.recommended_sell else "-",
                        "watch_lo": f"{p.watch_below:.2f}" if p.watch_below else "-",
                        "watch_hi": f"{p.watch_above:.2f}" if p.watch_above else "-",
                        "sl": f"{p.stop_loss:.2f}" if p.stop_loss else "-",
                        "tp": f"{p.take_profit:.2f}" if p.take_profit else "-",
                        "_pid": p.id,
                    })
                with holdings_table:
                    ui.table(columns=[
                        {"name": "symbol", "label": "代码", "field": "symbol", "align": "left"},
                        {"name": "name", "label": "名称", "field": "name", "align": "left"},
                        {"name": "composite", "label": "综合分", "field": "composite"},
                        {"name": "qty", "label": "数量", "field": "qty"},
                        {"name": "cost", "label": "成本", "field": "cost"},
                        {"name": "price", "label": "现价", "field": "price"},
                        {"name": "day_chg", "label": "日涨幅", "field": "day_chg"},
                        {"name": "pnl_pct", "label": "盈亏%", "field": "pnl_pct"},
                        {"name": "rec_buy", "label": "推荐买", "field": "rec_buy"},
                        {"name": "rec_sell", "label": "推荐卖", "field": "rec_sell"},
                        {"name": "watch_lo", "label": "关注下限", "field": "watch_lo"},
                        {"name": "watch_hi", "label": "关注上限", "field": "watch_hi"},
                        {"name": "sl", "label": "止损", "field": "sl"},
                        {"name": "tp", "label": "止盈", "field": "tp"},
                    ], rows=rows, row_key="symbol").classes("w-full")
            finally:
                s.close()
        refresh_holdings()


# ────────── 持仓管理 ──────────
@ui.page("/positions")
def positions_page():
    render_header()
    with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-4"):
        ui.label("📋 持仓管理").classes("text-2xl font-bold")

        # 添加表单
        with ui.card().classes("w-full"):
            ui.label("➕ 添加持仓").classes("font-bold")
            with ui.row().classes("gap-2 items-end"):
                sym = ui.input("代码 (NVDA/00700)").classes("w-32")
                mkt = ui.select(["US", "HK"], value="US", label="市场").classes("w-24")
                name = ui.input("名称").classes("w-32")
                cost = ui.number("成本价", value=0, format="%.2f").classes("w-28")
                qty = ui.number("数量", value=0).classes("w-24")
                sl = ui.number("止损价", value=None, format="%.2f").classes("w-28")
                tp = ui.number("止盈价", value=None, format="%.2f").classes("w-28")
                wb = ui.number("关注下限", value=None, format="%.2f").classes("w-28")
                wa = ui.number("关注上限", value=None, format="%.2f").classes("w-28")

                def add():
                    if not sym.value or not cost.value:
                        ui.notify("代码和成本价必填", color="negative"); return
                    s = get_session()
                    try:
                        p = Position(symbol=sym.value.upper(), market=mkt.value,
                                     name=name.value or "", cost_price=float(cost.value),
                                     quantity=float(qty.value or 0),
                                     stop_loss=float(sl.value) if sl.value else None,
                                     take_profit=float(tp.value) if tp.value else None,
                                     watch_below=float(wb.value) if wb.value else None,
                                     watch_above=float(wa.value) if wa.value else None)
                        s.add(p); s.commit()
                        ui.notify(f"✅ 添加 {p.market}.{p.symbol}", color="positive")
                        sym.value=""; name.value=""; cost.value=0; qty.value=0
                        sl.value=None; tp.value=None
                        wb.value=None; wa.value=None
                        refresh()
                    finally:
                        s.close()
                ui.button("添加", on_click=add).props("color=primary")

        # 列表
        list_box = ui.element("div").classes("w-full")

        def refresh():
            list_box.clear()
            s = get_session()
            try:
                positions = s.query(Position).order_by(Position.id).all()
                with list_box:
                    for p in positions:
                        with ui.card().classes("w-full"):
                            with ui.row().classes("items-center gap-2 w-full"):
                                ui.label(f"{p.market}.{p.symbol}").classes("font-bold text-lg w-32")
                                name_in = ui.input(value=p.name or "").classes("w-32")
                                cost_in = ui.number(value=p.cost_price, format="%.2f").classes("w-28")
                                qty_in = ui.number(value=p.quantity).classes("w-24")
                                sl_in = ui.number(value=p.stop_loss, format="%.2f").classes("w-28")
                                tp_in = ui.number(value=p.take_profit, format="%.2f").classes("w-28")
                                wb_in = ui.number(value=p.watch_below, format="%.2f").classes("w-28")
                                wa_in = ui.number(value=p.watch_above, format="%.2f").classes("w-28")
                                ui.link("📐 打分详情", f"/positions/{p.id}").classes("text-sm")

                                def save(pid=p.id, ni=name_in, ci=cost_in, qi=qty_in,
                                         si=sl_in, ti=tp_in, wbi=wb_in, wai=wa_in):
                                    ss = get_session()
                                    try:
                                        pp = ss.query(Position).get(pid)
                                        pp.name = ni.value or ""
                                        pp.cost_price = float(ci.value)
                                        pp.quantity = float(qi.value or 0)
                                        pp.stop_loss = float(si.value) if si.value else None
                                        pp.take_profit = float(ti.value) if ti.value else None
                                        pp.watch_below = float(wbi.value) if wbi.value else None
                                        pp.watch_above = float(wai.value) if wai.value else None
                                        ss.commit()
                                        ui.notify("已保存", color="positive")
                                    finally:
                                        ss.close()
                                ui.button("💾 保存", on_click=save).props("size=sm")

                                def delete(pid=p.id):
                                    ss = get_session()
                                    try:
                                        ss.query(Position).filter_by(id=pid).delete()
                                        ss.commit()
                                    finally:
                                        ss.close()
                                    ui.notify("已删除", color="warning")
                                    refresh()
                                ui.button("🗑", on_click=delete).props("color=negative size=sm")

                                def fetch_n(sym_=p.symbol, mkt_=p.market, nm_=p.name):
                                    n = fetch_for_symbol(sym_, mkt_, nm_)
                                    ui.notify(f"新增 {n} 条新闻", color="info")
                                ui.button("📰", on_click=fetch_n).props("size=sm")
            finally:
                s.close()
        refresh()
        batch_score_btn = ui.button("📐 全部重新打分").props("color=secondary")
        _wire_scoring_button(batch_score_btn, "📐 全部重新打分", on_success=refresh)


@ui.page("/positions/{pos_id}")
def position_detail(pos_id: str):
    render_header()
    with ui.column().classes("w-full max-w-3xl mx-auto p-4 gap-4"):
        s = get_session()
        try:
            p = s.query(Position).get(int(pos_id))
            if not p:
                ui.label("未找到持仓").classes("text-red-600")
                return
            ui.label(f"📐 {p.market}.{p.symbol} {p.name or ''}").classes("text-2xl font-bold")
            updated = (
                p.score_updated_at.strftime("%Y-%m-%d %H:%M UTC")
                if p.score_updated_at else "尚未打分"
            )
            ui.label(f"更新时间: {updated}").classes("text-sm text-slate-500")

            incomplete = _is_score_incomplete(p)
            comp = p.composite_score
            ui.label(f"综合分: {_fmt_score(comp, incomplete=incomplete)}").classes(
                f"text-3xl font-bold text-{_score_color(comp)}-600"
            )
            if incomplete:
                ui.label("⚠️ 数据不完整，综合分为保底值").classes("text-sm text-amber-600")

            dims = [
                ("估值 25%", p.score_valuation, "valuation"),
                ("资金面 25%", p.score_capital, "capital"),
                ("技术面 20%", p.score_technical, "technical"),
                ("基本面 20%", p.score_fundamental, "fundamental"),
                ("新闻 10%", p.score_news, "news"),
            ]
            if p.market == "US":
                dims[0] = ("估值 33%", p.score_valuation, "valuation")
                dims[1] = ("资金面 —", p.score_capital, "capital")
                dims[2] = ("技术面 27%", p.score_technical, "technical")
                dims[3] = ("基本面 27%", p.score_fundamental, "fundamental")
                dims[4] = ("新闻 13%", p.score_news, "news")

            for label, val, _ in dims:
                with ui.row().classes("items-center gap-2 w-full"):
                    ui.label(label).classes("w-28")
                    v = val if val is not None else 0
                    ui.linear_progress(value=v / 100, show_value=False).classes("flex-1")
                    ui.label(_fmt_score(val)).classes("w-10 text-right")

            with ui.card().classes("w-full"):
                ui.label("推荐价 (打分驱动)").classes("font-bold")
                ui.label(
                    f"推荐买: {p.recommended_buy:.2f}" if p.recommended_buy else "推荐买: -"
                )
                ui.label(
                    f"推荐卖: {p.recommended_sell:.2f}" if p.recommended_sell else "推荐卖: -"
                )
                ui.label(
                    f"手工兜底 — 下限: {p.watch_below or '-'} / 上限: {p.watch_above or '-'}"
                ).classes("text-sm text-slate-600")

            ui.link("← 返回持仓列表", "/positions")
        finally:
            s.close()


# ────────── 新闻 ──────────
@ui.page("/news")
def news_page():
    render_header()
    with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-4"):
        ui.label("📰 新闻流").classes("text-2xl font-bold")
        box = ui.element("div").classes("w-full")

        def refresh():
            box.clear()
            s = get_session()
            try:
                rows = (s.query(News).order_by(desc(News.published_at)).limit(100).all())
                with box:
                    for n in rows:
                        color = {"bullish": "green", "bearish": "red", "neutral": "slate"}.get(n.sentiment, "slate")
                        with ui.card().classes("w-full"):
                            with ui.row().classes("items-start gap-2 w-full"):
                                ui.badge(n.symbol or "GLOBAL").props("color=blue")
                                ui.badge(n.sentiment or "neutral").props(f"color={color}")
                                ui.label(n.published_at.strftime("%m-%d %H:%M") if n.published_at else "").classes("text-xs text-slate-500")
                            ui.link(n.title, n.url, new_tab=True).classes("font-bold")
                            if n.summary and n.summary != n.title:
                                ui.label(n.summary).classes("text-sm text-slate-600")
                            ui.label(f"来源: {n.source}").classes("text-xs text-slate-400")
            finally:
                s.close()
        refresh()
        ui.button("🔄 刷新", on_click=refresh).props("color=primary")


# ────────── 信号 ──────────
@ui.page("/signals")
def signals_page():
    render_header()
    with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-4"):
        ui.label("🚨 信号历史").classes("text-2xl font-bold")
        box = ui.element("div").classes("w-full")

        def refresh():
            box.clear()
            s = get_session()
            try:
                rows = (s.query(Signal).filter(Signal.action != "HOLD")
                        .order_by(desc(Signal.created_at)).limit(200).all())
                data = [{
                    "time": r.created_at.strftime("%m-%d %H:%M"),
                    "symbol": f"{r.market}.{r.symbol}",
                    "action": r.action,
                    "price": f"{r.price:.2f}",
                    "cost": f"{r.cost_price:.2f}",
                    "pnl": f"{r.pnl_pct:+.2f}%",
                    "reason": r.reason,
                } for r in rows]
                with box:
                    ui.table(columns=[
                        {"name": "time", "label": "时间", "field": "time"},
                        {"name": "symbol", "label": "代码", "field": "symbol"},
                        {"name": "action", "label": "动作", "field": "action"},
                        {"name": "price", "label": "价格", "field": "price"},
                        {"name": "cost", "label": "成本", "field": "cost"},
                        {"name": "pnl", "label": "盈亏%", "field": "pnl"},
                        {"name": "reason", "label": "说明", "field": "reason", "align": "left"},
                    ], rows=data).classes("w-full")
            finally:
                s.close()
        refresh()


# ────────── 交易日志 ──────────
@ui.page("/trades")
def trades_page():
    render_header()
    with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-4"):
        ui.label("📒 交易日志").classes("text-2xl font-bold")

        list_box = ui.element("div").classes("w-full")

        def refresh():
            list_box.clear()
            s = get_session()
            try:
                trades = s.query(Trade).order_by(desc(Trade.traded_at)).limit(100).all()
                with list_box:
                    if not trades:
                        ui.label("(暂无交易)").classes("text-slate-500")
                        return
                    rows = [{
                        "time": t.traded_at.strftime("%m-%d %H:%M"),
                        "symbol": f"{t.market}.{t.symbol}",
                        "side": t.side,
                        "price": f"{t.price:.2f}",
                        "qty": f"{t.quantity:g}",
                        "pnl": f"{t.realized_pnl:+.2f}" if t.realized_pnl is not None else "-",
                        "hold": str(t.holding_days) if t.holding_days else "-",
                        "signal": f"#{t.linked_signal_id}" if t.linked_signal_id else "-",
                        "notes": (t.notes or "")[:40],
                    } for t in trades]
                    ui.table(columns=[
                        {"name": "time", "label": "时间", "field": "time"},
                        {"name": "symbol", "label": "代码", "field": "symbol"},
                        {"name": "side", "label": "方向", "field": "side"},
                        {"name": "price", "label": "价格", "field": "price"},
                        {"name": "qty", "label": "数量", "field": "qty"},
                        {"name": "pnl", "label": "盈亏", "field": "pnl"},
                        {"name": "hold", "label": "持有天", "field": "hold"},
                        {"name": "signal", "label": "信号", "field": "signal"},
                        {"name": "notes", "label": "备注", "field": "notes", "align": "left"},
                    ], rows=rows).classes("w-full")
            finally:
                s.close()

        with ui.card().classes("w-full mt-0"):
            ui.label("➕ 新增交易").classes("text-lg font-bold")
            s = get_session()
            try:
                positions = s.query(Position).all()
                pos_options = {p.id: f"{p.market}.{p.symbol} {p.name or ''}" for p in positions}
                cutoff = datetime.utcnow() - timedelta(days=30)
                open_signals = (
                    s.query(Signal)
                    .filter(
                        Signal.created_at >= cutoff,
                        Signal.acted_trade_id.is_(None),
                        Signal.action.in_(list(ACTIONABLE)),
                    )
                    .order_by(desc(Signal.created_at))
                    .limit(50)
                    .all()
                )
                sig_options = {0: "(无关联)"}
                for sig in open_signals:
                    sig_options[sig.id] = (
                        f"#{sig.id} {sig.market}.{sig.symbol} {sig.action} "
                        f"@ {sig.price:.2f} ({sig.created_at.strftime('%m-%d %H:%M')})"
                    )
            finally:
                s.close()

            with ui.row().classes("gap-2 items-end flex-wrap"):
                pos_sel = ui.select(pos_options, label="持仓").classes("w-64")
                side_sel = ui.select({"BUY": "买入", "SELL": "卖出"}, label="方向", value="BUY").classes("w-32")
                price_in = ui.number(label="成交价", format="%.4f", value=0).classes("w-32")
                qty_in = ui.number(label="数量", format="%.0f", value=0).classes("w-28")
                fee_in = ui.number(label="手续费", format="%.2f", value=0).classes("w-28")
                pnl_in = ui.number(label="实现盈亏(SELL)", format="%.2f", value=0).classes("w-32")
                hold_in = ui.number(label="持有天数(SELL)", format="%.0f", value=0).classes("w-28")
                sig_sel = ui.select(sig_options, label="关联信号", value=0).classes("w-96")
                date_in = ui.input(label="成交时间", value=datetime.now().strftime("%Y-%m-%d %H:%M")).classes("w-44")
                notes_in = ui.input(label="备注").classes("w-64")

                def submit():
                    if not pos_sel.value or not price_in.value or not qty_in.value:
                        ui.notify("持仓/成交价/数量必填", color="negative")
                        return
                    ss = get_session()
                    try:
                        p = ss.get(Position, int(pos_sel.value))
                        if not p:
                            ui.notify("持仓不存在", color="negative")
                            return
                        try:
                            traded_at = datetime.strptime(date_in.value, "%Y-%m-%d %H:%M")
                        except ValueError:
                            traded_at = datetime.utcnow()
                        side = side_sel.value
                        linked_sig_id = int(sig_sel.value) if sig_sel.value else None
                        t = Trade(
                            symbol=p.symbol,
                            market=p.market,
                            side=side,
                            price=float(price_in.value),
                            quantity=float(qty_in.value),
                            fee=float(fee_in.value or 0),
                            realized_pnl=float(pnl_in.value) if side == "SELL" and pnl_in.value else None,
                            holding_days=int(hold_in.value) if side == "SELL" and hold_in.value else None,
                            linked_signal_id=linked_sig_id,
                            notes=notes_in.value or "",
                            traded_at=traded_at,
                        )
                        ss.add(t)
                        ss.flush()
                        p.last_trade_id = t.id
                        if linked_sig_id:
                            sig = ss.get(Signal, linked_sig_id)
                            if sig:
                                sig.acted_trade_id = t.id
                        ss.commit()
                        ui.notify(f"✅ 已记录 {side} {p.symbol} #{t.id}", color="positive")
                        refresh()
                    finally:
                        ss.close()

                ui.button("提交", on_click=submit).props("color=primary")

        ui.label("📋 交易记录").classes("text-xl font-bold mt-4")
        refresh()
        ui.button("🔄 刷新", on_click=refresh).props("color=primary")
