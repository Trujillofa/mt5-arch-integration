#!/usr/bin/env python3
"""Specified-book replay: 3 lots, TP $20, SL $100, halt -$300.

Lock: results/eurusd_ny_scalp_usd_book_lock.json
New search_id (not a retune of eurusd_ny_scalp_develop_v1).
promote / live_go = false. Offline only.

TP/SL are percent of the $10k account, converted to points via 3 lots x $1/pt:
  TP $20  ->  6.67 points (0.67 pip)
  SL $100 -> 33.33 points (3.33 pip)
Round-trip at median spread: 22 pt x $3 = $66 > $20 TP.
"""

from __future__ import annotations

import argparse
import json
import sys
import time as pytime
from dataclasses import asdict
from datetime import date
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from eurusd_ny_scalp_autoresearch import (  # noqa: E402
    FORBIDDEN_HOLDOUT_DEFAULT,
    GOAL_DAILY,
    pack_metrics,
    rank_develop,
    score_row,
    simulate_config,
    verify_data_sha,
)
from eurusd_ny_scalp_core import (  # noqa: E402
    build_context,
    load_eurusd_m5,
    rotate_returns_within_days,
)
from us_index_session_backtest import (  # noqa: E402
    CostSpec,
    write_slim_json,
)

SEARCH_ID = "eurusd_ny_scalp_usd_book_v1"
LOCK_PATH = _ROOT / "results" / "eurusd_ny_scalp_usd_book_lock.json"
CSV_PATH = _ROOT / "results" / "eurusd_data" / "history_EURUSD.csv"
OUT_JSON = _ROOT / "results" / "eurusd_ny_scalp_usd_book.json"
FULL_JSON = _ROOT / "results" / "eurusd_ny_scalp_usd_book_full.json"
NULL_JSON = _ROOT / "results" / "eurusd_ny_scalp_usd_book_null.json"

USD_EXIT = {"kind": "usd", "tp_usd": 20.0, "sl_usd": 100.0}


def load_usd_lock(path: Path = LOCK_PATH) -> dict:
    lock = json.loads(Path(path).read_text())
    if lock.get("search_id") != SEARCH_ID:
        raise SystemExit(f"search_id mismatch: {lock.get('search_id')}")
    if lock.get("promote") is True or lock.get("live_go") is True:
        raise SystemExit("promote / live_go must stay false")
    b = lock["book"]
    if str(b.get("sizing_policy")) != "fixed_lots":
        raise SystemExit("usd-book lock must be sizing_policy=fixed_lots")
    if float(b["lots"]) != 3.0:
        raise SystemExit("usd-book lock lots must be 3.0")
    if float(b["tp_usd"]) != 20.0 or float(b["sl_usd"]) != 100.0:
        raise SystemExit("usd-book lock TP/SL must be $20 / $100")
    return lock


def holdout_start(lock: dict) -> date:
    hs = date.fromisoformat(str(lock["holdout"]["holdout_start"]))
    if hs == FORBIDDEN_HOLDOUT_DEFAULT:
        raise SystemExit("holdout_start equals the us_index module default")
    return hs


def costs_from_lock(lock: dict) -> CostSpec:
    c = lock["costs"]
    return CostSpec(
        point_size=1e-5,
        contract_size=100_000.0,
        lots=float(lock["book"]["lots"]),
        commission_per_lot=float(c["commission_per_lot"]),
        slippage_points=float(c["slippage_points"]),
        max_spread_points=float(c["max_spread_points"]),
    )


def run_usd_grid(d, lock: dict, costs: CostSpec, holdout: date) -> list[dict]:
    balance = float(lock["book"]["balance_usd"])
    halt = float(lock["risk"]["daily_halt_usd"])
    rows: list[dict] = []
    for opd in (False, True):
        ctxs = build_context(d, one_per_day=opd)
        for fam, ctx in ctxs.items():
            try:
                trades = simulate_config(
                    d,
                    ctx.signals,
                    USD_EXIT,
                    ctx.tgt_long,
                    ctx.tgt_short,
                    ctx.atr,
                    costs,
                    lock,
                )
            except RuntimeError as exc:
                if str(exc) != "equity_floor":
                    raise
                rows.append(
                    {
                        "params": {
                            "family": fam,
                            "one_per_day": opd,
                            "exit": "usd_tp20_sl100",
                        },
                        "develop": pack_metrics([], balance, halt) | {"bankrupt": True},
                        "holdout": pack_metrics([], balance, halt) | {"bankrupt": True},
                        "develop_score": -1e9,
                    }
                )
                continue
            dev = [t for t in trades if date.fromisoformat(t.et_date) < holdout]
            ho = [t for t in trades if date.fromisoformat(t.et_date) >= holdout]
            row = {
                "params": {
                    "family": fam,
                    "one_per_day": opd,
                    "exit": "usd_tp20_sl100",
                },
                "develop": pack_metrics(dev, balance, halt),
                "holdout": pack_metrics(ho, balance, halt),
            }
            row["develop_score"] = score_row(row["develop"])
            rows.append(row)
    return rows


