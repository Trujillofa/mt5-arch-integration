#!/usr/bin/env python3
"""Causal BTCUSD H1 range + volatility-expansion breakout.

Closed-bar close-through of ``donchian_prior`` (i-n .. i-1) only when
ATR14/ATR50 at i-1 is squeezed and TR[i] expands vs ATR14[i-1].
No EMA, no H4, no RSI/MACD, no sweep labels.

Pivots / Fib are not used. Do not import ``htf_fib_core``.

SAFETY: offline research only. No orders.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from btc_trend_pullback_core import (  # noqa: E402
    FROZEN_COMMISSION,
    FROZEN_CONTRACT,
    FROZEN_LOTS,
    FROZEN_MAX_SPREAD_POINTS,
    FROZEN_POINT,
    FROZEN_SLIPPAGE_POINTS,
    HOLDOUT_START,
    MAX_DD_PCT_MAX,
    N_TRADES_MIN,
    PF_MIN,
    START_BALANCE,
    frozen_cost_spec,
    require_frozen_btc_book,
    split_btc,
)
from us_index_session_core import wilder_atr  # noqa: E402
from us_index_session_htf import donchian_prior  # noqa: E402

SEARCH_ID = "btc_h1_range_vol_breakout_v1"
SELECT_END = date(2026, 1, 1)
ATR_FAST = 14
ATR_SLOW = 50
TP_RR = 2.0

__all__ = [
    "ATR_FAST",
    "ATR_SLOW",
    "FROZEN_COMMISSION",
    "FROZEN_CONTRACT",
    "FROZEN_LOTS",
    "FROZEN_MAX_SPREAD_POINTS",
    "FROZEN_POINT",
    "FROZEN_SLIPPAGE_POINTS",
    "HOLDOUT_START",
    "MAX_DD_PCT_MAX",
    "N_TRADES_MIN",
    "PF_MIN",
    "SEARCH_ID",
    "SELECT_END",
    "START_BALANCE",
    "TP_RR",
    "breakout_signals",
    "frozen_cost_spec",
    "range_known_at_prior_bars",
    "refuse_mutated_btc_book",
    "require_frozen_btc_book",
    "split_btc",
    "true_range",
]


def refuse_mutated_btc_book(lock: dict) -> None:
    if lock.get("promote") is True:
        raise SystemExit("promote must stay false")
    if lock.get("live_go") is True:
        raise SystemExit("live_go must stay false")
    if lock.get("search_id") != SEARCH_ID:
        raise SystemExit(f"search_id must be {SEARCH_ID}")
    lots = lock.get("lots")
    if lots is not None and float(lots) != FROZEN_LOTS:
        raise SystemExit(f"frozen BTC book lots must be {FROZEN_LOTS:g}")
    costs = lock.get("costs") if isinstance(lock.get("costs"), dict) else {}
    slip = costs.get("slippage_points")
    if slip is not None and float(slip) != FROZEN_SLIPPAGE_POINTS:
        raise SystemExit(
            f"frozen BTC slippage_points must be {FROZEN_SLIPPAGE_POINTS:g}"
        )
    cost_lots = costs.get("lots")
    if cost_lots is not None and float(cost_lots) != FROZEN_LOTS:
        raise SystemExit(f"frozen BTC book lots must be {FROZEN_LOTS:g}")
    point = costs.get("point_size")
    if point is not None and float(point) != FROZEN_POINT:
        raise SystemExit(f"frozen BTC point_size must be {FROZEN_POINT}")
    contract = costs.get("contract_size")
    if contract is not None and float(contract) != FROZEN_CONTRACT:
        raise SystemExit(f"frozen BTC contract_size must be {FROZEN_CONTRACT}")
    if lock.get("families", {}).get("h1_range_vol_breakout", {}).get("use_ema") is True:
        raise SystemExit("use_ema must stay false — v1 EMA stack is sealed")
    if lock.get("families", {}).get("h1_range_vol_breakout", {}).get("use_h4") is True:
        raise SystemExit("use_h4 must stay false")


def true_range(
    high: np.ndarray, low: np.ndarray, close: np.ndarray
) -> np.ndarray:
    h = np.asarray(high, dtype=float)
    low_a = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    n = int(h.shape[0])
    tr = np.empty(n, dtype=float)
    if n == 0:
        return tr
    tr[0] = h[0] - low_a[0]
    for i in range(1, n):
        tr[i] = max(h[i] - low_a[i], abs(h[i] - c[i - 1]), abs(low_a[i] - c[i - 1]))
    return tr


def range_known_at_prior_bars(
    high: np.ndarray, low: np.ndarray, i: int, n: int
) -> tuple[float, float]:
    """Prior-N high/low used at bar ``i`` — ``high[i]`` / ``low[i]`` excluded."""
    if i < n:
        return float("nan"), float("nan")
    window_h = np.asarray(high, dtype=float)[i - n : i]
    window_l = np.asarray(low, dtype=float)[i - n : i]
    return float(np.max(window_h)), float(np.min(window_l))


def breakout_signals(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    *,
    range_n: int,
    squeeze_max: float,
    expand_min: float,
    allow_shorts: bool = True,
    exclude_forming: bool = True,
) -> np.ndarray:
    """Ternary +1/−1/0 on closed H1. Last bar is 0 when exclude_forming."""
    c = np.asarray(close, dtype=float)
    h = np.asarray(high, dtype=float)
    l = np.asarray(low, dtype=float)
    n = int(c.shape[0])
    out = np.zeros(n, dtype=np.int8)
    need = max(int(range_n), ATR_SLOW) + 2
    if n < need + 2:
        return out
    rh, rl = donchian_prior(h, l, int(range_n))
    atr_fast = wilder_atr(h, l, c, ATR_FAST)
    atr_slow = wilder_atr(h, l, c, ATR_SLOW)
    tr = true_range(h, l, c)
    last = n - 1 if exclude_forming else n

    def _setup_at(i: int, side: int) -> bool:
        if i < 1 or i >= n:
            return False
        a1 = float(atr_fast[i - 1])
        a2 = float(atr_slow[i - 1])
        hi = float(rh[i])
        lo = float(rl[i])
        px = float(c[i])
        rng = float(tr[i])
        if not (
            np.isfinite(a1)
            and np.isfinite(a2)
            and np.isfinite(hi)
            and np.isfinite(lo)
            and np.isfinite(px)
            and np.isfinite(rng)
            and a1 > 0.0
            and a2 > 0.0
            and rng > 0.0
        ):
            return False
        if (a1 / a2) > float(squeeze_max):
            return False
        if (rng / a1) < float(expand_min):
            return False
        if side > 0:
            return px > hi
        if not allow_shorts:
            return False
        return px < lo

    for i in range(need, last):
        long_now = _setup_at(i, 1)
        short_now = _setup_at(i, -1)
        if long_now and not _setup_at(i - 1, 1):
            out[i] = 1
        elif short_now and not _setup_at(i - 1, -1):
            out[i] = -1
    return out
