#!/usr/bin/env python3
"""EURUSD NY-session scalp core — causal clock, sessions, indicators, signals.

Lock: results/eurusd_ny_scalp_lock.json (frozen 2026-08-20, before any metric).
promote / live_go = false. Offline research only.

Hard rules encoded here (see docs/research/EURUSD-NY-SCALP-DESIGN.md §2):
- C1: server wall clock is ET+7h and tracks US DST. ET is derived per bar by
  localizing (server - 7h) to America/New_York. NEVER the constant-offset
  path of us_index_session_backtest.load_m5_csv.
- Signals are decided on the CLOSE of bar i; the simulator fills at the open
  of i+1. Forming bars never signal. Warmup periods are NaN, never signal.
- Every indicator value at i uses bars <= i only (rolling volume means and
  breakout boxes exclude the signal bar itself).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from us_index_session_core import (  # noqa: E402
    ema_series,
    rsi_series,
    to_utc,
    wilder_atr,
)

# --- clock rule (lock: clock) -------------------------------------------
SERVER_MINUS_HOURS = 7
TZ_ET = "America/New_York"

# --- session (lock: session) --------------------------------------------
SESSION_START_MIN = 8 * 60  # 08:00 ET
SESSION_END_MIN = 17 * 60  # 17:00 ET (exclusive)
FLAT_MIN = 16 * 60 + 45  # force-flat at first bar open >= 16:45 ET
FRIDAY_CUTOFF_MIN = 14 * 60  # no new entries at/after 14:00 ET Friday

# --- frozen family params (lock: grid.families) -------------------------
EMA_FAST, EMA_SLOW = 9, 21
RIBBON = (8, 10, 12, 15)
BB_PERIOD, BB_STD = 20, 2.0
RSI_PERIOD, RSI_LO, RSI_HI = 7, 30.0, 70.0
VOL_CONFIRM_K = 1.2  # trend continuation volume multiple
BREAKOUT_VOL_K = 2.0  # breakout volume multiple
BOX_BARS = 12  # consolidation box length (prior bars)
ROLL_VOL_WINDOW = 20  # rolling volume mean window
TREND_TARGET_WINDOW = 20  # prior-N-bar extreme for trend structure TP


def et_from_server(server_naive: pd.Series) -> pd.Series:
    """Per-bar DST-aware ET: (server wall clock - 7h) localized to New York.

    ambiguous=True (fall-back hour) / nonexistent='shift_forward' (spring-forward
    hour): both ET transition windows (01:00-03:00) fall outside the 08:00-17:00
    FX session, so the choice never touches a tradable bar.
    """
    shifted = server_naive - pd.Timedelta(hours=SERVER_MINUS_HOURS)
    return shifted.dt.tz_localize(TZ_ET, ambiguous=True, nonexistent="shift_forward")


@dataclass
class M5Data:
    """Array bundle for one M5 EURUSD history (ET-annotated)."""

    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    vol: np.ndarray
    spread: np.ndarray  # points, imputed (no zeros remain)
    et_min: np.ndarray  # int32 minute-of-day ET
    et_key: np.ndarray  # int32 YYYYMMDD ET
    et_dow: np.ndarray  # int8 weekday (Mon=0)
    times_et: list[datetime]  # tz-aware ET bar opens

    def __len__(self) -> int:  # pragma: no cover - trivial
        return int(self.close.shape[0])


def load_eurusd_m5(csv_path: Path) -> M5Data:
    """Load the Vantage export. ET via the lock clock rule; spread imputed."""
    df = pd.read_csv(csv_path)
    server = pd.to_datetime(df["time"])
    et = et_from_server(server)
    spread = df["spread"].to_numpy(float)
    # lock: costs.spread_imputation — zeros forward-fill within ET day, else median
    bad = spread <= 0.0
    if bad.any():
        med = float(np.median(spread[~bad])) if (~bad).any() else 12.0
        key = et.dt.strftime("%Y%m%d").to_numpy()
        s = pd.Series(spread)
        s_bad = s.where(~bad)
        s_bad = s_bad.groupby(key, sort=False).ffill()
        spread = s_bad.fillna(med).to_numpy(float)
    return M5Data(
        open=df["open"].to_numpy(float),
        high=df["high"].to_numpy(float),
        low=df["low"].to_numpy(float),
        close=df["close"].to_numpy(float),
        vol=df["tick_volume"].to_numpy(float),
        spread=spread,
        et_min=(et.dt.hour * 60 + et.dt.minute).to_numpy(np.int32),
        et_key=(et.dt.year * 10000 + et.dt.month * 100 + et.dt.day).to_numpy(np.int32),
        et_dow=et.dt.weekday.to_numpy(np.int8),
        times_et=[t.to_pydatetime() for t in et],
    )


def entry_ok_mask(d: M5Data) -> np.ndarray:
    """[08:00, 17:00) ET, Friday >= 14:00 blocked (lock: session)."""
    m = (d.et_min >= SESSION_START_MIN) & (d.et_min < SESSION_END_MIN)
    m &= ~((d.et_dow == 4) & (d.et_min >= FRIDAY_CUTOFF_MIN))
    return m


# --- indicators ----------------------------------------------------------


def session_vwap_series(d: M5Data) -> np.ndarray:
    """Session VWAP (typical x tick_volume, floor 1), anchored at the first
    bar of the ET day inside [08:00, 17:00). Value at i includes bar i."""
    n = len(d)
    out = np.full(n, np.nan)
    num = den = 0.0
    day = -1
    for i in range(n):
        k = int(d.et_key[i])
        if k != day:
            day = k
            num = den = 0.0
        if SESSION_START_MIN <= int(d.et_min[i]) < SESSION_END_MIN:
            typ = (d.high[i] + d.low[i] + d.close[i]) / 3.0
            v = max(float(d.vol[i]), 1.0)
            num += typ * v
            den += v
            out[i] = num / den if den > 0.0 else np.nan
    return out


def bb_series(
    close: np.ndarray, period: int = BB_PERIOD, k: float = BB_STD
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Causal Bollinger (SMA/STD include bar i). mid, upper, lower; NaN warmup."""
    s = pd.Series(close)
    mid = s.rolling(period).mean().to_numpy(float)
    sd = s.rolling(period).std(ddof=0).to_numpy(float)
    return mid, mid + k * sd, mid - k * sd


