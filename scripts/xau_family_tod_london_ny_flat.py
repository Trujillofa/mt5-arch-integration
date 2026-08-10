#!/usr/bin/env python3
"""Zero-knob London–NY overlap long, force flat end of session.

Charter: ``results/xau_charters/2026-08-10_tod_london_ny_flat_v1.json``

* Entry: long at close of server hour 13 if flat (one per day).
* SL 1.5 ATR / TP 2.0 ATR (fixed).
* Exit: SL/TP or force flat at close of hour 16 same day (intraday flat).
* Grid cardinality 1 (no free knobs).

SAFETY: offline only. Null for this family must be day_block_shuffle (charter).
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

FAMILY = "tod_london_ny_flat"
NAME = FAMILY
kill_label = "KILL_TOD_LONDON_NY_FLAT"
use_soft_primary = True

ENTRY_HOUR = 13
FLAT_HOUR = 16
SL_ATR = 1.5
TP_ATR = 2.0
RISK_PCT = 0.01
MAX_LOTS = 0.5
ATR_PERIOD = 14


def prepare(raw: pd.DataFrame) -> pd.DataFrame:
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
    """Exactly one config — zero free knobs."""
    return [
        {
            "entry_hour": ENTRY_HOUR,
            "flat_hour": FLAT_HOUR,
            "sl_atr": SL_ATR,
            "tp_atr": TP_ATR,
            "risk_pct": RISK_PCT,
            "max_lots": MAX_LOTS,
        }
    ]


def grid(*, max_n: int = 1200, seed: int = 42) -> list[dict]:
    _ = max_n, seed
    return build_grid()


def simulate(
    d: pd.DataFrame,
    *,
    entry_hour: int = ENTRY_HOUR,
    flat_hour: int = FLAT_HOUR,
    sl_atr: float = SL_ATR,
    tp_atr: float = TP_ATR,
    risk_pct: float = RISK_PCT,
    max_lots: float = MAX_LOTS,
    spread_col: str | None = "spread",
    point_size: float = 0.01,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    **_extra: Any,
) -> Metrics:
    n = len(d)
    if n == 0:
        return Metrics(0, 0, 0, 0, 0, 0, 0)
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

    bal = START_BALANCE
    eq = np.zeros(n)
    pnls: list[float] = []
    pos = 0
    entry = sl = tp = lots = 0.0
    trade_cost = 0.0
    entered_day: str | None = None
    warmup = max(ATR_PERIOD + 5, 20)

    for i in range(n):
        px = close[i]
        floating = bal + ((px - entry) * CONTRACT_SIZE * lots * pos if pos else 0.0)
        eq[i] = floating

        if pos != 0 and i >= 1 and not np.isnan(atr[i]):
            exit_px = None
            if low[i] <= sl:
                exit_px = sl
            elif high[i] >= tp:
                exit_px = tp
            elif int(hour[i]) >= int(flat_hour):
                # force flat at/after flat hour close
                exit_px = px
            if exit_px is not None:
                pnl = (exit_px - entry) * CONTRACT_SIZE * lots * pos - trade_cost
                bal += pnl
                pnls.append(pnl)
                pos = 0
                lots = 0.0
                trade_cost = 0.0
                eq[i] = bal

        if pos != 0 or i < warmup:
            continue
        if np.isnan(atr[i]) or atr[i] <= 0:
            continue
        # one entry per day at session open hour
        if int(hour[i]) != int(entry_hour):
            continue
        dkey = str(day[i])
        if entered_day == dkey:
            continue

        stop_dist = float(atr[i]) * float(sl_atr)
        if stop_dist <= 1e-9:
            continue
        risk_cash = bal * float(risk_pct)
        raw_lots = risk_cash / (stop_dist * CONTRACT_SIZE)
        lots = float(np.floor(raw_lots * 100 + 1e-12) / 100.0)
        lots = min(lots, float(max_lots))
        min_lot = 0.01
        if lots < min_lot or stop_dist * CONTRACT_SIZE * min_lot > risk_cash + 1e-9:
            continue

        trade_cost = (
            (spread_pts[i] + 2.0 * float(slippage_points)) * float(point_size) * CONTRACT_SIZE * lots
            + 2.0 * float(commission_per_lot) * lots
        )
        pos = 1
        entry = px
        sl = entry - stop_dist
        tp = entry + float(atr[i]) * float(tp_atr)
        entered_day = dkey

    if pos != 0:
        pnl = (close[-1] - entry) * CONTRACT_SIZE * lots * pos - trade_cost
        bal += pnl
        pnls.append(pnl)
        eq[-1] = bal

    return metrics_from_pnls(pnls, eq)


def classic_pass(m: Any) -> bool:
    """Unused when --charter is passed; harness overrides from charter."""
    from xau_null_core import hard_pass_classic, metrics_dict

    return hard_pass_classic(metrics_dict(m))


def soft_pass(m: Any) -> bool:
    """Charter soft: n>=20 PF>=1.1 NP>0 — harness prefers charter when provided."""
    from xau_null_core import metrics_dict

    md = metrics_dict(m)
    return (
        int(md["n_trades"]) >= 20
        and float(md["profit_factor"]) >= 1.1
        and float(md["net_profit"]) > 0.0
    )
