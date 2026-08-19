#!/usr/bin/env python3
"""US100 v7 screen: IB false-break fade + M5 z-score / tick-vol exhaustion.

Lock: results/us_index_session_v7_lock.json
  select et_date < 2026-06-01
  holdout et_date >= 2026-07-01
  June 2026 is a burned buffer. July–August is cleaner, not virgin.

Architectural pivot after v6 starvation: intraday kinetics, not daily
Hurst/ADX/ATR. Does not retune v1–v6. Does not use US30 / XAU / news.
Costs keep 10 pt slippage/side. promote / live_go stay no. Python-only.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time as pytime
from dataclasses import asdict
from datetime import date
from pathlib import Path

import numpy as np

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from us_index_session_autoresearch import (  # noqa: E402
    GOAL_DAILY_PCT,
    GOAL_MONTHLY_PCT,
    START_BALANCE,
    _et_arrays,
    _or_and_vwap,
    pack_metrics,
    score_row,
    simulate_exits,
)
from us_index_session_autoresearch_v4 import split_v4  # noqa: E402
from us_index_session_backtest import (  # noqa: E402
    CostSpec,
    costs_from_meta,
    load_m5_csv,
    parse_meta,
    refuse_mutated_frozen_book,
    require_frozen_cost_book,
    write_slim_json,
)
from us_index_session_core import (  # noqa: E402
    ATR_PERIOD,
    IB_END_MIN,
    ib_false_break_signals,
    rolling_zscore_typical,
    to_utc,
    wilder_atr,
)

SEARCH_ID = "us_index_session_v7"
LOCK_PATH = _ROOT / "results" / "us_index_session_v7_lock.json"
SELECT_END = date(2026, 6, 1)
HOLDOUT_START = date(2026, 7, 1)
IB_MINUTES = 60
ENTRY_START = 9 * 60 + 45
FRIDAY_CUTOFF = 14 * 60

IB_ENTRY_ENDS = (11 * 60 + 30, 12 * 60)
IB_TARGETS = ("ib_mid", "opposite_ib")
IB_ONE_PER_DAY = (True, False)

Z_THR = (2.0, 2.5)
VOL_K = (1.5, 2.0)
Z_WINDOWS = (12, 24)
Z_SESSIONS = (
    (ENTRY_START, 15 * 60),
    (ENTRY_START, 11 * 60 + 30),
)
Z_ONE_PER_DAY = (True, False)

IB_EXIT = {"kind": "vwap", "sl": 1.0, "hh": 15, "mm": 45, "running": False}
Z_EXIT = {"kind": "vwap", "sl": 1.0, "hh": 15, "mm": 45, "running": True}


def _session_label(start_min: int, end_min: int) -> str:
    return f"{start_min // 60:02d}:{start_min % 60:02d}-{end_min // 60:02d}:{end_min % 60:02d}"


def _end_label(end_min: int) -> str:
    return f"{end_min // 60:02d}:{end_min % 60:02d}"


def build_grid() -> list[dict]:
    rows: list[dict] = []
    for end, tgt, opd in itertools.product(IB_ENTRY_ENDS, IB_TARGETS, IB_ONE_PER_DAY):
        spec = dict(IB_EXIT)
        rows.append(
            {
                "family": "ib_false_breakout_fade",
                "or_minutes": IB_MINUTES,
                "entry_end": _end_label(end),
                "entry_end_min": end,
                "target": tgt,
                "one_per_day": opd,
                "exit": "vwap_sl1.0_flat15:45",
                "exit_spec": spec,
            }
        )
    for z_thr, vk, win, (a, b), opd in itertools.product(
        Z_THR, VOL_K, Z_WINDOWS, Z_SESSIONS, Z_ONE_PER_DAY
    ):
        spec = dict(Z_EXIT)
        rows.append(
            {
                "family": "m5_zscore_tick_vol_exhaustion",
                "z_thr": z_thr,
                "vol_k": vk,
                "window": win,
                "session": _session_label(a, b),
                "entry_start_min": a,
                "entry_end_min": b,
                "one_per_day": opd,
                "exit": "mu_sl1.0_flat15:45",
                "exit_spec": spec,
            }
        )
    return rows


def _slim(cfg: dict) -> dict:
    skip = {"exit_spec", "entry_end_min", "entry_start_min"}
    return {k: cfg[k] for k in cfg if k not in skip}


def zscore_vol_signals(
    z: np.ndarray,
    vol: np.ndarray,
    vol_mu: np.ndarray,
    mins: np.ndarray,
    keys: np.ndarray,
    dow: np.ndarray,
    *,
    z_thr: float,
    vol_k: float,
    entry_start_min: int,
    entry_end_min: int,
    one_per_day: bool,
    exclude_forming: bool = True,
) -> np.ndarray:
    n = len(z)
    out = np.zeros(n, dtype=np.int8)
    last = n - 1 if exclude_forming else n
    fired = -1
    for i in range(last):
        m = int(mins[i])
        if int(dow[i]) == 4 and m >= FRIDAY_CUTOFF:
            continue
        if m < entry_start_min or m >= entry_end_min:
            continue
        if m < 9 * 60 + 30 or m >= 16 * 60:
            continue
        if one_per_day and int(keys[i]) == fired:
            continue
        zi = float(z[i])
        v = float(vol[i])
        vm = float(vol_mu[i])
        if not (np.isfinite(zi) and np.isfinite(v) and np.isfinite(vm) and vm > 0.0):
            continue
        if v <= vol_k * vm:
            continue
        if zi <= -z_thr:
            out[i] = 1
        elif zi >= z_thr:
            out[i] = -1
        else:
            continue
        fired = int(keys[i])
    return out


def _opposite_target(sigs: np.ndarray, or_h: np.ndarray, or_l: np.ndarray) -> np.ndarray:
    tgt = np.full(len(sigs), np.nan)
    long = sigs > 0
    short = sigs < 0
    tgt[long] = or_h[long]
    tgt[short] = or_l[short]
    return tgt


def _run(
    cfg: dict,
    times: list,
    mins: np.ndarray,
    keys: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    atr: np.ndarray,
    spread: np.ndarray,
    costs: CostSpec,
    sigs: np.ndarray,
    exit_spec: dict,
    target: np.ndarray,
) -> dict:
    trades = simulate_exits(
        times,
        mins,
        keys,
        open_,
        high,
        low,
        atr,
        spread,
        sigs,
        costs,
        exit_spec,
        target=target,
    )
    pre, post = split_v4(trades)
    return {
        "params": _slim(cfg),
        "develop": pack_metrics(pre),
        "holdout": pack_metrics(post),
        "develop_score": score_row(pack_metrics(pre)),
    }


def run_search(csv_path: Path, meta_path: Path | None, costs: CostSpec) -> dict:
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
    or_h, or_l, ready, _vwap = _or_and_vwap(mins, keys, ny, high, low, close, vol, IB_MINUTES)
    z_cache: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
    for win in Z_WINDOWS:
        z_cache[win] = rolling_zscore_typical(high, low, close, vol, win, include_i=False)

    grid = build_grid()
    rows: list[dict] = []
    t0 = pytime.time()
    for i, cfg in enumerate(grid):
        fam = cfg["family"]
        if fam == "ib_false_breakout_fade":
            sigs = ib_false_break_signals(
                high,
                low,
                close,
                mins,
                keys,
                dow,
                or_h,
                or_l,
                ready,
                entry_end_min=cfg["entry_end_min"],
                one_per_day=cfg["one_per_day"],
            )
            if cfg["target"] == "ib_mid":
                target = (or_h + or_l) / 2.0
            else:
                target = _opposite_target(sigs, or_h, or_l)
        else:
            z, mu, _sig, vmu = z_cache[int(cfg["window"])]
            sigs = zscore_vol_signals(
                z,
                vol,
                vmu,
                mins,
                keys,
                dow,
                z_thr=float(cfg["z_thr"]),
                vol_k=float(cfg["vol_k"]),
                entry_start_min=int(cfg["entry_start_min"]),
                entry_end_min=int(cfg["entry_end_min"]),
                one_per_day=cfg["one_per_day"],
            )
            target = mu
        row = _run(
            cfg,
            times,
            mins,
            keys,
            open_,
            high,
            low,
            atr14,
            spread,
            costs,
            sigs,
            cfg["exit_spec"],
            target,
        )
        row["index"] = i
        rows.append(row)
    elapsed = pytime.time() - t0
    eligible = [r for r in rows if r["develop_score"] > -1e8]
    ranked = sorted(
        eligible,
        key=lambda r: (
            r["develop"]["profit_factor"] or 3.0,
            r["develop"]["expectancy"],
        ),
        reverse=True,
    )
    best = ranked[0] if ranked else None
    top20 = ranked[:20]
    n_hit = sum(1 for r in eligible if r["develop"]["goal_both"])
    n_ho = sum(1 for r in top20 if r["holdout"]["goal_both"])
    by_fam: dict[str, dict] = {}
    fam_rank = sorted(
        rows,
        key=lambda r: (
            r["develop"]["profit_factor"] or 0.0,
            r["develop"]["expectancy"],
            r["develop"]["trades"],
        ),
        reverse=True,
    )
    for pool in (ranked, fam_rank):
        for r in pool:
            fam = r["params"]["family"]
            if fam not in by_fam:
                by_fam[fam] = r
    elig_by_fam = {
        fam: sum(1 for r in eligible if r["params"]["family"] == fam)
        for fam in {r["params"]["family"] for r in rows}
    }
    return {
        "search_id": SEARCH_ID,
        "promote": False,
        "live_go": False,
        "python_only": True,
        "selection_end": str(SELECT_END),
        "holdout_start": str(HOLDOUT_START),
        "start_balance": START_BALANCE,
        "goal_daily_pct": GOAL_DAILY_PCT,
        "goal_monthly_pct": GOAL_MONTHLY_PCT,
        "n_configs": len(rows),
        "n_eligible_develop": len(eligible),
        "n_eligible_by_family": elig_by_fam,
        "n_develop_hit_goal": n_hit,
        "n_top20_holdout_hit_goal": n_ho,
        "elapsed_sec": round(elapsed, 2),
        "costs": asdict(costs),
        "bars": int(len(df)),
        "from": str(df["time_utc"].iloc[0]) if len(df) else "",
        "to": str(df["time_utc"].iloc[-1]) if len(df) else "",
        "ib_minutes": IB_MINUTES,
        "ib_ready_min": IB_END_MIN,
        "z_window_include_i": False,
        "best_develop": best,
        "best_by_family": by_fam,
        "top20": top20,
        "note": (
            "New search. IB false-break is sweep-then-next-bar close-inside, "
            "not a 15m OR close-break and not a v3 wick fade. Z-score μ/σ/Vμ "
            "exclude bar i. promote=no."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
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
    ap.add_argument("--out", type=Path, default=_ROOT / "results" / "us_index_session_v7.json")
    args = ap.parse_args()
    lock = json.loads(LOCK_PATH.read_text())
    if lock.get("search_id") != SEARCH_ID:
        raise SystemExit("search_id mismatch")
    if lock.get("selection_end") != "2026-06-01" or lock.get("holdout_start") != "2026-07-01":
        raise SystemExit("holdout/selection lock mismatch")
    if lock.get("causality", {}).get("z_window_include_i") is not False:
        raise SystemExit("z_window_include_i must be frozen false")
    refuse_mutated_frozen_book(lock)
    grid = build_grid()
    if len(grid) != int(lock["n_configs_expected"]):
        raise SystemExit(f"grid {len(grid)} != lock {lock['n_configs_expected']}")
    meta = parse_meta(args.meta) if args.meta.is_file() else {}
    costs = require_frozen_cost_book(
        costs_from_meta(
            meta, lots=1.0, slippage_points=10.0, commission_per_lot=0.0, max_spread_points=200.0
        )
    )
    report = run_search(args.csv, args.meta, costs)
    write_slim_json(args.out, report)
    best = report["best_develop"]
    print(
        json.dumps(
            {
                "n_configs": report["n_configs"],
                "n_eligible_develop": report["n_eligible_develop"],
                "n_develop_hit_goal": report["n_develop_hit_goal"],
                "n_top20_holdout_hit_goal": report["n_top20_holdout_hit_goal"],
                "elapsed_sec": report["elapsed_sec"],
                "best_develop_params": None if best is None else best["params"],
                "best_develop": None if best is None else best["develop"],
                "best_holdout": None if best is None else best["holdout"],
                "best_by_family": {
                    k: {
                        "params": v["params"],
                        "develop_day": v["develop"]["median_daily_pct"],
                        "holdout_day": v["holdout"]["median_daily_pct"],
                    }
                    for k, v in report["best_by_family"].items()
                },
                "promote": False,
            },
            indent=2,
        )
    )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
