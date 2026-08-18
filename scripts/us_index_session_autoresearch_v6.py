#!/usr/bin/env python3
"""US100 v6 screen: daily Hurst/ADX/ATR regime switch + London XAU risk gate.

Lock: results/us_index_session_v6_lock.json
  select et_date < 2026-06-01
  holdout et_date >= 2026-07-01
  June 2026 is a burned buffer. July–August is cleaner, not virgin.

Does not retune v1–v5. Does not use US30. Does not stamp hours {7,8,9}.
Does not naive-join Vantage H1. Costs keep 10 pt slippage/side.
promote / live_go stay no. Python-only — stay off the overlay.
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
import pandas as pd

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
from us_index_session_autoresearch_v4 import split_v4  # noqa: E402
from us_index_session_backtest import (  # noqa: E402
    CostSpec,
    costs_from_meta,
    load_m5_csv,
    parse_meta,
    read_mt5_hc_m5,
)
from us_index_session_core import (  # noqa: E402
    ATR_PERIOD,
    CASH_START_MIN,
    LONDON_FEATURE_END_MIN,
    REGIME_MOM,
    REGIME_MR,
    cash_open_gap_pct,
    causal_session_vwap_prev,
    completed_daily_regime_state,
    ema_series,
    london_et_displacement,
    london_feature_on_m5,
    prior_cash_close_series,
    to_utc,
    wilder_atr,
)

SEARCH_ID = "us_index_session_v6"
LOCK_PATH = _ROOT / "results" / "us_index_session_v6_lock.json"
SELECT_END = date(2026, 6, 1)
HOLDOUT_START = date(2026, 7, 1)
ENTRY_START = 9 * 60 + 45
ENTRY_END_MIN = 11 * 60 + 30
MR_GAP_MAX = 0.02

ATR_N = (20, 50)
HURST_LB = (32, 64)
MOM_TRAILS: tuple[dict, ...] = (
    {"kind": "trail", "trail": "swing", "k": 6, "sl": 1.0, "hh": 15, "mm": 45},
    {"kind": "trail", "trail": "swing", "k": 12, "sl": 1.0, "hh": 15, "mm": 45},
    {"kind": "trail", "trail": "ema", "ema": 9, "sl": 1.0, "hh": 15, "mm": 45},
    {"kind": "trail", "trail": "ema", "ema": 21, "sl": 1.0, "hh": 15, "mm": 45},
)
MR_GAP_MIN = (0.005, 0.0075)
MR_TARGET = ("prior_cash_close", "vwap")
MR_SL = (0.75, 1.0)
XAU_MIN_ATR = (0.5, 1.0)

DEFAULT_XAU_H1 = Path.home() / (
    ".mt5-fpmarkets/drive_c/Program Files/FP Markets MT5 Terminal/"
    "Bases/FPMarketsSC-Live/history/XAUUSD.r/cache/H1.hc"
)


def trail_name(ex: dict) -> str:
    return exit_name(ex)


def build_grid() -> list[dict]:
    rows: list[dict] = []
    for an, hl, trail, gmin, tgt, sl in itertools.product(
        ATR_N, HURST_LB, MOM_TRAILS, MR_GAP_MIN, MR_TARGET, MR_SL
    ):
        rows.append(
            {
                "family": "daily_regime_switch",
                "atr_n": an,
                "hurst_lb": hl,
                "mom_trail": trail_name(trail),
                "mom_exit_spec": trail,
                "gap_min": gmin,
                "gap_max": MR_GAP_MAX,
                "mr_target": tgt,
                "mr_sl": sl,
                "mr_exit_spec": {
                    "kind": "vwap",
                    "sl": sl,
                    "hh": 11,
                    "mm": 30,
                    "running": tgt == "vwap",
                },
                "one_per_day": True,
            }
        )
    for k, trail in itertools.product(XAU_MIN_ATR, MOM_TRAILS):
        rows.append(
            {
                "family": "london_xau_fx_risk_gate",
                "min_disp_atr": k,
                "trail": trail_name(trail),
                "exit_spec": trail,
                "one_per_day": True,
            }
        )
    return rows


def _slim(cfg: dict) -> dict:
    skip = {"mom_exit_spec", "mr_exit_spec", "exit_spec"}
    return {k: cfg[k] for k in cfg if k not in skip}


def _friday_blocked(dow: np.ndarray, mins: np.ndarray, i: int) -> bool:
    return int(dow[i]) == 4 and int(mins[i]) >= 14 * 60


def mom_or_signals(
    close: np.ndarray,
    mins: np.ndarray,
    keys: np.ndarray,
    dow: np.ndarray,
    or_h: np.ndarray,
    or_l: np.ndarray,
    ready: np.ndarray,
    allow: np.ndarray,
    *,
    one_per_day: bool,
    entry_end_min: int = ENTRY_END_MIN,
) -> np.ndarray:
    n = len(close)
    out = np.zeros(n, dtype=np.int8)
    fired = -1
    for i in range(n - 1):
        if not allow[i]:
            continue
        if _friday_blocked(dow, mins, i):
            continue
        m = int(mins[i])
        if m < ENTRY_START or m >= entry_end_min:
            continue
        if not ready[i]:
            continue
        if one_per_day and int(keys[i]) == fired:
            continue
        px = float(close[i])
        sig = 1 if px > float(or_h[i]) else (-1 if px < float(or_l[i]) else 0)
        if sig == 0:
            continue
        out[i] = sig
        fired = int(keys[i])
    return out


def mr_gap_signals(
    mins: np.ndarray,
    keys: np.ndarray,
    dow: np.ndarray,
    gap: np.ndarray,
    prior_close: np.ndarray,
    allow: np.ndarray,
    *,
    gap_min: float,
    gap_max: float,
    one_per_day: bool,
) -> np.ndarray:
    n = len(gap)
    out = np.zeros(n, dtype=np.int8)
    fired = -1
    for i in range(n - 1):
        if not allow[i]:
            continue
        if _friday_blocked(dow, mins, i):
            continue
        d = int(keys[i])
        if one_per_day and d == fired:
            continue
        if int(mins[i]) < CASH_START_MIN:
            continue
        if i > 0 and int(keys[i - 1]) == d and int(mins[i - 1]) >= CASH_START_MIN:
            continue
        g = float(gap[i])
        pc = float(prior_close[i])
        if not (np.isfinite(g) and np.isfinite(pc) and pc > 0.0):
            continue
        ag = abs(g)
        if ag < gap_min or ag > gap_max:
            continue
        sig = -1 if g > 0.0 else (1 if g < 0.0 else 0)
        if sig == 0:
            continue
        out[i] = sig
        fired = d
    return out


def london_gated_or_signals(
    close: np.ndarray,
    mins: np.ndarray,
    keys: np.ndarray,
    dow: np.ndarray,
    or_h: np.ndarray,
    or_l: np.ndarray,
    ready: np.ndarray,
    xau_sign: np.ndarray,
    xau_disp: np.ndarray,
    xau_atr: np.ndarray,
    *,
    min_disp_atr: float,
    one_per_day: bool,
) -> np.ndarray:
    n = len(close)
    out = np.zeros(n, dtype=np.int8)
    fired = -1
    for i in range(n - 1):
        if _friday_blocked(dow, mins, i):
            continue
        m = int(mins[i])
        if m < ENTRY_START or m >= ENTRY_END_MIN:
            continue
        if int(mins[i]) < LONDON_FEATURE_END_MIN:
            continue
        if not ready[i]:
            continue
        if one_per_day and int(keys[i]) == fired:
            continue
        xs = float(xau_sign[i])
        xd = float(xau_disp[i])
        xa = float(xau_atr[i])
        if not (np.isfinite(xs) and xs != 0.0 and np.isfinite(xd) and np.isfinite(xa)):
            continue
        if xa <= 0.0 or abs(xd) < min_disp_atr * xa:
            continue
        px = float(close[i])
        sig = 1 if px > float(or_h[i]) else (-1 if px < float(or_l[i]) else 0)
        if sig == 0 or int(xs) != sig:
            continue
        out[i] = sig
        fired = int(keys[i])
    return out


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
    *,
    target: np.ndarray | None = None,
    ema: np.ndarray | None = None,
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
        ema=ema,
    )
    pre, post = split_v4(trades)
    return {
        "params": _slim(cfg),
        "develop": pack_metrics(pre),
        "holdout": pack_metrics(post),
        "develop_score": score_row(pack_metrics(pre)),
    }


def load_h1_hc(path: Path, server_utc_offset_sec: int) -> pd.DataFrame:
    df = read_mt5_hc_m5(path)
    server = pd.to_datetime(df["server_epoch"], unit="s", utc=True)
    utc = server - pd.to_timedelta(int(server_utc_offset_sec), unit="s")
    out = df.copy()
    out["time_utc"] = utc
    return out.sort_values("time_utc").reset_index(drop=True)


def run_search(
    csv_path: Path,
    meta_path: Path | None,
    xau_h1_path: Path,
    costs: CostSpec,
) -> dict:
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
    or_h, or_l, ready, _vwap = _or_and_vwap(mins, keys, ny, high, low, close, vol, 15)
    prior_c = prior_cash_close_series(mins, keys, close)
    gap = cash_open_gap_pct(mins, keys, open_, prior_c)
    vwap_prev = causal_session_vwap_prev(mins, keys, ny, high, low, close, vol)
    ema9 = ema_series(close, 9)
    ema21 = ema_series(close, 21)
    regime_cache: dict[tuple[int, int], np.ndarray] = {}
    for an, hl in itertools.product(ATR_N, HURST_LB):
        st, _hu, _ad = completed_daily_regime_state(
            keys, open_, high, low, close, atr_n=an, hurst_lb=hl
        )
        regime_cache[(an, hl)] = st

    if not xau_h1_path.is_file():
        raise FileNotFoundError(f"FP XAUUSD.r H1 cache missing: {xau_h1_path}")
    xau = load_h1_hc(xau_h1_path, offset)
    x_times = [to_utc(ts.to_pydatetime()) for ts in xau["time_utc"]]
    feat = london_et_displacement(
        x_times,
        xau["open"].to_numpy(float),
        xau["high"].to_numpy(float),
        xau["low"].to_numpy(float),
        xau["close"].to_numpy(float),
    )
    x_sign = london_feature_on_m5(keys, mins, feat, "sign")
    x_disp = london_feature_on_m5(keys, mins, feat, "disp")
    x_atr = london_feature_on_m5(keys, mins, feat, "atr")

    grid = build_grid()
    rows: list[dict] = []
    t0 = pytime.time()
    for i, cfg in enumerate(grid):
        fam = cfg["family"]
        if fam == "daily_regime_switch":
            st = regime_cache[(cfg["atr_n"], cfg["hurst_lb"])]
            mom_allow = st == REGIME_MOM
            mr_allow = st == REGIME_MR
            mom_sigs = mom_or_signals(
                close,
                mins,
                keys,
                dow,
                or_h,
                or_l,
                ready,
                mom_allow,
                one_per_day=cfg["one_per_day"],
            )
            mr_sigs = mr_gap_signals(
                mins,
                keys,
                dow,
                gap,
                prior_c,
                mr_allow,
                gap_min=cfg["gap_min"],
                gap_max=cfg["gap_max"],
                one_per_day=cfg["one_per_day"],
            )
            mom_ema = ema9 if cfg["mom_exit_spec"].get("ema") == 9 else ema21
            mr_tgt = vwap_prev if cfg["mr_target"] == "vwap" else prior_c
            mom_trades = simulate_exits(
                times,
                mins,
                keys,
                open_,
                high,
                low,
                atr14,
                spread,
                mom_sigs,
                costs,
                cfg["mom_exit_spec"],
                ema=mom_ema,
            )
            mr_trades = simulate_exits(
                times,
                mins,
                keys,
                open_,
                high,
                low,
                atr14,
                spread,
                mr_sigs,
                costs,
                cfg["mr_exit_spec"],
                target=mr_tgt,
            )
            combined = sorted(
                mom_trades + mr_trades, key=lambda t: (t.et_date, t.fill_time)
            )
            pre, post = split_v4(combined)
            row = {
                "params": _slim(cfg),
                "develop": pack_metrics(pre),
                "holdout": pack_metrics(post),
                "develop_score": score_row(pack_metrics(pre)),
                "mom_develop_trades": pack_metrics(split_v4(mom_trades)[0])["trades"],
                "mr_develop_trades": pack_metrics(split_v4(mr_trades)[0])["trades"],
            }
        else:
            sigs = london_gated_or_signals(
                close,
                mins,
                keys,
                dow,
                or_h,
                or_l,
                ready,
                x_sign,
                x_disp,
                x_atr,
                min_disp_atr=cfg["min_disp_atr"],
                one_per_day=cfg["one_per_day"],
            )
            ema = ema9 if cfg["exit_spec"].get("ema") == 9 else ema21
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
                ema=ema,
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
        "xau_h1_bars": int(len(xau)),
        "london_feature_days": len(feat),
        "best_develop": best,
        "best_by_family": by_fam,
        "top20": top20,
        "note": (
            "New search. Daily regime uses completed ET-days only. "
            "London gate is FP XAUUSD.r H1, ET 07:00–09:00, not hours {7,8,9}. "
            "EUR/GBP skipped (stale cache / Vantage clock). promote=no."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=_ROOT / "results" / "us_index_data" / "history_US100_M5.csv")
    ap.add_argument("--meta", type=Path, default=_ROOT / "results" / "us_index_data" / "symbol_meta_US100.csv")
    ap.add_argument("--xau-h1", type=Path, default=DEFAULT_XAU_H1)
    ap.add_argument("--out", type=Path, default=_ROOT / "results" / "us_index_session_v6.json")
    args = ap.parse_args()
    lock = json.loads(LOCK_PATH.read_text())
    if lock.get("search_id") != SEARCH_ID:
        raise SystemExit("search_id mismatch")
    if lock.get("selection_end") != "2026-06-01" or lock.get("holdout_start") != "2026-07-01":
        raise SystemExit("holdout/selection lock mismatch")
    grid = build_grid()
    if len(grid) != int(lock["n_configs_expected"]):
        raise SystemExit(f"grid {len(grid)} != lock {lock['n_configs_expected']}")
    meta = parse_meta(args.meta) if args.meta.is_file() else {}
    costs = costs_from_meta(
        meta, lots=1.0, slippage_points=10.0, commission_per_lot=0.0, max_spread_points=200.0
    )
    report = run_search(args.csv, args.meta, args.xau_h1, costs)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
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
