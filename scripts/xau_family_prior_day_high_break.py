#!/usr/bin/env python3
"""Family: prior_day_high_break — Prior-day high breakout (fixed geometry).

Charter: results/xau_next_design_charter.json (FROZEN 2026-08-08).

Rule (causal, long-only)
------------------------
* prior_day_high = max(high) over all H1 bars on server calendar day D-1.
* Long when H1 close *first* crosses above that level:
    close[i] > prior_day_high  and  close[i-1] <= prior_day_high
  and hour[i] ∈ {8..16}, one position at a time.
* Exit: fixed SL/TP only (no trail, no time stop, no signal flip).
    SL = entry - sl_atr * ATR(14)
    TP = entry + tp_rr * sl_atr * ATR(14)   with tp_rr fixed at 2.0
* Fill: signal-bar close (house convention; same as backtest.simulate).

Free knobs (1): sl_atr ∈ {1.0, 1.5, 2.0}. Search cardinality = 3.

Plugin API for xau_family_null_maxstat:
  prepare / simulate / grid  (+ build_grid alias)

Develop scorer (this module CLI):
  python3 scripts/xau_family_prior_day_high_break.py
  → results/xau_prior_day_high_break_develop_grid.json

SAFETY: offline only. develop window only for search. costs from
load_research_costs(). Never --live. No holdout selection.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from xau_null_core import metrics_dict, serializable_params  # noqa: E402
from xau_research_costs import load_research_costs  # noqa: E402

from backtest import (  # noqa: E402
    CONTRACT_SIZE,
    START_BALANCE,
    Metrics,
    develop_only,
    holdout_start,
    load_h1,
    metrics_from_pnls,
    passes as classic_passes,
)

# ---------------------------------------------------------------------------
# Identity / fixed seeds (charter)
# ---------------------------------------------------------------------------
FAMILY = "prior_day_high_break"
NAME = FAMILY
kill_label = "KILL_PRIOR_DAY_HIGH_BREAK"

FIXED: dict[str, Any] = {
    "risk_pct": 0.01,
    "long_only": True,
    "max_lots": 0.5,
    "tp_rr": 2.0,
    "hours": (8, 9, 10, 11, 12, 13, 14, 15, 16),
    "atr_period": 14,
    "cooldown": 0,
}

# Only free axis (charter free_knobs).
SL_ATR_VALUES: tuple[float, ...] = (1.0, 1.5, 2.0)

# Soft passer for null n_passers count (charter.passer_definition_soft).
SOFT_N_TRADES_MIN = 20
SOFT_PF_MIN = 1.2

WARMUP = 220  # ATR + first full prior day; match house lane sims

CHARTER_PATH = ROOT / "results" / "xau_next_design_charter.json"
OUT_DEVELOP_GRID = ROOT / "results" / "xau_prior_day_high_break_develop_grid.json"


# ---------------------------------------------------------------------------
# Prepare
# ---------------------------------------------------------------------------
def prepare(raw: pd.DataFrame) -> pd.DataFrame:
    """ATR(14), hour, day_id, prior_day_high (max high of calendar day D-1)."""
    d = raw.copy()
    times = pd.to_datetime(d["time"], utc=True)
    d["hour"] = times.dt.hour.astype(int)
    d["day_id"] = times.dt.strftime("%Y%m%d").astype(int)

    c = d["close"].astype(float)
    h = d["high"].astype(float)
    l = d["low"].astype(float)
    prev = c.shift(1)
    tr = pd.concat([(h - l), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    period = int(FIXED["atr_period"])
    d["atr"] = tr.ewm(alpha=1.0 / period, adjust=False).mean()

    # Prior calendar day high: known for every bar of day D once D-1 is complete.
    day_high = d.groupby("day_id", sort=True)["high"].max()
    prior_by_day = day_high.shift(1)
    d["prior_day_high"] = d["day_id"].map(prior_by_day).astype(float)

    return d


prepare_frame = prepare  # alias for harnesses that look for prepare_frame


# ---------------------------------------------------------------------------
# Simulate
# ---------------------------------------------------------------------------
def simulate(
    d: pd.DataFrame,
    *,
    sl_atr: float = 1.5,
    tp_rr: float = 2.0,
    risk_pct: float = 0.01,
    max_lots: float = 0.5,
    hours: tuple[int, ...] | list[int] | None = None,
    cooldown: int = 0,
    long_only: bool = True,
    atr_period: int = 14,  # fixed seed; ATR already in frame from prepare
    spread_col: str | None = None,
    point_size: float = 0.01,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    **_extra: Any,
) -> Metrics:
    """Prior-day high first-close-through; fixed SL/TP geometry; cost-aware.

    Cost kwargs match backtest.simulate: round-trip charged once off entry bar.
    """
    _ = atr_period, long_only  # charter fixed seeds accepted for grid splat
    n = len(d)
    close = d["close"].to_numpy(float)
    high = d["high"].to_numpy(float)
    low = d["low"].to_numpy(float)
    atr = d["atr"].to_numpy(float)
    hour = d["hour"].to_numpy(int) if "hour" in d.columns else np.zeros(n, dtype=int)
    pdh = (
        d["prior_day_high"].to_numpy(float)
        if "prior_day_high" in d.columns
        else np.full(n, np.nan)
    )

    if hours is None:
        hours_t = FIXED["hours"]
    else:
        hours_t = tuple(int(h) for h in hours)

    if spread_col is not None and spread_col in d.columns:
        spread_pts = np.nan_to_num(d[spread_col].to_numpy(float), nan=0.0)
    else:
        spread_pts = np.zeros(n)

    sl_mult = float(sl_atr)
    rr = float(tp_rr)
    cool_cfg = int(cooldown)

    bal = START_BALANCE
    eq = np.zeros(n)
    pnls: list[float] = []
    pos = 0
    entry = sl = tp = lots = 0.0
    trade_cost = 0.0
    cool = 0

    for i in range(n):
        px = close[i]
        floating = bal + ((px - entry) * CONTRACT_SIZE * lots * pos if pos else 0.0)
        eq[i] = floating

        # Fixed SL/TP only — no trail, no time stop, no signal flip.
        if pos != 0 and i >= 1:
            exit_px = None
            if pos > 0:
                if low[i] <= sl:
                    exit_px = sl
                elif high[i] >= tp:
                    exit_px = tp
            else:
                # long_only family; shorts never opened
                if high[i] >= sl:
                    exit_px = sl
                elif low[i] <= tp:
                    exit_px = tp
            if exit_px is not None:
                pnl = (exit_px - entry) * CONTRACT_SIZE * lots * pos - trade_cost
                bal += pnl
                pnls.append(pnl)
                pos = 0
                lots = 0.0
                trade_cost = 0.0
                cool = cool_cfg
                eq[i] = bal

        if cool > 0:
            cool -= 1
            continue
        if pos != 0 or i < WARMUP or i < 1:
            continue
        if np.isnan(atr[i]) or atr[i] <= 0:
            continue
        if np.isnan(pdh[i]):
            continue
        if hour[i] not in hours_t:
            continue

        # First close through prior day high (causal: pdh known for day D).
        long_sig = close[i] > pdh[i] and close[i - 1] <= pdh[i]
        if not long_sig:
            continue

        stop_dist = atr[i] * sl_mult
        if stop_dist <= 1e-9:
            continue
        risk_cash = bal * float(risk_pct)
        raw_lots = risk_cash / (stop_dist * CONTRACT_SIZE)
        lots_sz = float(np.floor(raw_lots * 100 + 1e-12) / 100.0)
        lots_sz = min(lots_sz, float(max_lots))
        min_lot = 0.01
        if lots_sz < min_lot or stop_dist * CONTRACT_SIZE * min_lot > risk_cash + 1e-9:
            continue

        trade_cost = (
            (float(spread_pts[i]) + 2.0 * float(slippage_points))
            * float(point_size)
            * CONTRACT_SIZE
            * lots_sz
            + 2.0 * float(commission_per_lot) * lots_sz
        )

        pos = 1
        lots = lots_sz
        entry = px  # signal-bar close fill (house convention)
        sl = entry - stop_dist
        tp = entry + rr * stop_dist  # tp_rr * sl_atr * ATR

    if pos != 0:
        pnl = (close[-1] - entry) * CONTRACT_SIZE * lots * pos - trade_cost
        bal += pnl
        pnls.append(pnl)
        eq[-1] = bal

    return metrics_from_pnls(pnls, eq)


# ---------------------------------------------------------------------------
# Grid
# ---------------------------------------------------------------------------
def build_grid() -> list[dict]:
    """Full charter grid: 3 points (sl_atr free; all other seeds fixed)."""
    out: list[dict] = []
    for sl in SL_ATR_VALUES:
        p: dict[str, Any] = {
            "sl_atr": float(sl),
            "tp_rr": float(FIXED["tp_rr"]),
            "risk_pct": float(FIXED["risk_pct"]),
            "max_lots": float(FIXED["max_lots"]),
            "hours": tuple(FIXED["hours"]),
            "atr_period": int(FIXED["atr_period"]),
            "cooldown": int(FIXED["cooldown"]),
            "long_only": bool(FIXED["long_only"]),
        }
        out.append(p)
    return out


def grid(*, max_n: int = 1200, seed: int = 42) -> list[dict]:
    """Plugin entry for xau_family_null_maxstat (full enumerate; n=3 ≪ max_n)."""
    _ = max_n, seed  # fixed full grid; no subsample needed at cardinality 3
    return build_grid()


# ---------------------------------------------------------------------------
# Pass helpers (null harness optional hooks)
# ---------------------------------------------------------------------------
def classic_pass(m: Any) -> bool:
    """Hard classic: PF>1.5 WR>55 DD<10 n>=20."""
    try:
        return bool(classic_passes(m))
    except Exception:
        md = metrics_dict(m)
        return (
            int(md["n_trades"]) >= 20
            and float(md["profit_factor"]) > 1.5
            and float(md["win_rate"]) > 55.0
            and float(md["max_drawdown_pct"]) < 10.0
        )


def soft_pass(m: Any) -> bool:
    """Charter soft passer: n>=20, PF>=1.2, net>0 (null n_passers primary)."""
    md = metrics_dict(m)
    return (
        int(md["n_trades"]) >= SOFT_N_TRADES_MIN
        and float(md["profit_factor"]) >= SOFT_PF_MIN
        and float(md["net_profit"]) > 0.0
    )


use_soft_primary = True


# ---------------------------------------------------------------------------
# Develop full-grid scorer
# ---------------------------------------------------------------------------
def score_develop_grid(
    *,
    costs: dict[str, Any] | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Score every grid point on develop with research costs. No early exit."""
    costs = dict(costs if costs is not None else load_research_costs())
    candidates = build_grid()

    raw = load_h1()
    cutoff = holdout_start()
    if cutoff is None:
        raise SystemExit("holdout lock missing; cannot define develop window")
    # Ensure time comparable
    if raw["time"].dt.tz is None:
        raw = raw.copy()
        raw["time"] = pd.to_datetime(raw["time"], utc=True)
    dev_raw = develop_only(raw, cutoff)
    d = prepare(dev_raw)

    rows: list[dict[str, Any]] = []
    t0 = time.time()
    best_i = 0
    best_pf = -1.0
    n_soft = 0
    n_classic = 0

    for i, p in enumerate(candidates):
        m = simulate(d, **{**costs, **p})
        md = metrics_dict(m)
        sp = soft_pass(m)
        cp = classic_pass(m)
        if sp:
            n_soft += 1
        if cp:
            n_classic += 1
        row = {
            "index": i,
            "params": serializable_params(p),
            "metrics": md,
            "passes_soft": sp,
            "passes_classic": cp,
        }
        rows.append(row)
        pf = float(md["profit_factor"])
        net = float(md["net_profit"])
        if pf > best_pf or (
            pf == best_pf and net > float(rows[best_i]["metrics"]["net_profit"])
        ):
            best_pf = pf
            best_i = i

    elapsed = time.time() - t0
    best = rows[best_i]
    # n_passers under full costs = soft charter definition (primary for family)
    report: dict[str, Any] = {
        "status": "DEVELOP_GRID_SCORED",
        "family": FAMILY,
        "display_name": "Prior-day high breakout (fixed geometry)",
        "charter": str(CHARTER_PATH.relative_to(ROOT)) if CHARTER_PATH.is_file() else None,
        "claim_edge": False,
        "note": (
            "Develop-only full grid with research costs (RAW $3 RT floor). "
            "No edge claim; null max-stat + costed WF still required."
        ),
        "window": {
            "holdout_start": cutoff.isoformat(),
            "bars": int(len(dev_raw)),
            "start": dev_raw["time"].iloc[0].isoformat(),
            "end": dev_raw["time"].iloc[-1].isoformat(),
            "rule": "time < holdout_start",
        },
        "costs": costs,
        "fixed": {
            **{k: (list(v) if isinstance(v, tuple) else v) for k, v in FIXED.items()},
        },
        "free_knobs": {"sl_atr": list(SL_ATR_VALUES)},
        "grid": {
            "n_configs": len(candidates),
            "search_cardinality": len(candidates),
            "early_exit": False,
        },
        "results": rows,
        "summary": {
            "max_pf": float(best["metrics"]["profit_factor"]),
            "max_pf_params": best["params"],
            "max_pf_metrics": best["metrics"],
            "n_passers": n_soft,
            "n_passers_soft": n_soft,
            "n_passers_classic": n_classic,
            "passer_definition_soft": {
                "n_trades_min": SOFT_N_TRADES_MIN,
                "profit_factor_min": SOFT_PF_MIN,
                "net_profit": "gt_0",
            },
            "elapsed_s": float(elapsed),
        },
        "safety": {
            "offline_only": True,
            "promote": "no",
            "live_go": False,
            "holdout_used_for_selection": False,
        },
    }

    if write:
        OUT_DEVELOP_GRID.parent.mkdir(parents=True, exist_ok=True)
        OUT_DEVELOP_GRID.write_text(json.dumps(report, indent=2) + "\n")
        print(f"Wrote {OUT_DEVELOP_GRID}", flush=True)

    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--no-write",
        action="store_true",
        help="print summary only; do not write develop grid JSON",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="print full report JSON to stdout",
    )
    args = ap.parse_args(argv)

    report = score_develop_grid(write=not args.no_write)
    s = report["summary"]
    print(
        f"family={FAMILY} develop_grid n={report['grid']['n_configs']} "
        f"max_PF={s['max_pf']:.4f} n_passers={s['n_passers']} "
        f"(soft PF>={SOFT_PF_MIN} n>={SOFT_N_TRADES_MIN} net>0) "
        f"classic_passers={s['n_passers_classic']} "
        f"best={s['max_pf_params']} "
        f"costs={report['costs']}",
        flush=True,
    )
    for row in report["results"]:
        md = row["metrics"]
        print(
            f"  sl_atr={row['params']['sl_atr']}: "
            f"PF={md['profit_factor']:.4f} net={md['net_profit']:.2f} "
            f"WR={md['win_rate']:.1f} DD={md['max_drawdown_pct']:.2f} "
            f"n={md['n_trades']} soft={row['passes_soft']} classic={row['passes_classic']}",
            flush=True,
        )
    if args.json:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
