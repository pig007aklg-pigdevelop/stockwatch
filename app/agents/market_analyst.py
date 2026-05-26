"""Market analyst agent node — sector sentiment and daily market view."""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from app.agents.llm import get_llm
from app.agents.state import AgentState, StockNews

log = logging.getLogger(__name__)

MARKET_LABELS = {"hk": "港股", "us": "美股"}


def _avg_sentiment(items: list[StockNews]) -> float | None:
    if not items:
        return None
    return sum(n["sentiment"] for n in items) / len(items)


def _build_context(market: str, news: dict[str, list[StockNews]]) -> tuple[float | None, str]:
    all_scores: list[float] = []
    lines: list[str] = []

    for code, items in sorted(news.items()):
        avg = _avg_sentiment(items)
        if avg is not None:
            all_scores.append(avg)
        if not items:
            lines.append(f"- {code}: 无近期新闻")
            continue
        headlines = "; ".join(
            f"{n['title'][:40]}(情绪{n['sentiment']:+.2f})" for n in items[:3]
        )
        stock_avg = f", 均分{avg:+.2f}" if avg is not None else ""
        lines.append(f"- {code}: {headlines}{stock_avg}")

    sector_avg = sum(all_scores) / len(all_scores) if all_scores else None
    return sector_avg, "\n".join(lines)


def market_analyst_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    market = (state.get("market") or "hk").lower()
    label = MARKET_LABELS.get(market, market)
    news = state.get("news") or {}

    sector_avg, stock_block = _build_context(market, news)
    dry_run = bool((config.get("configurable") or {}).get("dry_run"))

    if dry_run:
        avg_txt = f"{sector_avg:+.2f}" if sector_avg is not None else "N/A"
        return {
            "market_view": (
                f"[dry-run] 今日{label}观察: 板块平均新闻情绪 {avg_txt}。"
                f"共覆盖 {len(news)} 只成分股,数据流正常。"
            )
        }

    avg_line = (
        f"板块平均新闻情绪: {sector_avg:+.2f} (-1极负面~+1极正面)。"
        if sector_avg is not None
        else "板块平均新闻情绪: 暂无足够新闻样本。"
    )

    prompt = f"""你是资深{label}市场分析师。根据以下今日新闻情绪数据与各股新闻摘要,写一段约200字的中文「今日大盘观察」。

要求:
- 先概括整体情绪与板块氛围
- 点出情绪偏强/偏弱的几只代表股(若有)
- 语气客观,不做具体买卖建议
- 直接输出正文,不要标题、不要 JSON

{avg_line}

各股摘要:
{stock_block or '(无新闻数据)'}
"""

    try:
        resp = get_llm().invoke([HumanMessage(content=prompt)])
        text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        if not text:
            raise ValueError("empty LLM response")
        return {"market_view": text[:800]}
    except Exception as e:
        log.warning("market_analyst LLM failed: %s", e)
        fallback_avg = f"{sector_avg:+.2f}" if sector_avg is not None else "N/A"
        return {
            "market_view": (
                f"今日{label}新闻情绪均分 {fallback_avg}。"
                f"覆盖 {len(news)} 只成分股,LLM 生成失败,请稍后重试。"
            )
        }
