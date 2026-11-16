#!/usr/bin/env python3
"""Prometheus textfile metrics for the MT5 file bridge (read-only).

Reads the EA snapshots in ``mt5_arch/`` and prints Prometheus exposition text.
No orders, no writes into the bridge. ``--out`` writes atomically (temp file +
``os.replace``) so a cron job can feed node_exporter's textfile collector.

Staleness is a metric (``mt5_feed_stale``), not an exit code: a dead bridge must
still produce a scrapeable file. ``control.json`` uses the same fail-closed rule
as ``DeskControl.mqh`` (malformed = inhibited).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_MAX_AGE_SECONDS = 15.0


def _read_json(path: Path) -> tuple[Any | None, bool]:
    if not path.exists():
        return None, False
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace")), True
    except (OSError, json.JSONDecodeError):
        return None, False


def _age_seconds(path: Path, now: float) -> float | None:
    if not path.exists():
        return None
    try:
        return max(0.0, now - path.stat().st_mtime)
    except OSError:
        return None


def _fmt(value: float) -> str:
    if float(value).is_integer() and abs(value) < 1e15:
        return str(int(value))
    return repr(float(value))


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def parse_control(raw: Any) -> dict[str, Any]:
    """Control state with the EA's fail-closed semantics."""
    if not isinstance(raw, dict):
        return {"valid": False, "inhibited": True, "reason": "control.json malformed"}
    flag = raw.get("inhibited")
    if flag is True:
        return {"valid": True, "inhibited": True, "reason": str(raw.get("reason") or "")}
    if flag is False:
        return {"valid": True, "inhibited": False, "reason": str(raw.get("reason") or "")}
    return {"valid": False, "inhibited": True, "reason": "control.json malformed"}


def _positions(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict) and isinstance(raw.get("positions"), list):
        return [row for row in raw["positions"] if isinstance(row, dict)]
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    return []


def _symbols(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    if isinstance(raw, dict) and isinstance(raw.get("symbols"), list):
        return [row for row in raw["symbols"] if isinstance(row, dict)]
    return []


def compute_exposure(
    positions: list[dict[str, Any]], symbols: list[dict[str, Any]]
) -> tuple[dict[str, float], int]:
    """Quote-currency notional per symbol; unpriced positions are counted.

    Uses the broker's ``contract_size`` from symbols.json (XAUUSD 100 vs 10 oz is
    per-firm data, never a hardcoded guess). Not account-currency converted.
    """
    contract: dict[str, float] = {}
    for row in symbols:
        symbol = str(row.get("symbol") or "")
        if symbol:
            contract[symbol] = float(row.get("contract_size") or 0)

    per_symbol: defaultdict[str, float] = defaultdict(float)
    unpriced = 0
    for pos in positions:
        symbol = str(pos.get("symbol") or "")
        volume = float(pos.get("volume") or 0)
        price = float(pos.get("price_current") or pos.get("open_price") or 0)
        size = contract.get(symbol, 0.0)
        if size <= 0 or price <= 0 or volume <= 0:
            unpriced += 1
            continue
        per_symbol[symbol] += volume * size * price
    return dict(per_symbol), unpriced


def collect(
    bridge_dir: Path,
    *,
    max_age: float = DEFAULT_MAX_AGE_SECONDS,
    now: float | None = None,
) -> dict[str, Any]:
    now = time.time() if now is None else now
    bridge_dir = Path(bridge_dir)
    heartbeat_age = _age_seconds(bridge_dir / "heartbeat.txt", now)
    account, account_ok = _read_json(bridge_dir / "account.json")
    positions_raw, positions_ok = _read_json(bridge_dir / "positions.json")
    symbols_raw, symbols_ok = _read_json(bridge_dir / "symbols.json")
    control_path = bridge_dir / "control.json"
    control_present = control_path.exists()
    control_raw, control_ok = _read_json(control_path)
    positions = _positions(positions_raw)
    symbols = _symbols(symbols_raw)
    exposure, unpriced = compute_exposure(positions, symbols)

    return {
        "bridge_dir_present": bridge_dir.is_dir(),
        "heartbeat_age": heartbeat_age,
        "feed_stale": heartbeat_age is None or heartbeat_age > max_age,
        "account": account if account_ok and isinstance(account, dict) else None,
        "account_ok": account_ok,
        "positions": positions,
        "positions_ok": positions_ok,
        "symbols_ok": symbols_ok,
        "exposure": exposure,
        "unpriced": unpriced,
        "control_present": control_present,
        "control_parse_ok": control_ok,
        "control": parse_control(control_raw) if control_present else None,
        "control_age": _age_seconds(control_path, now),
    }


def _family(
    lines: list[str], name: str, help_text: str, mtype: str, samples: list[tuple[str, float]]
) -> None:
    lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} {mtype}")
    for labels, value in samples:
        suffix = f"{{{labels}}}" if labels else ""
        lines.append(f"{name}{suffix} {_fmt(value)}")


