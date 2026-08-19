#!/usr/bin/env python3
"""US100 structure screen: sweep / FVG / US100-US30 divergence (new search).

Lock: results/us_index_session_structure_v3_lock.json
  holdout_start = 2026-06-01  — NEVER used for selection
  macro_news_fix_api is skipped in the lock (no joinable calendar).

Not a retune of orb / develop_v1 / playbook_v2.
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
    fvg_at,
    pre_ny_liquidity_levels,
    to_utc,
    wick_parts,
    wilder_atr,
)

SEARCH_ID = "us_index_session_structure_v3"
LOCK_PATH = _ROOT / "results" / "us_index_session_structure_v3_lock.json"
SWEEP_START = 9 * 60 + 45
FVG_START = 9 * 60 + 35
DIV_START = 9 * 60 + 35

LEVEL_SETS = (
    ("asia_london", True, True, False, False),
    ("pdh_or", False, False, True, True),
    ("all_four", True, True, True, True),
)
WICK_FRACS = (0.25, 0.40)
SWEEP_ENDS = (time(10, 30), time(11, 0))
ONE_PER_DAY = (True, False)
SWEEP_EXITS: tuple[dict, ...] = (
    {"kind": "vwap", "sl": 1.0, "tag": "box_opposite"},
    {"kind": "vwap", "sl": 1.0, "tag": "range_1.5x"},
    {"kind": "flatten", "hh": 11, "mm": 30},
    {"kind": "atr", "sl": 1.0, "tp": 1.5},
)

GAP_ATRS = (0.15, 0.25, 0.40)
FVG_ENDS = (time(11, 30), time(12, 0))
FVG_EXITS: tuple[dict, ...] = (
    {"kind": "flatten", "hh": 11, "mm": 30},
    {"kind": "flatten", "hh": 15, "mm": 45},
    {"kind": "atr", "sl": 1.0, "tp": 1.5},
    {"kind": "vwap", "sl": 1.0, "tag": "ce_swing"},
)

LOOKBACKS = (3, 6, 12)
DIV_ENDS = (time(10, 30), time(11, 30))
LEGS = ("pair", "us100_only")
DIV_EXITS: tuple[dict, ...] = (
    {"kind": "flatten", "hh": 11, "mm": 30},
    {"kind": "flatten", "hh": 12, "mm": 0},
    {"kind": "atr", "sl": 1.0, "tp": 1.5},
    {"kind": "bars", "n": 6},
)


def _exit_label(ex: dict) -> str:
    tag = ex.get("tag")
    if tag:
        return str(tag)
    return exit_name(ex)


def build_grid() -> list[dict]:
    rows: list[dict] = []
    for (lname, *flags), wick, end, opd, ex in itertools.product(
        LEVEL_SETS, WICK_FRACS, SWEEP_ENDS, ONE_PER_DAY, SWEEP_EXITS
    ):
        rows.append(
            {
                "family": "ny_cash_liquidity_sweep",
                "level_set": lname,
                "use_asia": flags[0],
                "use_london": flags[1],
                "use_pdh": flags[2],
                "use_or": flags[3],
                "wick_frac": wick,
                "entry_end": f"{end.hour:02d}:{end.minute:02d}",
                "entry_end_min": end.hour * 60 + end.minute,
                "one_per_day": opd,
                "exit": _exit_label(ex),
                "exit_spec": ex,
            }
        )
    for gap, end, opd, ex in itertools.product(GAP_ATRS, FVG_ENDS, ONE_PER_DAY, FVG_EXITS):
        rows.append(
            {
                "family": "ny_cash_fvg_mitigation",
                "min_gap_atr": gap,
                "entry_end": f"{end.hour:02d}:{end.minute:02d}",
                "entry_end_min": end.hour * 60 + end.minute,
                "one_per_day": opd,
                "exit": _exit_label(ex),
                "exit_spec": ex,
            }
        )
    for lb, end, opd, legs, ex in itertools.product(
        LOOKBACKS, DIV_ENDS, ONE_PER_DAY, LEGS, DIV_EXITS
    ):
        rows.append(
            {
                "family": "us100_us30_divergence",
                "lookback": lb,
                "entry_end": f"{end.hour:02d}:{end.minute:02d}",
                "entry_end_min": end.hour * 60 + end.minute,
                "one_per_day": opd,
                "legs": legs,
                "exit": _exit_label(ex),
                "exit_spec": ex,
            }
        )
    return rows


def _slim(cfg: dict) -> dict:
    skip = {
        "exit_spec",
        "entry_end_min",
        "use_asia",
        "use_london",
        "use_pdh",
        "use_or",
    }
    return {k: cfg[k] for k in cfg if k not in skip}


def sweep_signals(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    mins: np.ndarray,
    keys: np.ndarray,
    dow: np.ndarray,
    asia_h: np.ndarray,
    asia_l: np.ndarray,
    lon_h: np.ndarray,
    lon_l: np.ndarray,
    pdh: np.ndarray,
    pdl: np.ndarray,
    or_h: np.ndarray,
    or_l: np.ndarray,
    or_ready: np.ndarray,
    *,
    use_asia: bool,
    use_london: bool,
    use_pdh: bool,
    use_or: bool,
    wick_frac: float,
    entry_end_min: int,
    one_per_day: bool,
    exit_tag: str,
) -> tuple[np.ndarray, np.ndarray]:
    n = len(close)
    out = np.zeros(n, dtype=np.int8)
    target = np.full(n, np.nan)
    fired = -1
    for i in range(n - 1):
        m = int(mins[i])
        if int(dow[i]) == 4 and m >= 14 * 60:
            continue
        if m < SWEEP_START or m >= entry_end_min:
            continue
        if one_per_day and int(keys[i]) == fired:
            continue
        upper, lower, rng = wick_parts(float(open_[i]), float(high[i]), float(low[i]), float(close[i]))
        if rng <= 0.0:
            continue
        boxes: list[tuple[float, float]] = []
        if use_asia and np.isfinite(asia_h[i]) and np.isfinite(asia_l[i]):
            boxes.append((float(asia_h[i]), float(asia_l[i])))
        if use_london and np.isfinite(lon_h[i]) and np.isfinite(lon_l[i]):
            boxes.append((float(lon_h[i]), float(lon_l[i])))
        if use_pdh and np.isfinite(pdh[i]) and np.isfinite(pdl[i]):
            boxes.append((float(pdh[i]), float(pdl[i])))
        if use_or and or_ready[i] and np.isfinite(or_h[i]) and np.isfinite(or_l[i]):
            boxes.append((float(or_h[i]), float(or_l[i])))
        sig = 0
        tgt = float("nan")
        px = float(close[i])
        for bh, bl in boxes:
            width = bh - bl
            if width <= 0.0:
                continue
            if high[i] > bh and close[i] < bh and (upper / rng) >= wick_frac:
                sig = -1
                tgt = bl if exit_tag == "box_opposite" else px - 1.5 * width
                break
            if low[i] < bl and close[i] > bl and (lower / rng) >= wick_frac:
                sig = 1
                tgt = bh if exit_tag == "box_opposite" else px + 1.5 * width
                break
        if sig == 0:
            continue
        out[i] = sig
        target[i] = tgt
        fired = int(keys[i])
    return out, target


def fvg_signals(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    mins: np.ndarray,
    keys: np.ndarray,
    dow: np.ndarray,
    atr: np.ndarray,
    *,
    min_gap_atr: float,
    entry_end_min: int,
    one_per_day: bool,
) -> tuple[np.ndarray, np.ndarray]:
    n = len(close)
    out = np.zeros(n, dtype=np.int8)
    target = np.full(n, np.nan)
    pending: list[tuple[int, int, float, float, float, float]] = []
    fired = -1
    last_day = -1
    swing_h = np.full(n, np.nan)
    swing_l = np.full(n, np.nan)
    for i in range(n):
        if i >= 6:
            swing_h[i] = float(np.max(high[i - 6 : i]))
            swing_l[i] = float(np.min(low[i - 6 : i]))
        day = int(keys[i])
        if day != last_day:
            pending = []
            last_day = day
        m = int(mins[i])
        if int(dow[i]) == 4 and m >= 14 * 60:
            continue
        if i >= 2 and FVG_START <= m < 16 * 60:
            gap = fvg_at(high, low, i)
            if gap is not None:
                side, top, bot, ce = gap
                at = float(atr[i])
                if at > 0.0 and (top - bot) >= min_gap_atr * at:
                    pending.append((i, side, top, bot, ce, float(swing_h[i] if side > 0 else swing_l[i])))
        if m < FVG_START or m >= entry_end_min:
            continue
        if one_per_day and day == fired:
            continue
        nxt: list[tuple[int, int, float, float, float, float]] = []
        took = False
        for created, side, top, bot, ce, swing in pending:
            if created >= i:
                nxt.append((created, side, top, bot, ce, swing))
                continue
            hit = False
            if not took and side > 0 and low[i] <= ce and close[i] > ce:
                out[i] = 1
                target[i] = swing if np.isfinite(swing) else top
                hit = True
            elif not took and side < 0 and high[i] >= ce and close[i] < ce:
                out[i] = -1
                target[i] = swing if np.isfinite(swing) else bot
                hit = True
            if hit:
                took = True
                fired = day
                continue
            nxt.append((created, side, top, bot, ce, swing))
        pending = [] if (took and one_per_day) else nxt
    return out, target


def div_signals(
    high_a: np.ndarray,
    low_a: np.ndarray,
    high_b: np.ndarray,
    low_b: np.ndarray,
    mins: np.ndarray,
    keys: np.ndarray,
    dow: np.ndarray,
    *,
    lookback: int,
    entry_end_min: int,
    one_per_day: bool,
) -> np.ndarray:
    n = len(high_a)
    out = np.zeros(n, dtype=np.int8)
    fired = -1
    for i in range(lookback, n - 1):
        m = int(mins[i])
        if int(dow[i]) == 4 and m >= 14 * 60:
            continue
        if m < DIV_START or m >= entry_end_min:
            continue
        if one_per_day and int(keys[i]) == fired:
            continue
        prev_h_a = float(np.max(high_a[i - lookback : i]))
        prev_h_b = float(np.max(high_b[i - lookback : i]))
        prev_l_a = float(np.min(low_a[i - lookback : i]))
        prev_l_b = float(np.min(low_b[i - lookback : i]))
        hh_a = float(high_a[i]) > prev_h_a
        hh_b = float(high_b[i]) > prev_h_b
        ll_a = float(low_a[i]) < prev_l_a
        ll_b = float(low_b[i]) < prev_l_b
        sig = 0
        if hh_a and not hh_b:
            sig = -1
        elif ll_a and not ll_b:
            sig = 1
        if sig == 0:
            continue
        out[i] = sig
        fired = int(keys[i])
    return out


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


def _load_frame(csv_path: Path, meta_path: Path | None) -> tuple[object, dict]:
    meta = parse_meta(meta_path) if meta_path and meta_path.is_file() else {}
    offset = int(float(meta.get("server_utc_offset_sec") or 10800))
    return load_m5_csv(csv_path, offset), meta


def run_search(
    csv100: Path,
    meta100: Path | None,
    csv30: Path,
    meta30: Path | None,
    costs100: CostSpec,
    costs30: CostSpec,
) -> dict:
    df100, _ = _load_frame(csv100, meta100)
    df30, _ = _load_frame(csv30, meta30)
    times = [to_utc(ts.to_pydatetime()) for ts in df100["time_utc"]]
    high = df100["high"].to_numpy(float)
    low = df100["low"].to_numpy(float)
    close = df100["close"].to_numpy(float)
    open_ = df100["open"].to_numpy(float)
    vol = df100["tick_volume"].to_numpy(float)
    spread = df100["spread"].to_numpy(float)
    mins, keys, dow, ny = _et_arrays(times)
    atr = wilder_atr(high, low, close, ATR_PERIOD)
    or_h, or_l, ready, _vwap = _or_and_vwap(mins, keys, ny, high, low, close, vol, 15)
    asia_h, asia_l, lon_h, lon_l, pdh, pdl = pre_ny_liquidity_levels(times, high, low, keys)

    pair = df100[["time_utc", "open", "high", "low", "close", "spread"]].merge(
        df30[["time_utc", "open", "high", "low", "close", "spread"]],
        on="time_utc",
        suffixes=("_a", "_b"),
    )
    pair = pair.sort_values("time_utc").reset_index(drop=True)
    p_times = [to_utc(ts.to_pydatetime()) for ts in pair["time_utc"]]
    p_mins, p_keys, p_dow, _pny = _et_arrays(p_times)
    p_atr = wilder_atr(pair["high_a"].to_numpy(float), pair["low_a"].to_numpy(float), pair["close_a"].to_numpy(float), ATR_PERIOD)

    grid = build_grid()
    rows: list[dict] = []
    t0 = pytime.time()
    for i, cfg in enumerate(grid):
        fam = cfg["family"]
        if fam == "ny_cash_liquidity_sweep":
            sigs, tgt = sweep_signals(
                open_,
                high,
                low,
                close,
                mins,
                keys,
                dow,
                asia_h,
                asia_l,
                lon_h,
                lon_l,
                pdh,
                pdl,
                or_h,
                or_l,
                ready,
                use_asia=cfg["use_asia"],
                use_london=cfg["use_london"],
                use_pdh=cfg["use_pdh"],
                use_or=cfg["use_or"],
                wick_frac=cfg["wick_frac"],
                entry_end_min=cfg["entry_end_min"],
                one_per_day=cfg["one_per_day"],
                exit_tag=cfg["exit"],
            )
            row = _run_one(
                cfg, times, mins, keys, open_, high, low, atr, spread, costs100, sigs, tgt
            )
        elif fam == "ny_cash_fvg_mitigation":
            sigs, tgt = fvg_signals(
                high,
                low,
                close,
                mins,
                keys,
                dow,
                atr,
                min_gap_atr=cfg["min_gap_atr"],
                entry_end_min=cfg["entry_end_min"],
                one_per_day=cfg["one_per_day"],
            )
            row = _run_one(
                cfg, times, mins, keys, open_, high, low, atr, spread, costs100, sigs, tgt
            )
        else:
            div = div_signals(
                pair["high_a"].to_numpy(float),
                pair["low_a"].to_numpy(float),
                pair["high_b"].to_numpy(float),
                pair["low_b"].to_numpy(float),
                p_mins,
                p_keys,
                p_dow,
                lookback=cfg["lookback"],
                entry_end_min=cfg["entry_end_min"],
                one_per_day=cfg["one_per_day"],
            )
            if cfg["legs"] == "pair":
                trades_a = simulate_exits(
                    p_times,
                    p_mins,
                    p_keys,
                    pair["open_a"].to_numpy(float),
                    pair["high_a"].to_numpy(float),
                    pair["low_a"].to_numpy(float),
                    p_atr,
                    pair["spread_a"].to_numpy(float),
                    div,
                    costs100,
                    cfg["exit_spec"],
                )
                trades_b = simulate_exits(
                    p_times,
                    p_mins,
                    p_keys,
                    pair["open_b"].to_numpy(float),
                    pair["high_b"].to_numpy(float),
                    pair["low_b"].to_numpy(float),
                    p_atr,
                    pair["spread_b"].to_numpy(float),
                    -div,
                    costs30,
                    cfg["exit_spec"],
                )
                pre_t, post_t = split_by_holdout(trades_a + trades_b)
                row = {
                    "params": _slim(cfg),
                    "develop": pack_metrics(pre_t),
                    "holdout": pack_metrics(post_t),
                    "develop_score": score_row(pack_metrics(pre_t)),
                }
            else:
                row = _run_one(
                    cfg,
                    p_times,
                    p_mins,
                    p_keys,
                    pair["open_a"].to_numpy(float),
                    pair["high_a"].to_numpy(float),
                    pair["low_a"].to_numpy(float),
                    p_atr,
                    pair["spread_a"].to_numpy(float),
                    costs100,
                    div,
                    None,
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
    by_fam = {
        "ny_cash_liquidity_sweep": [],
        "ny_cash_fvg_mitigation": [],
        "us100_us30_divergence": [],
    }
    for r in ranked:
        fam = r["params"]["family"]
        if len(by_fam[fam]) < 5:
            by_fam[fam].append(r)
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
        "n_develop_hit_goal": sum(1 for r in rows if r["develop"]["goal_both"]),
        "n_top20_holdout_hit_goal": sum(1 for r in ranked[:20] if r["holdout"]["goal_both"]),
        "elapsed_sec": round(elapsed, 2),
        "costs": asdict(costs100),
        "bars": int(len(df100)),
        "pair_bars": int(len(pair)),
        "from": str(df100["time_utc"].iloc[0]),
        "to": str(df100["time_utc"].iloc[-1]),
        "best_develop": ranked[0] if ranked else None,
        "top10_develop": ranked[:10],
        "top5_by_family": by_fam,
        "news_family": "skipped",
        "goal_note": (
            "1%/day and 20%/month are median trade-day / median month on $10k 1-lot. "
            "Selection never sees holdout, US30 transfer, or news."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=_ROOT / "results" / "us_index_data" / "history_US100_M5.csv")
    ap.add_argument("--meta", type=Path, default=_ROOT / "results" / "us_index_data" / "symbol_meta_US100.csv")
    ap.add_argument("--csv30", type=Path, default=_ROOT / "results" / "us_index_data" / "history_US30_M5.csv")
    ap.add_argument("--meta30", type=Path, default=_ROOT / "results" / "us_index_data" / "symbol_meta_US30.csv")
    ap.add_argument("--out", type=Path, default=_ROOT / "results" / "us_index_session_structure_v3.json")
    args = ap.parse_args()
    if not LOCK_PATH.is_file():
        raise SystemExit(f"missing lock {LOCK_PATH}")
    lock = json.loads(LOCK_PATH.read_text())
    if lock.get("holdout_start") != "2026-06-01" or lock.get("search_id") != SEARCH_ID:
        raise SystemExit("lock mismatch")
    refuse_mutated_frozen_book(lock)
    grid = build_grid()
    if len(grid) != int(lock["n_configs_expected"]):
        raise SystemExit(f"grid {len(grid)} != lock {lock['n_configs_expected']}")
    meta = parse_meta(args.meta) if args.meta.is_file() else {}
    costs100 = require_frozen_cost_book(
        costs_from_meta(meta, lots=1.0, slippage_points=10.0, commission_per_lot=0.0, max_spread_points=200.0)
    )
    costs30 = require_frozen_cost_book(
        costs_from_meta(meta, lots=1.0, slippage_points=10.0, commission_per_lot=0.0, max_spread_points=400.0)
    )
    report = run_search(args.csv, args.meta, args.csv30, args.meta30, costs100, costs30)
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
                "news_family": "skipped",
                "promote": False,
            },
            indent=2,
        )
    )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
