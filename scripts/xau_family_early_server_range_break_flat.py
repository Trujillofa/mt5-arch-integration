#!/usr/bin/env python3
"""Zero-knob same-day early-server-block range break long, intraday flat.

Charter (runnable): ``results/xau_charters/2026-08-10_early_server_range_break_flat_v2.json``

Execution contract (frozen v2):
* Wilder ATR14 via TR ewm(alpha=1/14, adjust=False); atr[i] at signal close.
* Early-block high: causal running max of high on same calendar day for hours 1–8.
* Long entry at close when hour in 9–15, flat, early_high defined, close > early_high.
* One entry per day; no trade if no early-block bars that day.
* Exits begin next bar: SL (low<=sl) before TP (high>=tp) before time-flat (hour>=16 at close).
* Lot floor 0.01 / max 0.5; RT costs on entry bar.

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

FAMILY = "early_server_range_break_flat"
NAME = FAMILY
kill_label = "KILL_EARLY_SERVER_RANGE_BREAK_FLAT"
use_soft_primary = True

EARLY_BLOCK_HOURS = frozenset(range(1, 9))  # 1..8
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
            "early_block_hours": sorted(EARLY_BLOCK_HOURS),
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
    early_block_hours: list[int] | frozenset[int] | None = None,
    entry_allowed_hours: list[int] | frozenset[int] | None = None,
    spread_col: str | None = "spread",
    point_size: float = 0.01,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    **_extra: Any,
) -> Metrics:
    """Simulate long early-range break with v2 execution contract."""
    n = len(d)
    if n == 0:
        return Metrics(0, 0, 0, 0, 0, 0, 0)

    early_hrs = frozenset(early_block_hours or EARLY_BLOCK_HOURS)
    entry_hrs = frozenset(entry_allowed_hours or ENTRY_ALLOWED_HOURS)

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

    bal = START_BALANCE
    eq = np.zeros(n)
    pnls: list[float] = []
    pos = 0
    entry = sl = tp = lots = 0.0
    trade_cost = 0.0
    entered_day: str | None = None
    early_high: float | None = None
    early_day: str | None = None
    entry_bar: int = -1  # bar index of last entry; exits only for i > entry_bar
    pos_day: str | None = None  # calendar day of open position (overnight guard)

    for i in range(n):
        dkey = str(day[i])
        h_i = int(hour[i])
        px = close[i]

        # Daily reset of early-block high (causal per calendar day)
        if early_day != dkey:
            early_day = dkey
            early_high = None

        if h_i in early_hrs:
            hi = float(high[i])
            early_high = hi if early_high is None else max(early_high, hi)

        floating = bal + ((px - entry) * CONTRACT_SIZE * lots * pos if pos else 0.0)
        eq[i] = floating

        # Fail-closed: never evaluate overnight bars for an open position.
        # Positions must be flattened by hour>=flat_hour on the entry day; if a
        # day boundary is crossed while still open, discard the open trade
        # (no overnight fill rule is frozen) so it cannot hit next-day SL/TP.
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
            if low[i] <= sl:
                exit_px = sl
            elif high[i] >= tp:
                exit_px = tp
            elif h_i >= flat_h:
                exit_px = px
            if exit_px is not None:
                pnl = (exit_px - entry) * CONTRACT_SIZE * lots * pos - trade_cost
                bal += pnl
                pnls.append(pnl)
                pos = 0
                lots = 0.0
                trade_cost = 0.0
                pos_day = None
                eq[i] = bal

        if pos != 0 or i < WARMUP:
            continue
        if np.isnan(atr[i]) or atr[i] <= 0:
            continue
        # No early-block bars → early_high undefined → no trade
        if early_high is None:
            continue
        if h_i not in entry_hrs:
            continue
        if entered_day == dkey:
            continue
        # Fail-closed no-overnight: day must have a bar hour >= flat_hour
        if dkey not in days_with_flat_bar:
            continue
        # Strict close > early_high
        if not (px > float(early_high)):
            continue

        stop_dist = float(atr[i]) * float(sl_atr)
        if stop_dist <= 1e-9:
            continue
        risk_cash = bal * float(risk_pct)
        raw_lots = risk_cash / (stop_dist * CONTRACT_SIZE)
        lots = _round_lots(raw_lots, max_lots)
        if lots < MIN_LOT or stop_dist * CONTRACT_SIZE * MIN_LOT > risk_cash + 1e-9:
            continue

        trade_cost = (
            (spread_pts[i] + 2.0 * float(slippage_points))
            * float(point_size)
            * CONTRACT_SIZE
            * lots
            + 2.0 * float(commission_per_lot) * lots
        )
        pos = 1
        entry = px
        sl = entry - stop_dist
        tp = entry + float(atr[i]) * float(tp_atr)
        entered_day = dkey
        pos_day = dkey
        entry_bar = i

    # End-of-series: only book a final exit if still on the entry day (no overnight).
    if pos != 0 and pos_day is not None and str(day[-1]) == pos_day:
        pnl = (close[-1] - entry) * CONTRACT_SIZE * lots * pos - trade_cost
        bal += pnl
        pnls.append(pnl)
        eq[-1] = bal

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
