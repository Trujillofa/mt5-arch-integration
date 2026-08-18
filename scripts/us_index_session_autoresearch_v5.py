#!/usr/bin/env python3
"""US100 v5 screen: cash-open gap fade, HTF-locked OR, US30→US100 follow.

Lock: results/us_index_session_v5_lock.json
  select et_date < 2026-06-01
  holdout et_date >= 2026-07-01
  June 2026 is a burned buffer.

Does not retune v1–v4. Does not copy XAU London-FX hours {7,8,9}.
Does not add Timescale / M1 / US500. Costs keep 10 pt slippage/side.
promote / live_go stay no.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time as pytime
from dataclasses import asdict
from datetime import date, time
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
from us_index_session_autoresearch_v4 import split_v4  # noqa: E402
from us_index_session_backtest import (  # noqa: E402
    CostSpec,
    costs_from_meta,
    load_m5_csv,
    parse_meta,
)
from us_index_session_core import (  # noqa: E402
    ATR_PERIOD,
    CASH_START_MIN,
    IB_END_MIN,
    cash_adr_series,
    cash_open_gap_pct,
    completed_daily_donch_state,
    completed_h4_ema_bias,
    prior_cash_close_series,
    to_utc,
    wilder_atr,
)

SEARCH_ID = "us_index_session_v5"
LOCK_PATH = _ROOT / "results" / "us_index_session_v5_lock.json"
SELECT_END = date(2026, 6, 1)
HOLDOUT_START = date(2026, 7, 1)
ENTRY_START = 9 * 60 + 45

GAP_MIN = (0.005, 0.0075)
GAP_MAX = (0.01, 0.02)
ADR_N = (10, 14)
ADR_K = (0.4, 0.6)
GAP_ENTRY = ("next_0930", "after_ib")
GAP_EXITS: tuple[dict, ...] = (
    {"kind": "flatten", "hh": 11, "mm": 30},
    {"kind": "flatten", "hh": 15, "mm": 45},
    {"kind": "atr", "sl": 1.0, "tp": 1.5},
)

LOCK_MODES = ("h4", "donch", "both")
ORB_ENDS = (time(10, 30), time(11, 30))
ORB_EXITS = GAP_EXITS

US30_ATR = (0.0, 0.35)
US30_EXITS = GAP_EXITS


def _exit_label(ex: dict) -> str:
    return exit_name(ex)


def build_grid() -> list[dict]:
    rows: list[dict] = []
    for gmin, gmax, adn, adk, entry, ex in itertools.product(
        GAP_MIN, GAP_MAX, ADR_N, ADR_K, GAP_ENTRY, GAP_EXITS
    ):
        rows.append(
            {
                "family": "ny_cash_gap_fade_adr",
                "gap_min": gmin,
                "gap_max": gmax,
                "adr_n": adn,
                "adr_k": adk,
                "entry": entry,
                "one_per_day": True,
                "exit": _exit_label(ex),
                "exit_spec": ex,
            }
        )
    for mode, end, ex in itertools.product(LOCK_MODES, ORB_ENDS, ORB_EXITS):
        rows.append(
            {
                "family": "htf_lock_orb",
                "lock": mode,
                "entry_end": f"{end.hour:02d}:{end.minute:02d}",
                "entry_end_min": end.hour * 60 + end.minute,
                "one_per_day": True,
                "exit": _exit_label(ex),
                "exit_spec": ex,
            }
        )
    for k, ex in itertools.product(US30_ATR, US30_EXITS):
        rows.append(
            {
                "family": "exog_us30_ny_cash_cosign_us100_follow",
                "min_us30_atr": k,
                "entry_end": "11:30",
                "one_per_day": True,
                "exit": _exit_label(ex),
                "exit_spec": ex,
            }
        )
    return rows


def _slim(cfg: dict) -> dict:
    return {k: cfg[k] for k in cfg if k not in {"exit_spec", "entry_end_min"}}


def _in_window(mins: np.ndarray, dow: np.ndarray, i: int, end_min: int) -> bool:
    m = int(mins[i])
    if int(dow[i]) == 4 and m >= 14 * 60:
        return False
    return ENTRY_START <= m < end_min


def gap_fade_signals(
    close: np.ndarray,
    mins: np.ndarray,
    keys: np.ndarray,
    dow: np.ndarray,
    gap: np.ndarray,
    adr: np.ndarray,
    prior_close: np.ndarray,
    *,
    gap_min: float,
    gap_max: float,
    adr_k: float,
    entry: str,
    one_per_day: bool,
) -> np.ndarray:
    n = len(close)
    out = np.zeros(n, dtype=np.int8)
    fired = -1
    for i in range(n - 1):
        d = int(keys[i])
        if one_per_day and d == fired:
            continue
        if int(dow[i]) == 4 and int(mins[i]) >= 14 * 60:
            continue
        g = float(gap[i])
        pc = float(prior_close[i])
        ad = float(adr[i])
        if not (np.isfinite(g) and np.isfinite(pc) and pc > 0.0):
            continue
        ag = abs(g)
        if ag < gap_min or ag > gap_max:
            continue
        if np.isfinite(ad) and ad > 0.0 and ag * pc < adr_k * ad:
            continue
        if entry == "next_0930":
            if int(mins[i]) < CASH_START_MIN:
                continue
            # first cash bar only
            if i > 0 and int(keys[i - 1]) == d and int(mins[i - 1]) >= CASH_START_MIN:
                continue
        elif entry == "after_ib":
            if int(mins[i]) < IB_END_MIN:
                continue
            if i > 0 and int(keys[i - 1]) == d and int(mins[i - 1]) >= IB_END_MIN:
                continue
            px = float(close[i])
            if g > 0.0 and px <= pc:
                continue
            if g < 0.0 and px >= pc:
                continue
        else:
            continue
        sig = -1 if g > 0.0 else (1 if g < 0.0 else 0)
        if sig == 0:
            continue
        out[i] = sig
        fired = d
    return out


def htf_lock_orb_signals(
    close: np.ndarray,
    mins: np.ndarray,
    keys: np.ndarray,
    dow: np.ndarray,
    or_h: np.ndarray,
    or_l: np.ndarray,
    ready: np.ndarray,
    lock: np.ndarray,
    *,
    entry_end_min: int,
    one_per_day: bool,
) -> np.ndarray:
    n = len(close)
    out = np.zeros(n, dtype=np.int8)
    fired = -1
    for i in range(n - 1):
        if not _in_window(mins, dow, i, entry_end_min):
            continue
        if not ready[i]:
            continue
        if one_per_day and int(keys[i]) == fired:
            continue
        px = float(close[i])
        sig = 1 if px > float(or_h[i]) else (-1 if px < float(or_l[i]) else 0)
        if sig == 0 or int(lock[i]) != sig:
            continue
        out[i] = sig
        fired = int(keys[i])
    return out


def combine_lock(mode: str, h4: np.ndarray, donch: np.ndarray) -> np.ndarray:
    if mode == "h4":
        return h4
    if mode == "donch":
        return donch
    out = np.zeros(len(h4), dtype=np.int8)
    for i in range(len(h4)):
        a, b = int(h4[i]), int(donch[i])
        if a == 0:
            continue
        if b == -a:
            continue
        out[i] = a
    return out


def us30_cosign_signals(
    us30_open: np.ndarray,
    us30_close: np.ndarray,
    us30_atr: np.ndarray,
    mins: np.ndarray,
    keys: np.ndarray,
    dow: np.ndarray,
    *,
    min_atr_k: float,
    one_per_day: bool,
) -> np.ndarray:
    """US30 T* sign only. Traded US100 bar is not read."""
    n = len(us30_close)
    out = np.zeros(n, dtype=np.int8)
    fired = -1
    for i in range(n - 1):
        d = int(keys[i])
        if one_per_day and d == fired:
            continue
        if not _in_window(mins, dow, i, 11 * 60 + 30):
            continue
        if i > 0 and int(keys[i - 1]) == d and int(mins[i - 1]) >= ENTRY_START:
            continue
        move = float(us30_close[i]) - float(us30_open[i])
        if move == 0.0:
            continue
        at = float(us30_atr[i])
        if min_atr_k > 0.0 and (not np.isfinite(at) or abs(move) < min_atr_k * at):
            continue
        out[i] = 1 if move > 0.0 else -1
        fired = d
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
    )
    pre, post = split_v4(trades)
    return {
        "params": _slim(cfg),
        "develop": pack_metrics(pre),
        "holdout": pack_metrics(post),
        "develop_score": score_row(pack_metrics(pre)),
    }


def run_search(
    csv_path: Path,
    meta_path: Path | None,
    csv30: Path,
    meta30: Path | None,
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
    adr = {n: cash_adr_series(mins, keys, high, low, n) for n in ADR_N}
    h4 = completed_h4_ema_bias(times, close)
    donch = completed_daily_donch_state(keys, high, low, close, n=20)
    locks = {mode: combine_lock(mode, h4, donch) for mode in LOCK_MODES}

    meta30d = parse_meta(meta30) if meta30 and meta30.is_file() else {}
    off30 = int(float(meta30d.get("server_utc_offset_sec") or 10800))
    df30 = load_m5_csv(csv30, off30)
    pair = df[["time_utc", "open", "high", "low", "close", "spread"]].merge(
        df30[["time_utc", "open", "high", "low", "close"]],
        on="time_utc",
        suffixes=("_a", "_b"),
    )
    pair = pair.sort_values("time_utc").reset_index(drop=True)
    p_times = [to_utc(ts.to_pydatetime()) for ts in pair["time_utc"]]
    p_mins, p_keys, p_dow, _pny = _et_arrays(p_times)
    p_open = pair["open_a"].to_numpy(float)
    p_high = pair["high_a"].to_numpy(float)
    p_low = pair["low_a"].to_numpy(float)
    p_close = pair["close_a"].to_numpy(float)
    p_spread = pair["spread"].to_numpy(float)
    p_atr = wilder_atr(p_high, p_low, p_close, ATR_PERIOD)
    u30_open = pair["open_b"].to_numpy(float)
    u30_high = pair["high_b"].to_numpy(float)
    u30_low = pair["low_b"].to_numpy(float)
    u30_close = pair["close_b"].to_numpy(float)
    u30_atr = wilder_atr(u30_high, u30_low, u30_close, ATR_PERIOD)

    grid = build_grid()
    rows: list[dict] = []
    t0 = pytime.time()
    for i, cfg in enumerate(grid):
        fam = cfg["family"]
        if fam == "ny_cash_gap_fade_adr":
            sigs = gap_fade_signals(
                close,
                mins,
                keys,
                dow,
                gap,
                adr[cfg["adr_n"]],
                prior_c,
                gap_min=cfg["gap_min"],
                gap_max=cfg["gap_max"],
                adr_k=cfg["adr_k"],
                entry=cfg["entry"],
                one_per_day=cfg["one_per_day"],
            )
            row = _run(
                cfg, times, mins, keys, open_, high, low, atr14, spread, costs, sigs
            )
        elif fam == "htf_lock_orb":
            sigs = htf_lock_orb_signals(
                close,
                mins,
                keys,
                dow,
                or_h,
                or_l,
                ready,
                locks[cfg["lock"]],
                entry_end_min=cfg["entry_end_min"],
                one_per_day=cfg["one_per_day"],
            )
            row = _run(
                cfg, times, mins, keys, open_, high, low, atr14, spread, costs, sigs
            )
        else:
            sigs = us30_cosign_signals(
                u30_open,
                u30_close,
                u30_atr,
                p_mins,
                p_keys,
                p_dow,
                min_atr_k=cfg["min_us30_atr"],
                one_per_day=cfg["one_per_day"],
            )
            row = _run(
                cfg,
                p_times,
                p_mins,
                p_keys,
                p_open,
                p_high,
                p_low,
                p_atr,
                p_spread,
                costs,
                sigs,
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
    for r in ranked:
        fam = r["params"]["family"]
        if fam not in by_fam:
            by_fam[fam] = r
    return {
        "search_id": SEARCH_ID,
        "promote": False,
        "live_go": False,
        "selection_end": str(SELECT_END),
        "holdout_start": str(HOLDOUT_START),
        "start_balance": START_BALANCE,
        "goal_daily_pct": GOAL_DAILY_PCT,
        "goal_monthly_pct": GOAL_MONTHLY_PCT,
        "n_configs": len(rows),
        "n_eligible_develop": len(eligible),
        "n_develop_hit_goal": n_hit,
        "n_top20_holdout_hit_goal": n_ho,
        "elapsed_sec": round(elapsed, 2),
        "costs": asdict(costs),
        "bars": int(len(df)),
        "from": str(df["time_utc"].iloc[0]) if len(df) else "",
        "to": str(df["time_utc"].iloc[-1]) if len(df) else "",
        "best_develop": best,
        "best_by_family": by_fam,
        "top20": top20,
        "note": (
            "New search. Gap is vs prior cash close. HTF uses completed H4/Daily only. "
            "US30 cosign isolates US100 T*. promote=no."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=_ROOT / "results" / "us_index_data" / "history_US100_M5.csv")
    ap.add_argument("--meta", type=Path, default=_ROOT / "results" / "us_index_data" / "symbol_meta_US100.csv")
    ap.add_argument("--csv30", type=Path, default=_ROOT / "results" / "us_index_data" / "history_US30_M5.csv")
    ap.add_argument("--meta30", type=Path, default=_ROOT / "results" / "us_index_data" / "symbol_meta_US30.csv")
    ap.add_argument("--out", type=Path, default=_ROOT / "results" / "us_index_session_v5.json")
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
    report = run_search(args.csv, args.meta, args.csv30, args.meta30, costs)
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
