from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ashare_research.snapshot import save_stock_snapshot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("code", help="6-digit A-share stock code")
    parser.add_argument("--date", dest="trade_date", help="trade date like 2026-05-15")
    parser.add_argument("--output-dir", default=None, help="directory for snapshot json")
    args = parser.parse_args()

    path = save_stock_snapshot(args.code, trade_date=args.trade_date, output_dir=args.output_dir)
    print(Path(path).resolve())


if __name__ == "__main__":
    main()