def roll_mean_prior(x: np.ndarray, window: int = ROLL_VOL_WINDOW) -> np.ndarray:
    """Mean of bars [i-window, i-1] — the signal bar is EXCLUDED."""
    s = pd.Series(x)
    return s.rolling(window).mean().shift(1).to_numpy(float)


def box_levels(
    high: np.ndarray, low: np.ndarray, n: int = BOX_BARS
) -> tuple[np.ndarray, np.ndarray]:
    """Consolidation box from the n bars strictly PRIOR to i."""
    hi = pd.Series(high).rolling(n).max().shift(1).to_numpy(float)
    lo = pd.Series(low).rolling(n).min().shift(1).to_numpy(float)
    return hi, lo


def prior_extreme(
    high: np.ndarray, low: np.ndarray, n: int = TREND_TARGET_WINDOW
) -> tuple[np.ndarray, np.ndarray]:
    """Prior-n-bar high/low (strictly prior to i) — trend structure target."""
    return box_levels(high, low, n)


@dataclass
class FamilyContext:
    """Per-family indicator stack + structure-target arrays (all causal)."""

    name: str
    signals: np.ndarray  # int8 +1/-1/0, entry-window gated
    tgt_long: np.ndarray | None  # structure TP levels for longs (price)
    tgt_short: np.ndarray | None  # structure TP levels for shorts (price)
    atr: np.ndarray | None = None  # shared ATR14 (set once by build_context)


def _gate_and_dedupe(raw: np.ndarray, d: M5Data, one_per_day: bool) -> np.ndarray:
    """Apply entry window, Friday cutoff, optional one-signal-per-ET-day."""
    out = np.where(entry_ok_mask(d), raw, 0).astype(np.int8)
    if not one_per_day:
        return out
    fired = -1
    for i in range(len(out)):
        if out[i] == 0:
            continue
        k = int(d.et_key[i])
        if k == fired:
            out[i] = 0
        else:
            fired = k
    return out


def trend_continuation_signals(d: M5Data, one_per_day: bool) -> np.ndarray:
    """User strategy 1: pull back to EMA9/VWAP in trend, close back through
    EMA9, volume confirms. Decided on the close of i; fill at open of i+1."""
    c = d.close
    ema_f = ema_series(c, EMA_FAST)
    ema_s = ema_series(c, EMA_SLOW)
    vwap = session_vwap_series(d)
    rv = roll_mean_prior(d.vol)
    n = len(c)
    raw = np.zeros(n, dtype=np.int8)
    for i in range(1, n):
        px, ef, es, vw, r = c[i], ema_f[i], ema_s[i], vwap[i], rv[i]
        ef1 = ema_f[i - 1]
        vw1 = vwap[i - 1]
        if not all(np.isfinite(v) for v in (px, ef, es, vw, r, ef1, vw1)):
            continue
        if r <= 0.0 or d.vol[i] <= VOL_CONFIRM_K * r:
            continue
        lo1, hi1 = d.low[i - 1], d.high[i - 1]
        pulled_long = lo1 <= ef1 or lo1 <= vw1
        pulled_short = hi1 >= ef1 or hi1 >= vw1
        if pulled_long and px > ef and ef > es and px > vw:
            raw[i] = 1
        elif pulled_short and px < ef and ef < es and px < vw:
            raw[i] = -1
    return _gate_and_dedupe(raw, d, one_per_day)


def mean_reversion_signals(d: M5Data, one_per_day: bool) -> np.ndarray:
    """User strategy 2: close pierces BB(20,2) AND RSI(7) beyond 30/70."""
    mid, upper, lower = bb_series(d.close)
    rsi = rsi_series(d.close, RSI_PERIOD)
    c = d.close
    ok = np.isfinite(lower) & np.isfinite(upper) & np.isfinite(rsi)
    raw = np.zeros(len(c), dtype=np.int8)
    long_ok = ok & (c < lower) & (rsi < RSI_LO)
    short_ok = ok & (c > upper) & (rsi > RSI_HI)
    raw[long_ok] = 1
    raw[short_ok & (raw == 0)] = -1
    return _gate_and_dedupe(raw, d, one_per_day)


