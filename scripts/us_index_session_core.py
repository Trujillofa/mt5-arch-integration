#!/usr/bin/env python3
"""Causal US-index session / ORB / VWAP / EMA helpers (offline research).

Frozen combo (not a search)
---------------------------
``ny_cash_orb_vwap_ema_flat`` — US30 / US100 scalp stack:

1. **NY cash open is the event.** Equity-index CFDs have a real 09:30 ET
   cash print. FX majors do not; that is why FX ORB was closed in
   ``manual-trading-agent`` and must not be copied blindly.
2. **Opening range** = first ``or_minutes`` of NY cash. The range is
   knowable only on the first bar whose *open* is at or after
   ``09:30 + or_minutes`` ET (last OR bar has then closed).
3. **Session VWAP** from the first NY-cash bar of that ET date
   (typical price × tick_volume; volume floor 1, same as BtcTrendPullback).
4. **EMA 9 / 21** scalp stack (not the FX 20/50/200 swing stack).
5. **AND signal on a closed bar** in ``[OR end, 11:30)`` ET:
   close beyond OR + close vs VWAP + EMA stack + ATR% floor.
   Wick-only breaks do not count (close must confirm).
6. **Friday:** no new entries at or after 14:00 ET (weekend gap).
   Force-flat visual is 15:45 ET — not an entry rule.

Sessions (draw; DST-safe local clocks — mirrors ctrader ``SessionClock``)
------------------------------------------------------------------------
- Tokyo:  09:00–18:00 Asia/Tokyo
- London: 08:00–17:00 Europe/London
- NY cash: 09:30–16:00 America/New_York
- Overlap: London ∩ NY cash

SAFETY: offline research only. No orders. Consumers must not re-derive
the OR stamp (lookahead lives in “range known at 09:30”).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import IntEnum
from zoneinfo import ZoneInfo

import numpy as np

TZ_ET = ZoneInfo("America/New_York")
TZ_LON = ZoneInfo("Europe/London")
TZ_TYO = ZoneInfo("Asia/Tokyo")

# Frozen defaults (indicator + tests share these names).
OR_MINUTES = 15
ENTRY_END = time(11, 30)
FLAT_WARN = time(15, 45)
FRIDAY_CUTOFF = time(14, 0)
EMA_FAST = 9
EMA_SLOW = 21
ATR_PERIOD = 14
MIN_ATR_PCT = 0.00015  # 1.5 bp of price — dead-lunch floor
OR_BUFFER_ATR_FRAC = 0.0  # close must clear OR; extra buffer is 0 by default


class SessionId(IntEnum):
    NONE = 0
    TOKYO = 1
    LONDON = 2
    NY_CASH = 3
    OVERLAP = 4


@dataclass(frozen=True)
class SessionSpan:
    """One session box for drawing (ET calendar date + local window)."""

    name: str
    session_id: SessionId
    start_utc: datetime
    end_utc: datetime
    et_date: date


@dataclass(frozen=True)
class OrState:
    """Opening range as known at a closed bar (or not yet)."""

    complete: bool
    high: float
    low: float
    last_or_idx: int  # inclusive last OR bar, -1 if none


@dataclass(frozen=True)
class ScalpSignal:
    value: int  # +1 / -1 / 0
    reason: str
    or_high: float
    or_low: float
    vwap: float


def to_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def to_et(ts: datetime) -> datetime:
    return to_utc(ts).astimezone(TZ_ET)


def to_london(ts: datetime) -> datetime:
    return to_utc(ts).astimezone(TZ_LON)


def to_tokyo(ts: datetime) -> datetime:
    return to_utc(ts).astimezone(TZ_TYO)


def _in_local_window(local: datetime, start: time, end: time) -> bool:
    t = local.timetz().replace(tzinfo=None)
    if start < end:
        return start <= t < end
    return t >= start or t < end


def is_tokyo_open(ts: datetime) -> bool:
    return _in_local_window(to_tokyo(ts), time(9, 0), time(18, 0))


def is_london_open(ts: datetime) -> bool:
    return _in_local_window(to_london(ts), time(8, 0), time(17, 0))


def is_ny_cash(ts: datetime) -> bool:
    return _in_local_window(to_et(ts), time(9, 30), time(16, 0))


def session_id(ts: datetime) -> SessionId:
    lon = is_london_open(ts)
    ny = is_ny_cash(ts)
    if lon and ny:
        return SessionId.OVERLAP
    if ny:
        return SessionId.NY_CASH
    if lon:
        return SessionId.LONDON
    if is_tokyo_open(ts):
        return SessionId.TOKYO
    return SessionId.NONE


def session_name(sid: SessionId) -> str:
    return {
        SessionId.TOKYO: "Tokyo",
        SessionId.LONDON: "London",
        SessionId.NY_CASH: "NY cash",
        SessionId.OVERLAP: "LDN+NY",
        SessionId.NONE: "Off",
    }[sid]


def ny_cash_open_et(et_day: date) -> datetime:
    return datetime(et_day.year, et_day.month, et_day.day, 9, 30, tzinfo=TZ_ET)


def or_end_et(et_day: date, or_minutes: int = OR_MINUTES) -> datetime:
    return ny_cash_open_et(et_day) + timedelta(minutes=or_minutes)


def friday_entry_blocked(ts: datetime, cutoff: time = FRIDAY_CUTOFF) -> bool:
    et = to_et(ts)
    if et.weekday() != 4:
        return False
    return et.timetz().replace(tzinfo=None) >= cutoff


def in_entry_window(
    ts: datetime,
    or_minutes: int = OR_MINUTES,
    entry_end: time = ENTRY_END,
) -> bool:
    """True on bars whose open is in [OR end, entry_end) ET, same ET date."""
    et = to_et(ts)
    t = et.timetz().replace(tzinfo=None)
    start = or_end_et(et.date(), or_minutes).timetz().replace(tzinfo=None)
    return start <= t < entry_end


def session_spans_for_et_date(et_day: date) -> list[SessionSpan]:
    """Local-clock windows converted to UTC for one ET calendar date.

    Tokyo's 09:00 JST on *this* ET date is the Tokyo session that overlaps
    the US overnight (evening ET previous / morning JST).
    """
    et0 = datetime(et_day.year, et_day.month, et_day.day, 0, 0, tzinfo=TZ_ET)
    # Probe a UTC instant that sits on this ET date, then build local midnights.
    lon0 = datetime(et_day.year, et_day.month, et_day.day, 0, 0, tzinfo=TZ_LON)
    tyo0 = datetime(et_day.year, et_day.month, et_day.day, 0, 0, tzinfo=TZ_TYO)
    # Tokyo session that *precedes* NY cash on this ET date is JST morning
    # of et_day + 1 (09:00 JST = 20:00 ET previous in winter). For drawing
    # "the Asia box before today's NY" use Tokyo 09:00 JST on et_day
    # (which is still previous-evening ET in summer). Operators want the
    # box that sits on the chart left of NY — that is Tokyo of et_day JST.
    tokyo = SessionSpan(
        "Tokyo",
        SessionId.TOKYO,
        (tyo0 + timedelta(hours=9)).astimezone(UTC),
        (tyo0 + timedelta(hours=18)).astimezone(UTC),
        et_day,
    )
    london = SessionSpan(
        "London",
        SessionId.LONDON,
        (lon0 + timedelta(hours=8)).astimezone(UTC),
        (lon0 + timedelta(hours=17)).astimezone(UTC),
        et_day,
    )
    ny = SessionSpan(
        "NY cash",
        SessionId.NY_CASH,
        (et0 + timedelta(hours=9, minutes=30)).astimezone(UTC),
        (et0 + timedelta(hours=16)).astimezone(UTC),
        et_day,
    )
    return [tokyo, london, ny]


def _as_utc_array(times: np.ndarray | list) -> list[datetime]:
    out: list[datetime] = []
    for t in times:
        if isinstance(t, np.datetime64):
            # ns → datetime
            epoch = t.astype("datetime64[ns]").astype(np.int64)
            out.append(datetime.fromtimestamp(epoch / 1e9, tz=UTC))
        elif isinstance(t, datetime):
            out.append(to_utc(t))
        else:
            raise TypeError(f"unsupported timestamp type: {type(t)}")
    return out


def opening_range_at(
    times: np.ndarray | list,
    high: np.ndarray,
    low: np.ndarray,
    i: int,
    *,
    or_minutes: int = OR_MINUTES,
) -> OrState:
    """OR as known on the *close* of bar ``i`` (no lookahead past ``i``).

    Bars with open in ``[09:30, 09:30+or_minutes)`` ET on bar ``i``'s ET
    date form the range. Complete iff bar ``i`` open >= OR end (last OR
    bar has closed).
    """
    high_a = np.asarray(high, dtype=float)
    low_a = np.asarray(low, dtype=float)
    ts = _as_utc_array(times)
    if i < 0 or i >= len(ts):
        return OrState(False, float("nan"), float("nan"), -1)

    et_day = to_et(ts[i]).date()
    start = ny_cash_open_et(et_day)
    end = or_end_et(et_day, or_minutes)
    or_h = -np.inf
    or_l = np.inf
    last = -1
    for k in range(i + 1):
        et = to_et(ts[k])
        if et.date() != et_day:
            continue
        if start <= et < end:
            or_h = max(or_h, float(high_a[k]))
            or_l = min(or_l, float(low_a[k]))
            last = k
    if last < 0:
        return OrState(False, float("nan"), float("nan"), -1)
    complete = to_et(ts[i]) >= end
    if not complete:
        return OrState(False, float("nan"), float("nan"), last)
    return OrState(True, float(or_h), float(or_l), last)


def session_vwap_at(
    times: np.ndarray | list,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    i: int,
) -> float:
    """NY-cash VWAP through closed bar ``i`` (same ET date). NaN if none."""
    high_a = np.asarray(high, dtype=float)
    low_a = np.asarray(low, dtype=float)
    close_a = np.asarray(close, dtype=float)
    vol_a = np.asarray(volume, dtype=float)
    ts = _as_utc_array(times)
    if i < 0 or i >= len(ts):
        return float("nan")
    et_day = to_et(ts[i]).date()
    num = 0.0
    den = 0.0
    for k in range(i + 1):
        if not is_ny_cash(ts[k]):
            continue
        if to_et(ts[k]).date() != et_day:
            continue
        typ = (high_a[k] + low_a[k] + close_a[k]) / 3.0
        vol = max(float(vol_a[k]), 1.0)
        num += typ * vol
        den += vol
    if den <= 0.0:
        return float("nan")
    return num / den


def ema_series(price: np.ndarray, period: int) -> np.ndarray:
    """Seed SMA then recursive EMA — index 0 = oldest (matches FxEmaSeries)."""
    x = np.asarray(price, dtype=float)
    n = int(x.shape[0])
    out = np.full(n, np.nan, dtype=float)
    if period < 1 or n < period:
        return out
    out[period - 1] = float(np.mean(x[:period]))
    mult = 2.0 / (period + 1.0)
    for i in range(period, n):
        out[i] = x[i] * mult + out[i - 1] * (1.0 - mult)
    return out


def rsi_series(price: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder RSI — index 0 = oldest (matches MT5 ``iRSI``)."""
    x = np.asarray(price, dtype=float)
    n = int(x.shape[0])
    out = np.full(n, np.nan, dtype=float)
    if period < 1 or n < period + 1:
        return out
    delta = np.empty(n, dtype=float)
    delta[0] = 0.0
    delta[1:] = x[1:] - x[:-1]
    gain = np.where(delta > 0.0, delta, 0.0)
    loss = np.where(delta < 0.0, -delta, 0.0)
    avg_g = float(np.mean(gain[1 : period + 1]))
    avg_l = float(np.mean(loss[1 : period + 1]))

    def _rsi(ag: float, al: float) -> float:
        if al <= 0.0:
            return 100.0 if ag > 0.0 else 50.0
        return 100.0 - 100.0 / (1.0 + ag / al)

    out[period] = _rsi(avg_g, avg_l)
    for i in range(period + 1, n):
        avg_g = (avg_g * (period - 1) + gain[i]) / period
        avg_l = (avg_l * (period - 1) + loss[i]) / period
        out[i] = _rsi(avg_g, avg_l)
    return out