def run_usd_null(d, lock: dict, costs: CostSpec, holdout: date) -> dict:
    seeds = [int(s) for s in lock["null_calibration"]["seeds"]]
    per_seed = []
    t0 = pytime.time()
    for i, seed in enumerate(seeds, 1):
        rng = __import__("numpy").random.default_rng(seed)
        dn = rotate_returns_within_days(d, rng)
        rows = run_usd_grid(dn, lock, costs, holdout)
        ranked = rank_develop(rows)
        best = ranked[0]["develop"] if ranked else None
        rec = {
            "seed": seed,
            "n_eligible": len(ranked),
            "best_develop_median_daily_pct": (None if best is None else best["median_daily_pct"]),
        }
        per_seed.append(rec)
        print(
            f"null seed {i}/{len(seeds)}={seed} eligible={rec['n_eligible']} "
            f"best={rec['best_develop_median_daily_pct']} "
            f"({pytime.time() - t0:.0f}s)",
            flush=True,
        )
    vals = [
        s["best_develop_median_daily_pct"]
        for s in per_seed
        if s["best_develop_median_daily_pct"] is not None
    ]
    return {
        "seeds": seeds,
        "per_seed": per_seed,
        "max_null_best": float(max(vals)) if vals else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--csv", type=Path, default=CSV_PATH)
    ap.add_argument("--lock", type=Path, default=LOCK_PATH)
    ap.add_argument("--out", type=Path, default=OUT_JSON)
    ap.add_argument("--full-out", type=Path, default=FULL_JSON)
    ap.add_argument("--null-out", type=Path, default=NULL_JSON)
    args = ap.parse_args()

    lock = load_usd_lock(args.lock)
    costs = costs_from_lock(lock)
    verify_data_sha(args.csv, lock)
    holdout = holdout_start(lock)
    d = load_eurusd_m5(args.csv)

    t0 = pytime.time()
    null = run_usd_null(d, lock, costs, holdout)
    args.null_out.parent.mkdir(parents=True, exist_ok=True)
    args.null_out.write_text(json.dumps(null, indent=2) + "\n")
    print(f"null: max_null_best={null['max_null_best']} -> {args.null_out}")

    rows = run_usd_grid(d, lock, costs, holdout)
    ranked = rank_develop(rows)
    best = ranked[0] if ranked else None
    mnb = null["max_null_best"]
    gate = None
    if best is not None and mnb is not None:
        gate = {
            "threshold": mnb + 0.5 * GOAL_DAILY,
            "best_develop_median_daily_pct": best["develop"]["median_daily_pct"],
            "passes": bool(best["develop"]["median_daily_pct"] >= mnb + 0.5 * GOAL_DAILY),
        }
    report = {
        "search_id": SEARCH_ID,
        "promote": False,
        "live_go": False,
        "holdout_start": str(holdout),
        "n_configs": len(rows),
        "n_eligible_develop": len(ranked),
        "n_develop_hit_goal": sum(1 for r in rows if r["develop"]["goal_both"]),
        "null": null,
        "gate": gate,
        "elapsed_sec": round(pytime.time() - t0, 1),
        "book": {
            "lots": 3.0,
            "tp_usd": 20.0,
            "sl_usd": 100.0,
            "daily_halt_usd": -300.0,
        },
        "costs": asdict(costs),
        "data": lock["data"],
        "best_develop": best,
        "all_develop": [
            {
                "params": r["params"],
                "develop": {
                    k: r["develop"][k]
                    for k in (
                        "trades",
                        "win_rate",
                        "profit_factor",
                        "net_pnl",
                        "avg_trade",
                        "median_daily_pct",
                        "halt_days",
                    )
                    if k in r["develop"]
                },
                "holdout": {
                    k: r["holdout"][k]
                    for k in ("trades", "win_rate", "profit_factor", "net_pnl")
                    if k in r["holdout"]
                },
            }
            for r in rows
        ],
        "goal_note": (
            "Specified book: 3 lots, TP $20, SL $100, halt -$300. "
            "TP is 6.67 points vs 12-pt median spread. Not a v1 retune."
        ),
    }
    write_slim_json(args.out, report)
    args.full_out.write_text(
        json.dumps({"rows": rows, "report": report}, indent=2, default=float) + "\n"
    )
    print(
        json.dumps(
            {
                "n_configs": report["n_configs"],
                "n_eligible_develop": report["n_eligible_develop"],
                "n_develop_hit_goal": report["n_develop_hit_goal"],
                "max_null_best": mnb,
                "gate": gate,
                "all_develop": report["all_develop"],
                "promote": False,
            },
            indent=2,
        )
    )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
