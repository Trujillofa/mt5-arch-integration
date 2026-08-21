#!/usr/bin/env python3
"""Zero-knob fade of last daily close-to-close after 5d/20d variance expansion.

Charter (runnable):
``results/xau_charters/2026-08-20_multi_day_variance_expansion_flat_v1.json``

Execution contract (frozen v1):
* Clock: server_clock_as_stored (no DST). Hours are flatten/fill eligibility only.
* Completed-day last H1 close C_D; r_D = ln(C_D / C_{D-1}).
* short_var = sample var (ddof=1) of last 5 completed daily log returns;
  long_var last 20. Day T excluded. Need 21 completed days (20 returns).
* Expansion iff long_var > 0 and short_var / long_var >= 1.5.
* Fade only: C_{T-1} > C_{T-2} → short; < → long; = skip.
* Signal at close of the first printed H1 of day T; fill open[i+1] if same
  calendar day and hour[i+1] <= 16.
* SL dist = |C_{T-1} - O_{T-1}| (first-bar open of prior day); TP = 2R.
  Skip if SL dist <= 0.
* entry_gap_policy: evaluate at fill open BEFORE sizing, using provisional
  SL/TP from the **signal-bar close** (not the fill). Actual entry = fill
  open; actual SL/TP = entry ± dist / ± 2R.
* Flat hour 16. Intraday flat. One entry/day. First eligible exit is the
  fill bar, then later same-day bars until hour 16. SL before TP.
* Lot floor 0.01 / max 0.5; RT cost measured at entry, deducted at exit.
* start_balance=10000; realized-balance compounding.

Rejected sister (do not implement): asia_box_london_sweep_fade_flat.

SAFETY: offline only. No --live. No develop screen without separate AUTHORIZE.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from backtest import (
    CONTRACT_SIZE,
    START_BALANCE,
    Metrics,
    metrics_from_pnls,
)

FAMILY = "multi_day_variance_expansion_flat"
NAME = FAMILY
kill_label = "KILL_MULTI_DAY_VARIANCE_EXPANSION_FLAT"
use_soft_primary = True

# Rejected Stage-2 sister — do not implement or flip (SCREEN_FAIL 2026-08-19).
REJECTED_SISTER = "asia_box_london_sweep_fade_flat"

FLAT_HOUR = 16
SHORT_N = 5
LONG_N = 20
EXPANSION_RATIO = 1.5
RR = 2.0
RISK_PCT = 0.01
MAX_LOTS = 0.5
MIN_LOT = 0.01
WARMUP_COMPLETED_DAYS = 21


def prepare(raw: pd.DataFrame) -> pd.DataFrame:
    """Add hour/day_id from stored timestamps (server_clock_as_stored)."""
    d = raw.copy()
    if "time" in d.columns:
        d["time"] = pd.to_datetime(d["time"], utc=True)
        d["hour"] = d["time"].dt.hour
        d["day_id"] = d["time"].dt.strftime("%Y-%m-%d")
    return d


def build_grid() -> list[dict]:
    """Exactly one config — zero free knobs (charter search_cardinality=1)."""
    return [
        {
            "flat_hour": FLAT_HOUR,
            "short_n": SHORT_N,
            "long_n": LONG_N,
            "expansion_ratio": EXPANSION_RATIO,
            "rr": RR,
        }
    ]


def grid(*, max_n: int = 1200, seed: int = 42) -> list[dict]:
    _ = max_n, seed
    return build_grid()


def _round_lots(raw_lots: float, max_lots: float) -> float:
    lots = float(np.floor(raw_lots * 100 + 1e-12) / 100.0)
    return min(lots, float(max_lots))


def _completed_day_signal(
    prior_ids: list[str],
    first_open: dict[str, float],
    last_close: dict[str, float],
    *,
    short_n: int,
    long_n: int,
    expansion_ratio: float,
    warmup_days: int = WARMUP_COMPLETED_DAYS,
) -> tuple[int, float] | None:
    """Fade direction (+1 long / -1 short) and SL dist, or None if ineligible."""
    if len(prior_ids) < int(warmup_days):
        return None
    closes = [float(last_close[d]) for d in prior_ids]
    rets: list[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev <= 0.0:
            continue
        rets.append(math.log(closes[i] / prev))
    if len(rets) < int(long_n) or int(short_n) < 2:
        return None
    short_var = float(np.var(np.asarray(rets[-int(short_n) :], dtype=float), ddof=1))
    long_var = float(np.var(np.asarray(rets[-int(long_n) :], dtype=float), ddof=1))
    if not (long_var > 0.0 and short_var / long_var >= float(expansion_ratio)):
        return None
    c_tm1 = closes[-1]
    c_tm2 = closes[-2]
    if c_tm1 == c_tm2:
        return None
    direction = -1 if c_tm1 > c_tm2 else 1
    sl_dist = abs(c_tm1 - float(first_open[prior_ids[-1]]))
    if sl_dist <= 0.0:
        return None
    return direction, sl_dist


def simulate(
    d: pd.DataFrame,
    *,
    flat_hour: int = FLAT_HOUR,
    short_n: int = SHORT_N,
    long_n: int = LONG_N,
    expansion_ratio: float = EXPANSION_RATIO,
    rr: float = RR,
    risk_pct: float = RISK_PCT,
    max_lots: float = MAX_LOTS,
    spread_col: str | None = "spread",
    point_size: float = 0.01,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    trade_log: list[dict[str, Any]] | None = None,
    equity_out: list[float] | None = None,
    **_extra: Any,
) -> Metrics:
    """Simulate variance-expansion fade with next-open fill and gap policy."""
    n = len(d)
    if n == 0:
        return Metrics(0, 0, 0, 0, 0, 0, 0)

    flat_h = int(flat_hour)
    sn = int(short_n)
    ln_ = int(long_n)
    ratio = float(expansion_ratio)
    rr_f = float(rr)

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

    order: list[str] = []
    first_idx: dict[str, int] = {}
    last_idx: dict[str, int] = {}
    first_open: dict[str, float] = {}
    last_close: dict[str, float] = {}
    for i in range(n):
        dk = str(day[i])
        if dk not in first_idx:
            first_idx[dk] = i
            first_open[dk] = float(open_[i])
            order.append(dk)
        last_close[dk] = float(close[i])
        last_idx[dk] = i

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

    pending_dir = 0
    pending_sl_dist = 0.0
    pending_signal_close = 0.0
    pending_signal_bar = -1

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
            )
            sl_dist = float(pending_sl_dist)
            sig_c = float(pending_signal_close)
            # entry_gap_policy: provisional SL/TP from signal-bar close, evaluated
            # at fill_bar_open BEFORE sizing. Using fill as both entry and gap
            # check would make open-beyond-own-SL/TP vacuous (entry ± dist is
            # never beyond the fill by construction). Actual SL/TP after a
            # pass are still entry ± dist / ± 2R.
            if pending_dir > 0:
                beyond_sl = op < sig_c - sl_dist
                beyond_tp = op > sig_c + rr_f * sl_dist
            else:
                beyond_sl = op > sig_c + sl_dist
                beyond_tp = op < sig_c - rr_f * sl_dist
            degenerate = sl_dist <= 0.0
            if fill_ok and not beyond_sl and not beyond_tp and not degenerate:
                risk_cash = bal * float(risk_pct)
                raw_lots = risk_cash / (sl_dist * CONTRACT_SIZE)
                lots_sz = _round_lots(raw_lots, max_lots)
                if not (
                    lots_sz < MIN_LOT
                    or sl_dist * CONTRACT_SIZE * MIN_LOT > risk_cash + 1e-9
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
                    if pos > 0:
                        sl = entry - sl_dist
                        tp = entry + rr_f * sl_dist
                    else:
                        sl = entry + sl_dist
                        tp = entry - rr_f * sl_dist
                    entered_day = dkey
                    pos_day = dkey
                    entry_bar = i
                    eq[i] = bal + (
                        (px - entry) * CONTRACT_SIZE * lots * pos if pos else 0.0
                    )
            pending_dir = 0

        # Exits: allowed on fill/entry bar. Priority SL > TP > time-flat.
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

        # Signal only on the first printed H1 of day T (one pending / day).
        if (
            i == first_idx.get(dkey, -1)
            and pos == 0
            and pending_dir == 0
            and entered_day != dkey
        ):
            t_idx = order.index(dkey)
            sig = _completed_day_signal(
                order[:t_idx],
                first_open,
                last_close,
                short_n=sn,
                long_n=ln_,
                expansion_ratio=ratio,
            )
            if sig is not None:
                pending_dir, pending_sl_dist = sig
                pending_signal_close = px
                pending_signal_bar = i

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
    """Charter soft primary: n≥40, PF≥1.2, NP>0, DD≤15% (not day_open 20/1.1)."""
    from xau_null_core import metrics_dict

    md = metrics_dict(m)
    return (
        int(md["n_trades"]) >= 40
        and float(md["profit_factor"]) >= 1.2
        and float(md["net_profit"]) > 0.0
        and float(md["max_drawdown_pct"]) <= 15.0
    )
