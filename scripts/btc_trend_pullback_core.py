#!/usr/bin/env python3
"""Causal BTCUSD H1 pullback — Python port of BtcTrendPullback v1.10.

H4 completed-bar EMA50/200 stack is bias. H1 closed-bar shallow reclaim
(RSI + MACD hist + rising close) is the entry. Optional continuation.
VWAP and deep-reclaim stay OFF. Forming last H1 has no signal.

Pivots / Fib are not used. Do not import ``htf_fib_core``.

SAFETY: offline research only. No orders.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from us_index_session_backtest import CostSpec, Trade  # noqa: E402
from us_index_session_core import (  # noqa: E402
    ema_series,
    macd_series,
    rsi_series,
    to_utc,
    wilder_atr,
)

SEARCH_ID = "btc_h1_trend_pullback_v1"
HOLDOUT_START = date(2026, 1, 1)
SELECT_END = date(2026, 1, 1)
START_BALANCE = 10_000.0
FROZEN_LOTS = 0.01
FROZEN_SLIPPAGE_POINTS = 250.0
FROZEN_MAX_SPREAD_POINTS = 4000.0
FROZEN_POINT = 0.01
FROZEN_CONTRACT = 1.0
FROZEN_COMMISSION = 0.0
N_TRADES_MIN = 40
PF_MIN = 1.1
MAX_DD_PCT_MAX = 0.25
H4_SECONDS = 14400
EMA_FAST = 50
EMA_SLOW = 200
MIN_TREND_STRENGTH = 0.01
STRONG_TREND_STRENGTH = 0.015
RSI_PERIOD = 14
RSI_RECLAIM = 50.0
CONTINUATION_RSI = 54.0
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
ATR_PERIOD = 14
MIN_ATR_PCT = 0.01
MAX_EXTENSION_PCT = 0.03
PANIC_RSI = 35.0
PANIC_ATR_PCT = 0.08
TP_RR = 2.0


def frozen_cost_spec() -> CostSpec:
    return CostSpec(
        point_size=FROZEN_POINT,
        contract_size=FROZEN_CONTRACT,
        lots=FROZEN_LOTS,
        commission_per_lot=FROZEN_COMMISSION,
        slippage_points=FROZEN_SLIPPAGE_POINTS,
        max_spread_points=FROZEN_MAX_SPREAD_POINTS,
    )


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


def require_frozen_btc_book(costs: CostSpec) -> CostSpec:
    if (
        float(costs.lots) != FROZEN_LOTS
        or float(costs.slippage_points) != FROZEN_SLIPPAGE_POINTS
        or float(costs.point_size) != FROZEN_POINT
        or float(costs.contract_size) != FROZEN_CONTRACT
        or float(costs.max_spread_points) != FROZEN_MAX_SPREAD_POINTS
    ):
        raise SystemExit(
            f"frozen BTC book is {FROZEN_LOTS:g} lot / "
            f"{FROZEN_SLIPPAGE_POINTS:g} pt slip / "
            f"point {FROZEN_POINT} / contract {FROZEN_CONTRACT}"
        )
    return costs


def split_btc(trades: list[Trade], holdout_start: date = HOLDOUT_START):
    """Split on signal UTC date. Holdout is never used for selection."""
    pre: list[Trade] = []
    post: list[Trade] = []
    for t in trades:
        d = date.fromisoformat(str(t.signal_time)[:10])
        if d < holdout_start:
            pre.append(t)
        else:
            post.append(t)
    return pre, post


def completed_htf_index(
    h1_open_ts: np.ndarray,
    h4_open_ts: np.ndarray,
    htf_sec: int = H4_SECONDS,
) -> np.ndarray:
    """Last H4 whose period has ended by each H1 open (CompletedHtfShift).

    ``idx[i] = -1`` when no completed H4 exists yet.
    """
    ends = np.asarray(h4_open_ts, dtype=float) + float(htf_sec)
    t = np.asarray(h1_open_ts, dtype=float)
    idx = np.searchsorted(ends, t, side="right") - 1
    return idx.astype(np.int32)


def htf_bias_strength(
    idx: np.ndarray,
    h4_close: np.ndarray,
    h4_ema50: np.ndarray,
    h4_ema200: np.ndarray,
    min_strength: float = MIN_TREND_STRENGTH,
) -> tuple[np.ndarray, np.ndarray]:
    n = int(idx.shape[0])
    bias = np.zeros(n, dtype=np.int8)
    strength = np.zeros(n, dtype=float)
    c = np.asarray(h4_close, dtype=float)
    e50 = np.asarray(h4_ema50, dtype=float)
    e200 = np.asarray(h4_ema200, dtype=float)
    for i in range(n):
        j = int(idx[i])
        if j < 0:
            continue
        px, a, b = float(c[j]), float(e50[j]), float(e200[j])
        if not (np.isfinite(px) and np.isfinite(a) and np.isfinite(b) and b > 0.0):
            continue
        s = (a - b) / b
        strength[i] = s
        if px > b and a > b and s >= min_strength:
            bias[i] = 1
        elif px < b and a < b and (-s) >= min_strength:
            bias[i] = -1
    return bias, strength


def _panic_long(rsi: float, atr_pct: float, close_px: float, ema200: float) -> bool:
    stress = rsi <= PANIC_RSI or atr_pct >= PANIC_ATR_PCT
    return stress and close_px < ema200


def _panic_short(rsi: float, atr_pct: float, close_px: float, ema200: float) -> bool:
    stress = rsi >= (100.0 - PANIC_RSI) or atr_pct >= PANIC_ATR_PCT
    return stress and close_px > ema200


def _long_setup(
    i: int,
    htf_bias: int,
    htf_strength: float,
    close: np.ndarray,
    ema50: np.ndarray,
    ema200: np.ndarray,
    rsi: np.ndarray,
    macd_hist: np.ndarray,
    atr_pct: float,
    *,
    allow_continuation: bool,
    max_pullback_pct: float,
) -> bool:
    if htf_bias != 1 or i < 1:
        return False
    if _panic_long(float(rsi[i]), atr_pct, float(close[i]), float(ema200[i])):
        return False
    e50 = float(ema50[i])
    if e50 <= 0.0 or not np.isfinite(e50):
        return False
    dist = abs(float(close[i]) - e50) / e50
    recovery = (
        float(rsi[i]) >= RSI_RECLAIM
        and float(rsi[i]) > float(rsi[i - 1])
        and float(macd_hist[i]) >= 0.0
        and float(macd_hist[i]) > float(macd_hist[i - 1])
        and float(close[i]) > float(close[i - 1])
    )
    if dist <= max_pullback_pct and recovery:
        return True
    if not allow_continuation:
        return False
    ext = (float(close[i]) - e50) / e50
    mom = float(rsi[i]) >= CONTINUATION_RSI and (
        float(rsi[i]) > float(rsi[i - 1]) or float(macd_hist[i]) > float(macd_hist[i - 1])
    )
    return (
        htf_strength >= STRONG_TREND_STRENGTH
        and float(close[i]) >= e50
        and 0.0 <= ext <= MAX_EXTENSION_PCT
        and mom
    )


def _short_setup(
    i: int,
    htf_bias: int,
    htf_strength: float,
    close: np.ndarray,
    ema50: np.ndarray,
    ema200: np.ndarray,
    rsi: np.ndarray,
    macd_hist: np.ndarray,
    atr_pct: float,
    *,
    allow_continuation: bool,
    max_pullback_pct: float,
) -> bool:
    if htf_bias != -1 or i < 1:
        return False
    if _panic_short(float(rsi[i]), atr_pct, float(close[i]), float(ema200[i])):
        return False
    e50 = float(ema50[i])
    if e50 <= 0.0 or not np.isfinite(e50):
        return False
    dist = abs(float(close[i]) - e50) / e50
    recovery = (
        float(rsi[i]) <= (100.0 - RSI_RECLAIM)
        and float(rsi[i]) < float(rsi[i - 1])
        and float(macd_hist[i]) <= 0.0
        and float(macd_hist[i]) < float(macd_hist[i - 1])
        and float(close[i]) < float(close[i - 1])
    )
    if dist <= max_pullback_pct and recovery:
        return True
    if not allow_continuation:
        return False
    ext = (e50 - float(close[i])) / e50
    mom = float(rsi[i]) <= (100.0 - CONTINUATION_RSI) and (
        float(rsi[i]) < float(rsi[i - 1]) or float(macd_hist[i]) < float(macd_hist[i - 1])
    )
    return (
        (-htf_strength) >= STRONG_TREND_STRENGTH
        and float(close[i]) <= e50
        and 0.0 <= ext <= MAX_EXTENSION_PCT
        and mom
    )


def pullback_signals(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    h1_open_ts: np.ndarray,
    h4_open_ts: np.ndarray,
    h4_close: np.ndarray,
    *,
    allow_continuation: bool,
    allow_shorts: bool,
    max_pullback_pct: float,
    exclude_forming: bool = True,
) -> np.ndarray:
    """Ternary +1/−1/0 on closed H1. Last bar is always 0 when exclude_forming."""
    c = np.asarray(close, dtype=float)
    n = int(c.shape[0])
    out = np.zeros(n, dtype=np.int8)
    if n < EMA_SLOW + 5:
        return out
    ema50 = ema_series(c, EMA_FAST)
    ema200 = ema_series(c, EMA_SLOW)
    rsi = rsi_series(c, RSI_PERIOD)
    _macd, _sig, hist = macd_series(c, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
    atr = wilder_atr(high, low, c, ATR_PERIOD)
    h4_e50 = ema_series(np.asarray(h4_close, dtype=float), EMA_FAST)
    h4_e200 = ema_series(np.asarray(h4_close, dtype=float), EMA_SLOW)
    idx = completed_htf_index(h1_open_ts, h4_open_ts)
    bias, strength = htf_bias_strength(idx, h4_close, h4_e50, h4_e200)
    last = n - 1 if exclude_forming else n
    need = max(EMA_SLOW, MACD_SLOW + MACD_SIGNAL, ATR_PERIOD) + 2

    def _setup_at(i: int, side: int) -> bool:
        if i < 1 or i >= n:
            return False
        if not np.isfinite(c[i]) or not np.isfinite(atr[i]) or c[i] <= 0.0 or atr[i] <= 0.0:
            return False
        atr_pct = float(atr[i]) / float(c[i])
        if atr_pct < MIN_ATR_PCT:
            return False
        if not (
            np.isfinite(rsi[i])
            and np.isfinite(hist[i])
            and np.isfinite(ema50[i])
            and np.isfinite(ema200[i])
        ):
            return False
        if side > 0:
            return _long_setup(
                i,
                int(bias[i]),
                float(strength[i]),
                c,
                ema50,
                ema200,
                rsi,
                hist,
                atr_pct,
                allow_continuation=allow_continuation,
                max_pullback_pct=max_pullback_pct,
            )
        if not allow_shorts:
            return False
        return _short_setup(
            i,
            int(bias[i]),
            float(strength[i]),
            c,
            ema50,
            ema200,
            rsi,
            hist,
            atr_pct,
            allow_continuation=allow_continuation,
            max_pullback_pct=max_pullback_pct,
        )

    for i in range(need, last):
        long_now = _setup_at(i, 1)
        short_now = _setup_at(i, -1)
        long_fire = long_now and not _setup_at(i - 1, 1)
        short_fire = short_now and not _setup_at(i - 1, -1)
        if long_fire:
            out[i] = 1
        elif short_fire:
            out[i] = -1
    return out


def h1_open_timestamps(times: list[datetime]) -> np.ndarray:
    return np.array([to_utc(t).timestamp() for t in times], dtype=float)
