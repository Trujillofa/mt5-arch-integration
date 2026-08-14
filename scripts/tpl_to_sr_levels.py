#!/usr/bin/env python3
"""Convert MT5 chart templates (.tpl) into an S/R level table for ForexHtfPivotsFib.

The manual-trading-agent `plantillas/*.tpl` files are UTF-16LE chart templates whose
hand-drawn zones are stored as `OBJ_HLINE` objects (`type=1`). MT5 names an
auto-created object after the timeframe it was drawn on ("H4 Horizontal Line 23987"),
so the drawing timeframe -- not the template's own ad-hoc colour -- is what carries
the trader's intent about how much a level matters.

Relevance tiers (drives the colour the indicator paints):

    HIGH   Monthly / Weekly / Daily / H4   -> yellow
    MED    H1 / M30 / M15                  -> white
    LOW    M5 / M1                         -> blue

Object types other than 1 are skipped: 2 is a trendline (not a horizontal level),
31/32 are the terminal's own buy/sell trade arrows, and 109 is a news event marker.
None of those are S/R levels.

Output is an ASCII CSV read at runtime by the indicator, so re-exporting zones needs
no MetaEditor recompile -- regenerate, redeploy, refresh the chart.

Usage:
    python3 scripts/tpl_to_sr_levels.py                    # default plantillas dir
    python3 scripts/tpl_to_sr_levels.py a.tpl b.tpl        # explicit templates
    python3 scripts/tpl_to_sr_levels.py -o path/out.csv
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO / "mql5" / "Files" / "forex_sr_levels.csv"
DEFAULT_SRC = Path(
    os.environ.get(
        "PLANTILLAS_DIR",
        Path.home() / "Projects" / "trading" / "manual-trading-agent" / "plantillas",
    )
)

OBJ_HLINE = 1

# MT5 prefixes object names with the timeframe the object was drawn on.
TIER_BY_TF: dict[str, str] = {
    "MN": "HIGH", "MN1": "HIGH", "MONTHLY": "HIGH",
    "W1": "HIGH", "WEEKLY": "HIGH",
    "D1": "HIGH", "DAILY": "HIGH",
    "H4": "HIGH",
    "H1": "MED", "M30": "MED", "M15": "MED",
    "M5": "LOW", "M1": "LOW",
}
FALLBACK_TIER = "MED"  # unnamed / unrecognised prefix: don't over- or under-state it

OBJECT_RE = re.compile(r"<object>(.*?)</object>", re.S)


def read_tpl(path: Path) -> str:
    """Decode a .tpl. They are UTF-16LE with a BOM; tolerate UTF-8 exports too."""
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n")


def parse_block(block: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in block.strip().splitlines():
        if "=" in line:
            key, val = line.split("=", 1)
            out[key.strip()] = val.strip()
    return out


def tier_for(name: str) -> tuple[str, str]:
    """Return (tier, tf) from an MT5 object name like 'H4 Horizontal Line 23987'."""
    prefix = name.split(" ", 1)[0].upper() if name else ""
    return TIER_BY_TF.get(prefix, FALLBACK_TIER), (prefix or "?")


def parse_template(path: Path) -> tuple[str, list[tuple[float, str, str, str]]]:
    """Return (symbol, [(price, tier, tf, object_name), ...]) for one template."""
    text = read_tpl(path)
    sym_m = re.search(r"^symbol=(.*)$", text, re.M)
    symbol = sym_m.group(1).strip() if sym_m else ""
    if not symbol:
        raise ValueError(f"{path}: no symbol= header")

    levels: list[tuple[float, str, str, str]] = []
    for block in OBJECT_RE.findall(text):
        obj = parse_block(block)
        if obj.get("type") != str(OBJ_HLINE):
            continue
        raw_price = obj.get("value1")
        if raw_price is None:
            continue
        try:
            price = float(raw_price)
        except ValueError:
            continue
        if price <= 0:
            continue
        name = obj.get("name", "")
        tier, tf = tier_for(name)
        levels.append((price, tier, tf, name))
    return symbol, levels


TIER_RANK = {"HIGH": 3, "MED": 2, "LOW": 1}


def dedupe(levels: list[tuple[float, str, str, str]]) -> list[tuple[float, str, str, str]]:
    """Collapse levels that land on the same price, keeping the strongest tier.

    Two lines drawn at the same price on different timeframes are one level, and the
    higher timeframe is the one that decides how much it matters.
    """
    best: dict[float, tuple[float, str, str, str]] = {}
    for lv in levels:
        key = round(lv[0], 6)
        prev = best.get(key)
        if prev is None or TIER_RANK[lv[1]] > TIER_RANK[prev[1]]:
            best[key] = lv
    return sorted(best.values(), key=lambda x: x[0])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("templates", nargs="*", type=Path,
                    help=f"template files (default: all *.tpl in {DEFAULT_SRC})")
    ap.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT,
                    help=f"output CSV (default: {DEFAULT_OUT})")
    args = ap.parse_args(argv)

    templates = args.templates
    if not templates:
        if not DEFAULT_SRC.is_dir():
            print(f"ERROR: {DEFAULT_SRC} not found; pass template paths or set "
                  f"PLANTILLAS_DIR", file=sys.stderr)
            return 1
        templates = sorted(DEFAULT_SRC.glob("*.tpl"))
    if not templates:
        print("ERROR: no templates to convert", file=sys.stderr)
        return 1

    rows: list[str] = []
    summary: list[str] = []
    for tpl in templates:
        if not tpl.is_file():
            print(f"ERROR: {tpl} not found", file=sys.stderr)
            return 1
        symbol, levels = parse_template(tpl)
        levels = dedupe(levels)
        if not levels:
            print(f"WARN: {tpl.name} ({symbol}) has no horizontal lines", file=sys.stderr)
            continue
        counts = {"HIGH": 0, "MED": 0, "LOW": 0}
        rows.append(f"# {tpl.name} -> {symbol}")
        for price, tier, tf, _name in levels:
            counts[tier] += 1
            rows.append(f"{symbol},{price:.8f},{tier},{tf}")
        summary.append(f"  {symbol:<10} {len(levels):>3} levels  "
                       f"HIGH={counts['HIGH']} MED={counts['MED']} LOW={counts['LOW']}"
                       f"   ({tpl.name})")

    if not rows:
        print("ERROR: no levels extracted", file=sys.stderr)
        return 1

    header = [
        "# forex_sr_levels.csv - generated by scripts/tpl_to_sr_levels.py",
        "# Static snapshot of hand-drawn MT5 template zones. Regenerate after re-drawing.",
        "# symbol,price,tier,source_tf   tier: HIGH=yellow MED=white LOW=blue",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # ASCII + \n: the indicator reads it with FILE_ANSI.
    args.out.write_text("\n".join(header + rows) + "\n", encoding="ascii")

    print(f"Wrote {args.out}")
    for line in summary:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
