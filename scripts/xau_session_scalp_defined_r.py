#!/usr/bin/env python3
"""Defined-R gold scalp family ``xau_london_defined_r_be_flat_v1``.

Risk-first refactor of the London/NY-metals entry stack. Same gold clock.
New family because exits / filters changed. Grid and score were frozen in
``results/xau_session_scalp/defined_r_v1_lock.json`` before this script
produced official metrics.

Select on ``utc_date <= 2025-10-31`` only. Nov-Dec 2025 = confirm.
Holdout ``>= 2026-01-01`` is evaluate-once. Never ``--live``.
"""

from __future__ import annotations

import argparse
import itertools
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

from xau_session_scalp_backtest import (  # noqa: E402, I001
    ATR_PERIOD,
    CONTRACT_SIZE,
    HOLDOUT_START,
    LIVE_GO,
    OR_MINUTES,
    PROMOTE,
    CostSpec,
    Trade,
    _flatten_index,
    _round_trip_cost,
    _arrays,
    data_block,
    default_fp_m5,
    gold_cost_book,
    load_bars,
    metrics_from_trades,
    refuse_frictionless,
    slim_committed_report,
    write_slim_json,
)
from xau_session_scalp_core import (  # noqa: E402
    MIN_ATR_PCT,
    SessionBox,
    scalp_signal_series,
    session_box_at,
    to_utc,
    wilder_atr,
)

FAMILY_ID = "xau_london_defined_r_be_flat_v1"
SELECT_END = date(2025, 10, 31)
CONFIRM_START = date(2025, 11, 1)
CONFIRM_END = date(2025, 12, 31)
SL_ATR = 1.0
OR_WIDTH_ATR_MIN = 0.35
OR_WIDTH_ATR_MAX = 2.5
MAX_COST_TO_TP = 0.35
EQUITY_REF = 10_000.0
RISK_PCT = 0.005
TP_R_GRID = (0.35, 0.50, 0.70, 1.00)
BE_R_GRID = (0.0, 0.40)
TIME_STOP_GRID = (0, 6)
LOCK_PATH = _ROOT / "results" / "xau_session_scalp" / "defined_r_v1_lock.json"


def load_lock() -> dict:
    lock = json.loads(LOCK_PATH.read_text())
    if lock.get("family_id") != FAMILY_ID:
        raise SystemExit("lock family_id mismatch")
    if lock.get("promote") is True or lock.get("live_go") is True:
        raise SystemExit("lock promote/live_go must stay false")
    if str(lock.get("holdout_start", "")).startswith("2026-01-01") is False:
        raise SystemExit("lock holdout must stay 2026-01-01")
    if lock.get("grid", {}).get("cardinality") != 16:
        raise SystemExit("lock grid cardinality must stay 16")
    return lock


def frozen_grid() -> list[dict]:
    rows = []
    for tp_r, be_r, ts in itertools.product(TP_R_GRID, BE_R_GRID, TIME_STOP_GRID):
        rows.append(
            {
                "id": f"tpr{tp_r:g}_be{be_r:g}_ts{ts}",
                "tp_r": float(tp_r),
                "be_r": float(be_r),
                "time_stop_bars": int(ts),
                "sl_atr": SL_ATR,
            }
        )
    if len(rows) != 16:
        raise SystemExit(f"grid size {len(rows)} != 16")
    return rows


def or_width_series(
    times: list,
    high: np.ndarray,
    low: np.ndarray,
    *,
    or_minutes: int = OR_MINUTES,
) -> np.ndarray:
    """Incremental London OR width (NaN until complete). O(n)."""
    from xau_session_scalp_core import london_open_local, london_or_end, to_london

    n = len(times)
    out = np.full(n, np.nan, dtype=float)
    vday = None
    or_h = float("nan")
    or_l = float("nan")
    or_set = False
    for i, ts in enumerate(times):
        lon = to_london(ts)
        day = lon.date()
        if day != vday:
            vday = day
            or_h = float("nan")
            or_l = float("nan")
            or_set = False
        start = london_open_local(day)
        end = london_or_end(day, or_minutes)
        if start <= lon < end:
            if not or_set:
                or_h = float(high[i])
                or_l = float(low[i])
                or_set = True
            else:
                or_h = max(or_h, float(high[i]))
                or_l = min(or_l, float(low[i]))
        if or_set and lon >= end:
            out[i] = float(or_h - or_l)
    return out