def macd_series(
    price: np.ndarray,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """MACD / signal / histogram — index 0 = oldest (matches MT5 ``iMACD``)."""
    x = np.asarray(price, dtype=float)
    n = int(x.shape[0])
    macd = np.full(n, np.nan, dtype=float)
    sig = np.full(n, np.nan, dtype=float)
    hist = np.full(n, np.nan, dtype=float)
    if fast < 1 or slow <= fast or signal < 1 or n < slow:
        return macd, sig, hist
    macd = ema_series(x, fast) - ema_series(x, slow)
    start = slow - 1
    if start >= n:
        return macd, sig, hist
    sig_part = ema_series(macd[start:], signal)
    sig[start:] = sig_part
    hist = macd - sig
    return macd, sig, hist


def wilder_atr(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = ATR_PERIOD,
) -> np.ndarray:
    """Wilder ATR — index 0 = oldest (matches FxAtrSeries)."""
    h = np.asarray(high, dtype=float)
    low_a = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    n = int(h.shape[0])
    out = np.full(n, np.nan, dtype=float)
    if period < 1 or n < period + 1:
        return out
    tr = np.empty(n, dtype=float)
    tr[0] = h[0] - low_a[0]
    for i in range(1, n):
        tr[i] = max(h[i] - low_a[i], abs(h[i] - c[i - 1]), abs(low_a[i] - c[i - 1]))
    out[period] = float(np.mean(tr[1 : period + 1]))
    for i in range(period + 1, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def scalp_signal_at(
    times: np.ndarray | list,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    i: int,
    *,
    ema_fast: np.ndarray | None = None,
    ema_slow: np.ndarray | None = None,
    atr: np.ndarray | None = None,
    or_minutes: int = OR_MINUTES,
    min_atr_pct: float = MIN_ATR_PCT,
    or_buffer_atr_frac: float = OR_BUFFER_ATR_FRAC,
    one_per_day: bool = True,
    prior_signal_et_dates: set[date] | None = None,
    ors: OrState | None = None,
    vwap: float | None = None,
    ts_utc: list[datetime] | None = None,
) -> ScalpSignal:
    """AND confluence on closed bar ``i``. No look-ahead past ``i``."""
    close_a = np.asarray(close, dtype=float)
    ts = ts_utc if ts_utc is not None else _as_utc_array(times)
    if i < 0 or i >= len(ts):
        return ScalpSignal(0, "bad_index", float("nan"), float("nan"), float("nan"))

    if friday_entry_blocked(ts[i]):
        return ScalpSignal(0, "friday_cutoff", float("nan"), float("nan"), float("nan"))
    if not in_entry_window(ts[i], or_minutes):
        return ScalpSignal(0, "outside_entry_window", float("nan"), float("nan"), float("nan"))

    if ors is None:
        ors = opening_range_at(times, high, low, i, or_minutes=or_minutes)
    if not ors.complete:
        return ScalpSignal(0, "or_incomplete", float("nan"), float("nan"), float("nan"))

    if vwap is None:
        vwap = session_vwap_at(times, high, low, close, volume, i)
    if not np.isfinite(vwap):
        return ScalpSignal(0, "no_vwap", ors.high, ors.low, float("nan"))

    if ema_fast is None:
        ema_fast = ema_series(close_a, EMA_FAST)
    if ema_slow is None:
        ema_slow = ema_series(close_a, EMA_SLOW)
    ef = float(np.asarray(ema_fast, dtype=float)[i])
    es = float(np.asarray(ema_slow, dtype=float)[i])
    if not (np.isfinite(ef) and np.isfinite(es)):
        return ScalpSignal(0, "ema_warmup", ors.high, ors.low, vwap)

    if atr is None:
        atr = wilder_atr(high, low, close, ATR_PERIOD)
    atr_i = float(np.asarray(atr, dtype=float)[i])
    px = float(close_a[i])
    if not np.isfinite(atr_i) or px <= 0.0:
        return ScalpSignal(0, "atr_warmup", ors.high, ors.low, vwap)
    if atr_i / px < min_atr_pct:
        return ScalpSignal(0, "dead_atr", ors.high, ors.low, vwap)

    if one_per_day:
        et_day = to_et(ts[i]).date()
        if prior_signal_et_dates and et_day in prior_signal_et_dates:
            return ScalpSignal(0, "already_signaled_today", ors.high, ors.low, vwap)

    buf = or_buffer_atr_frac * atr_i
    long_ok = px > ors.high + buf and px > vwap and ef > es
    short_ok = px < ors.low - buf and px < vwap and ef < es
    if long_ok:
        return ScalpSignal(+1, "orb_vwap_ema_long", ors.high, ors.low, vwap)
    if short_ok:
        return ScalpSignal(-1, "orb_vwap_ema_short", ors.high, ors.low, vwap)
    return ScalpSignal(0, "no_confluence", ors.high, ors.low, vwap)


def scalp_signal_series(
    times: np.ndarray | list,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    *,
    or_minutes: int = OR_MINUTES,
    min_atr_pct: float = MIN_ATR_PCT,
    one_per_day: bool = True,
    exclude_forming: bool = True,
) -> np.ndarray:
    """Walk-forward signals. Forming last bar is 0 when ``exclude_forming``."""
    close_a = np.asarray(close, dtype=float)
    n = int(close_a.shape[0])
    ema_f = ema_series(close_a, EMA_FAST)
    ema_s = ema_series(close_a, EMA_SLOW)
    atr = wilder_atr(high, low, close, ATR_PERIOD)
    high_a = np.asarray(high, dtype=float)
    low_a = np.asarray(low, dtype=float)
    vol_a = np.asarray(volume, dtype=float)
    out = np.zeros(n, dtype=int)
    fired: set[date] = set()
    last = n - 1 if exclude_forming else n
    ts = _as_utc_array(times)
    vday: date | None = None
    vnum = 0.0
    vden = 0.0
    or_h = float("nan")
    or_l = float("nan")
    or_set = False
    last_or = -1
    for i in range(last):
        et = to_et(ts[i])
        day = et.date()
        if day != vday:
            vday = day
            vnum = 0.0
            vden = 0.0
            or_h = float("nan")
            or_l = float("nan")
            or_set = False
            last_or = -1
        if is_ny_cash(ts[i]):
            typ = (high_a[i] + low_a[i] + close_a[i]) / 3.0
            vol = max(float(vol_a[i]), 1.0)
            vnum += typ * vol
            vden += vol
        start = ny_cash_open_et(day)
        end = or_end_et(day, or_minutes)
        if start <= et < end:
            if not or_set:
                or_h = float(high_a[i])
                or_l = float(low_a[i])
                or_set = True
            else:
                or_h = max(or_h, float(high_a[i]))
                or_l = min(or_l, float(low_a[i]))
            last_or = i
        vwap_i = (vnum / vden) if vden > 0.0 else float("nan")
        ors = (
            OrState(True, float(or_h), float(or_l), last_or)
            if or_set and et >= end
            else OrState(False, float("nan"), float("nan"), last_or)
        )
        sig = scalp_signal_at(
            times,
            high,
            low,
            close,
            volume,
            i,
            ema_fast=ema_f,
            ema_slow=ema_s,
            atr=atr,
            or_minutes=or_minutes,
            min_atr_pct=min_atr_pct,
            one_per_day=one_per_day,
            prior_signal_et_dates=fired,
            ors=ors,
            vwap=vwap_i,
            ts_utc=ts,
        )
        out[i] = sig.value
        if sig.value != 0:
            fired.add(day)
    return out


def looks_like_us_index(symbol: str) -> bool:
    u = symbol.upper().replace(" ", "").replace("-", "").replace("/", "")
    needles = (
        "US30",
        "DJ30",
        "DJIA",
        "US100",
        "NAS100",
        "USTEC",
        "NASDAQ",
        "NDX",
        "US500",
        "SPX",
        "SP500",
        "US2000",
    )
    return any(n in u for n in needles)
