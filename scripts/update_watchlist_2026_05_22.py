"""一次性迁移 watchlist — 2026-05-22

删除: AMD, V, JPM, UNH, XOM; HK 2015.HK / 9868.HK (symbol 02015 / 09868 等变体)
新增: HK.00700, HK.03690, HK.09999, US.PDD, US.PLTR, US.CRWD

用法:
  python scripts/update_watchlist_2026_05_22.py
  docker compose exec -T app python /app/scripts/update_watchlist_2026_05_22.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.init_db import init_db
from app.db.models import Watchlist, get_session

REMOVE_US = ("AMD", "V", "JPM", "UNH", "XOM")
REMOVE_HK_LABELS = ("2015.HK", "9868.HK")

ADD = (
    ("HK", "00700", "腾讯控股"),
    ("HK", "03690", "美团-W"),
    ("HK", "09999", "网易-S"),
    ("US", "PDD", "拼多多"),
    ("US", "PLTR", "Palantir"),
    ("US", "CRWD", "CrowdStrike"),
)


def _hk_symbol_variants(label: str) -> list[str]:
    """2015.HK / 9868 / 02015 → 可能出现在 DB 里的 symbol 写法。"""
    raw = label.split(".", 1)[0] if "." in label else label
    digits = "".join(c for c in raw if c.isdigit())
    if not digits:
        return []
    n = int(digits)
    padded = f"{n:05d}"
    return list({padded, digits, str(n)})


def _normalize_symbol(market: str, symbol: str) -> str:
    sym = symbol.strip().upper()
    if market == "HK":
        digits = "".join(c for c in sym if c.isdigit())
        if not digits:
            raise ValueError(f"invalid HK symbol: {symbol}")
        return f"{int(digits):05d}"
    return sym


def _delete_us(session, symbol: str) -> int:
    sym = symbol.upper()
    rows = session.query(Watchlist).filter_by(market="US", symbol=sym).all()
    for row in rows:
        session.delete(row)
    return len(rows)


def _delete_hk(session, label: str) -> int:
    variants = _hk_symbol_variants(label)
    if not variants:
        return 0
    rows = (
        session.query(Watchlist)
        .filter(Watchlist.market == "HK", Watchlist.symbol.in_(variants))
        .all()
    )
    for row in rows:
        session.delete(row)
    return len(rows)


def _add_entry(session, market: str, symbol: str, name: str) -> str:
    sym = _normalize_symbol(market, symbol)
    existing = session.query(Watchlist).filter_by(market=market, symbol=sym).first()
    if existing:
        if name and not existing.name:
            existing.name = name
        return f"skip exists {market}.{sym}"
    session.add(Watchlist(market=market, symbol=sym, name=name))
    return f"added {market}.{sym} ({name})"


def main() -> None:
    init_db()
    session = get_session()
    try:
        print("=== Remove ===")
        removed = 0
        for sym in REMOVE_US:
            n = _delete_us(session, sym)
            print(f"  US.{sym}: deleted {n}")
            removed += n
        for label in REMOVE_HK_LABELS:
            n = _delete_hk(session, label)
            variants = _hk_symbol_variants(label)
            print(f"  HK {label} (try {variants}): deleted {n}")
            removed += n

        print("=== Add ===")
        added = 0
        for market, symbol, name in ADD:
            msg = _add_entry(session, market, symbol, name)
            print(f"  {msg}")
            if msg.startswith("added"):
                added += 1

        session.commit()
        total = session.query(Watchlist).count()
        print(f"=== Done: removed {removed}, added {added}, watchlist count={total} ===")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
