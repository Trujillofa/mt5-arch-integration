#!/usr/bin/env python3
"""Verify config/symbols/registry.json and an optional capability dump.

Usage:
  uv run python scripts/verify_symbol_registry.py
  uv run python scripts/verify_symbol_registry.py /path/to/capabilities/dir
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mt5_arch.symbol_registry import (  # noqa: E402
    load_registry,
    render_mql5_include,
    verify_capability_dump,
    write_mql5_include,
)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help"}:
        print(__doc__)
        return 0
    if args and args[0] == "--write-include":
        dest = write_mql5_include()
        print(f"wrote {dest}")
        return 0
    reg = load_registry()
    generated = render_mql5_include(reg)
    include = (ROOT / "mql5" / "Include" / "FxSymbolRegistry.mqh").read_text(
        encoding="utf-8"
    )
    if generated != include:
        print("FAIL: FxSymbolRegistry.mqh is stale; run --write-include", file=sys.stderr)
        return 1
    print(
        f"registry ok brokers={list(reg.brokers())} "
        f"mappings={len(reg.mappings)} include lockstep"
    )
    if args:
        report = verify_capability_dump(Path(args[0]), reg)
        print(f"capability dump PASSED {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
