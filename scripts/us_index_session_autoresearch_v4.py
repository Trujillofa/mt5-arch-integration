#!/usr/bin/env python3
"""US100 v4 screen: vol regime, proxy-CVD, prior-day POC (new search).

Lock: results/us_index_session_v4_lock.json
  select et_date < 2026-06-01
  holdout et_date >= 2026-07-01
  June 2026 is a burned buffer.

True bid/ask CVD is skipped (no TimescaleDB / no aggressor ticks).
HMM is skipped (ATR fast>slow only). Costs keep 10 pt slippage/side.
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
from us_index_session_backtest import (  # noqa: E402
    CostSpec,
    Trade,
    costs_from_meta,
    load_m5_csv,
    parse_meta,
)
from us_index_session_core import (  # noqa: E402
    ATR_PERIOD,
    atr_expanding,
    pre_ny_liquidity_levels,
    prior_day_poc,
    proxy_cvd_series,
    to_utc,
    wilder_atr,
)

SEARCH_ID = "us_index_session_v4"
LOCK_PATH = _ROOT / "results" / "us_index_session_v4_lock.json"
SELECT_END = date(2026, 6, 1)
HOLDOUT_START = date(2026, 7, 1)
ENTRY_START = 9 * 60 + 45

ATR_PAIRS = ((7, 28), (14, 56))
REGIME_K = (1.0, 1.15)
ORB_ENDS = (time(10, 30), time(11, 30))
ONE_PER_DAY = (True, False)
ORB_EXITS: tuple[dict, ...] = (
    {"kind": "flatten", "hh": 11, "mm": 30},
    {"kind": "flatten", "hh": 15, "mm": 45},
    {"kind": "atr", "sl": 1.0, "tp": 1.5},
)

CVD_LEVELS = ("or", "pdh")
CVD_LOOKBACK = (6, 12)
CVD_EXITS: tuple[dict, ...] = (
    {"kind": "flatten", "hh": 11, "mm": 30},
    {"kind": "atr", "sl": 1.0, "tp": 1.5},
    {"kind": "bars", "n": 6},
)

POC_KINDS = ("volume", "tpo")
POC_DEV = (0.75, 1.25)
POC_ENDS = (time(11, 30), time(12, 0))
POC_EXITS: tuple[dict, ...] = (
    {"kind": "vwap", "sl": 1.0, "tag": "poc_target"},
    {"kind": "flatten", "hh": 11, "mm": 30},
    {"kind": "atr", "sl": 1.0, "tp": 1.5},
)


def _exit_label(ex: dict) -> str:
    return str(ex["tag"]) if "tag" in ex else exit_name(ex)


def build_grid() -> list[dict]:
    rows: list[dict] = []
    for (af, as_), k, end, opd, ex in itertools.product(
        ATR_PAIRS, REGIME_K, ORB_ENDS, ONE_PER_DAY, ORB_EXITS
    ):
        rows.append(
            {
                "family": "vol_regime_orb",
                "atr_fast": af,
                "atr_slow": as_,
                "regime_k": k,
                "entry_end": f"{end.hour:02d}:{end.minute:02d}",
                "entry_end_min": end.hour * 60 + end.minute,
                "one_per_day": opd,
                "exit": _exit_label(ex),
                "exit_spec": ex,
            }
        )
    for lvl, lb, gate, opd, ex in itertools.product(
        CVD_LEVELS, CVD_LOOKBACK, (True, False), ONE_PER_DAY, CVD_EXITS
    ):
        rows.append(
            {
                "family": "tick_proxy_cvd",
                "level": lvl,
                "lookback": lb,
                "regime_gate": gate,
                "entry_end": "11:30",
                "entry_end_min": 11 * 60 + 30,
                "one_per_day": opd,
                "exit": _exit_label(ex),
                "exit_spec": ex,
            }
        )
    for kind, dev, gate, end, opd, ex in itertools.product(
        POC_KINDS, POC_DEV, (True, False), POC_ENDS, ONE_PER_DAY, POC_EXITS
    ):
        rows.append(
            {
                "family": "prior_poc_reversion",
                "profile": kind,
                "atr_dev": dev,
                "regime_gate": gate,
                "entry_end": f"{end.hour:02d}:{end.minute:02d}",
                "entry_end_min": end.hour * 60 + end.minute,
                "one_per_day": opd,
                "exit": _exit_label(ex),
                "exit_spec": ex,
            }
        )
    return rows


def split_v4(trades: list[Trade]) -> tuple[list[Trade], list[Trade]]:
    pre = [t for t in trades if date.fromisoformat(t.et_date) < SELECT_END]
    post = [t for t in trades if date.fromisoformat(t.et_date) >= HOLDOUT_START]
    return pre, post


def _slim(cfg: dict) -> dict:
    return {k: cfg[k] for k in cfg if k not in {"exit_spec", "entry_end_min"}}


def _in_window(mins: np.ndarray, dow: np.ndarray, i: int, end_min: int) -> bool:
    m = int(mins[i])
    if int(dow[i]) == 4 and m >= 14 * 60:
        return False
    return ENTRY_START <= m < end_min


def orb_regime_signals(
    close: np.ndarray,
    mins: np.ndarray,
    keys: np.ndarray,
    dow: np.ndarray,
    or_h: np.ndarray,
    or_l: np.ndarray,
    ready: np.ndarray,
    expanding: np.ndarray,
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
        if not ready[i] or not expanding[i]:
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


def cvd_signals(
    high: np.ndarray,
    low: np.ndarray,
    cvd: np.ndarray,
    mins: np.ndarray,
    keys: np.ndarray,
    dow: np.ndarray,
    or_h: np.ndarray,
    or_l: np.ndarray,
    ready: np.ndarray,
    pdh: np.ndarray,
    pdl: np.ndarray,
    expanding: np.ndarray,
    *,
    level: str,
    lookback: int,
    regime_gate: bool,
    entry_end_min: int,
    one_per_day: bool,
) -> np.ndarray:
    n = len(high)
    out = np.zeros(n, dtype=np.int8)
    fired = -1
    for i in range(lookback, n - 1):
        if not _in_window(mins, dow, i, entry_end_min):
            continue
        if regime_gate and not expanding[i]:
            continue
        if one_per_day and int(keys[i]) == fired:
            continue
        prev_h = float(np.max(high[i - lookback : i]))
        prev_l = float(np.min(low[i - lookback : i]))
        prev_c = float(np.max(cvd[i - lookback : i]))
        prev_cl = float(np.min(cvd[i - lookback : i]))
        hh_px = float(high[i]) > prev_h
        ll_px = float(low[i]) < prev_l
        hh_c = float(cvd[i]) > prev_c
        ll_c = float(cvd[i]) < prev_cl
        if level == "or":
            at_hi = bool(ready[i]) and float(high[i]) >= float(or_h[i])
            at_lo = bool(ready[i]) and float(low[i]) <= float(or_l[i])
        else:
            at_hi = np.isfinite(pdh[i]) and float(high[i]) >= float(pdh[i])
            at_lo = np.isfinite(pdl[i]) and float(low[i]) <= float(pdl[i])
        sig = 0
        if at_hi and hh_px and not hh_c:
            sig = -1
        elif at_lo and ll_px and not ll_c:
            sig = 1
        if sig == 0:
            continue
        out[i] = sig
        fired = int(keys[i])
    return out


def poc_signals(
    close: np.ndarray,
    vol: np.ndarray,
    atr: np.ndarray,
    poc: np.ndarray,
    mins: np.ndarray,
    keys: np.ndarray,
    dow: np.ndarray,
    expanding: np.ndarray,
    *,
    atr_dev: float,
    regime_gate: bool,
    entry_end_min: int,
    one_per_day: bool,
) -> tuple[np.ndarray, np.ndarray]:
    n = len(close)
    out = np.zeros(n, dtype=np.int8)
    target = np.full(n, np.nan)
    fired = -1
    for i in range(20, n - 1):
        if not _in_window(mins, dow, i, entry_end_min):
            continue
        if regime_gate and not expanding[i]:
            continue
        if one_per_day and int(keys[i]) == fired:
            continue
        px = float(close[i])
        at = float(atr[i])
        pc = float(poc[i])
        if not (np.isfinite(at) and np.isfinite(pc) and at > 0.0):
            continue
        med = float(np.median(vol[i - 20 : i]))
        if float(vol[i]) >= med:
            continue
        ext = (px - pc) / at
        sig = 0
        if ext >= atr_dev:
            sig = -1
        elif ext <= -atr_dev:
            sig = 1
        if sig == 0:
            continue
        out[i] = sig
        target[i] = pc
        fired = int(keys[i])
    return out, target


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
    atr_cache = {
        p: wilder_atr(high, low, close, p) for p in (7, 14, 28, 56)
    }
    expand = {
        (af, as_, k): atr_expanding(atr_cache[af], atr_cache[as_], k)
        for af, as_ in ATR_PAIRS
        for k in REGIME_K
    }
    or_h, or_l, ready, _vwap = _or_and_vwap(mins, keys, ny, high, low, close, vol, 15)
    _ah, _al, _lh, _ll, pdh, pdl = pre_ny_liquidity_levels(times, high, low, keys)
    cvd = proxy_cvd_series(keys, open_, close, vol)
    poc = {
        kind: prior_day_poc(keys, high, low, vol, bin_price=2.0, kind=kind)
        for kind in POC_KINDS
    }
    default_exp = expand[(7, 28, 1.0)]

    grid = build_grid()
    rows: list[dict] = []
    t0 = pytime.time()
    for i, cfg in enumerate(grid):
        fam = cfg["family"]
        if fam == "vol_regime_orb":
            exp = expand[(cfg["atr_fast"], cfg["atr_slow"], cfg["regime_k"])]
            sigs = orb_regime_signals(
                close,
                mins,
                keys,
                dow,
                or_h,
                or_l,
                ready,
                exp,
                entry_end_min=cfg["entry_end_min"],
                one_per_day=cfg["one_per_day"],
            )
            row = _run(
                cfg, times, mins, keys, open_, high, low, atr14, spread, costs, sigs, None
            )
        elif fam == "tick_proxy_cvd":
            sigs = cvd_signals(
                high,
                low,
                cvd,
                mins,
                keys,
                dow,
                or_h,
                or_l,
                ready,
                pdh,
                pdl,
                default_exp,
                level=cfg["level"],
                lookback=cfg["lookback"],
                regime_gate=cfg["regime_gate"],
                entry_end_min=cfg["entry_end_min"],
                one_per_day=cfg["one_per_day"],
            )
            row = _run(
                cfg, times, mins, keys, open_, high, low, atr14, spread, costs, sigs, None
            )
        else:
            sigs, tgt = poc_signals(
                close,
                vol,
                atr14,
                poc[cfg["profile"]],
                mins,
                keys,
                dow,
                default_exp,
                atr_dev=cfg["atr_dev"],
                regime_gate=cfg["regime_gate"],
                entry_end_min=cfg["entry_end_min"],
                one_per_day=cfg["one_per_day"],
            )
            row = _run(
                cfg, times, mins, keys, open_, high, low, atr14, spread, costs, sigs, tgt
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
    by_fam = {k: [] for k in ("vol_regime_orb", "tick_proxy_cvd", "prior_poc_reversion")}
    for r in ranked:
        fam = r["params"]["family"]
        if len(by_fam[fam]) < 5:
            by_fam[fam].append(r)
    return {
        "search_id": SEARCH_ID,
        "promote": False,
        "live_go": False,
        "selection_end": str(SELECT_END),
        "holdout_start": str(HOLDOUT_START),
        "start_balance": START_BALANCE,
        "goal_daily_pct": GOAL_DAILY_PCT,
        "goal_monthly_pct": GOAL_MONTHLY_PCT,
        "n_configs": len(grid),
        "n_eligible_develop": len(eligible),
        "n_develop_hit_goal": sum(1 for r in rows if r["develop"]["goal_both"]),
        "n_top20_holdout_hit_goal": sum(
            1 for r in ranked[:20] if r["holdout"]["goal_both"]
        ),
        "elapsed_sec": round(elapsed, 2),
        "costs": asdict(costs),
        "bars": int(len(df)),
        "from": str(df["time_utc"].iloc[0]),
        "to": str(df["time_utc"].iloc[-1]),
        "best_develop": ranked[0] if ranked else None,
        "top10_develop": ranked[:10],
        "top5_by_family": by_fam,
        "true_cvd": "skipped",
        "hmm": "skipped",
        "goal_note": (
            "Selection never sees 2026-06-01 onward. Holdout is 2026-07-01 onward. "
            "June is unused. Proxy-CVD is not bid/ask CVD."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=_ROOT / "results" / "us_index_data" / "history_US100_M5.csv")
    ap.add_argument("--meta", type=Path, default=_ROOT / "results" / "us_index_data" / "symbol_meta_US100.csv")
    ap.add_argument("--out", type=Path, default=_ROOT / "results" / "us_index_session_v4.json")
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
    report = run_search(args.csv, args.meta, costs)
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
                "true_cvd": "skipped",
                "promote": False,
            },
            indent=2,
        )
    )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
