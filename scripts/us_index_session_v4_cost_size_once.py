#!/usr/bin/env python3
"""One-shot cost/size diagnostic. Not a search. Not a promote.

Lock: results/us_index_session_v4_cost_size_once_lock.json

Replays the frozen ORB flatten combo and the already-selected v4 develop
winner under five pre-registered books. Does not add Timescale / M1 / US500.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

import numpy as np

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from us_index_session_autoresearch import (  # noqa: E402
    _et_arrays,
    _or_and_vwap,
    pack_metrics,
    simulate_exits,
)
from us_index_session_autoresearch_v4 import (  # noqa: E402
    orb_regime_signals,
    split_v4,
)
from us_index_session_backtest import (  # noqa: E402
    CostSpec,
    costs_from_meta,
    load_m5_csv,
    parse_meta,
    simulate_flatten,
    split_by_holdout,
)
from us_index_session_core import (  # noqa: E402
    ATR_PERIOD,
    atr_expanding,
    scalp_signal_series,
    to_utc,
    wilder_atr,
)

SEARCH_ID = "us_index_session_v4_cost_size_once"
LOCK_PATH = _ROOT / "results" / "us_index_session_v4_cost_size_once_lock.json"
FROZEN_HOLDOUT = date(2026, 6, 1)
V4_EXIT = {"kind": "atr", "sl": 1.0, "tp": 1.5}
V4_ENTRY_END_MIN = 10 * 60 + 30


def load_lock() -> dict:
    lock = json.loads(LOCK_PATH.read_text())
    if lock.get("search_id") != SEARCH_ID:
        raise SystemExit("search_id mismatch")
    if lock.get("not_a_search") is not True:
        raise SystemExit("this file is a diagnostic, not a search")
    if lock.get("promote") is not False or lock.get("live_go") is not False:
        raise SystemExit("promote/live_go must stay false")
    return lock


def books_from_lock(lock: dict) -> list[tuple[str, float, float]]:
    return [
        (str(b["id"]), float(b["lots"]), float(b["slippage_points"]))
        for b in lock["books_replayed"]
    ]


def _slim(m: dict) -> dict:
    keep = (
        "trades",
        "win_rate",
        "profit_factor",
        "net_pnl",
        "median_daily_pct",
        "median_monthly_pct",
        "hit_daily_goal",
        "hit_monthly_goal",
        "goal_both",
    )
    return {k: m[k] for k in keep}


def run_once(csv_path: Path, meta_path: Path | None, lock: dict) -> dict:
    meta = parse_meta(meta_path) if meta_path and meta_path.is_file() else {}
    offset = int(float(meta.get("server_utc_offset_sec") or 10800))
    df = load_m5_csv(csv_path, offset)
    times = [to_utc(ts.to_pydatetime()) for ts in df["time_utc"]]
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    open_ = df["open"].to_numpy(float)
    vol = df["tick_volume"].to_numpy(float)
    spread = df["spread"].to_numpy(float)
    mins, keys, dow, ny = _et_arrays(times)
    atr14 = wilder_atr(high, low, close, ATR_PERIOD)
    expanding = atr_expanding(
        wilder_atr(high, low, close, 7),
        wilder_atr(high, low, close, 28),
        1.0,
    )
    or_h, or_l, ready, _vwap = _or_and_vwap(mins, keys, ny, high, low, close, vol, 15)
    frozen_sigs = scalp_signal_series(times, high, low, close, vol)
    v4_sigs = orb_regime_signals(
        close,
        mins,
        keys,
        dow,
        or_h,
        or_l,
        ready,
        expanding,
        entry_end_min=V4_ENTRY_END_MIN,
        one_per_day=True,
    )

    rows: list[dict] = []
    any_goal = False
    for book_id, lots, slip in books_from_lock(lock):
        costs = costs_from_meta(
            meta,
            lots=lots,
            slippage_points=slip,
            commission_per_lot=float(lock["commission_per_lot"]),
            max_spread_points=float(lock["max_spread_points"]),
        )
        frozen_trades = simulate_flatten(
            times, open_, high, low, close, spread, frozen_sigs, costs
        )
        frozen_pre, frozen_post = split_by_holdout(frozen_trades, FROZEN_HOLDOUT)
        v4_trades = simulate_exits(
            times,
            mins,
            keys,
            open_,
            high,
            low,
            atr14,
            spread,
            v4_sigs,
            costs,
            V4_EXIT,
        )
        v4_pre, v4_post = split_v4(v4_trades)
        frozen_dev = pack_metrics(frozen_pre)
        frozen_ho = pack_metrics(frozen_post)
        v4_dev = pack_metrics(v4_pre)
        v4_ho = pack_metrics(v4_post)
        hit = bool(
            frozen_dev["goal_both"]
            or frozen_ho["goal_both"]
            or v4_dev["goal_both"]
            or v4_ho["goal_both"]
        )
        any_goal = any_goal or hit
        rows.append(
            {
                "book": book_id,
                "costs": asdict(costs),
                "frozen_orb_flatten": {
                    "develop": _slim(frozen_dev),
                    "holdout": _slim(frozen_ho),
                },
                "v4_best_develop": {
                    "develop": _slim(v4_dev),
                    "holdout": _slim(v4_ho),
                },
                "goal_both_any_window": hit,
            }
        )

    return {
        "search_id": SEARCH_ID,
        "kind": "diagnostic_replay",
        "not_a_search": True,
        "promote": False,
        "live_go": False,
        "skipped": lock["skipped"],
        "bars": int(len(df)),
        "from": str(df["time_utc"].iloc[0]) if len(df) else "",
        "to": str(df["time_utc"].iloc[-1]) if len(df) else "",
        "n_books": len(rows),
        "n_windows_hit_goal": int(sum(1 for r in rows if r["goal_both_any_window"])),
        "any_goal_both": any_goal,
        "rows": rows,
        "note": lock["note"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--csv",
        type=Path,
        default=_ROOT / "results" / "us_index_data" / "history_US100_M5.csv",
    )
    ap.add_argument(
        "--meta",
        type=Path,
        default=_ROOT / "results" / "us_index_data" / "symbol_meta_US100.csv",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "results" / "us_index_session_v4_cost_size_once.json",
    )
    args = ap.parse_args()
    lock = load_lock()
    if len(books_from_lock(lock)) != 5:
        raise SystemExit("lock must list exactly five books")
    report = run_once(args.csv, args.meta, lock)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "search_id": report["search_id"],
                "n_books": report["n_books"],
                "any_goal_both": report["any_goal_both"],
                "n_windows_hit_goal": report["n_windows_hit_goal"],
                "skipped": report["skipped"],
                "promote": False,
                "rows": [
                    {
                        "book": r["book"],
                        "frozen_dev_day": r["frozen_orb_flatten"]["develop"][
                            "median_daily_pct"
                        ],
                        "frozen_ho_day": r["frozen_orb_flatten"]["holdout"][
                            "median_daily_pct"
                        ],
                        "v4_dev_day": r["v4_best_develop"]["develop"][
                            "median_daily_pct"
                        ],
                        "v4_ho_day": r["v4_best_develop"]["holdout"][
                            "median_daily_pct"
                        ],
                        "goal_both_any_window": r["goal_both_any_window"],
                    }
                    for r in report["rows"]
                ],
            },
            indent=2,
        )
    )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
