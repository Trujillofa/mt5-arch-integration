#!/usr/bin/env python3
"""Verify a read-only OnTradeTransaction journal.

Usage:
  uv run python scripts/verify_trade_journal.py
  uv run python scripts/verify_trade_journal.py /path/to/journal/dir
  uv run python scripts/verify_trade_journal.py /path/to/manifest.json

Does not import research scripts. Does not place orders. Does not attach to MT5.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mt5_arch.trade_journal import verify_journal  # noqa: E402

OFFLINE = ROOT / "tests" / "fixtures" / "trade_journal" / "offline_ok"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dump",
        nargs="?",
        default=str(OFFLINE),
        help="journal directory or manifest.json (default: committed synthetic fixture)",
    )
    args = parser.parse_args(argv)
    report = verify_journal(Path(args.dump))
    print(f"trade-journal PASSED {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