def extra_metrics(trades: list[Trade]) -> dict:
    base = metrics_from_trades(trades)
    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [t.pnl for t in trades if t.pnl <= 0]
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0
    if avg_loss < 0:
        payoff = avg_win / abs(avg_loss)
    elif wins:
        payoff = 3.0
    else:
        payoff = 0.0
    reasons: dict[str, int] = {}
    for tr in trades:
        reasons[tr.reason] = reasons.get(tr.reason, 0) + 1
    base.update(
        {
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "payoff": float(payoff),
            "exits": reasons,
            "equity_ref": EQUITY_REF,
            "risk_pct": RISK_PCT,
        }
    )
    return base


def metrics_with_risk(trades: list[Trade], sl_dists: list[float]) -> dict:
    m = extra_metrics(trades)
    risk_cash = EQUITY_REF * RISK_PCT
    pnls: list[float] = []
    lots: list[float] = []
    for tr, sl_d in zip(trades, sl_dists, strict=True):
        if sl_d <= 1e-12:
            continue
        risk_lots = risk_cash / (sl_d * CONTRACT_SIZE)
        lots.append(risk_lots)
        pnls.append(tr.pnl * risk_lots)
    m["pnl_at_0p5pct_risk"] = float(sum(pnls)) if pnls else 0.0
    m["median_risk_lots"] = float(np.median(lots)) if lots else 0.0
    return m


def window_pack(trades: list[Trade], sl_dists: list[float]) -> dict:
    buckets = {
        "select": ([], []),
        "confirm": ([], []),
        "holdout": ([], []),
        "develop": ([], []),
    }
    for tr, sl_d in zip(trades, sl_dists, strict=True):
        d = date.fromisoformat(tr.utc_date)
        if d <= SELECT_END:
            buckets["select"][0].append(tr)
            buckets["select"][1].append(sl_d)
        if CONFIRM_START <= d <= CONFIRM_END:
            buckets["confirm"][0].append(tr)
            buckets["confirm"][1].append(sl_d)
        if d >= HOLDOUT_START:
            buckets["holdout"][0].append(tr)
            buckets["holdout"][1].append(sl_d)
        if d < HOLDOUT_START:
            buckets["develop"][0].append(tr)
            buckets["develop"][1].append(sl_d)
    return {k: metrics_with_risk(ts, sd) for k, (ts, sd) in buckets.items()}