def breakout_signals(d: M5Data, one_per_day: bool) -> np.ndarray:
    """User strategy 3: 12-bar box break + volume spike + ribbon fan."""
    c = d.close
    box_h, box_l = box_levels(d.high, d.low)
    rv = roll_mean_prior(d.vol)
    emas = [ema_series(c, p) for p in RIBBON]
    n = len(c)
    raw = np.zeros(n, dtype=np.int8)
    for i in range(n):
        if not (
            np.isfinite(box_h[i]) and np.isfinite(box_l[i]) and np.isfinite(rv[i]) and rv[i] > 0.0
        ):
            continue
        if d.vol[i] < BREAKOUT_VOL_K * rv[i]:
            continue
        if not all(np.isfinite(e[i]) for e in emas):
            continue
        fan_long = emas[0][i] > emas[1][i] > emas[2][i] > emas[3][i]
        fan_short = emas[0][i] < emas[1][i] < emas[2][i] < emas[3][i]
        if c[i] > box_h[i] and fan_long:
            raw[i] = 1
        elif c[i] < box_l[i] and fan_short:
            raw[i] = -1
    return _gate_and_dedupe(raw, d, one_per_day)


def build_context(d: M5Data, one_per_day: bool) -> dict[str, FamilyContext]:
    """Indicator stacks + signals + structure targets for the three families."""
    atr = wilder_atr(d.high, d.low, d.close, 14)
    mid, _upper, _lower = bb_series(d.close)
    pri_hi, pri_lo = prior_extreme(d.high, d.low)
    box_h, box_l = box_levels(d.high, d.low)
    box_hgt = np.where(np.isfinite(box_h) & np.isfinite(box_l), box_h - box_l, np.nan)
    return {
        "trend_continuation": FamilyContext(
            name="trend_continuation",
            signals=trend_continuation_signals(d, one_per_day),
            tgt_long=pri_hi,
            tgt_short=pri_lo,
            atr=atr,
        ),
        "mean_reversion": FamilyContext(
            name="mean_reversion",
            signals=mean_reversion_signals(d, one_per_day),
            tgt_long=mid,
            tgt_short=mid,
            atr=atr,
        ),
        "breakout": FamilyContext(
            name="breakout",
            signals=breakout_signals(d, one_per_day),
            tgt_long=box_h + box_hgt,  # measured move from the box extreme
            tgt_short=box_l - box_hgt,
            atr=atr,
        ),
    }


# --- null calibration support (lock: null_calibration) -------------------


def rotate_returns_within_days(d: M5Data, rng: np.random.Generator) -> M5Data:
    """Circular phase rotation of within-ET-day log returns.

    Per ET day: returns r = [ln(c0/o0), ln(c1/c0), ...] get one uniform
    circular offset; closes rebuild from o0; each bar's O/H/L scale by the
    close ratio (bar shape preserved). Times, volumes, spreads unchanged.
    """
    n = len(d)
    o = d.open.copy()
    h = d.high.copy()
    lo = d.low.copy()
    c = d.close.copy()
    i = 0
    while i < n:
        j = i
        k = int(d.et_key[i])
        while j < n and int(d.et_key[j]) == k:
            j += 1
        # bars [i, j) are one ET day
        seg_c = c[i:j]
        r = np.empty(j - i)
        r[0] = np.log(seg_c[0] / o[i])
        r[1:] = np.diff(np.log(seg_c))
        off = int(rng.integers(0, j - i))
        r = np.roll(r, off)
        new_c = o[i] * np.exp(np.cumsum(r))  # anchored at the day's first open
        ratio = new_c / seg_c
        h[i:j] *= ratio
        lo[i:j] *= ratio
        c[i:j] = new_c
        o[i + 1 : j] = new_c[:-1]  # opens chain from prior closes
        i = j
    return M5Data(
        open=o,
        high=h,
        low=lo,
        close=c,
        vol=d.vol.copy(),
        spread=d.spread.copy(),
        et_min=d.et_min,
        et_key=d.et_key,
        et_dow=d.et_dow,
        times_et=d.times_et,
    )


__all__ = [
    "M5Data",
    "FamilyContext",
    "SERVER_MINUS_HOURS",
    "SESSION_START_MIN",
    "SESSION_END_MIN",
    "FLAT_MIN",
    "FRIDAY_CUTOFF_MIN",
    "et_from_server",
    "load_eurusd_m5",
    "entry_ok_mask",
    "session_vwap_series",
    "bb_series",
    "roll_mean_prior",
    "box_levels",
    "prior_extreme",
    "build_context",
    "trend_continuation_signals",
    "mean_reversion_signals",
    "breakout_signals",
    "rotate_returns_within_days",
    "to_utc",
]
