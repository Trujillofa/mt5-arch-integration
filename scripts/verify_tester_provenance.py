#!/usr/bin/env python3
"""Verify a Strategy Tester provenance.json record.

Usage:
  uv run python scripts/verify_tester_provenance.py
  uv run python scripts/verify_tester_provenance.py /path/to/provenance.json
  uv run python scripts/verify_tester_provenance.py /path/to/dir

Does not import research scripts. Does not place orders. Does not launch the tester.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mt5_arch.symbol_registry import load_registry  # noqa: E402
from mt5_arch.tester_provenance import verify_provenance  # noqa: E402

OFFLINE = ROOT / "tests" / "fixtures" / "tester_provenance" / "offline_ok"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dump",
        nargs="?",
        default=str(OFFLINE),
        help="provenance.json or directory (default: committed synthetic fixture)",
    )
    args = parser.parse_args(argv)
    report = verify_provenance(Path(args.dump), load_registry())
    print(f"tester-provenance PASSED {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