def simulate_defined_r(
    times: list,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    spread: np.ndarray,
    signals: np.ndarray,
    costs: CostSpec,
    *,
    atr: np.ndarray,
    tp_r: float,
    be_r: float,
    time_stop_bars: int,
    sl_atr: float = SL_ATR,
    allow_ny: bool = True,
    or_minutes: int = OR_MINUTES,
    or_width_atr_min: float = OR_WIDTH_ATR_MIN,
    or_width_atr_max: float = OR_WIDTH_ATR_MAX,
    max_cost_to_tp: float = MAX_COST_TO_TP,
    or_width: np.ndarray | None = None,
) -> tuple[list[Trade], list[float]]:
    """Hard SL, defined-R TP, optional BE, optional time-stop."""
    n = len(times)
    if or_width is None:
        or_width = or_width_series(times, high, low, or_minutes=or_minutes)
    trades: list[Trade] = []
    sl_dists: list[float] = []
    i = 0
    while i < n - 1:
        sig = int(signals[i])
        if sig == 0:
            i += 1
            continue
        box = session_box_at(times[i], or_minutes=or_minutes, allow_ny=allow_ny)
        if box == SessionBox.NONE:
            i += 1
            continue
        atr_i = float(atr[i]) if np.isfinite(atr[i]) else 0.0
        if atr_i <= 0.0:
            i += 1
            continue
        or_w = float(or_width[i])
        if not np.isfinite(or_w):
            i += 1
            continue
        width_atr = or_w / atr_i
        if width_atr < or_width_atr_min or width_atr > or_width_atr_max:
            i += 1
            continue
        fill_i = i + 1
        if fill_i >= n:
            break
        spr = float(spread[fill_i]) if np.isfinite(spread[fill_i]) else 0.0
        if costs.max_spread_points > 0 and spr > costs.max_spread_points:
            i += 1
            continue
        sl_dist = sl_atr * atr_i
        tp_dist = tp_r * sl_dist
        cost = _round_trip_cost(spr, costs)
        tp_cash = tp_dist * costs.contract_size * costs.lots
        if tp_cash <= 0.0 or cost > max_cost_to_tp * tp_cash:
            i += 1
            continue
        flat_i = _flatten_index(times, fill_i, box)
        if flat_i is None or flat_i <= fill_i:
            i += 1
            continue
        exit_i = flat_i
        if time_stop_bars > 0:
            exit_i = min(exit_i, fill_i + int(time_stop_bars))
        entry = float(open_[fill_i])
        sl = entry - sig * sl_dist
        tp = entry + sig * tp_dist
        be_off = cost / (costs.contract_size * costs.lots)
        be_sl = entry + sig * be_off
        be_trig = entry + sig * be_r * sl_dist if be_r > 0.0 else None
        armed = False
        working_sl = sl
        reason = "time_stop" if time_stop_bars > 0 and exit_i < flat_i else "flatten_session"
        exit_px = float(open_[exit_i])
        hit_i = exit_i
        for j in range(fill_i, exit_i + 1):
            hj = float(high[j])
            lj = float(low[j])
            reached_be = (
                be_trig is not None
                and not armed
                and ((sig > 0 and hj >= be_trig) or (sig < 0 and lj <= be_trig))
            )
            if reached_be:
                armed = True
                working_sl = be_sl
            hit_sl = (lj <= working_sl) if sig > 0 else (hj >= working_sl)
            hit_tp = (hj >= tp) if sig > 0 else (lj <= tp)
            if hit_sl and hit_tp:
                exit_px = float(working_sl)
                reason = "sl_tp_same_bar"
                hit_i = j
                break
            if hit_sl:
                exit_px = float(working_sl)
                reason = "be" if armed else "sl"
                hit_i = j
                break
            if hit_tp:
                exit_px = float(tp)
                reason = "tp"
                hit_i = j
                break
        pnl = (exit_px - entry) * sig * costs.contract_size * costs.lots - cost
        window_h = high[fill_i : hit_i + 1]
        window_l = low[fill_i : hit_i + 1]
        if sig > 0:
            mae = float(entry - np.min(window_l)) if len(window_l) else 0.0
            mfe = float(np.max(window_h) - entry) if len(window_h) else 0.0
        else:
            mae = float(np.max(window_h) - entry) if len(window_h) else 0.0
            mfe = float(entry - np.min(window_l)) if len(window_l) else 0.0
        trades.append(
            Trade(
                side=sig,
                signal_i=i,
                fill_i=fill_i,
                exit_i=hit_i,
                entry=entry,
                exit=exit_px,
                reason=reason,
                box=box.name,
                utc_date=str(to_utc(times[fill_i]).date()),
                signal_time=to_utc(times[i]).isoformat(),
                fill_time=to_utc(times[fill_i]).isoformat(),
                exit_time=to_utc(times[hit_i]).isoformat(),
                spread_pts=spr,
                cost=cost,
                pnl=pnl,
                mae=mae,
                mfe=mfe,
            )
        )
        sl_dists.append(float(sl_dist))
        i = hit_i + 1
    return trades, sl_dists


def eligible_select(m: dict) -> bool:
    n = int(m.get("trades") or 0)
    pf = m.get("profit_factor")
    pf_v = 3.0 if pf is None else float(pf)
    payoff = float(m.get("payoff") or 0.0)
    if n < 40:
        return False
    if payoff < 0.20:
        return False
    if payoff < 0.22 and pf_v <= 1.2:
        return False
    return pf_v >= 1.0


def pick_primary(rows: list[dict]) -> dict:
    eligible = [r for r in rows if r["eligible"]]
    if eligible:
        eligible.sort(key=lambda r: (-r["select"]["win_rate"], -r["select"]["profit_factor"]))
        chosen = dict(eligible[0])
        chosen["pick_reason"] = "max_select_wr_among_eligible"
        return chosen
    viable = [r for r in rows if r["select"]["trades"] >= 30]
    pool = viable or rows
    pool.sort(
        key=lambda r: (
            -(r["select"]["profit_factor"] or 0.0),
            -r["select"]["win_rate"],
        )
    )
    chosen = dict(pool[0])
    chosen["pick_reason"] = "no_eligible_max_select_pf_n30"
    return chosen


