#!/usr/bin/env python3
"""US100 playbook screen: VWAP bounce + EMA/MACD (new search).

Lock: results/us_index_session_playbook_v2_lock.json
  holdout_start = 2026-06-01  — NEVER used for selection
  Not a retune of ny_cash_orb_vwap_ema_flat or us_index_session_develop_v1.

Selection is develop-only. Holdout and US30 transfer are scored after ranking.
promote / live_go stay no.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time as pytime
from dataclasses import asdict
from datetime import time
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
    exit_name,
    pack_metrics,
    score_row,
    simulate_exits,
)
from us_index_session_backtest import (  # noqa: E402
    HOLDOUT_START,
    CostSpec,
    costs_from_meta,
    load_m5_csv,
    parse_meta,
    refuse_mutated_frozen_book,
    require_frozen_cost_book,
    split_by_holdout,
    write_slim_json,
)
from us_index_session_core import (  # noqa: E402
    ATR_PERIOD,
    ema_series,
    macd_series,
    rsi_series,
    to_utc,
    wilder_atr,
)

SEARCH_ID = "us_index_session_playbook_v2"
LOCK_PATH = _ROOT / "results" / "us_index_session_playbook_v2_lock.json"
ENTRY_START_MIN = 9 * 60 + 35

BOUNCE_ENDS = (time(10, 0), time(10, 30))
RSI_PERIODS = (7, 14)
RSI_BANDS = ((75.0, 25.0), (70.0, 30.0))
ATR_DEVS = (0.75, 1.0, 1.5)
ONE_PER_DAY = (True, False)
BOUNCE_EXITS: tuple[dict, ...] = (
    {"kind": "vwap", "sl": 1.0},
    {"kind": "vwap", "sl": 1.5},
    {"kind": "flatten", "hh": 10, "mm": 30},
    {"kind": "flatten", "hh": 11, "mm": 30},
    {"kind": "atr", "sl": 1.0, "tp": 1.5},
)

MACD_EMA_PAIRS = ((5, 20), (8, 21))
MACD_SPECS = ((12, 26, 9), (5, 13, 5))
MACD_ENDS = (time(10, 30), time(11, 30), time(12, 0))
CROSS_ONLY = (True, False)
MACD_EXITS: tuple[dict, ...] = (
    {"kind": "flatten", "hh": 11, "mm": 30},
    {"kind": "flatten", "hh": 15, "mm": 45},
    {"kind": "atr", "sl": 1.0, "tp": 1.5},
    {"kind": "atr", "sl": 1.5, "tp": 2.0},
    {"kind": "bars", "n": 6},
    {"kind": "bars", "n": 12},
)


def build_grid() -> list[dict]:
    rows: list[dict] = []
    for end, rsi_p, (ob, os_), dev, opd, ex in itertools.product(
        BOUNCE_ENDS, RSI_PERIODS, RSI_BANDS, ATR_DEVS, ONE_PER_DAY, BOUNCE_EXITS
    ):
        rows.append(
            {
                "family": "ny_cash_vwap_bounce_rsi",
                "entry_end": f"{end.hour:02d}:{end.minute:02d}",
                "entry_end_min": end.hour * 60 + end.minute,
                "rsi_period": rsi_p,
                "rsi_ob": ob,
                "rsi_os": os_,
                "atr_dev": dev,
                "one_per_day": opd,
                "exit": exit_name(ex),
                "exit_spec": ex,
            }
        )
    for (ef, es), (mf, ms, sig), end, opd, cross, ex in itertools.product(
        MACD_EMA_PAIRS, MACD_SPECS, MACD_ENDS, ONE_PER_DAY, CROSS_ONLY, MACD_EXITS
    ):
        rows.append(
            {
                "family": "ny_cash_ema_macd",
                "ema_fast": ef,
                "ema_slow": es,
                "macd_fast": mf,
                "macd_slow": ms,
                "macd_signal": sig,
                "entry_end": f"{end.hour:02d}:{end.minute:02d}",
                "entry_end_min": end.hour * 60 + end.minute,
                "one_per_day": opd,
                "cross_only": cross,
                "exit": exit_name(ex),
                "exit_spec": ex,
            }
        )
    return rows


def bounce_signals(
    close: np.ndarray,
    mins: np.ndarray,
    keys: np.ndarray,
    dow: np.ndarray,
    ny: np.ndarray,
    vwap: np.ndarray,
    atr: np.ndarray,
    rsi: np.ndarray,
    *,
    entry_end_min: int,
    atr_dev: float,
    rsi_ob: float,
    rsi_os: float,
    one_per_day: bool,
    min_atr_pct: float = 0.00015,
) -> np.ndarray:
    n = len(close)
    out = np.zeros(n, dtype=np.int8)
    fired = -1
    for i in range(n - 1):
        if not ny[i]:
            continue
        m = int(mins[i])
        if int(dow[i]) == 4 and m >= 14 * 60:
            continue
        if m < ENTRY_START_MIN or m >= entry_end_min:
            continue
        px = float(close[i])
        at = float(atr[i])
        vw = float(vwap[i])
        rv = float(rsi[i])
        if not (np.isfinite(at) and np.isfinite(vw) and np.isfinite(rv)):
            continue
        if px <= 0.0 or (at / px) < min_atr_pct or at <= 0.0:
            continue
        if one_per_day and int(keys[i]) == fired:
            continue
        ext = (px - vw) / at
        sig = 0
        if ext >= atr_dev and rv >= rsi_ob:
            sig = -1
        elif ext <= -atr_dev and rv <= rsi_os:
            sig = 1
        if sig == 0:
            continue
        out[i] = sig
        fired = int(keys[i])
    return out


def macd_signals(
    mins: np.ndarray,
    keys: np.ndarray,
    dow: np.ndarray,
    ny: np.ndarray,
    ema_f: np.ndarray,
    ema_s: np.ndarray,
    hist: np.ndarray,
    *,
    entry_end_min: int,
    one_per_day: bool,
    cross_only: bool,
) -> np.ndarray:
    n = len(mins)
    out = np.zeros(n, dtype=np.int8)
    fired = -1
    for i in range(1, n - 1):
        if not ny[i]:
            continue
        m = int(mins[i])
        if int(dow[i]) == 4 and m >= 14 * 60:
            continue
        if m < ENTRY_START_MIN or m >= entry_end_min:
            continue
        ef = float(ema_f[i])
        es = float(ema_s[i])
        hf = float(hist[i])
        if not (np.isfinite(ef) and np.isfinite(es) and np.isfinite(hf)):
            continue
        if one_per_day and int(keys[i]) == fired:
            continue
        if cross_only:
            efp = float(ema_f[i - 1])
            esp = float(ema_s[i - 1])
            if not (np.isfinite(efp) and np.isfinite(esp)):
                continue
            long_ok = ef > es and efp <= esp and hf > 0.0
            short_ok = ef < es and efp >= esp and hf < 0.0
        else:
            long_ok = ef > es and hf > 0.0
            short_ok = ef < es and hf < 0.0
        sig = 1 if long_ok else (-1 if short_ok else 0)
        if sig == 0:
            continue
        out[i] = sig
        fired = int(keys[i])
    return out


def _slim(cfg: dict) -> dict:
    skip = {"exit_spec", "entry_end_min"}
    return {k: cfg[k] for k in cfg if k not in skip}


def _run_one(
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
    target: np.ndarray | None,
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
        cfg["exit_spec"],
        target=target,
    )
    pre, post = split_by_holdout(trades)
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
    atr = wilder_atr(high, low, close, ATR_PERIOD)
    _or_h, _or_l, _ready, vwap = _or_and_vwap(
        mins, keys, ny, high, low, close, vol, 15
    )
    rsi_cache = {p: rsi_series(close, p) for p in RSI_PERIODS}
    ema_cache = {
        p: ema_series(close, p)
        for p in sorted({x for pair in MACD_EMA_PAIRS for x in pair})
    }
    macd_cache = {spec: macd_series(close, *spec)[2] for spec in MACD_SPECS}

    grid = build_grid()
    rows: list[dict] = []
    t0 = pytime.time()
    for i, cfg in enumerate(grid):
        if cfg["family"] == "ny_cash_vwap_bounce_rsi":
            sigs = bounce_signals(
                close,
                mins,
                keys,
                dow,
                ny,
                vwap,
                atr,
                rsi_cache[cfg["rsi_period"]],
                entry_end_min=cfg["entry_end_min"],
                atr_dev=cfg["atr_dev"],
                rsi_ob=cfg["rsi_ob"],
                rsi_os=cfg["rsi_os"],
                one_per_day=cfg["one_per_day"],
            )
            target = vwap
        else:
            sigs = macd_signals(
                mins,
                keys,
                dow,
                ny,
                ema_cache[cfg["ema_fast"]],
                ema_cache[cfg["ema_slow"]],
                macd_cache[
                    (cfg["macd_fast"], cfg["macd_slow"], cfg["macd_signal"])
                ],
                entry_end_min=cfg["entry_end_min"],
                one_per_day=cfg["one_per_day"],
                cross_only=cfg["cross_only"],
            )
            target = None
        row = _run_one(
            cfg, times, mins, keys, open_, high, low, atr, spread, costs, sigs, target
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
    by_fam: dict[str, list[dict]] = {"ny_cash_vwap_bounce_rsi": [], "ny_cash_ema_macd": []}
    for r in ranked:
        fam = r["params"]["family"]
        if len(by_fam[fam]) < 5:
            by_fam[fam].append(r)
    goal_dev = [r for r in rows if r["develop"]["goal_both"]]
    goal_ho = [r for r in ranked[:20] if r["holdout"]["goal_both"]]
    return {
        "search_id": SEARCH_ID,
        "promote": False,
        "live_go": False,
        "holdout_start": str(HOLDOUT_START),
        "start_balance": START_BALANCE,
        "goal_daily_pct": GOAL_DAILY_PCT,
        "goal_monthly_pct": GOAL_MONTHLY_PCT,
        "n_configs": len(grid),
        "n_eligible_develop": len(eligible),
        "n_develop_hit_goal": len(goal_dev),
        "n_top20_holdout_hit_goal": len(goal_ho),
        "elapsed_sec": round(elapsed, 2),
        "costs": asdict(costs),
        "bars": int(len(df)),
        "from": str(df["time_utc"].iloc[0]),
        "to": str(df["time_utc"].iloc[-1]),
        "best_develop": best,
        "top10_develop": ranked[:10],
        "top5_by_family": by_fam,
        "goal_note": (
            "1%/day and 20%/month are scored as median trade-day / median month "
            "on a $10k 1-lot book. Selection never sees holdout or US30."
        ),
    }


def transfer_us30(best_params: dict, costs: CostSpec) -> dict | None:
    csv = _ROOT / "results" / "us_index_data" / "history_US30_M5.csv"
    meta = _ROOT / "results" / "us_index_data" / "symbol_meta_US30.csv"
    if not csv.is_file():
        return None
    # Rebuild the single winning config on US30 after US100 ranking is frozen.
    grid = build_grid()
    match = None
    for cfg in grid:
        if _slim(cfg) == best_params:
            match = cfg
            break
    if match is None:
        return {"error": "best params not in grid"}
    meta_d = parse_meta(meta) if meta.is_file() else {}
    offset = int(float(meta_d.get("server_utc_offset_sec") or 10800))
    df = load_m5_csv(csv, offset)
    times = [to_utc(ts.to_pydatetime()) for ts in df["time_utc"]]
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    open_ = df["open"].to_numpy(float)
    vol = df["tick_volume"].to_numpy(float)
    spread = df["spread"].to_numpy(float)
    mins, keys, dow, ny = _et_arrays(times)
    atr = wilder_atr(high, low, close, ATR_PERIOD)
    _or_h, _or_l, _ready, vwap = _or_and_vwap(
        mins, keys, ny, high, low, close, vol, 15
    )
    cfg = match
    if cfg["family"] == "ny_cash_vwap_bounce_rsi":
        sigs = bounce_signals(
            close,
            mins,
            keys,
            dow,
            ny,
            vwap,
            atr,
            rsi_series(close, cfg["rsi_period"]),
            entry_end_min=cfg["entry_end_min"],
            atr_dev=cfg["atr_dev"],
            rsi_ob=cfg["rsi_ob"],
            rsi_os=cfg["rsi_os"],
            one_per_day=cfg["one_per_day"],
        )
        target = vwap
    else:
        sigs = macd_signals(
            mins,
            keys,
            dow,
            ny,
            ema_series(close, cfg["ema_fast"]),
            ema_series(close, cfg["ema_slow"]),
            macd_series(close, cfg["macd_fast"], cfg["macd_slow"], cfg["macd_signal"])[2],
            entry_end_min=cfg["entry_end_min"],
            one_per_day=cfg["one_per_day"],
            cross_only=cfg["cross_only"],
        )
        target = None
    row = _run_one(
        cfg, times, mins, keys, open_, high, low, atr, spread, costs, sigs, target
    )
    return {
        "symbol": "US30",
        "params": row["params"],
        "develop": row["develop"],
        "holdout": row["holdout"],
        "note": "Transfer check after US100 ranking. Not used for selection.",
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
    ap.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "results" / "us_index_session_playbook_v2.json",
    )
    args = ap.parse_args()
    if not LOCK_PATH.is_file():
        raise SystemExit(f"missing lock {LOCK_PATH}")
    lock = json.loads(LOCK_PATH.read_text())
    if lock.get("holdout_start") != "2026-06-01":
        raise SystemExit("holdout lock mismatch")
    if lock.get("search_id") != SEARCH_ID:
        raise SystemExit("search_id mismatch")
    refuse_mutated_frozen_book(lock)
    grid = build_grid()
    if len(grid) != int(lock["n_configs_expected"]):
        raise SystemExit(f"grid {len(grid)} != lock {lock['n_configs_expected']}")
    meta = parse_meta(args.meta) if args.meta.is_file() else {}
    costs = require_frozen_cost_book(
        costs_from_meta(
            meta,
            lots=1.0,
            slippage_points=10.0,
            commission_per_lot=0.0,
            max_spread_points=200.0,
        )
    )
    report = run_search(args.csv, args.meta, costs)
    best = report["best_develop"]
    if best is not None:
        report["us30_transfer"] = transfer_us30(best["params"], costs)
    else:
        report["us30_transfer"] = None
    write_slim_json(args.out, report)
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
                "us30_transfer": report.get("us30_transfer"),
                "promote": False,
            },
            indent=2,
        )
    )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
