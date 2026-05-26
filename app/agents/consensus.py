"""Consensus node — LLM generates trade plan for Top N (dry-run uses rules)."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from app.agents.llm import get_llm
from app.agents.state import AgentState
from app.services.futu_client import futu

log = logging.getLogger(__name__)

CONSENSUS_PROMPT = """你是投资组合共识会议主持。根据以下候选标的的技术面、新闻情绪与市场观察，为每只给出具体交易计划。

要求:
- 买入区间为合理低吸区间(低<高), 参考现价与支撑
- 止损应低于买入区间下沿
- 目标价应高于现价且有空间
- tech_view: 一句话技术面点评
- risk_view: 一句话风控提示
- 返回 JSON 数组,不要其它文字:
[{{"code":"HK.00700","buy_range_low":380,"buy_range_high":395,"stop_loss":360,"target":450,"tech_view":"...","risk_view":"..."}}]

市场观察:
{market_view}

候选标的:
{blocks}
"""


def _dry_run_from_config(config: RunnableConfig) -> bool:
    return bool((config.get("configurable") or {}).get("dry_run"))


def _rule_prices(pick: dict[str, Any], ind: dict[str, Any] | None) -> dict[str, float]:
    price = float(pick.get("price") or (ind or {}).get("price") or 0)
    if price <= 0:
        price = 100.0
    low_20 = float((ind or {}).get("low_20d") or price * 0.95)
    high_52 = float((ind or {}).get("high_52w") or price * 1.1)
    buy_low = round(min(low_20, price * 0.97), 2)
    buy_high = round(min(price * 0.995, buy_low * 1.03), 2)
    if buy_high <= buy_low:
        buy_high = round(buy_low * 1.02, 2)
    stop = round(buy_low * 0.95, 2)
    target = round(min(high_52, price * 1.12), 2)
    if target <= price:
        target = round(price * 1.08, 2)
    return {
        "buy_range_low": buy_low,
        "buy_range_high": buy_high,
        "stop_loss": stop,
        "target": target,
    }


def _build_block(pick: dict[str, Any], ind: dict[str, Any] | None, news_avg: float | None) -> str:
    code = pick.get("code", "")
    score = pick.get("score")
    tv = pick.get("tech_view") or (ind or {}).get("tech_view") or ""
    price = pick.get("price") or (ind or {}).get("price")
    sent = news_avg if news_avg is not None else pick.get("news_sentiment_avg")
    return (
        f"- {code} 规则分{score} 现价{price} 情绪{sent} "
        f"技术:{tv} DIF={(ind or {}).get('dif')} DEA={(ind or {}).get('dea')} RSI={(ind or {}).get('rsi')}"
    )


def _parse_llm_json(text: str) -> list[dict]:
    text = text.strip()
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return []
    data = json.loads(m.group())
    if isinstance(data, list):
        return data
    return []


def _merge_llm_row(pick: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    out = dict(pick)
    for key in ("buy_range_low", "buy_range_high", "stop_loss", "target", "tech_view", "risk_view"):
        if row.get(key) is not None:
            out[key] = row[key]
    return out


def _enrich_snapshots(picks: list[dict[str, Any]]) -> None:
    codes = [p.get("code") for p in picks if p.get("code")]
    if not codes:
        return
    try:
        snap = futu.get_snapshot(codes)
    except Exception as e:
        log.warning("consensus snapshot failed: %s", e)
        return
    for p in picks:
        code = p.get("code")
        row = snap.get(code) if code else None
        if not row:
            continue
        if row.get("name"):
            p["name"] = row["name"]
        if row.get("price"):
            p["price"] = row["price"]


def consensus_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    picks = list(state.get("consensus_picks") or [])
    if not picks:
        return {"final_picks": []}

    technical = state.get("technical") or {}
    news = state.get("news") or {}
    market_view = (state.get("market_view") or "").strip()
    dry_run = _dry_run_from_config(config)

    _enrich_snapshots(picks)

    if dry_run:
        final: list[dict[str, Any]] = []
        for p in picks:
            code = p.get("code", "")
            ind = technical.get(code)
            prices = _rule_prices(p, ind)
            final.append(
                {
                    **p,
                    **prices,
                    "tech_view": p.get("tech_view") or (ind or {}).get("tech_view") or "[dry-run] 技术面",
                    "risk_view": "[dry-run] 规则风控已通过",
                }
            )
        return {"final_picks": final}

    blocks = []
    for p in picks:
        code = p.get("code", "")
        items = news.get(code) or []
        avg = None
        if items:
            avg = sum(n["sentiment"] for n in items) / len(items)
        blocks.append(_build_block(p, technical.get(code), avg))

    prompt = CONSENSUS_PROMPT.format(
        market_view=market_view or "(无)",
        blocks="\n".join(blocks),
    )

    final = []
    try:
        llm = get_llm()
        resp = llm.invoke([HumanMessage(content=prompt)])
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        rows = _parse_llm_json(text)
        by_code = {r.get("code"): r for r in rows if r.get("code")}
        for p in picks:
            code = p.get("code")
            row = by_code.get(code, {})
            merged = _merge_llm_row(p, row)
            if not merged.get("tech_view"):
                merged["tech_view"] = p.get("tech_view") or ""
            if not merged.get("risk_view"):
                merged["risk_view"] = "关注仓位与波动"
            if not merged.get("buy_range_low"):
                merged.update(_rule_prices(p, technical.get(code)))
            final.append(merged)
    except Exception as e:
        log.exception("consensus LLM failed: %s", e)
        for p in picks:
            code = p.get("code", "")
            ind = technical.get(code)
            final.append(
                {
                    **p,
                    **_rule_prices(p, ind),
                    "tech_view": p.get("tech_view") or "",
                    "risk_view": f"LLM失败,规则兜底: {e}",
                }
            )

    return {"final_picks": final}