def run_cell(df, meta, costs: CostSpec, cell: dict, signals, atr, arrays, or_width) -> dict:
    times, open_, high, low, close, _vol, spread = arrays
    trades, sl_dists = simulate_defined_r(
        times,
        open_,
        high,
        low,
        close,
        spread,
        signals,
        costs,
        atr=atr,
        tp_r=float(cell["tp_r"]),
        be_r=float(cell["be_r"]),
        time_stop_bars=int(cell["time_stop_bars"]),
        sl_atr=float(cell["sl_atr"]),
        or_width=or_width,
    )
    windows = window_pack(trades, sl_dists)
    return {
        "id": cell["id"],
        "params": cell,
        "select": windows["select"],
        "eligible": eligible_select(windows["select"]),
        "n_trades_all": len(trades),
        "_trades": trades,
        "_sl_dists": sl_dists,
        "_windows": windows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hc", type=Path, default=None)
    ap.add_argument("--server-utc-offset", type=int, default=0)
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_ROOT / "results" / "xau_session_scalp",
    )
    args = ap.parse_args()
    lock = load_lock()
    costs = refuse_frictionless(gold_cost_book())
    hc = args.hc or default_fp_m5()
    df, meta = load_bars(hc=hc, server_utc_offset_sec=args.server_utc_offset)
    arrays = _arrays(df)
    times, _o, high, low, close, vol, _s = arrays
    signals = scalp_signal_series(
        times,
        high,
        low,
        close,
        vol,
        or_minutes=OR_MINUTES,
        min_atr_pct=MIN_ATR_PCT,
        or_buffer_atr_frac=0.10,
        allow_ny=True,
    )
    atr = wilder_atr(high, low, close, ATR_PERIOD)
    or_width = or_width_series(times, high, low, or_minutes=OR_MINUTES)

    rows = []
    full = []
    for cell in frozen_grid():
        rec = run_cell(df, meta, costs, cell, signals, atr, arrays, or_width)
        full.append(rec)
        rows.append(
            {
                "id": rec["id"],
                "params": rec["params"],
                "select": rec["select"],
                "eligible": rec["eligible"],
            }
        )

    pick = pick_primary(rows)
    winner = next(r for r in full if r["id"] == pick["id"])
    win_windows = winner["_windows"]

    pareto = {
        "family_id": FAMILY_ID,
        "promote": PROMOTE,
        "live_go": LIVE_GO,
        "lock": str(LOCK_PATH.relative_to(_ROOT)),
        "score": lock["score"],
        "select_end": str(SELECT_END),
        "holdout_start": str(HOLDOUT_START),
        "costs": asdict(costs),
        "data": data_block(df, meta),
        "grid": rows,
        "primary": {
            "id": pick["id"],
            "params": pick["params"],
            "pick_reason": pick["pick_reason"],
            "eligible": pick["eligible"],
            "select": win_windows["select"],
            "confirm": win_windows["confirm"],
            "develop": win_windows["develop"],
            "holdout": win_windows["holdout"],
        },
        "wr80_verdict": _verdict(pick, win_windows),
        "note": (
            "Select-window metrics only were used to pick. "
            "Confirm and holdout are evaluation. Not permission to --live."
        ),
    }
    out_dir = args.out_dir
    write_slim_json(out_dir / "defined_r_v1_pareto.json", pareto)
    write_slim_json(
        out_dir / "defined_r_v1_primary.json",
        {
            "family_id": FAMILY_ID,
            "promote": False,
            "live_go": False,
            **pareto["primary"],
            "costs": asdict(costs),
            "data": data_block(df, meta),
            "wr80_verdict": pareto["wr80_verdict"],
        },
    )
    print(json.dumps(slim_committed_report(pareto), indent=2))
    print(f"wrote {out_dir / 'defined_r_v1_pareto.json'}")
    print(f"wrote {out_dir / 'defined_r_v1_primary.json'}")


def _verdict(pick: dict, windows: dict) -> dict:
    sel = windows["select"]
    wr = float(sel.get("win_rate") or 0.0)
    pf = sel.get("profit_factor")
    pf_v = 3.0 if pf is None else float(pf)
    n = int(sel.get("trades") or 0)
    hit = bool(pick["eligible"] and wr >= 0.80 and pf_v >= 1.0 and n >= 40)
    return {
        "hit_80_and_pf1_on_select": hit,
        "select_wr": wr,
        "select_pf": pf,
        "select_n": n,
        "if_missed": (
            None
            if hit
            else (
                "80% WR and PF>=1 after gold costs are incompatible on this "
                "select tape under the frozen 16-cell defined-R grid. "
                "Tight TP cells raise WR but fail payoff/PF; wider TP keeps "
                "the 2-bar SL/TP race."
            )
        ),
    }


if __name__ == "__main__":
    main()