def render(state: dict[str, Any]) -> str:
    lines: list[str] = []

    _family(
        lines,
        "mt5_bridge_dir_present",
        "1 when the configured bridge directory exists.",
        "gauge",
        [("", 1.0 if state["bridge_dir_present"] else 0.0)],
    )
    _family(
        lines,
        "mt5_feed_stale",
        "1 when heartbeat.txt is missing or older than the max age.",
        "gauge",
        [("", 1.0 if state["feed_stale"] else 0.0)],
    )
    if state["heartbeat_age"] is not None:
        _family(
            lines,
            "mt5_heartbeat_age_seconds",
            "Age of heartbeat.txt in seconds.",
            "gauge",
            [("", float(state["heartbeat_age"]))],
        )

    snapshot_samples = [
        (f'file="{_label(name)}"', 1.0 if state[key] else 0.0)
        for name, key in (
            ("account.json", "account_ok"),
            ("positions.json", "positions_ok"),
            ("symbols.json", "symbols_ok"),
        )
    ]
    _family(
        lines,
        "mt5_snapshot_ok",
        "1 when the snapshot exists and parses.",
        "gauge",
        snapshot_samples,
    )

    account = state["account"]
    if account is not None:
        _family(
            lines,
            "mt5_account_equity",
            "Account equity in account currency.",
            "gauge",
            [("", float(account.get("equity") or 0))],
        )
        _family(
            lines,
            "mt5_account_margin",
            "Used margin in account currency.",
            "gauge",
            [("", float(account.get("margin") or 0))],
        )
        _family(
            lines,
            "mt5_account_free_margin",
            "Free margin in account currency.",
            "gauge",
            [("", float(account.get("free_margin") or 0))],
        )

    if state["positions_ok"]:
        positions = state["positions"]
        _family(
            lines,
            "mt5_positions_open",
            "Open positions reported by the EA.",
            "gauge",
            [("", float(len(positions)))],
        )
        volume: defaultdict[tuple[str, str], float] = defaultdict(float)
        for pos in positions:
            key = (str(pos.get("symbol") or ""), str(pos.get("side") or ""))
            volume[key] += float(pos.get("volume") or 0)
        _family(
            lines,
            "mt5_position_volume",
            "Open volume in lots, by symbol and side.",
            "gauge",
            [
                (f'symbol="{_label(sym)}",side="{_label(side)}"', amount)
                for (sym, side), amount in sorted(volume.items())
            ],
        )

    if state["positions_ok"] and state["symbols_ok"]:
        exposure = state["exposure"]
        _family(
            lines,
            "mt5_exposure_quote",
            "Open notional in quote currency, by symbol (not account converted).",
            "gauge",
            [(f'symbol="{_label(sym)}"', amount) for sym, amount in sorted(exposure.items())],
        )
        _family(
            lines,
            "mt5_exposure_quote_total",
            "Open notional in quote currency across priced symbols.",
            "gauge",
            [("", float(sum(exposure.values())))],
        )
        _family(
            lines,
            "mt5_positions_unpriced",
            "Positions skipped for exposure because symbol contract_size or price is missing.",
            "gauge",
            [("", float(state["unpriced"]))],
        )

    _family(
        lines,
        "mt5_control_present",
        "1 when mt5_arch/control.json exists.",
        "gauge",
        [("", 1.0 if state["control_present"] else 0.0)],
    )
    control = state["control"]
    if control is not None:
        _family(
            lines,
            "mt5_control_parse_ok",
            "1 when control.json parses with a boolean inhibited.",
            "gauge",
            [("", 1.0 if state["control_parse_ok"] else 0.0)],
        )
        _family(
            lines,
            "mt5_control_inhibited",
            "1 when entries are inhibited (malformed control.json counts as inhibited).",
            "gauge",
            [("", 1.0 if control["inhibited"] else 0.0)],
        )
    if state["control_age"] is not None:
        _family(
            lines,
            "mt5_control_age_seconds",
            "Age of control.json in seconds (coordinator write, not EA read).",
            "gauge",
            [("", float(state["control_age"]))],
        )

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bridge-dir",
        type=Path,
        default=os.environ.get("MT5_BRIDGE_DIR"),
        help="Bridge snapshot directory (default: $MT5_BRIDGE_DIR)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write the exposition atomically here instead of stdout",
    )
    parser.add_argument(
        "--max-age",
        type=float,
        default=float(os.environ.get("MT5_BRIDGE_MAX_AGE", DEFAULT_MAX_AGE_SECONDS)),
        help=f"Heartbeat staleness threshold in seconds (default: {DEFAULT_MAX_AGE_SECONDS:g})",
    )
    args = parser.parse_args(argv)
    if args.bridge_dir is None:
        print("error: --bridge-dir or MT5_BRIDGE_DIR is required", file=sys.stderr)
        return 2

    text = render(collect(Path(args.bridge_dir), max_age=args.max_age))
    if args.out is not None:
        tmp = args.out.with_name(args.out.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, args.out)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
