#!/usr/bin/env python3
"""Zero-knob same-day day-open undercut reclaim long, intraday flat.

Charter (runnable): ``results/xau_charters/2026-08-11_day_open_reclaim_flat_v2.json``

Execution contract (frozen v2):
* Wilder ATR14 via TR ewm(alpha=1/14, adjust=False); atr[i] at signal close.
* day_open = open of first printed H1 bar of the calendar day.
* undercut_seen_before_i = any(low[j] < day_open for j < i) same day (prior bars only).
* Long reclaim at close when hour in 9–15, flat, undercut_seen_before_i, close > day_open.
* Same-bar undercut+reclaim does not qualify.
* One entry per day; exits begin next bar: SL before TP before time-flat (hour>=16).
* Lot floor 0.01 / max 0.5; RT cost measured at entry, deducted at exit booking.
* start_balance=10000; realized-balance compounding.

Hours are server labels only — not Tokyo/Asia or London–NY wall-clock claims.

SAFETY: offline only. No --live.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from backtest import (
    CONTRACT_SIZE,
    START_BALANCE,
    Metrics,
    metrics_from_pnls,
)

FAMILY = "day_open_reclaim_flat"
NAME = FAMILY
kill_label = "KILL_DAY_OPEN_RECLAIM_FLAT"
use_soft_primary = True

ENTRY_ALLOWED_HOURS = frozenset(range(9, 16))  # 9..15
FLAT_HOUR = 16
SL_ATR = 1.5
TP_ATR = 2.0
RISK_PCT = 0.01
MAX_LOTS = 0.5
MIN_LOT = 0.01
ATR_PERIOD = 14
WARMUP = max(ATR_PERIOD + 5, 20)


def prepare(raw: pd.DataFrame) -> pd.DataFrame:
    """Add hour/day_id and Wilder ATR14 (ewm alpha=1/14)."""
    d = raw.copy()
    if "time" in d.columns:
        d["time"] = pd.to_datetime(d["time"], utc=True)
        d["hour"] = d["time"].dt.hour
        d["day_id"] = d["time"].dt.strftime("%Y-%m-%d")
    h = d["high"].astype(float)
    lo = d["low"].astype(float)
    c = d["close"].astype(float)
    prev = c.shift(1)
    tr = pd.concat([(h - lo), (h - prev).abs(), (lo - prev).abs()], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1 / ATR_PERIOD, adjust=False).mean()
    return d


def build_grid() -> list[dict]:
    """Exactly one config — zero free knobs (charter search_cardinality=1)."""
    return [
        {
            "flat_hour": FLAT_HOUR,
            "sl_atr": SL_ATR,
            "tp_atr": TP_ATR,
            "risk_pct": RISK_PCT,
            "max_lots": MAX_LOTS,
            "entry_allowed_hours": sorted(ENTRY_ALLOWED_HOURS),
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
    sl_atr: float = SL_ATR,
    tp_atr: float = TP_ATR,
    risk_pct: float = RISK_PCT,
    max_lots: float = MAX_LOTS,
    entry_allowed_hours: list[int] | frozenset[int] | None = None,
    spread_col: str | None = "spread",
    point_size: float = 0.01,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    trade_log: list[dict[str, Any]] | None = None,
    equity_out: list[float] | None = None,
    **_extra: Any,
) -> Metrics:
    """Simulate long day-open reclaim with v2 execution contract.

    Optional ``trade_log`` collects per-trade dicts for fixture assertions.
    Optional ``equity_out`` is filled with per-bar equity (same length as ``d``).
    """
    n = len(d)
    if n == 0:
        return Metrics(0, 0, 0, 0, 0, 0, 0)

    entry_hrs = frozenset(entry_allowed_hours or ENTRY_ALLOWED_HOURS)

    open_ = d["open"].to_numpy(float)
    close = d["close"].to_numpy(float)
    high = d["high"].to_numpy(float)
    low = d["low"].to_numpy(float)
    atr = d["atr"].to_numpy(float)
    hour = d["hour"].to_numpy(int) if "hour" in d.columns else np.zeros(n, dtype=int)
    day = d["day_id"].to_numpy() if "day_id" in d.columns else np.array([""] * n)
    if spread_col and spread_col in d.columns:
        spread_pts = np.nan_to_num(d[spread_col].to_numpy(float), nan=0.0)
    else:
        spread_pts = np.zeros(n)

    # Fail-closed no-overnight: only enter on calendar days that have a bar
    # with hour >= flat_hour so time-flat can fire without carrying overnight.
    flat_h = int(flat_hour)
    days_with_flat_bar: set[str] = set()
    for j in range(n):
        if int(hour[j]) >= flat_h:
            days_with_flat_bar.add(str(day[j]))

    bal = float(START_BALANCE)
    eq = np.zeros(n)
    pnls: list[float] = []
    pos = 0
    entry = sl = tp = lots = 0.0
    trade_cost = 0.0
    entered_day: str | None = None
    day_open_px: float | None = None
    day_open_day: str | None = None
    undercut_seen = False  # sticky: prior bars only for entry at i
    entry_bar: int = -1
    pos_day: str | None = None
    bal_at_entry = 0.0

    for i in range(n):
        dkey = str(day[i])
        h_i = int(hour[i])
        px = close[i]

        # Calendar-day reset: day_open = open of first printed bar that day.
        if day_open_day != dkey:
            day_open_day = dkey
            day_open_px = float(open_[i])
            undercut_seen = False

        floating = bal + ((px - entry) * CONTRACT_SIZE * lots * pos if pos else 0.0)
        eq[i] = floating

        # Fail-closed: discard open position across day boundary (no overnight).
        if pos != 0 and pos_day is not None and dkey != pos_day:
            pos = 0
            lots = 0.0
            trade_cost = 0.0
            pos_day = None
            entry_bar = -1
            eq[i] = bal

        # Exits: open positions only; never on entry bar (i > entry_bar)
        if pos != 0 and i > entry_bar and not np.isnan(atr[i]):
            exit_px = None
            exit_reason = ""
            if low[i] <= sl:
                exit_px = sl
                exit_reason = "sl"
            elif high[i] >= tp:
                exit_px = tp
                exit_reason = "tp"
            elif h_i >= flat_h:
                exit_px = px
                exit_reason = "time_flat"
            if exit_px is not None:
                gross = (exit_px - entry) * CONTRACT_SIZE * lots * pos
                pnl = gross - trade_cost
                bal += pnl
                pnls.append(pnl)
                if trade_log is not None:
                    trade_log.append(
                        {
                            "entry_bar": entry_bar,
                            "exit_bar": i,
                            "entry": entry,
                            "exit": exit_px,
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
                eq[i] = bal

        # Entry uses undercut_seen from prior bars only (j < i).
        undercut_before_i = undercut_seen
        can_enter = (
            pos == 0
            and i >= WARMUP
            and not np.isnan(atr[i])
            and atr[i] > 0
            and day_open_px is not None
            and undercut_before_i
            and h_i in entry_hrs
            and entered_day != dkey
            and dkey in days_with_flat_bar
            and px > float(day_open_px)
        )
        if can_enter:
            stop_dist = float(atr[i]) * float(sl_atr)
            if stop_dist > 1e-9:
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
                    # Balance unchanged at entry (cost stored, deducted at exit).
                    bal_at_entry = bal
                    pos = 1
                    entry = px
                    lots = lots_sz
                    sl = entry - stop_dist
                    tp = entry + float(atr[i]) * float(tp_atr)
                    entered_day = dkey
                    pos_day = dkey
                    entry_bar = i
                    # Equity while open at entry close: floating may be 0 at fill.
                    eq[i] = bal + (
                        (px - entry) * CONTRACT_SIZE * lots * pos if pos else 0.0
                    )

        # After entry evaluation: update sticky undercut for subsequent bars.
        if day_open_px is not None and float(low[i]) < float(day_open_px):
            undercut_seen = True

    # End-of-series: only book a final exit if still on the entry day (no overnight).
    if pos != 0 and pos_day is not None and str(day[-1]) == pos_day:
        gross = (close[-1] - entry) * CONTRACT_SIZE * lots * pos
        pnl = gross - trade_cost
        bal += pnl
        pnls.append(pnl)
        if trade_log is not None:
            trade_log.append(
                {
                    "entry_bar": entry_bar,
                    "exit_bar": n - 1,
                    "entry": entry,
                    "exit": float(close[-1]),
                    "lots": lots,
                    "trade_cost": trade_cost,
                    "gross": gross,
                    "pnl": pnl,
                    "bal_at_entry": bal_at_entry,
                    "bal_after_exit": bal,
                    "reason": "end_of_series",
                }
            )
        eq[-1] = bal

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
    )
