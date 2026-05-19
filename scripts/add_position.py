"""命令行加持仓
用法:
  python scripts/add_position.py NVDA US 135.0 10 [--sl 125 --tp 200] [--name 英伟达]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
from app.db.models import get_session, Position
from app.db.init_db import init_db


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("market", choices=["US", "HK"])
    ap.add_argument("cost_price", type=float)
    ap.add_argument("quantity", type=float)
    ap.add_argument("--sl", type=float, default=None)
    ap.add_argument("--tp", type=float, default=None)
    ap.add_argument("--watch-below", type=float, default=None)
    ap.add_argument("--watch-above", type=float, default=None)
    ap.add_argument("--name", default="")
    args = ap.parse_args()

    init_db()
    s = get_session()
    try:
        pos = Position(
            symbol=args.symbol.upper(), market=args.market, name=args.name,
            cost_price=args.cost_price, quantity=args.quantity,
            stop_loss=args.sl, take_profit=args.tp,
            watch_below=args.watch_below, watch_above=args.watch_above,
        )
        s.add(pos); s.commit()
        print(f"✅ Added {pos.market}.{pos.symbol} @ {pos.cost_price} x {pos.quantity}")
    finally:
        s.close()


if __name__ == "__main__":
    main()
