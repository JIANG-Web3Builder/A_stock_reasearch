from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ashare_research.common import SNAPSHOT_DIR, write_json
from ashare_research.signals import (
    analyze_hot_topics,
    capture_northbound_close,
    daily_dragon_tiger,
    industry_comparison,
    ths_hot_reason,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", dest="trade_date", help="trade date like 2026-05-15")
    args = parser.parse_args()

    trade_date = args.trade_date or datetime.now().strftime("%Y-%m-%d")
    hot_df = ths_hot_reason(trade_date)
    payload = {
        "trade_date": trade_date,
        "hot_count": len(hot_df),
        "hot_topics": analyze_hot_topics(trade_date, top_n=20),
        "northbound": capture_northbound_close(trade_date),
        "daily_dragon_tiger": daily_dragon_tiger(trade_date),
        "industry_comparison": industry_comparison(top_n=20),
    }
    path = SNAPSHOT_DIR / f"market_signal_{trade_date}.json"
    write_json(path, payload)
    print(Path(path).resolve())


if __name__ == "__main__":
    main()
