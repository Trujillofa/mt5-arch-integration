#!/usr/bin/env python3
"""Multi-year frozen catalog evaluation (offline, no retune).

Loads results/xau_frozen_champions_catalog.json (8 frozen configs) and evaluates
each on calendar / develop windows using the same simulators as
xau_lane_deep_opt / preregistered (import reuse).

SAFETY:
  - Offline only. NEVER retune. NEVER --live.
  - Params ONLY from results/xau_frozen_champions_catalog.json
  - year_2026_to_peek is known peeked holdout-era (diagnostic, not selection).

Writes:
  results/xau_frozen_multi_year_eval.json
  results/xau_frozen_multi_year_matrix.csv
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from backtest import Metrics, load_h1  # noqa: E402
from xau_lane_deep_opt import (  # noqa: E402
    HOLDOUT_START,
    metrics_dict,
    prepare_frame,
    simulate_atr_trail,
    simulate_donchian,
    simulate_htf_fib_enhanced,
    simulate_htf_pullback,
    simulate_vol_gate,
)

CATALOG_PATH = ROOT / "results" / "xau_frozen_champions_catalog.json"
OUT_JSON = ROOT / "results" / "xau_frozen_multi_year_eval.json"
OUT_CSV = ROOT / "results" / "xau_frozen_multi_year_matrix.csv"

# Classic promote gates (vol_gate / high-WR styles)
HARD_PASS_CLASSIC = {
    "profit_factor": 1.5,  # PF > 1.5
    "win_rate": 55.0,  # WR > 55
    "max_drawdown_pct": 10.0,  # DD < 10
    "n_trades": 20,  # n >= 20
}

# Turtle / expectancy-centric soft gates (WR diagnostic only)
SOFT_PASS_EXPECTANCY = {
    "profit_factor": 1.5,  # PF >= 1.5
    "n_trades": 40,  # n >= 40
    "max_drawdown_pct": 12.0,  # DD <= 12
    "expectancy": 20.0,  # exp >= 20
}

LANE_SIM: dict[str, Callable[..., Metrics]] = {
    "vol_gate_sparse": simulate_vol_gate,
    "donchian_turtle": simulate_donchian,
    "atr_trail_breakout": simulate_atr_trail,
    "htf_fib_xau": simulate_htf_fib_enhanced,
    "htf_pullback_new": simulate_htf_pullback,
}

# Lanes for which soft_pass_expectancy is the primary turtle-style gate
TURTLE_LIKE_LANES = {"donchian_turtle", "atr_trail_breakout"}


def ts(s: str) -> pd.Timestamp:
    t = pd.Timestamp(s)
    if t.tzinfo is None:
        return t.tz_localize("UTC")
    return t.tz_convert("UTC")


def normalize_params(params: dict[str, Any]) -> dict[str, Any]:
    """Catalog params → kwargs for deep_opt simulators."""
    p = dict(params)
    p.pop("mode", None)
    hours = p.get("hours")
    if isinstance(hours, list):
        p["hours"] = tuple(hours) if hours else None
    elif hours is not None and not isinstance(hours, tuple):
        p["hours"] = None
    return p


def hard_pass_classic(md: dict[str, Any]) -> bool:
    """PF>1.5 WR>55 DD<10 n>=20."""
    return (
        float(md["profit_factor"]) > HARD_PASS_CLASSIC["profit_factor"]
        and float(md["win_rate"]) > HARD_PASS_CLASSIC["win_rate"]
        and float(md["max_drawdown_pct"]) < HARD_PASS_CLASSIC["max_drawdown_pct"]
        and int(md["n_trades"]) >= int(HARD_PASS_CLASSIC["n_trades"])
    )


def soft_pass_expectancy(md: dict[str, Any]) -> bool:
    """PF>=1.5 n>=40 DD<=12 exp>=20 (WR diagnostic only)."""
    return (
        float(md["profit_factor"]) >= SOFT_PASS_EXPECTANCY["profit_factor"]
        and int(md["n_trades"]) >= int(SOFT_PASS_EXPECTANCY["n_trades"])
        and float(md["max_drawdown_pct"]) <= SOFT_PASS_EXPECTANCY["max_drawdown_pct"]
        and float(md["expectancy"]) >= SOFT_PASS_EXPECTANCY["expectancy"]
    )


def window_mask(
    times: pd.Series,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
    *,
    end_inclusive: bool = False,
) -> pd.Series:
    m = pd.Series(True, index=times.index)
    if start is not None:
        m &= times >= start
    if end is not None:
        if end_inclusive:
            m &= times <= end
        else:
            m &= times < end
    return m


def define_windows(times: pd.Series) -> list[dict[str, Any]]:
    """Calendar / develop windows; empty ones are skipped later."""
    specs: list[tuple[str, pd.Timestamp | None, pd.Timestamp | None, bool, str]] = [
        ("year_2023", ts("2023-01-01"), ts("2024-01-01"), False, "[2023-01-01, 2024-01-01)"),
        ("year_2024", ts("2024-01-01"), ts("2025-01-01"), False, "[2024-01-01, 2025-01-01)"),
        ("year_2025", ts("2025-01-01"), ts("2026-01-01"), False, "[2025-01-01, 2026-01-01)"),
        (
            "year_2026_to_peek",
            ts("2026-01-01"),
            ts("2026-08-06 18:00"),
            True,
            "[2026-01-01, 2026-08-06 18:00] known peeked holdout-era",
        ),
        ("develop_like", None, HOLDOUT_START, False, "time < 2026-01-01"),
        ("full_available", None, None, False, "all H1 bars"),
        ("h2_2024", ts("2024-07-01"), ts("2025-01-01"), False, "[2024-07-01, 2025-01-01)"),
        ("h1_2025", ts("2025-01-01"), ts("2025-07-01"), False, "[2025-01-01, 2025-07-01)"),
        ("h2_2025", ts("2025-07-01"), ts("2026-01-01"), False, "[2025-07-01, 2026-01-01)"),
    ]
    out: list[dict[str, Any]] = []
    for name, start, end, end_incl, note in specs:
        mask = window_mask(times, start, end, end_inclusive=end_incl)
        n = int(mask.sum())
        if n == 0:
            out.append(
                {
                    "name": name,
                    "note": note,
                    "n_bars": 0,
                    "empty": True,
                    "start": None,
                    "end": None,
                }
            )
            continue
        t_win = times.loc[mask]
        out.append(
            {
                "name": name,
                "note": note,
                "n_bars": n,
                "empty": False,
                "start": str(t_win.iloc[0]),
                "end": str(t_win.iloc[-1]),
                "start_bound": str(start) if start is not None else None,
                "end_bound": str(end) if end is not None else None,
                "end_inclusive": end_incl,
                "mask": mask,
            }
        )
    return out


def bar_range(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {"n_bars": 0, "start": None, "end": None}
    t = pd.to_datetime(df["time"], utc=True)
    return {
        "n_bars": int(len(df)),
        "start": str(t.iloc[0]),
        "end": str(t.iloc[-1]),
    }


def run_one(
    sim: Callable[..., Metrics],
    d: pd.DataFrame,
    params: dict[str, Any],
) -> dict[str, Any]:
    m = sim(d, **params)
    return metrics_dict(m)


def main() -> int:
    t0 = time.time()
    if not CATALOG_PATH.is_file():
        print(f"ERROR: catalog missing: {CATALOG_PATH}", file=sys.stderr)
        return 1

    catalog = json.loads(CATALOG_PATH.read_text())
    entries = catalog.get("entries", [])
    if len(entries) != 8:
        print(
            f"WARN: expected 8 catalog entries, got {len(entries)}",
            file=sys.stderr,
        )

    print("Loading H1 + prepare_frame (same as xau_lane_deep_opt) ...", flush=True)
    raw = load_h1()
    d_all = prepare_frame(raw)
    times = pd.to_datetime(d_all["time"], utc=True)
    print(f"full H1 bars={len(d_all)} {times.iloc[0]} → {times.iloc[-1]}", flush=True)

    windows = define_windows(times)
    active = [w for w in windows if not w["empty"]]
    skipped = [w["name"] for w in windows if w["empty"]]
    print(
        f"windows: {len(active)} active, {len(skipped)} empty {skipped}",
        flush=True,
    )

    cells: list[dict[str, Any]] = []
    matrix_rows: list[dict[str, Any]] = []
    n_hard = 0
    n_soft = 0
    n_total = 0

    for entry in entries:
        eid = entry["id"]
        lane = entry["lane"]
        role = entry.get("role")
        mode = entry.get("mode") or entry.get("params", {}).get("mode")
        sim = LANE_SIM.get(lane)
        if sim is None:
            print(f"ERROR: no simulator for lane={lane} id={eid}", file=sys.stderr)
            return 1
        params = normalize_params(entry.get("params", {}))
        print(f"  config {eid} lane={lane} ...", flush=True)

        for w in active:
            mask = w["mask"]
            d_win = d_all.loc[mask].reset_index(drop=True)
            if len(d_win) < 50:
                # too short to simulate meaningfully — treat as empty cell
                md = {
                    "net_profit": 0.0,
                    "win_rate": 0.0,
                    "profit_factor": 0.0,
                    "max_drawdown_pct": 0.0,
                    "n_trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "expectancy": 0.0,
                    "expectancy_sqrt_n": 0.0,
                }
            else:
                md = run_one(sim, d_win, params)

            hp = hard_pass_classic(md)
            sp = soft_pass_expectancy(md)
            n_total += 1
            if hp:
                n_hard += 1
            if sp:
                n_soft += 1

            cell = {
                "id": eid,
                "lane": lane,
                "role": role,
                "mode": mode,
                "window": w["name"],
                "window_note": w["note"],
                "window_bars": w["n_bars"],
                "window_start": w["start"],
                "window_end": w["end"],
                "metrics": md,
                "hard_pass_classic": hp,
                "soft_pass_expectancy": sp,
                "turtle_like_lane": lane in TURTLE_LIKE_LANES,
            }
            cells.append(cell)
            matrix_rows.append(
                {
                    "id": eid,
                    "window": w["name"],
                    "pf": round(float(md["profit_factor"]), 6),
                    "wr": round(float(md["win_rate"]), 6),
                    "dd": round(float(md["max_drawdown_pct"]), 6),
                    "n": int(md["n_trades"]),
                    "np": round(float(md["net_profit"]), 6),
                    "hard_pass": hp,
                }
            )
            print(
                f"    {w['name']}: n={md['n_trades']} PF={md['profit_factor']:.3f} "
                f"WR={md['win_rate']:.1f} DD={md['max_drawdown_pct']:.2f} "
                f"hard={hp} soft={sp}",
                flush=True,
            )

    # Per-window hard_pass counts
    by_window: dict[str, dict[str, Any]] = {}
    for w in active:
        wcells = [c for c in cells if c["window"] == w["name"]]
        by_window[w["name"]] = {
            "n_bars": w["n_bars"],
            "start": w["start"],
            "end": w["end"],
            "note": w["note"],
            "n_configs": len(wcells),
            "n_hard_pass_classic": sum(1 for c in wcells if c["hard_pass_classic"]),
            "n_soft_pass_expectancy": sum(1 for c in wcells if c["soft_pass_expectancy"]),
        }

    by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        eid = entry["id"]
        icells = [c for c in cells if c["id"] == eid]
        by_id[eid] = {
            "lane": entry["lane"],
            "role": entry.get("role"),
            "n_windows": len(icells),
            "n_hard_pass_classic": sum(1 for c in icells if c["hard_pass_classic"]),
            "n_soft_pass_expectancy": sum(1 for c in icells if c["soft_pass_expectancy"]),
            "windows_hard_pass": [c["window"] for c in icells if c["hard_pass_classic"]],
            "windows_soft_pass": [c["window"] for c in icells if c["soft_pass_expectancy"]],
        }

    years_available = [
        w["name"]
        for w in windows
        if not w["empty"] and w["name"].startswith("year_")
    ]
    all_windows_available = [w["name"] for w in active]

    payload = {
        "meta": {
            "script": "scripts/xau_frozen_multi_year_eval.py",
            "catalog": "results/xau_frozen_champions_catalog.json",
            "n_catalog_entries": len(entries),
            "simulators": "xau_lane_deep_opt.py (import reuse; same as deep opt / preregistered lineage)",
            "safety": "offline only; NEVER retune; NEVER --live; params only from frozen catalog",
            "hard_pass_classic": {
                "rule": "PF>1.5 WR>55 DD<10 n>=20",
                "gates": HARD_PASS_CLASSIC,
            },
            "soft_pass_expectancy": {
                "rule": "PF>=1.5 n>=40 DD<=12 exp>=20 (WR diagnostic only)",
                "gates": SOFT_PASS_EXPECTANCY,
                "intended_for": sorted(TURTLE_LIKE_LANES),
            },
            "seconds": round(time.time() - t0, 3),
        },
        "data": {
            "csv": "xauusd_data.csv",
            "full": bar_range(d_all),
        },
        "windows_defined": [
            {
                "name": w["name"],
                "note": w["note"],
                "empty": w["empty"],
                "n_bars": w["n_bars"],
                "start": w.get("start"),
                "end": w.get("end"),
            }
            for w in windows
        ],
        "windows_skipped_empty": skipped,
        "years_available": years_available,
        "windows_available": all_windows_available,
        "summary": {
            "n_cells": n_total,
            "n_hard_pass_classic": n_hard,
            "n_soft_pass_expectancy": n_soft,
            "n_configs": len(entries),
            "n_windows_active": len(active),
            "by_window": by_window,
            "by_id": by_id,
        },
        "cells": cells,
        "catalog_meta": catalog.get("meta"),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print(f"Wrote {OUT_JSON}", flush=True)

    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["id", "window", "pf", "wr", "dd", "n", "np", "hard_pass"],
        )
        writer.writeheader()
        for row in matrix_rows:
            writer.writerow(row)
    print(f"Wrote {OUT_CSV} ({len(matrix_rows)} rows)", flush=True)

    print(
        f"DONE cells={n_total} hard_pass={n_hard}/{n_total} soft_pass={n_soft}/{n_total} "
        f"years={years_available} sec={time.time() - t0:.1f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
