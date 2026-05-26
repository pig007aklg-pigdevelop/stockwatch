"""CLI entry for the multi-agent stock analysis pipeline."""
from __future__ import annotations

import argparse
import logging
import sys

from app.agents.graph import build_graph
from app.agents.state import StockNews
from app.services.futu_client import futu

log = logging.getLogger(__name__)

MARKET_LABELS = {"hk": "港股", "us": "美股"}


def _avg_sentiment(items: list[StockNews]) -> float | None:
    if not items:
        return None
    return sum(n["sentiment"] for n in items) / len(items)


def _print_results(market: str, result: dict, *, dry_run: bool) -> None:
    label = MARKET_LABELS.get(market, market)
    candidates = result.get("candidates") or []
    news: dict[str, list[StockNews]] = result.get("news") or {}
    market_view = (result.get("market_view") or "").strip()

    mode = "dry-run" if dry_run else "live"
    print()
    print("=" * 60)
    print(f"StockWatch 多智能体分析 | {label} | {mode}")
    print("=" * 60)
    print(f"\n候选池: {len(candidates)} 只\n")

    for code in candidates:
        items = news.get(code) or []
        if not items:
            print(f"  {code}: 0 条新闻")
            continue
        scores = [n["sentiment"] for n in items]
        avg = _avg_sentiment(items)
        avg_txt = f"{avg:+.2f}" if avg is not None else "N/A"
        score_txt = ", ".join(f"{s:+.2f}" for s in scores)
        print(f"  {code}: {len(items)} 条新闻 | 情绪 [{score_txt}] | 均分 {avg_txt}")
        for n in items:
            title = (n.get("title") or "")[:56]
            print(f"      · {title} ({n['sentiment']:+.2f})")

    print("\n今日大盘观察:\n")
    if market_view:
        print(f"  {market_view}\n")
    else:
        print("  (无输出)\n")

    print("=" * 60)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="StockWatch multi-agent analysis (Stage 1)")
    parser.add_argument("--market", choices=("hk", "us"), default="hk", help="市场: hk 或 us")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="不调 DeepSeek,用 mock 数据验证数据流",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    initial = {
        "market": args.market,
        "candidates": [],
        "news": {},
        "market_view": "",
        "trader_picks": [],
        "risk_assessment": [],
        "final_picks": [],
    }

    try:
        futu.connect()
        graph = build_graph()
        result = graph.invoke(
            initial,
            config={"configurable": {"dry_run": args.dry_run}},
        )
        _print_results(args.market, result, dry_run=args.dry_run)
        return 0
    except Exception as e:
        log.exception("pipeline failed: %s", e)
        print(f"\n错误: {e}\n", file=sys.stderr)
        return 1
    finally:
        futu.close()


if __name__ == "__main__":
    raise SystemExit(main())
