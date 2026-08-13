#!/usr/bin/env python3
"""Export MT5 SYMBOL_SWAP_* into carry-lane verified_swap_rates JSON.

Reads the live file bridge (or a symbols.json snapshot), keeps raw MT5 units,
and when swap_mode == POINTS converts to approximate pips/day/lot for the
manual-trading-agent carry harness.

Usage:
  uv run python scripts/export_swap_rates.py \\
    --broker "Vantage International MT5 / login …" \\
    --output /tmp/verified_swap_rates_VANTAGE_$(date +%F).json
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


WEEKDAY = {0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat"}


def _to_slash_pair(symbol: str) -> str | None:
    compact = (
        symbol.upper()
        .replace("/", "")
        .replace(".", "")
        .replace("M", "")  # Exness raw suffix when trailing
        .replace("#", "")
        .replace("PRO", "")
        .replace("R", "")
    )
    # Undo over-stripping: only strip known suffixes from the end.
    base = symbol.upper()
    for suf in ("M", ".R", ".M", "#", "PRO"):
        if base.endswith(suf):
            base = base[: -len(suf)]
            break
    base = base.replace("/", "").replace(".", "")
    if len(base) == 6 and base.isalpha():
        return f"{base[:3]}/{base[3:]}"
    return None


def _points_to_pips(swap_points: float, digits: int) -> float:
    """MT5 POINTS mode: swap is in points; pip = 10 points on 5-digit FX (3-digit JPY)."""
    pip_points = 10.0 if digits in {3, 5} else 1.0
    return swap_points / pip_points


def convert_row(row: dict[str, Any]) -> dict[str, Any]:
    mode = str(row.get("swap_mode") or "")
    digits = int(row.get("digits") or 5)
    long_raw = float(row.get("swap_long") or 0.0)
    short_raw = float(row.get("swap_short") or 0.0)
    out: dict[str, Any] = {
        "symbol": row.get("symbol"),
        "requested": row.get("requested"),
        "swap_mode": mode,
        "swap_rollover3days": int(row.get("swap_rollover3days") or 0),
        "swap_long_raw": long_raw,
        "swap_short_raw": short_raw,
        "digits": digits,
        "point": row.get("point"),
        "tick_value": row.get("tick_value"),
        "contract_size": row.get("contract_size"),
    }
    pair = _to_slash_pair(str(row.get("requested") or row.get("symbol") or ""))
    out["pair"] = pair
    if mode == "POINTS":
        out["long_pips_per_day_per_lot"] = _points_to_pips(long_raw, digits)
        out["short_pips_per_day_per_lot"] = _points_to_pips(short_raw, digits)
        out["units_converted"] = "pips per day per standard lot (from POINTS)"
    else:
        out["long_pips_per_day_per_lot"] = None
        out["short_pips_per_day_per_lot"] = None
        out["units_converted"] = f"unconverted ({mode or 'unknown'} — keep raw)"
    return out


def load_symbols(path: Path | None) -> list[dict[str, Any]]:
    if path is not None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise SystemExit(f"{path} is not a list")
        return payload

    # Prefer live bridge via mt5_arch when available.
    from mt5_arch.file_bridge import FileBridgeClient

    client = FileBridgeClient()
    client.ensure_alive()
    rows = client._read_json("symbols.json")  # noqa: SLF001 — intentional dump
    if not isinstance(rows, list):
        raise SystemExit("bridge symbols.json is not a list")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols-json", type=Path, default=None)
    parser.add_argument("--broker", required=True, help="Broker / account type label")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(f"/tmp/verified_swap_rates_MT5_{date.today().isoformat()}.json"),
    )
    parser.add_argument(
        "--carry-pairs-only",
        action="store_true",
        help="Keep only pairs matching AUD/JPY,NZD/JPY,AUD/USD,NZD/USD,USD/ZAR,USD/TRY,EUR/TRY,GBP/TRY",
    )
    args = parser.parse_args()

    rows = load_symbols(args.symbols_json)
    converted = [convert_row(r) for r in rows if isinstance(r, dict)]

    carry_keys = {
        "AUD/JPY",
        "NZD/JPY",
        "AUD/USD",
        "NZD/USD",
        "USD/ZAR",
        "USD/TRY",
        "EUR/TRY",
        "GBP/TRY",
    }
    if args.carry_pairs_only:
        converted = [c for c in converted if c.get("pair") in carry_keys]

    rates: dict[str, dict[str, float]] = {}
    raw_by_pair: dict[str, Any] = {}
    nonzero = 0
    for row in converted:
        pair = row.get("pair")
        if not pair:
            continue
        raw_by_pair[pair] = row
        long_v = row.get("long_pips_per_day_per_lot")
        short_v = row.get("short_pips_per_day_per_lot")
        if long_v is None or short_v is None:
            # Still record raw so we can see zeros / non-POINTS modes.
            rates[pair] = {
                "long": float(row["swap_long_raw"]),
                "short": float(row["swap_short_raw"]),
            }
        else:
            rates[pair] = {"long": float(long_v), "short": float(short_v)}
        if rates[pair]["long"] != 0.0 or rates[pair]["short"] != 0.0:
            nonzero += 1

    rollover_days = sorted(
        {
            int(r.get("swap_rollover3days") or 0)
            for r in converted
            if r.get("swap_rollover3days") is not None
        }
    )
    rollover_label = ", ".join(WEEKDAY.get(d, str(d)) for d in rollover_days) or "unknown"

    modes = sorted({str(r.get("swap_mode") or "") for r in converted})
    payload = {
        "source_date": date.today().isoformat(),
        "broker": args.broker,
        "retrieved": (
            f"Mt5ArchBridge symbols.json SYMBOL_SWAP_* via mt5-arch "
            f"({datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')})"
        ),
        "units": (
            "pips per day per standard lot when swap_mode=POINTS "
            "(positive = receive when long); otherwise raw MT5 swap_long/short"
        ),
        "rollover_rule": f"3x swap on weekday(s) = {rollover_label} (SYMBOL_SWAP_ROLLOVER3DAYS)",
        "swap_modes_seen": modes,
        "notes": (
            "Raw rows in raw_by_pair. If all long/short are 0.0, account may be swap-free "
            "(same discard class as Hetzner cTrader). Non-POINTS modes need explicit conversion "
            "before GROSS_PASS_REAL_DATA."
        ),
        "nonzero_pairs": nonzero,
        "rates": rates,
        "raw_by_pair": raw_by_pair,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(args.output), "pairs": len(rates), "nonzero_pairs": nonzero, "modes": modes}, indent=2))
    return 0 if rates else 2


if __name__ == "__main__":
    # Allow running without install: repo src on path
    repo = Path(__file__).resolve().parents[1]
    src = repo / "src"
    if src.is_dir():
        os.environ.setdefault("PYTHONPATH", f"{src}:{os.environ.get('PYTHONPATH', '')}")
    raise SystemExit(main())
