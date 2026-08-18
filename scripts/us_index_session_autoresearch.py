#!/usr/bin/env python3
"""US100 session-scalp develop screen (new search, not a retune).

Lock: results/us_index_session_develop_lock.json
  holdout_start = 2026-06-01  — NEVER used for selection
  goals: 1% daily / 20% monthly on a $10k / 1-lot book (costed)

Selection is develop-only. Holdout is scored after the ranking is frozen.
promote / live_go stay no unless a later human AUTHORIZE says otherwise.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time as pytime
from collections import defaultdict
from dataclasses import asdict
from datetime import time
from pathlib import Path

import numpy as np

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from us_index_session_backtest import (  # noqa: E402
    HOLDOUT_START,
    CostSpec,
    Trade,
    _round_trip_cost,
    costs_from_meta,
    load_m5_csv,
    metrics_from_trades,
    parse_meta,
    split_by_holdout,
)
from us_index_session_core import (  # noqa: E402
    ATR_PERIOD,
    ema_series,
    is_ny_cash,
    to_et,
    to_utc,
    wilder_atr,
)

SEARCH_ID = "us_index_session_develop_v1"
LOCK_PATH = _ROOT / "results" / "us_index_session_develop_lock.json"
START_BALANCE = 10_000.0
GOAL_DAILY_PCT = 0.01
GOAL_MONTHLY_PCT = 0.20
MIN_TRADES_DEVELOP = 40

OR_MINUTES = (5, 15, 30)
EMA_PAIRS = ((5, 13), (8, 21), (9, 21))
FILTERS = (
    ("orb_vwap_ema", True, True),
    ("orb_vwap", True, False),
    ("orb_ema", False, True),
    ("orb_only", False, False),
)
ENTRY_ENDS = (time(10, 30), time(11, 30), time(12, 0))
ONE_PER_DAY = (True, False)
EXITS: tuple[dict, ...] = (
    {"kind": "flatten", "hh": 11, "mm": 30},
    {"kind": "flatten", "hh": 12, "mm": 0},
    {"kind": "flatten", "hh": 15, "mm": 45},
    {"kind": "atr", "sl": 1.0, "tp": 1.5},
    {"kind": "atr", "sl": 1.5, "tp": 2.0},
    {"kind": "atr", "sl": 1.0, "tp": 2.0},
    {"kind": "bars", "n": 6},
    {"kind": "bars", "n": 12},
)


def exit_name(ex: dict) -> str:
    if ex["kind"] == "flatten":
        return f"flatten_{ex['hh']:02d}:{ex['mm']:02d}"
    if ex["kind"] == "atr":
        return f"atr_sl{ex['sl']}_tp{ex['tp']}"
    if ex["kind"] == "vwap":
        sl = float(ex.get("sl") or 0.0)
        return f"vwap_sl{sl}" if sl > 0.0 else "vwap"
    if ex["kind"] == "trail":
        sl = ex.get("sl", 1.0)
        if ex.get("trail") == "ema":
            return f"trail_ema{ex['ema']}_sl{sl}"
        return f"trail_swing{ex['k']}_sl{sl}"
    return f"bars_{ex['n']}"


def build_grid() -> list[dict]:
    rows: list[dict] = []
    for or_m, (ef, es), (fname, use_v, use_e), end, opd, ex in itertools.product(
        OR_MINUTES, EMA_PAIRS, FILTERS, ENTRY_ENDS, ONE_PER_DAY, EXITS
    ):
        rows.append(
            {
                "or_minutes": or_m,
                "ema_fast": ef,
                "ema_slow": es,
                "filter": fname,
                "use_vwap": use_v,
                "use_ema": use_e,
                "entry_end": f"{end.hour:02d}:{end.minute:02d}",
                "entry_end_min": end.hour * 60 + end.minute,
                "one_per_day": opd,
                "exit": exit_name(ex),
                "exit_spec": ex,
            }
        )
    return rows


def _et_arrays(times: list) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    et = [to_et(t) for t in times]
    mins = np.array([e.hour * 60 + e.minute for e in et], dtype=np.int32)
    keys = np.array([e.year * 10000 + e.month * 100 + e.day for e in et], dtype=np.int32)
    dow = np.array([e.weekday() for e in et], dtype=np.int8)
    ny = np.array([is_ny_cash(t) for t in times], dtype=bool)
    return mins, keys, dow, ny


def _or_and_vwap(
    mins: np.ndarray,
    keys: np.ndarray,
    ny: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    vol: np.ndarray,
    or_minutes: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n = len(close)
    or_h = np.full(n, np.nan)
    or_l = np.full(n, np.nan)
    ready = np.zeros(n, dtype=bool)
    vwap = np.full(n, np.nan)
    start_m = 9 * 60 + 30
    end_m = start_m + or_minutes
    vday = -1
    vnum = 0.0
    vden = 0.0
    oh = 0.0
    ol = 0.0
    oset = False
    for i in range(n):
        day = int(keys[i])
        if day != vday:
            vday = day
            vnum = 0.0
            vden = 0.0
            oset = False
        if ny[i]:
            typ = (high[i] + low[i] + close[i]) / 3.0
            v = max(float(vol[i]), 1.0)
            vnum += typ * v
            vden += v
            vwap[i] = vnum / vden
        m = int(mins[i])
        if start_m <= m < end_m:
            if not oset:
                oh = float(high[i])
                ol = float(low[i])
                oset = True
            else:
                if high[i] > oh:
                    oh = float(high[i])
                if low[i] < ol:
                    ol = float(low[i])
        if oset and m >= end_m:
            or_h[i] = oh
            or_l[i] = ol
            ready[i] = True
    return or_h, or_l, ready, vwap


def signal_series(
    close: np.ndarray,
    mins: np.ndarray,
    keys: np.ndarray,
    dow: np.ndarray,
    or_h: np.ndarray,
    or_l: np.ndarray,
    ready: np.ndarray,
    vwap: np.ndarray,
    ema_f: np.ndarray,
    ema_s: np.ndarray,
    atr: np.ndarray,
    *,
    or_minutes: int,
    entry_end_min: int,
    use_vwap: bool,
    use_ema: bool,
    one_per_day: bool,
    min_atr_pct: float = 0.00015,
) -> np.ndarray:
    n = len(close)
    out = np.zeros(n, dtype=np.int8)
    or_end = 9 * 60 + 30 + or_minutes
    fired = -1
    last = n - 1
    for i in range(last):
        m = int(mins[i])
        if int(dow[i]) == 4 and m >= 14 * 60:
            continue
        if m < or_end or m >= entry_end_min:
            continue
        if not ready[i]:
            continue
        px = float(close[i])
        at = float(atr[i])
        if not np.isfinite(at) or px <= 0.0 or (at / px) < min_atr_pct:
            continue
        if one_per_day and int(keys[i]) == fired:
            continue
        long_ok = px > float(or_h[i])
        short_ok = px < float(or_l[i])
        if use_vwap:
            vw = float(vwap[i])
            if not np.isfinite(vw):
                continue
            long_ok = long_ok and px > vw
            short_ok = short_ok and px < vw
        if use_ema:
            ef = float(ema_f[i])
            es = float(ema_s[i])
            if not (np.isfinite(ef) and np.isfinite(es)):
                continue
            long_ok = long_ok and ef > es
            short_ok = short_ok and ef < es
        sig = 1 if long_ok else (-1 if short_ok else 0)
        if sig == 0:
            continue
        out[i] = sig
        fired = int(keys[i])
    return out


def simulate_exits(
    times: list,
    mins: np.ndarray,
    keys: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    atr: np.ndarray,
    spread: np.ndarray,
    signals: np.ndarray,
    costs: CostSpec,
    exit_spec: dict,
    target: np.ndarray | None = None,
    ema: np.ndarray | None = None,
) -> list[Trade]:
    n = len(times)
    trades: list[Trade] = []
    i = 0
    kind = exit_spec["kind"]
    while i < n - 1:
        sig = int(signals[i])
        if sig == 0:
            i += 1
            continue
        fill = i + 1
        if fill >= n or int(keys[fill]) != int(keys[i]):
            i += 1
            continue
        spr = float(spread[fill]) if np.isfinite(spread[fill]) else 0.0
        if costs.max_spread_points > 0 and spr > costs.max_spread_points:
            i += 1
            continue
        entry = float(open_[fill])
        day = int(keys[fill])
        at = float(atr[i]) if np.isfinite(atr[i]) else 0.0
        sl = tp = None
        tgt = float("nan")
        if kind == "atr" and at > 0:
            sl = entry - sig * at * float(exit_spec["sl"])
            tp = entry + sig * at * float(exit_spec["tp"])
        if kind in {"vwap", "trail"}:
            sl_mult = float(exit_spec.get("sl") or 0.0)
            if sl_mult > 0.0 and at > 0.0:
                sl = entry - sig * at * sl_mult
        if kind == "vwap" and target is not None and not exit_spec.get("running"):
            tgt = float(target[i])
        exit_i = None
        reason = "eod"
        exit_px = float(open_[fill])
        j = fill
        limit = fill + int(exit_spec["n"]) if kind == "bars" else n
        if kind == "flatten":
            flat_m = exit_spec["hh"] * 60 + exit_spec["mm"]
            flat_reason = exit_name(exit_spec)
        elif kind in {"vwap", "trail"}:
            if "hh" in exit_spec and "mm" in exit_spec:
                flat_m = int(exit_spec["hh"]) * 60 + int(exit_spec["mm"])
                flat_reason = f"flatten_{int(exit_spec['hh']):02d}:{int(exit_spec['mm']):02d}"
            else:
                flat_m = 15 * 60 + 45
                flat_reason = "flatten_15:45"
        else:
            flat_m = None
            flat_reason = "flatten_15:45"
        while j < n and int(keys[j]) == day and j <= limit:
            if kind == "trail" and sl is not None and j > fill:
                if exit_spec.get("trail") == "swing":
                    k = int(exit_spec["k"])
                    a = max(0, j - k)
                    if sig > 0:
                        sl = max(sl, float(np.min(low[a:j])))
                    else:
                        sl = min(sl, float(np.max(high[a:j])))
                elif exit_spec.get("trail") == "ema" and ema is not None:
                    ev = float(ema[j - 1])
                    if np.isfinite(ev):
                        sl = max(sl, ev) if sig > 0 else min(sl, ev)
            if kind == "vwap" and exit_spec.get("running") and target is not None:
                tgt = float(target[j])
            if flat_m is not None and int(mins[j]) >= flat_m:
                exit_i, exit_px, reason = j, float(open_[j]), (
                    exit_name(exit_spec) if kind == "flatten" else flat_reason
                )
                break
            if sl is not None:
                if sig > 0 and low[j] <= sl:
                    exit_i, exit_px, reason = j, sl, "sl"
                    break
                if sig < 0 and high[j] >= sl:
                    exit_i, exit_px, reason = j, sl, "sl"
                    break
            if tp is not None:
                if sig > 0 and high[j] >= tp:
                    exit_i, exit_px, reason = j, tp, "tp"
                    break
                if sig < 0 and low[j] <= tp:
                    exit_i, exit_px, reason = j, tp, "tp"
                    break
            if kind == "vwap" and np.isfinite(tgt):
                if sig > 0 and high[j] >= tgt:
                    exit_i, exit_px, reason = j, tgt, "vwap"
                    break
                if sig < 0 and low[j] <= tgt:
                    exit_i, exit_px, reason = j, tgt, "vwap"
                    break
            if kind == "bars" and j == limit:
                exit_i, exit_px, reason = j, float(open_[j]), exit_name(exit_spec)
                break
            j += 1
        if exit_i is None:
            last = j - 1 if j > fill else fill
            if last <= fill:
                i += 1
                continue
            exit_i, exit_px, reason = last, float(open_[last]), "session_end"
        if exit_i <= fill:
            i += 1
            continue
        cost = _round_trip_cost(spr, costs)
        pnl = (exit_px - entry) * sig * costs.contract_size * costs.lots - cost
        wh = high[fill:exit_i]
        wl = low[fill:exit_i]
        if sig > 0:
            mae = float(entry - np.min(wl)) if len(wl) else 0.0
            mfe = float(np.max(wh) - entry) if len(wh) else 0.0
        else:
            mae = float(np.max(wh) - entry) if len(wh) else 0.0
            mfe = float(entry - np.min(wl)) if len(wl) else 0.0
        trades.append(
            Trade(
                side=sig,
                signal_i=i,
                fill_i=fill,
                exit_i=exit_i,
                entry=entry,
                exit=exit_px,
                reason=reason,
                et_date=str(to_et(times[i]).date()),
                signal_time=to_utc(times[i]).isoformat(),
                fill_time=to_utc(times[fill]).isoformat(),
                exit_time=to_utc(times[exit_i]).isoformat(),
                spread_pts=spr,
                cost=cost,
                pnl=pnl,
                mae=mae,
                mfe=mfe,
            )
        )
        i = exit_i + 1
    return trades


def daily_monthly(trades: list[Trade], balance: float = START_BALANCE) -> dict:
    if balance <= 0:
        balance = START_BALANCE
    by_day: dict[str, float] = defaultdict(float)
    for t in trades:
        by_day[t.et_date] += t.pnl
    day_pcts = [p / balance for p in by_day.values()] if by_day else []
    by_month: dict[str, float] = defaultdict(float)
    for d, p in by_day.items():
        by_month[d[:7]] += p
    month_pcts = [p / balance for p in by_month.values()] if by_month else []
    return {
        "trade_days": len(by_day),
        "months": len(by_month),
        "median_daily_pct": float(np.median(day_pcts)) if day_pcts else 0.0,
        "mean_daily_pct": float(np.mean(day_pcts)) if day_pcts else 0.0,
        "pct_days_ge_1pct": (
            float(np.mean([x >= GOAL_DAILY_PCT for x in day_pcts])) if day_pcts else 0.0
        ),
        "median_monthly_pct": float(np.median(month_pcts)) if month_pcts else 0.0,
        "mean_monthly_pct": float(np.mean(month_pcts)) if month_pcts else 0.0,
        "pct_months_ge_20pct": (
            float(np.mean([x >= GOAL_MONTHLY_PCT for x in month_pcts]))
            if month_pcts
            else 0.0
        ),
        "hit_daily_goal": bool(day_pcts) and float(np.median(day_pcts)) >= GOAL_DAILY_PCT,
        "hit_monthly_goal": (
            bool(month_pcts) and float(np.median(month_pcts)) >= GOAL_MONTHLY_PCT
        ),
    }


def score_row(m: dict) -> float:
    trades = int(m["trades"])
    if trades < MIN_TRADES_DEVELOP or float(m["net_pnl"]) <= 0:
        return -1e9
    pf = m["profit_factor"]
    pf_v = 3.0 if pf is None else float(pf)
    return pf_v * 1000.0 + float(m["expectancy"])


def pack_metrics(trades: list[Trade]) -> dict:
    m = metrics_from_trades(trades)
    m.update(daily_monthly(trades))
    m["goal_both"] = bool(m["hit_daily_goal"] and m["hit_monthly_goal"])
    return m


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
    ema_cache = {
        p: ema_series(close, p)
        for p in sorted({x for pair in EMA_PAIRS for x in pair})
    }
    or_cache = {
        om: _or_and_vwap(mins, keys, ny, high, low, close, vol, om) for om in OR_MINUTES
    }

    grid = build_grid()
    rows: list[dict] = []
    t0 = pytime.time()
    for i, cfg in enumerate(grid):
        or_h, or_l, ready, vwap = or_cache[cfg["or_minutes"]]
        sigs = signal_series(
            close,
            mins,
            keys,
            dow,
            or_h,
            or_l,
            ready,
            vwap,
            ema_cache[cfg["ema_fast"]],
            ema_cache[cfg["ema_slow"]],
            atr,
            or_minutes=cfg["or_minutes"],
            entry_end_min=cfg["entry_end_min"],
            use_vwap=cfg["use_vwap"],
            use_ema=cfg["use_ema"],
            one_per_day=cfg["one_per_day"],
        )
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
        pre, post = split_by_holdout(trades)
        slim = {
            k: cfg[k]
            for k in (
                "or_minutes",
                "ema_fast",
                "ema_slow",
                "filter",
                "entry_end",
                "one_per_day",
                "exit",
            )
        }
        rows.append(
            {
                "index": i,
                "params": slim,
                "develop": pack_metrics(pre),
                "holdout": pack_metrics(post),
                "develop_score": score_row(pack_metrics(pre)),
            }
        )
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
    # Holdout is read only after ranking is fixed.
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
        "goal_note": (
            "1%/day and 20%/month are scored as median trade-day / median month "
            "on a $10k 1-lot book. Selection never sees holdout."
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
    ap.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "results" / "us_index_session_autoresearch.json",
    )
    args = ap.parse_args()
    if not LOCK_PATH.is_file():
        raise SystemExit(f"missing lock {LOCK_PATH}")
    lock = json.loads(LOCK_PATH.read_text())
    if lock.get("holdout_start") != "2026-06-01":
        raise SystemExit("holdout lock mismatch")
    if lock.get("search_id") != SEARCH_ID:
        raise SystemExit("search_id mismatch")
    meta = parse_meta(args.meta) if args.meta.is_file() else {}
    costs = costs_from_meta(
        meta,
        lots=1.0,
        slippage_points=10.0,
        commission_per_lot=0.0,
        max_spread_points=200.0,
    )
    report = run_search(args.csv, args.meta, costs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
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
                "promote": False,
            },
            indent=2,
        )
    )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
