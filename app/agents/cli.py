"""CLI entry for the multi-agent stock analysis pipeline."""
from __future__ import annotations

import argparse
import logging
import sys
import time

from langchain_core.messages import HumanMessage

from app.agents.llm import get_llm
from app.agents.news import fetch_yahoo_rss_news
from app.agents.runner import run_agent_pipeline
from app.agents.state import StockNews
from app.config import config
from app.services.futu_client import futu

log = logging.getLogger(__name__)

MARKET_LABELS = {"hk": "港股", "us": "美股"}


def _avg_sentiment(items: list[StockNews]) -> float | None:
    if not items:
        return None
    return sum(n["sentiment"] for n in items) / len(items)


def _format_sentiments(scores: list[float]) -> str:
    if not scores:
        return "[]"
    return "[" + ", ".join(f"{s:.2f}" for s in scores) + "]"


def _print_results(market: str, result: dict, *, dry_run: bool) -> None:
    label = MARKET_LABELS.get(market, market)
    candidates = result.get("candidates") or []
    news: dict[str, list[StockNews]] = result.get("news") or {}
    market_view = (result.get("market_view") or "").strip()
    final_picks = result.get("final_picks") or []

    mode = "dry-run" if dry_run else "live"
    print()
    print("=" * 60)
    print(f"StockWatch 多智能体分析 | {label} | {mode}")
    print("=" * 60)
    print(f"\n候选池: {len(candidates)} 只\n")

    for code in candidates:
        items = news.get(code) or []
        scores = [n["sentiment"] for n in items]
        avg = _avg_sentiment(items)
        avg_txt = f"{avg:.2f}" if avg is not None else "N/A"
        print(
            f"  {code} | {len(items)} 条新闻 | sentiments: {_format_sentiments(scores)} | 均分 {avg_txt}"
        )

    print("-" * 60)
    print("\n今日大盘观察:\n")
    if market_view:
        print(f"  {market_view}\n")
    else:
        print("  (无输出)\n")

    print("-" * 60)
    print(f"\n最终推荐 ({len(final_picks)} 只):\n")
    if not final_picks:
        print("  (无)\n")
    for p in final_picks:
        rank = p.get("rank", "?")
        code = p.get("code", "")
        name = p.get("name") or code
        score = p.get("score")
        price = p.get("price")
        line = f"  {rank}. {name} ({code})"
        if score is not None:
            line += f" 分{score:.0f}"
        print(line)
        if price is not None:
            print(f"      现价 {price:.2f}")
        bl, bh = p.get("buy_range_low"), p.get("buy_range_high")
        if bl is not None and bh is not None:
            print(f"      买入 {bl:.2f} ~ {bh:.2f}")
        if p.get("stop_loss") is not None:
            print(f"      止损 {p['stop_loss']:.2f}")
        if p.get("target") is not None:
            print(f"      目标 {p['target']:.2f}")
        if p.get("tech_view"):
            print(f"      技术: {p['tech_view'][:100]}")
        if p.get("risk_view"):
            print(f"      风控: {p['risk_view'][:100]}")
        print()

    print("=" * 60)


def run_check() -> int:
    print()
    print("=" * 60)
    print("StockWatch 连通性自检")
    print("=" * 60)

    # DeepSeek
    print("\n[DeepSeek]")
    api_key = (config.OPENAI_API_KEY or "").strip()
    if not api_key:
        print("  状态: FAIL")
        print("  原因: OPENAI_API_KEY 未配置 (.env)")
    else:
        model = (config.OPENAI_MODEL or "").strip() or "(default)"
        base_url = (config.OPENAI_BASE_URL or "").strip() or "(default)"
        print(f"  model: {model}")
        print(f"  base_url: {base_url}")
        t0 = time.perf_counter()
        try:
            llm = get_llm()
            resp = llm.invoke(
                [HumanMessage(content='Reply with exactly one word: pong')],
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
            print(f"  状态: OK")
            print(f"  延迟: {latency_ms:.0f} ms")
            print(f"  响应: {text[:120]}")
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000
            print(f"  状态: FAIL")
            print(f"  延迟: {latency_ms:.0f} ms")
            print(f"  错误: {e}")

    # Futu
    print("\n[Futu OpenD]")
    try:
        futu.connect()
        snap = futu.get_snapshot(["HK.00700"])
        if snap.get("HK.00700"):
            row = snap["HK.00700"]
            print("  状态: OK")
            print(f"  HK.00700 最新价: {row.get('price')} 涨跌幅: {row.get('change_pct')}%")
        else:
            print("  状态: FAIL")
            print("  原因: get_snapshot 未返回 HK.00700 数据")
    except Exception as e:
        print(f"  状态: FAIL")
        print(f"  错误: {e}")
    finally:
        futu.close()

    # Yahoo RSS
    print("\n[Yahoo RSS]")
    try:
        items = fetch_yahoo_rss_news("HK.00700")
        print("  状态: OK")
        print(f"  HK.00700 条数: {len(items)}")
        for i, item in enumerate(items[:3], 1):
            title = (item.get("title") or "")[:70]
            print(f"    {i}. {title}")
    except Exception as e:
        print(f"  状态: FAIL")
        print(f"  错误: {e}")

    print("\n" + "=" * 60)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="StockWatch multi-agent analysis")
    parser.add_argument("--market", choices=("hk", "us"), default="hk", help="市场: hk 或 us")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="不调 DeepSeek(市场/共识用 mock/规则),验证数据流",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="跑完后发送 Telegram(默认仅打印)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="连通性自检 (DeepSeek / Futu / Yahoo RSS),不跑 graph",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.check:
        return run_check()

    try:
        result = run_agent_pipeline(
            args.market,
            notify=args.notify,
            dry_run=args.dry_run,
        )
        _print_results(args.market, result, dry_run=args.dry_run)
        return 0
    except Exception as e:
        log.exception("pipeline failed: %s", e)
        print(f"\n错误: {e}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
