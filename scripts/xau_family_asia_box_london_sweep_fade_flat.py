#!/usr/bin/env python3
"""Zero-knob Asia box (01-07) sweep-reclaim fade in hunt 08-13, intraday flat.

Charter (operative): ``results/xau_charters/2026-08-19_asia_box_london_sweep_fade_flat_v2.json``

Execution contract (frozen v2):
* Box = high/low over server hours {1..7}; defined once hour >= 8 if any box bars exist.
* Hunt signal at close: same-bar pierce + close back inside (long/short).
* Fill at next open if hour[i+1] <= 13 same day; else skip.
* entry_gap_policy: skip open-beyond-SL, open-beyond-TP, degenerate box_high==box_low.
* SL = exact swept extreme; TP = box midline; exits on entry bar: SL before TP before time-flat.
* One entry per day; start_balance=10000; RT cost measured at entry, deducted at exit.
* Hours are server labels only — eligibility scaffolding, not the alpha (flat-while-unswept).

SAFETY: offline only. No --live. No develop screen without separate AUTHORIZE.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backtest import (
    CONTRACT_SIZE,
    START_BALANCE,
    Metrics,
    metrics_from_pnls,
)

FAMILY = "asia_box_london_sweep_fade_flat"
NAME = FAMILY
kill_label = "KILL_ASIA_BOX_LONDON_SWEEP_FADE_FLAT"
use_soft_primary = True

DEFAULT_CHARTER_PATH = (
    Path(__file__).resolve().parents[1]
    / "results"
    / "xau_charters"
    / "2026-08-19_asia_box_london_sweep_fade_flat_v2.json"
)

BOX_HOURS = frozenset(range(1, 8))  # 1..7
HUNT_HOURS = frozenset(range(8, 14))  # 8..13
FLAT_HOUR = 13
RISK_PCT = 0.01
MAX_LOTS = 0.5
MIN_LOT = 0.01
WARMUP = 20


def prepare(raw: pd.DataFrame) -> pd.DataFrame:
    """Add hour/day_id. No ATR required for structural SL/TP."""
    d = raw.copy()
    if "time" in d.columns:
        d["time"] = pd.to_datetime(d["time"], utc=True)
        d["hour"] = d["time"].dt.hour
        d["day_id"] = d["time"].dt.strftime("%Y-%m-%d")
    return d


def build_grid() -> list[dict]:
    """Exactly one config — zero free knobs."""
    return [
        {
            "flat_hour": FLAT_HOUR,
            "risk_pct": RISK_PCT,
            "max_lots": MAX_LOTS,
            "box_hours": sorted(BOX_HOURS),
            "hunt_hours": sorted(HUNT_HOURS),
        }
    ]


def grid(*, max_n: int = 1200, seed: int = 42) -> list[dict]:
    _ = max_n, seed
    return build_grid()


def _round_lots(raw_lots: float, max_lots: float) -> float:
    lots = float(np.floor(raw_lots * 100 + 1e-12) / 100.0)
    return min(lots, float(max_lots))


def simulate(
    d: pd.DataFrame,
    *,
    flat_hour: int = FLAT_HOUR,
    risk_pct: float = RISK_PCT,
    max_lots: float = MAX_LOTS,
    box_hours: list[int] | frozenset[int] | None = None,
    hunt_hours: list[int] | frozenset[int] | None = None,
    spread_col: str | None = "spread",
    point_size: float = 0.01,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    trade_log: list[dict[str, Any]] | None = None,
    equity_out: list[float] | None = None,
    **_extra: Any,
) -> Metrics:
    """Simulate Asia-box sweep-fade with v2 entry_gap_policy."""
    n = len(d)
    if n == 0:
        return Metrics(0, 0, 0, 0, 0, 0, 0)

    box_hrs = frozenset(box_hours or BOX_HOURS)
    hunt_hrs = frozenset(hunt_hours or HUNT_HOURS)
    flat_h = int(flat_hour)

    open_ = d["open"].to_numpy(float)
    close = d["close"].to_numpy(float)
    high = d["high"].to_numpy(float)
    low = d["low"].to_numpy(float)
    hour = d["hour"].to_numpy(int) if "hour" in d.columns else np.zeros(n, dtype=int)
    day = d["day_id"].to_numpy() if "day_id" in d.columns else np.array([""] * n)
    if spread_col and spread_col in d.columns:
        spread_pts = np.nan_to_num(d[spread_col].to_numpy(float), nan=0.0)
    else:
        spread_pts = np.zeros(n)

    # Fail-closed no-overnight: only enter on days that have a flat-capable bar.
    days_with_flat_bar: set[str] = set()
    for j in range(n):
        if int(hour[j]) >= flat_h:
            days_with_flat_bar.add(str(day[j]))

    bal = float(START_BALANCE)
    eq = np.zeros(n)
    pnls: list[float] = []
    pos = 0  # +1 long, -1 short
    entry = sl = tp = lots = 0.0
    trade_cost = 0.0
    entered_day: str | None = None
    entry_bar = -1
    pos_day: str | None = None
    bal_at_entry = 0.0

    # Per-day box accumulation
    cur_day: str | None = None
    box_hi = np.nan
    box_lo = np.nan
    box_seen = False

    # Pending next-open fill from prior signal
    pending_dir = 0
    pending_sl = 0.0
    pending_tp = 0.0
    pending_box_hi = 0.0
    pending_box_lo = 0.0
    pending_signal_bar = -1

    def _reset_day(dkey: str) -> None:
        nonlocal cur_day, box_hi, box_lo, box_seen, pending_dir
        cur_day = dkey
        box_hi = np.nan
        box_lo = np.nan
        box_seen = False
        pending_dir = 0

    def _book_exit(i: int, exit_px: float, exit_reason: str) -> None:
        nonlocal bal, pos, lots, trade_cost, pos_day, entry_bar
        gross = (exit_px - entry) * CONTRACT_SIZE * lots * pos
        pnl = gross - trade_cost
        bal += pnl
        pnls.append(pnl)
        if trade_log is not None:
            trade_log.append(
                {
                    "entry_bar": entry_bar,
                    "exit_bar": i,
                    "direction": int(pos),
                    "entry": entry,
                    "exit": exit_px,
                    "sl": sl,
                    "tp": tp,
                    "lots": lots,
                    "trade_cost": trade_cost,
                    "gross": gross,
                    "pnl": pnl,
                    "bal_at_entry": bal_at_entry,
                    "bal_after_exit": bal,
                    "reason": exit_reason,
                }
            )
        pos = 0
        lots = 0.0
        trade_cost = 0.0
        pos_day = None
        entry_bar = -1
        eq[i] = bal

    for i in range(n):
        dkey = str(day[i])
        h_i = int(hour[i])
        px = float(close[i])
        op = float(open_[i])

        if cur_day != dkey:
            _reset_day(dkey)

        floating = bal + ((px - entry) * CONTRACT_SIZE * lots * pos if pos else 0.0)
        eq[i] = floating

        # Fail-closed: discard open position across day boundary.
        if pos != 0 and pos_day is not None and dkey != pos_day:
            pos = 0
            lots = 0.0
            trade_cost = 0.0
            pos_day = None
            entry_bar = -1
            eq[i] = bal

        # Fill pending entry at this bar's open (next_bar_open contract).
        if (
            pending_dir != 0
            and pos == 0
            and pending_signal_bar >= 0
            and i == pending_signal_bar + 1
        ):
            fill_ok = (
                dkey == str(day[pending_signal_bar])
                and h_i <= flat_h
                and entered_day != dkey
                and dkey in days_with_flat_bar
                and i >= WARMUP
            )
            # entry_gap_policy (v2)
            stop_dist = abs(op - pending_sl)
            beyond_sl = stop_dist <= 1e-12 or (
                (pending_dir > 0 and op < pending_sl)
                or (pending_dir < 0 and op > pending_sl)
            )
            beyond_tp = (pending_dir > 0 and op > pending_tp) or (
                pending_dir < 0 and op < pending_tp
            )
            degenerate = abs(pending_box_hi - pending_box_lo) <= 1e-12
            if fill_ok and not beyond_sl and not beyond_tp and not degenerate:
                risk_cash = bal * float(risk_pct)
                raw_lots = risk_cash / (stop_dist * CONTRACT_SIZE)
                lots_sz = _round_lots(raw_lots, max_lots)
                if not (
                    lots_sz < MIN_LOT
                    or stop_dist * CONTRACT_SIZE * MIN_LOT > risk_cash + 1e-9
                ):
                    trade_cost = (
                        (spread_pts[i] + 2.0 * float(slippage_points))
                        * float(point_size)
                        * CONTRACT_SIZE
                        * lots_sz
                        + 2.0 * float(commission_per_lot) * lots_sz
                    )
                    bal_at_entry = bal
                    pos = int(pending_dir)
                    entry = op
                    lots = lots_sz
                    sl = float(pending_sl)
                    tp = float(pending_tp)
                    entered_day = dkey
                    pos_day = dkey
                    entry_bar = i
                    eq[i] = bal + (
                        (px - entry) * CONTRACT_SIZE * lots * pos if pos else 0.0
                    )
            pending_dir = 0

        # Exits: allowed on entry bar (open fill). Priority SL > TP > time-flat.
        if pos != 0 and entry_bar >= 0 and i >= entry_bar:
            exit_px = None
            exit_reason = ""
            if pos > 0:
                if low[i] <= sl:
                    exit_px = sl
                    exit_reason = "sl"
                elif high[i] >= tp:
                    exit_px = tp
                    exit_reason = "tp"
                elif h_i >= flat_h:
                    exit_px = px
                    exit_reason = "time_flat"
            else:
                if high[i] >= sl:
                    exit_px = sl
                    exit_reason = "sl"
                elif low[i] <= tp:
                    exit_px = tp
                    exit_reason = "tp"
                elif h_i >= flat_h:
                    exit_px = px
                    exit_reason = "time_flat"
            if exit_px is not None:
                _book_exit(i, float(exit_px), exit_reason)

        # Accumulate Asia box during hours 1..7.
        if h_i in box_hrs:
            if not box_seen:
                box_hi = float(high[i])
                box_lo = float(low[i])
                box_seen = True
            else:
                box_hi = max(box_hi, float(high[i]))
                box_lo = min(box_lo, float(low[i]))

        # Signal at hunt close only; schedule next-open fill. Flat-while-unswept.
        # Box complete once we are in hunt hours (past 7) with any box bars seen.
        box_defined = box_seen and h_i in hunt_hrs
        can_signal = (
            pos == 0
            and pending_dir == 0
            and i >= WARMUP
            and box_defined
            and entered_day != dkey
            and dkey in days_with_flat_bar
            and h_i in hunt_hrs
        )
        if can_signal:
            mid = 0.5 * (box_hi + box_lo)
            long_sig = float(low[i]) < box_lo and float(close[i]) > box_lo
            short_sig = float(high[i]) > box_hi and float(close[i]) < box_hi
            # Prefer long if both (pathological); charter implies mutually exclusive
            # for a well-formed box, but freeze one deterministic choice.
            if long_sig and not short_sig:
                pending_dir = 1
                pending_sl = float(box_lo)
                pending_tp = float(mid)
                pending_box_hi = float(box_hi)
                pending_box_lo = float(box_lo)
                pending_signal_bar = i
            elif short_sig and not long_sig:
                pending_dir = -1
                pending_sl = float(box_hi)
                pending_tp = float(mid)
                pending_box_hi = float(box_hi)
                pending_box_lo = float(box_lo)
                pending_signal_bar = i

    # End-of-series: book only if still on entry day.
    if pos != 0 and pos_day is not None and str(day[-1]) == pos_day:
        _book_exit(n - 1, float(close[-1]), "end_of_series")

    if equity_out is not None:
        equity_out.clear()
        equity_out.extend(float(x) for x in eq.tolist())

    return metrics_from_pnls(pnls, eq)


def classic_pass(m: Any) -> bool:
    from xau_null_core import hard_pass_classic, metrics_dict

    return hard_pass_classic(metrics_dict(m))


def soft_pass(m: Any) -> bool:
    from xau_null_core import metrics_dict

    md = metrics_dict(m)
    return (
        int(md["n_trades"]) >= 20
        and float(md["profit_factor"]) >= 1.1
        and float(md["net_profit"]) > 0.0
        and float(md["max_drawdown_pct"]) <= 25.0
    )
