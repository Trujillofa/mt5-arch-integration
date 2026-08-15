#!/usr/bin/env python3
"""Verify a read-only ExportSymbolSyncAudit dump.

Usage:
  uv run python scripts/verify_symbol_sync_audit.py
  uv run python scripts/verify_symbol_sync_audit.py /path/to/sync_audit/dir
  uv run python scripts/verify_symbol_sync_audit.py dump.json --package package.json

Does not import research scripts. Does not place orders.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mt5_arch.symbol_registry import load_registry  # noqa: E402
from mt5_arch.symbol_sync_audit import (  # noqa: E402
    load_package_snapshot,
    verify_sync_audit_dump,
)

OFFLINE = ROOT / "tests" / "fixtures" / "symbol_sync_audit" / "offline_ok"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dump",
        nargs="?",
        default=str(OFFLINE),
        help="Audit dump directory or manifest.json (default: committed synthetic fixture)",
    )
    parser.add_argument(
        "--package",
        default=None,
        help="Optional readiness/package compare JSON (not a live MT5 dump)",
    )
    args = parser.parse_args(argv)
    reg = load_registry()
    package = Path(args.package) if args.package else None
    if package is not None:
        package = load_package_snapshot(package)
    report = verify_sync_audit_dump(Path(args.dump), reg, package=package)
    print(f"sync-audit PASSED {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
