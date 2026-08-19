#!/usr/bin/env python3
"""Causal H1/H4 helpers for US100 v8 (offline research).

M5 session-scalp helpers stay in ``us_index_session_core.py``. This module
owns BB/KC squeeze, prior-bar Donchian, completed Daily SMA50, H4 impulses
(via ``htf_fib_core.confirmed_pivots``), and a multi-day H1 walk.

SAFETY: offline research only. No orders.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from htf_fib_core import (  # noqa: E402
    confirmed_pivots,
    confirmed_pivots_with_centers,
    fib_level,
    walk_swing_and_fibs,
)
from us_index_session_backtest import CostSpec, Trade, _round_trip_cost  # noqa: E402
from us_index_session_core import ema_series, to_et, to_utc, wilder_atr  # noqa: E402

H1_SECONDS = 3600
H4_SECONDS = 14400
DAILY_SECONDS = 86400
BB_PERIOD = 20
KC_PERIOD = 20
DONCH_N = 20
SMA50 = 50
FIB_LO = 0.618
FIB_HI = 0.786
FRIDAY_CUTOFF_MIN = 14 * 60


@dataclass(frozen=True)
class H4Impulse:
    direction: int
    origin: float
    extreme: float
    confirm_i: int
    confirm_close_ts: float
    origin_center: int
    extreme_center: int
    atr: float
    fib_lo: float
    fib_hi: float
    sl: float
    tp: float


def _ts(t: datetime) -> float:
    return to_utc(t).timestamp()


def friday_last_mask(dow: np.ndarray) -> np.ndarray:
    n = len(dow)
    out = np.zeros(n, dtype=bool)
    for i in range(n):
        if int(dow[i]) == 4 and (i + 1 >= n or int(dow[i + 1]) != 4):
            out[i] = True
    return out


def friday_blocked(dow: int, mins: int, is_friday_last: bool) -> bool:
    if int(dow) != 4:
        return False
    return int(mins) >= FRIDAY_CUTOFF_MIN or bool(is_friday_last)


def bollinger(close: np.ndarray, period: int = BB_PERIOD, k: float = 2.0) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(close, dtype=float)
    n = len(x)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    if n < period:
        return upper, lower
    win = sliding_window_view(x, period)
    mid = np.mean(win, axis=1)
    std = np.std(win, axis=1, ddof=1)
    upper[period - 1 :] = mid + float(k) * std
    lower[period - 1 :] = mid - float(k) * std
    return upper, lower


def keltner(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    period: int = KC_PERIOD,
    atr_mult: float = 1.5,
) -> tuple[np.ndarray, np.ndarray]:
    mid = ema_series(close, period)
    atr = wilder_atr(high, low, close, period)
    upper = mid + float(atr_mult) * atr
    lower = mid - float(atr_mult) * atr
    return upper, lower


def squeezed(
    bb_u: np.ndarray, bb_l: np.ndarray, kc_u: np.ndarray, kc_l: np.ndarray
) -> np.ndarray:
    return (
        np.isfinite(bb_u)
        & np.isfinite(bb_l)
        & np.isfinite(kc_u)
        & np.isfinite(kc_l)
        & (bb_u < kc_u)
        & (bb_l > kc_l)
    )


def donchian_prior(
    high: np.ndarray, low: np.ndarray, n: int = DONCH_N
) -> tuple[np.ndarray, np.ndarray]:
    """Channel from ``i-n .. i-1``. Index ``i`` is never inside the window."""
    h = np.asarray(high, dtype=float)
    l = np.asarray(low, dtype=float)
    out_h = np.full(len(h), np.nan)
    out_l = np.full(len(l), np.nan)
    if len(h) <= n:
        return out_h, out_l
    wh = sliding_window_view(h[:-1], n)
    wl = sliding_window_view(l[:-1], n)
    out_h[n:] = np.max(wh, axis=1)
    out_l[n:] = np.min(wl, axis=1)
    return out_h, out_l


def completed_daily_sma50_slope(
    h1_times: list[datetime],
    daily_times: list[datetime],
    daily_close: np.ndarray,
    period: int = SMA50,
) -> np.ndarray:
    """+1 rising / −1 falling / 0 flat-or-unknown.

    Last Daily with ``open + 86400 <= H1 open``. Today's D1 is forming.
    Slope compares SMA50 at that completed day vs the previous completed SMA50.
    """
    n = len(h1_times)
    out = np.zeros(n, dtype=np.int8)
    closes = np.asarray(daily_close, dtype=float)
    nd = len(closes)
    if nd < period + 1 or n == 0:
        return out
    sma = np.full(nd, np.nan)
    win = sliding_window_view(closes, period)
    sma[period - 1 :] = np.mean(win, axis=1)
    d_end = np.array([_ts(t) + DAILY_SECONDS for t in daily_times], dtype=np.float64)
    h1_open = np.array([_ts(t) for t in h1_times], dtype=np.float64)
    last = np.searchsorted(d_end, h1_open, side="right") - 1
    for i in range(n):
        j = int(last[i])
        if j < period:
            continue
        a = sma[j]
        b = sma[j - 1]
        if not (np.isfinite(a) and np.isfinite(b)):
            continue
        if a > b:
            out[i] = 1
        elif a < b:
            out[i] = -1
    return out


def squeeze_breakout_signals(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    mins: np.ndarray,
    keys: np.ndarray,
    dow: np.ndarray,
    slope: np.ndarray,
    *,
    bb_k: float,
    kc_atr_mult: float,
    one_per_day: bool,
    exclude_forming: bool = True,
) -> np.ndarray:
    n = len(close)
    out = np.zeros(n, dtype=np.int8)
    bb_u, bb_l = bollinger(close, BB_PERIOD, bb_k)
    kc_u, kc_l = keltner(close, high, low, KC_PERIOD, kc_atr_mult)
    sq = squeezed(bb_u, bb_l, kc_u, kc_l)
    release = np.zeros(n, dtype=bool)
    release[1:] = sq[:-1] & ~sq[1:]
    dh, dl = donchian_prior(high, low, DONCH_N)
    flast = friday_last_mask(dow)
    last = n - 1 if exclude_forming else n
    fired = -1
    for i in range(last):
        if friday_blocked(int(dow[i]), int(mins[i]), bool(flast[i])):
            continue
        if one_per_day and int(keys[i]) == fired:
            continue
        if not release[i]:
            continue
        c = float(close[i])
        hi = float(dh[i])
        lo = float(dl[i])
        if not (np.isfinite(c) and np.isfinite(hi) and np.isfinite(lo)):
            continue
        side = 0
        if c > hi:
            side = 1
        elif c < lo:
            side = -1
        else:
            continue
        sl = int(slope[i])
        if sl == 0 or side != sl:
            continue
        out[i] = side
        fired = int(keys[i])
    return out


def _unidirectional(
    close: np.ndarray, direction: int, origin_center: int, extreme_center: int
) -> bool:
    start = int(origin_center) + 1
    end = int(extreme_center)
    if start < 1 or end >= len(close) or start > end:
        return False
    for j in range(start, end + 1):
        a = float(close[j])
        b = float(close[j - 1])
        if not (np.isfinite(a) and np.isfinite(b)):
            return False
        if direction == 1 and a < b:
            return False
        if direction == -1 and a > b:
            return False
    return True


def h4_impulses(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    times: list[datetime],
    atr: np.ndarray,
    *,
    left: int,
    right: int,
    k: float,
    exclude_forming: bool = True,
) -> list[H4Impulse]:
    """Qualify H4 swings from ``confirmed_pivots`` + ``walk_swing_and_fibs``."""
    events = confirmed_pivots_with_centers(
        high, low, left, right, exclude_forming=exclude_forming
    )
    official = {
        int(idx): (int(d), float(a), float(b))
        for idx, d, a, b in walk_swing_and_fibs(events, FIB_LO, FIB_HI)
    }
    last_type = 0
    last_price = 0.0
    last_center = -1
    swing_hi = swing_lo = 0.0
    origin_center = extreme_center = -1
    direction = 0
    out: list[H4Impulse] = []

    for ev in events:
        idx = int(ev[0])
        price = float(ev[1])
        ptype = int(ev[2])
        center = int(ev[3])
        fib_changed = False
        if ptype == 1:
            if last_type == 0:
                last_type, last_price, last_center = 1, price, center
            elif last_type == 1:
                if price > last_price:
                    last_price = price
                    last_center = center
                    if direction == 1:
                        swing_hi = price
                        extreme_center = center
                        fib_changed = True
            else:
                if price > last_price:
                    swing_lo = last_price
                    swing_hi = price
                    origin_center = last_center
                    extreme_center = center
                    direction = 1
                    fib_changed = True
                last_type, last_price, last_center = 1, price, center
        else:
            if last_type == 0:
                last_type, last_price, last_center = -1, price, center
            elif last_type == -1:
                if price < last_price:
                    last_price = price
                    last_center = center
                    if direction == -1:
                        swing_lo = price
                        extreme_center = center
                        fib_changed = True
            else:
                if price < last_price:
                    swing_hi = last_price
                    swing_lo = price
                    origin_center = last_center
                    extreme_center = center
                    direction = -1
                    fib_changed = True
                last_type, last_price, last_center = -1, price, center

        if not (fib_changed and direction != 0 and swing_hi > swing_lo):
            continue
        got = official.get(idx)
        if got is None or int(got[0]) != int(direction):
            continue
        _d, fa, fb = got
        at = float(atr[idx]) if 0 <= idx < len(atr) else float("nan")
        rng = swing_hi - swing_lo
        if not (np.isfinite(at) and at > 0.0 and rng > float(k) * at):
            continue
        if not _unidirectional(close, direction, origin_center, extreme_center):
            continue
        origin = swing_lo if direction == 1 else swing_hi
        extreme = swing_hi if direction == 1 else swing_lo
        sl = origin - direction * 0.5 * at
        if idx >= len(times):
            continue
        out.append(
            H4Impulse(
                direction=direction,
                origin=float(origin),
                extreme=float(extreme),
                confirm_i=idx,
                confirm_close_ts=_ts(times[idx]) + H4_SECONDS,
                origin_center=int(origin_center),
                extreme_center=int(extreme_center),
                atr=at,
                fib_lo=float(min(fa, fb)),
                fib_hi=float(max(fa, fb)),
                sl=float(sl),
                tp=float(extreme),
            )
        )
    return out


def fib_pullback_signals(
    h1_close: np.ndarray,
    h1_high: np.ndarray,
    h1_low: np.ndarray,
    h1_times: list[datetime],
    mins: np.ndarray,
    dow: np.ndarray,
    impulses: list[H4Impulse],
    *,
    entry: str,
    exclude_forming: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(h1_close)
    sigs = np.zeros(n, dtype=np.int8)
    sl = np.full(n, np.nan)
    tp = np.full(n, np.nan)
    if not impulses:
        return sigs, sl, tp
    h1_close_ts = np.array([_ts(t) + H1_SECONDS for t in h1_times], dtype=np.float64)
    ordered = sorted(impulses, key=lambda x: x.confirm_close_ts)
    flast = friday_last_mask(dow)
    last = n - 1 if exclude_forming else n
    j = 0
    active: H4Impulse | None = None
    used: set[int] = set()
    for i in range(last):
        while j < len(ordered) and ordered[j].confirm_close_ts <= h1_close_ts[i]:
            active = ordered[j]
            j += 1
        if active is None or active.confirm_i in used:
            continue
        if friday_blocked(int(dow[i]), int(mins[i]), bool(flast[i])):
            continue
        lo, hi = active.fib_lo, active.fib_hi
        if entry == "close_in_zone":
            hit = lo <= float(h1_close[i]) <= hi
        else:
            hit = float(h1_low[i]) <= hi and float(h1_high[i]) >= lo
        if not hit:
            continue
        sigs[i] = int(active.direction)
        sl[i] = active.sl
        tp[i] = active.tp
        used.add(active.confirm_i)
    return sigs, sl, tp


def simulate_htf_exits(
    times: list[datetime],
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    spread: np.ndarray,
    signals: np.ndarray,
    costs: CostSpec,
    *,
    sl_price: np.ndarray | None = None,
    tp_price: np.ndarray | None = None,
    atr: np.ndarray | None = None,
    sl_mult: float = 1.0,
    tp_mult: float = 2.0,
    flatten_friday: bool = False,
    dow: np.ndarray | None = None,
) -> list[Trade]:
    """Multi-day H1 walk. Fill = next H1 open. Same CostSpec as M5 screens."""
    n = len(times)
    trades: list[Trade] = []
    flast = friday_last_mask(dow) if dow is not None else np.zeros(n, dtype=bool)
    i = 0
    while i < n - 1:
        sig = int(signals[i])
        if sig == 0:
            i += 1
            continue
        fill = i + 1
        if fill >= n:
            i += 1
            continue
        if dow is not None and int(dow[fill]) >= 5:
            i += 1
            continue
        if flatten_friday and bool(flast[fill]):
            i += 1
            continue
        spr = float(spread[fill]) if np.isfinite(spread[fill]) else 0.0
        if costs.max_spread_points > 0 and spr > costs.max_spread_points:
            i += 1
            continue
        entry = float(open_[fill])
        if sl_price is not None and np.isfinite(sl_price[i]):
            sl_px = float(sl_price[i])
        else:
            at = float(atr[i]) if atr is not None and np.isfinite(atr[i]) else 0.0
            if at <= 0.0:
                i += 1
                continue
            sl_px = entry - sig * at * float(sl_mult)
        if tp_price is not None and np.isfinite(tp_price[i]):
            tp_px = float(tp_price[i])
        else:
            at = float(atr[i]) if atr is not None and np.isfinite(atr[i]) else 0.0
            if at <= 0.0:
                i += 1
                continue
            tp_px = entry + sig * at * float(tp_mult)
        exit_i = None
        reason = "eod"
        exit_px = entry
        for j in range(fill, n):
            if flatten_friday and bool(flast[j]) and j > fill:
                exit_i, exit_px, reason = j, float(open_[j]), "friday_last"
                break
            if dow is not None and int(dow[j]) >= 5:
                continue
            o = float(open_[j])
            h = float(high[j])
            l = float(low[j])
            if sig > 0:
                if o <= sl_px:
                    exit_i, exit_px, reason = j, o, "sl_gap"
                    break
                if o >= tp_px:
                    exit_i, exit_px, reason = j, o, "tp_gap"
                    break
                if l <= sl_px:
                    exit_i, exit_px, reason = j, sl_px, "sl"
                    break
                if h >= tp_px:
                    exit_i, exit_px, reason = j, tp_px, "tp"
                    break
            else:
                if o >= sl_px:
                    exit_i, exit_px, reason = j, o, "sl_gap"
                    break
                if o <= tp_px:
                    exit_i, exit_px, reason = j, o, "tp_gap"
                    break
                if h >= sl_px:
                    exit_i, exit_px, reason = j, sl_px, "sl"
                    break
                if l <= tp_px:
                    exit_i, exit_px, reason = j, tp_px, "tp"
                    break
        if exit_i is None:
            last = n - 1
            if last <= fill:
                i += 1
                continue
            exit_i, exit_px, reason = last, float(open_[last]), "data_end"
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
            mfe = float(entry - np.min(wl)) if len(wh) else 0.0
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


# Re-export so tests can assert the import path without re-deriving pivots.
_PIVOT_IMPORTS = (confirmed_pivots, confirmed_pivots_with_centers, walk_swing_and_fibs)
