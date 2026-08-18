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
from numpy.lib.stride_tricks import sliding_window_view

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


def wick_parts(open_: float, high: float, low: float, close: float) -> tuple[float, float, float]:
    """Upper wick, lower wick, range. Range 0 when the bar is flat."""
    rng = float(high) - float(low)
    body_top = max(float(open_), float(close))
    body_bot = min(float(open_), float(close))
    return float(high) - body_top, body_bot - float(low), rng


def fvg_at(
    high: np.ndarray, low: np.ndarray, i: int
) -> tuple[int, float, float, float] | None:
    """3-bar FVG known on the close of ``i``. No look-ahead past ``i``.

    Returns ``(side, gap_high, gap_low, ce)`` or None.
    side +1 = bullish gap (price left a hole up); −1 = bearish.
    """
    if i < 2:
        return None
    h = np.asarray(high, dtype=float)
    lo = np.asarray(low, dtype=float)
    if lo[i] > h[i - 2]:
        top, bot = float(lo[i]), float(h[i - 2])
        return +1, top, bot, 0.5 * (top + bot)
    if h[i] < lo[i - 2]:
        top, bot = float(lo[i - 2]), float(h[i])
        return -1, top, bot, 0.5 * (top + bot)
    return None


def pre_ny_liquidity_levels(
    times: list[datetime],
    high: np.ndarray,
    low: np.ndarray,
    keys: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Asia, London-pre-NY, and prior-ET-day ranges as known on each bar.

    Asia = Tokyo span for that ET date, bars strictly before 09:30 ET.
    London-pre-NY = London span bars strictly before 09:30 ET.
    PDH/PDL = full prior ET calendar day (complete, no look-ahead).
    """
    high_a = np.asarray(high, dtype=float)
    low_a = np.asarray(low, dtype=float)
    n = len(times)
    asia_h = np.full(n, np.nan)
    asia_l = np.full(n, np.nan)
    lon_h = np.full(n, np.nan)
    lon_l = np.full(n, np.nan)
    pdh = np.full(n, np.nan)
    pdl = np.full(n, np.nan)
    if n == 0:
        return asia_h, asia_l, lon_h, lon_l, pdh, pdl

    day_h: dict[int, float] = {}
    day_l: dict[int, float] = {}
    day_first: dict[int, int] = {}
    for i in range(n):
        d = int(keys[i])
        if d not in day_first:
            day_first[d] = i
            day_h[d] = float(high_a[i])
            day_l[d] = float(low_a[i])
        else:
            if high_a[i] > day_h[d]:
                day_h[d] = float(high_a[i])
            if low_a[i] < day_l[d]:
                day_l[d] = float(low_a[i])

    unique_days = sorted(day_first)
    prev: int | None = None
    for d in unique_days:
        y, mo, day = d // 10000, (d // 100) % 100, d % 100
        et_day = date(y, mo, day)
        spans = session_spans_for_et_date(et_day)
        tokyo = next(s for s in spans if s.session_id == SessionId.TOKYO)
        london = next(s for s in spans if s.session_id == SessionId.LONDON)
        ny_open = ny_cash_open_et(et_day).astimezone(UTC)
        i0 = max(0, day_first[d] - 400)
        i1 = min(n, day_first[d] + 120)
        ah, al = -np.inf, np.inf
        lh, ll = -np.inf, np.inf
        for k in range(i0, i1):
            t = times[k]
            if tokyo.start_utc <= t < tokyo.end_utc and t < ny_open:
                if high_a[k] > ah:
                    ah = float(high_a[k])
                if low_a[k] < al:
                    al = float(low_a[k])
            if london.start_utc <= t < london.end_utc and t < ny_open:
                if high_a[k] > lh:
                    lh = float(high_a[k])
                if low_a[k] < ll:
                    ll = float(low_a[k])
        if not np.isfinite(ah):
            ah = al = float("nan")
        if not np.isfinite(lh):
            lh = ll = float("nan")
        ph = day_h[prev] if prev is not None else float("nan")
        pl = day_l[prev] if prev is not None else float("nan")
        i_start = day_first[d]
        i_end = n
        for nxt in unique_days:
            if nxt > d:
                i_end = day_first[nxt]
                break
        asia_h[i_start:i_end] = ah
        asia_l[i_start:i_end] = al
        lon_h[i_start:i_end] = lh
        lon_l[i_start:i_end] = ll
        pdh[i_start:i_end] = ph
        pdl[i_start:i_end] = pl
        prev = d
    return asia_h, asia_l, lon_h, lon_l, pdh, pdl


def atr_expanding(
    atr_fast: np.ndarray, atr_slow: np.ndarray, k: float = 1.0
) -> np.ndarray:
    """True when short ATR exceeds long ATR * k (expanding vol)."""
    f = np.asarray(atr_fast, dtype=float)
    s = np.asarray(atr_slow, dtype=float)
    return np.isfinite(f) & np.isfinite(s) & (s > 0.0) & (f > s * float(k))


def proxy_cvd_series(
    keys: np.ndarray,
    open_: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
) -> np.ndarray:
    """ET-day cumulative sign(close-open)*tick_volume. Not bid/ask CVD."""
    o = np.asarray(open_, dtype=float)
    c = np.asarray(close, dtype=float)
    v = np.asarray(volume, dtype=float)
    n = len(c)
    out = np.zeros(n, dtype=float)
    acc = 0.0
    day = -1
    for i in range(n):
        d = int(keys[i])
        if d != day:
            day = d
            acc = 0.0
        if c[i] > o[i]:
            acc += float(v[i])
        elif c[i] < o[i]:
            acc -= float(v[i])
        out[i] = acc
    return out


def prior_day_poc(
    keys: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    volume: np.ndarray,
    *,
    bin_price: float = 2.0,
    kind: str = "volume",
) -> np.ndarray:
    """Prior ET-date profile POC. ``kind`` is ``volume`` or ``tpo``."""
    h = np.asarray(high, dtype=float)
    lo = np.asarray(low, dtype=float)
    vol = np.asarray(volume, dtype=float)
    n = len(h)
    out = np.full(n, np.nan)
    if n == 0 or bin_price <= 0.0:
        return out

    def _poc(idx: list[int]) -> float:
        if not idx:
            return float("nan")
        lo_m = float(np.min(lo[idx]))
        hi_m = float(np.max(h[idx]))
        if not (np.isfinite(lo_m) and np.isfinite(hi_m)) or hi_m <= lo_m:
            return float("nan")
        nbin = int(np.ceil((hi_m - lo_m) / bin_price)) + 1
        acc = np.zeros(nbin, dtype=float)
        for i in idx:
            a = float(lo[i])
            b = float(h[i])
            if not (np.isfinite(a) and np.isfinite(b)) or b < a:
                continue
            i0 = int((a - lo_m) / bin_price)
            i1 = int((b - lo_m) / bin_price)
            i0 = max(0, min(nbin - 1, i0))
            i1 = max(0, min(nbin - 1, i1))
            span = i1 - i0 + 1
            add = 1.0 if kind == "tpo" else float(max(vol[i], 0.0)) / span
            acc[i0 : i1 + 1] += add
        return lo_m + (int(np.argmax(acc)) + 0.5) * bin_price

    groups: dict[int, list[int]] = {}
    order: list[int] = []
    for i in range(n):
        d = int(keys[i])
        if d not in groups:
            groups[d] = []
            order.append(d)
        groups[d].append(i)
    prev_poc = float("nan")
    for d in order:
        idx = groups[d]
        out[idx[0] : idx[-1] + 1] = prev_poc
        prev_poc = _poc(idx)
    return out


CASH_START_MIN = 9 * 60 + 30
CASH_END_MIN = 16 * 60
IB_END_MIN = 10 * 60 + 30
H4_SECONDS = 4 * 3600


def prior_cash_close_series(
    mins: np.ndarray,
    keys: np.ndarray,
    close: np.ndarray,
) -> np.ndarray:
    """Prior *completed* NY-cash close (09:30–16:00 ET), known from that day on.

    Not the last pre-09:30 print. That jump is ~0 on this CFD.
    """
    c = np.asarray(close, dtype=float)
    n = len(c)
    out = np.full(n, np.nan)
    last_cash: dict[int, float] = {}
    order: list[int] = []
    for i in range(n):
        d = int(keys[i])
        m = int(mins[i])
        if d not in last_cash:
            last_cash[d] = float("nan")
            order.append(d)
        if CASH_START_MIN <= m < CASH_END_MIN:
            last_cash[d] = float(c[i])
    prev = float("nan")
    day_prev: dict[int, float] = {}
    for d in order:
        day_prev[d] = prev
        if np.isfinite(last_cash[d]):
            prev = last_cash[d]
    for i in range(n):
        out[i] = day_prev[int(keys[i])]
    return out


def cash_open_gap_pct(
    mins: np.ndarray,
    keys: np.ndarray,
    open_: np.ndarray,
    prior_close: np.ndarray,
) -> np.ndarray:
    """``open(first ≥09:30 ET) / prior_cash_close − 1``, ffilled for that ET day.

    Known at the 09:30 open. Does not use that bar's high/low/close.
    """
    o = np.asarray(open_, dtype=float)
    pc = np.asarray(prior_close, dtype=float)
    n = len(o)
    out = np.full(n, np.nan)
    day = -1
    gap = float("nan")
    seen = False
    for i in range(n):
        d = int(keys[i])
        if d != day:
            day = d
            gap = float("nan")
            seen = False
        if (not seen) and int(mins[i]) >= CASH_START_MIN and np.isfinite(pc[i]) and pc[i] > 0.0:
            gap = float(o[i]) / float(pc[i]) - 1.0
            seen = True
        out[i] = gap
    return out


def cash_adr_series(
    mins: np.ndarray,
    keys: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    n: int = 14,
) -> np.ndarray:
    """Mean of last ``n`` *completed* cash-session ranges. Excludes today."""
    h = np.asarray(high, dtype=float)
    lo = np.asarray(low, dtype=float)
    nbar = len(h)
    out = np.full(nbar, np.nan)
    if n < 1:
        return out
    day_hi: dict[int, float] = {}
    day_lo: dict[int, float] = {}
    order: list[int] = []
    for i in range(nbar):
        d = int(keys[i])
        m = int(mins[i])
        if d not in day_hi:
            day_hi[d] = -np.inf
            day_lo[d] = np.inf
            order.append(d)
        if CASH_START_MIN <= m < CASH_END_MIN:
            if h[i] > day_hi[d]:
                day_hi[d] = float(h[i])
            if lo[i] < day_lo[d]:
                day_lo[d] = float(lo[i])
    ranges: list[float] = []
    day_adr: dict[int, float] = {}
    for d in order:
        if ranges:
            take = ranges[-n:]
            day_adr[d] = float(np.mean(take))
        else:
            day_adr[d] = float("nan")
        if np.isfinite(day_hi[d]) and np.isfinite(day_lo[d]) and day_hi[d] > day_lo[d]:
            ranges.append(day_hi[d] - day_lo[d])
    for i in range(nbar):
        out[i] = day_adr[int(keys[i])]
    return out


def completed_h4_ema_bias(
    times: list[datetime],
    close: np.ndarray,
    *,
    fast: int = 50,
    slow: int = 200,
) -> np.ndarray:
    """BTC-style H4 bias from *completed* UTC 4h buckets only.

    +1 if completed H4 close > EMA200 and EMA50 > EMA200.
    Forming bucket is ignored (CompletedHtfShift).
    """
    c = np.asarray(close, dtype=float)
    n = len(c)
    out = np.zeros(n, dtype=np.int8)
    if n == 0 or slow < 2 or fast < 1 or slow <= fast:
        return out
    epochs = np.array([to_utc(t).timestamp() for t in times], dtype=float)
    bucket = np.floor(epochs / H4_SECONDS).astype(np.int64)
    h4_close: list[float] = []
    h4_end: list[float] = []
    b0 = int(bucket[0])
    last = float(c[0])
    for i in range(1, n):
        b = int(bucket[i])
        if b != b0:
            h4_close.append(last)
            h4_end.append(float((b0 + 1) * H4_SECONDS))
            b0 = b
        last = float(c[i])
    if not h4_close:
        return out
    h4 = np.asarray(h4_close, dtype=float)
    ema_f = ema_series(h4, fast)
    ema_s = ema_series(h4, slow)
    ends = np.asarray(h4_end, dtype=float)
    j = -1
    for i in range(n):
        while j + 1 < len(ends) and ends[j + 1] <= epochs[i]:
            j += 1
        if j < 0:
            continue
        ef = float(ema_f[j])
        es = float(ema_s[j])
        px = float(h4[j])
        if not (np.isfinite(ef) and np.isfinite(es)):
            continue
        if px > es and ef > es:
            out[i] = 1
        elif px < es and ef < es:
            out[i] = -1
    return out


def completed_daily_donch_state(
    keys: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    n: int = 20,
) -> np.ndarray:
    """ET-date Donchian state from *completed* days only.

    Channel = last ``n`` completed days **excluding** the last completed day.
    +1 if that day's close is above the channel high; −1 below the low; else 0.
    """
    h = np.asarray(high, dtype=float)
    lo = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    nbar = len(c)
    out = np.zeros(nbar, dtype=np.int8)
    if n < 1 or nbar == 0:
        return out
    day_h: dict[int, float] = {}
    day_l: dict[int, float] = {}
    day_c: dict[int, float] = {}
    order: list[int] = []
    for i in range(nbar):
        d = int(keys[i])
        if d not in day_h:
            day_h[d] = float(h[i])
            day_l[d] = float(lo[i])
            day_c[d] = float(c[i])
            order.append(d)
        else:
            if h[i] > day_h[d]:
                day_h[d] = float(h[i])
            if lo[i] < day_l[d]:
                day_l[d] = float(lo[i])
            day_c[d] = float(c[i])
    day_state: dict[int, int] = {}
    for k, d in enumerate(order):
        last_i = k - 1
        state = 0
        if last_i >= n:
            ch_days = order[last_i - n : last_i]
            ch_hi = max(day_h[x] for x in ch_days)
            ch_lo = min(day_l[x] for x in ch_days)
            last_c = day_c[order[last_i]]
            if last_c > ch_hi:
                state = 1
            elif last_c < ch_lo:
                state = -1
        day_state[d] = state
    for i in range(nbar):
        out[i] = day_state[int(keys[i])]
    return out


REGIME_MOM = 1
REGIME_MR = -1
REGIME_CHOP = 0
LONDON_ET_HOURS = (7, 8)
LONDON_FEATURE_END_MIN = 9 * 60


def et_day_ohlc(
    keys: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Full ET-date OHLC in first-seen order. The last day may still be forming."""
    k = np.asarray(keys, dtype=np.int64)
    o = np.asarray(open_, dtype=float)
    h = np.asarray(high, dtype=float)
    lo = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    order: list[int] = []
    recs: dict[int, list[float]] = {}
    for i in range(len(k)):
        d = int(k[i])
        if d not in recs:
            recs[d] = [float(o[i]), float(h[i]), float(lo[i]), float(c[i])]
            order.append(d)
            continue
        rec = recs[d]
        if h[i] > rec[1]:
            rec[1] = float(h[i])
        if lo[i] < rec[2]:
            rec[2] = float(lo[i])
        rec[3] = float(c[i])
    days = np.asarray(order, dtype=np.int64)
    oo = np.array([recs[d][0] for d in order], dtype=float)
    hh = np.array([recs[d][1] for d in order], dtype=float)
    ll = np.array([recs[d][2] for d in order], dtype=float)
    cc = np.array([recs[d][3] for d in order], dtype=float)
    return days, oo, hh, ll, cc


def wilder_adx_series(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = 14,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Wilder ADX / +DI / −DI. Index ``i`` uses bars ``<= i`` only.

    Algorithm matches ``manual-trading-agent/src/indicators/adx.py``
    (sum of first ``period`` TR/DM, then Wilder smooth; first ADX at
    ``2 * period - 1``).
    """
    h = np.asarray(high, dtype=float)
    lo = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    n = int(h.shape[0])
    adx = np.full(n, np.nan)
    plus_di = np.full(n, np.nan)
    minus_di = np.full(n, np.nan)
    if period < 1 or n < 2 * period + 1:
        return adx, plus_di, minus_di
    tr = np.zeros(n, dtype=float)
    plus_dm = np.zeros(n, dtype=float)
    minus_dm = np.zeros(n, dtype=float)
    for i in range(1, n):
        up = h[i] - h[i - 1]
        down = lo[i - 1] - lo[i]
        plus_dm[i] = up if (up > down and up > 0.0) else 0.0
        minus_dm[i] = down if (down > up and down > 0.0) else 0.0
        tr[i] = max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1]))
    sm_tr = np.full(n, np.nan)
    sm_p = np.full(n, np.nan)
    sm_m = np.full(n, np.nan)
    sm_tr[period] = float(np.sum(tr[1 : period + 1]))
    sm_p[period] = float(np.sum(plus_dm[1 : period + 1]))
    sm_m[period] = float(np.sum(minus_dm[1 : period + 1]))
    for i in range(period + 1, n):
        sm_tr[i] = sm_tr[i - 1] - (sm_tr[i - 1] / period) + tr[i]
        sm_p[i] = sm_p[i - 1] - (sm_p[i - 1] / period) + plus_dm[i]
        sm_m[i] = sm_m[i - 1] - (sm_m[i - 1] / period) + minus_dm[i]
    dx = np.full(n, np.nan)
    for i in range(period, n):
        if not np.isfinite(sm_tr[i]) or sm_tr[i] <= 0.0:
            continue
        plus_di[i] = 100.0 * sm_p[i] / sm_tr[i]
        minus_di[i] = 100.0 * sm_m[i] / sm_tr[i]
        di_sum = plus_di[i] + minus_di[i]
        dx[i] = 0.0 if di_sum == 0.0 else 100.0 * abs(plus_di[i] - minus_di[i]) / di_sum
    first = 2 * period - 1
    window = dx[period : period + period]
    if first < n and bool(np.all(np.isfinite(window))):
        adx[first] = float(np.mean(window))
        for i in range(first + 1, n):
            if not np.isfinite(dx[i]) or not np.isfinite(adx[i - 1]):
                continue
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period
    return adx, plus_di, minus_di


def hurst_rs(closes: np.ndarray) -> float:
    """R/S Hurst on completed closes. NaN if unstable (short / flat / non-finite)."""
    x = np.asarray(closes, dtype=float)
    x = x[np.isfinite(x)]
    n = int(x.shape[0])
    if n < 8:
        return float("nan")
    y = x - float(np.mean(x))
    z = np.cumsum(y)
    rng = float(np.max(z) - np.min(z))
    std = float(np.std(x, ddof=1))
    if rng <= 0.0 or std <= 0.0:
        return float("nan")
    return float(np.log(rng / std) / np.log(n))


def variance_ratio(closes: np.ndarray, k: int = 2) -> float:
    """Lo–MacKinlay VR(k) on log-returns of completed closes."""
    x = np.asarray(closes, dtype=float)
    x = x[np.isfinite(x) & (x > 0.0)]
    if k < 2 or int(x.shape[0]) < k + 3:
        return float("nan")
    ret = np.diff(np.log(x))
    if int(ret.shape[0]) < k + 2:
        return float("nan")
    v1 = float(np.var(ret, ddof=1))
    if v1 <= 0.0:
        return float("nan")
    summed = np.array(
        [float(np.sum(ret[i : i + k])) for i in range(int(ret.shape[0]) - k + 1)],
        dtype=float,
    )
    vk = float(np.var(summed, ddof=1))
    return vk / (float(k) * v1)


def persist_from_closes(
    closes: np.ndarray,
    lookback: int,
    *,
    fallback: str = "variance_ratio",
    vr_k: int = 2,
) -> float:
    """Hurst on the last ``lookback`` closes; locked VR fallback if Hurst is NaN."""
    x = np.asarray(closes, dtype=float)
    if lookback < 8 or int(x.shape[0]) < lookback:
        return float("nan")
    window = x[-lookback:]
    h = hurst_rs(window)
    if np.isfinite(h):
        return float(h)
    if fallback != "variance_ratio":
        return float("nan")
    vr = variance_ratio(window, k=vr_k)
    if not np.isfinite(vr):
        return float("nan")
    if vr > 1.0:
        return 0.56
    if vr < 1.0:
        return 0.44
    return 0.5


def completed_daily_regime_state(
    keys: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    *,
    atr_n: int = 20,
    hurst_lb: int = 32,
    adx_period: int = 14,
    adx_mom: float = 25.0,
    adx_mr: float = 20.0,
    atr_mom_pct: float = 60.0,
    atr_mr_pct: float = 40.0,
    hurst_mom: float = 0.55,
    hurst_mr: float = 0.45,
    hurst_fallback: str = "variance_ratio",
    vr_k: int = 2,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-M5 daily regime from *prior completed* ET-days only.

    ``+1`` momentum, ``-1`` mean-reversion, ``0`` chop. Today's forming
    ET-day OHLC never enters that day's predicate.
    """
    nbar = len(np.asarray(close, dtype=float))
    state_a = np.zeros(nbar, dtype=np.int8)
    hurst_a = np.full(nbar, np.nan)
    adx_a = np.full(nbar, np.nan)
    days, _o, h, lo, c = et_day_ohlc(keys, open_, high, low, close)
    nd = int(days.shape[0])
    if nd == 0:
        return state_a, hurst_a, adx_a
    adx, _p, _m = wilder_adx_series(h, lo, c, adx_period)
    atr = wilder_atr(h, lo, c, ATR_PERIOD)
    day_state: dict[int, int] = {}
    day_hurst: dict[int, float] = {}
    day_adx: dict[int, float] = {}
    for d in range(nd):
        last = d - 1
        st = REGIME_CHOP
        hu = float("nan")
        ad = float("nan")
        expanding = False
        compressed = False
        if last >= 0:
            ad = float(adx[last])
            at = float(atr[last])
            ref_i0 = last - int(atr_n)
            if ref_i0 >= 0 and np.isfinite(at):
                ref = atr[ref_i0:last]
                ref = ref[np.isfinite(ref)]
                if int(ref.shape[0]) == int(atr_n):
                    expanding = at > float(np.percentile(ref, atr_mom_pct))
                    compressed = at < float(np.percentile(ref, atr_mr_pct))
            if last + 1 >= int(hurst_lb):
                hu = persist_from_closes(
                    c[: last + 1],
                    int(hurst_lb),
                    fallback=hurst_fallback,
                    vr_k=vr_k,
                )
            mom = (
                np.isfinite(ad)
                and ad > adx_mom
                and expanding
                and np.isfinite(hu)
                and hu > hurst_mom
            )
            mr = (
                np.isfinite(ad)
                and ad < adx_mr
                and compressed
                and np.isfinite(hu)
                and hu < hurst_mr
            )
            if mom and not mr:
                st = REGIME_MOM
            elif mr and not mom:
                st = REGIME_MR
        day_key = int(days[d])
        day_state[day_key] = st
        day_hurst[day_key] = hu
        day_adx[day_key] = ad
    k = np.asarray(keys, dtype=np.int64)
    for i in range(nbar):
        d = int(k[i])
        state_a[i] = day_state.get(d, REGIME_CHOP)
        hurst_a[i] = day_hurst.get(d, float("nan"))
        adx_a[i] = day_adx.get(d, float("nan"))
    return state_a, hurst_a, adx_a


def causal_session_vwap_prev(
    mins: np.ndarray,
    keys: np.ndarray,
    ny: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
) -> np.ndarray:
    """NY-cash VWAP at ``i`` from completed session bars ``< i`` only."""
    h = np.asarray(high, dtype=float)
    lo = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    v = np.asarray(volume, dtype=float)
    n = len(c)
    out = np.full(n, np.nan)
    vday = -1
    num = 0.0
    den = 0.0
    last = float("nan")
    for i in range(n):
        d = int(keys[i])
        if d != vday:
            vday = d
            num = 0.0
            den = 0.0
            last = float("nan")
        out[i] = last
        if bool(ny[i]):
            typ = (h[i] + lo[i] + c[i]) / 3.0
            vv = max(float(v[i]), 1.0)
            num += typ * vv
            den += vv
            if den > 0.0:
                last = num / den
    return out


def london_et_displacement(
    times: list[datetime],
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    *,
    atr_period: int = ATR_PERIOD,
) -> dict[int, dict[str, float]]:
    """XAU/FX London window on *America/New_York* 07:00–09:00.

    Uses only H1 (or M5) bars whose ET open hour is 7 or 8. The 08:00 bar
    close is known at 09:00 ET. Bars with ET hour >= 9 are ignored
    (T* isolation — the 09:30 hour never enters).
    """
    o = np.asarray(open_, dtype=float)
    h = np.asarray(high, dtype=float)
    lo = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    atr = wilder_atr(h, lo, c, atr_period)
    by_day: dict[int, list[tuple[int, int]]] = {}
    for i, ts in enumerate(times):
        et = to_et(ts)
        d = et.year * 10000 + et.month * 100 + et.day
        by_day.setdefault(d, []).append((et.hour, i))
    out: dict[int, dict[str, float]] = {}
    for d, items in by_day.items():
        i7 = next((i for hour, i in items if hour == 7), None)
        i8 = next((i for hour, i in items if hour == 8), None)
        if i7 is None or i8 is None:
            continue
        disp = float(c[i8]) - float(o[i7])
        at = float(atr[i8])
        out[d] = {
            "disp": disp,
            "sign": 1.0 if disp > 0.0 else (-1.0 if disp < 0.0 else 0.0),
            "atr": at,
            "range": max(float(h[i7]), float(h[i8])) - min(float(lo[i7]), float(lo[i8])),
            "feature_end_min": float(LONDON_FEATURE_END_MIN),
        }
    return out


def london_feature_on_m5(
    keys: np.ndarray,
    mins: np.ndarray,
    feat: dict[int, dict[str, float]],
    field: str = "sign",
) -> np.ndarray:
    """As-of join: feature is visible only on bars with open >= 09:00 ET."""
    n = len(keys)
    out = np.full(n, np.nan)
    for i in range(n):
        if int(mins[i]) < LONDON_FEATURE_END_MIN:
            continue
        rec = feat.get(int(keys[i]))
        if rec is None:
            continue
        out[i] = float(rec[field])
    return out


def typical_price(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """(H + L + C) / 3."""
    return (
        np.asarray(high, dtype=float)
        + np.asarray(low, dtype=float)
        + np.asarray(close, dtype=float)
    ) / 3.0


def rolling_zscore_typical(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    window: int,
    *,
    include_i: bool = False,
    ddof: int = 1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Causal rolling z-score of typical price and the matching volume mean.

    Default (``include_i=False``, v7 lock): μ / σ / Vμ use bars
    ``i-window .. i-1``. Bar ``i`` and every later bar are excluded.
    ``include_i=True`` uses ``i-window+1 .. i`` (not the v7 freeze).
    σ uses sample std (``ddof=1``) unless overridden. Z is NaN when σ<=0.
    """
    p = typical_price(high, low, close)
    v = np.asarray(volume, dtype=float)
    n = int(p.shape[0])
    z = np.full(n, np.nan)
    mu = np.full(n, np.nan)
    sig = np.full(n, np.nan)
    vmu = np.full(n, np.nan)
    if window < 2 or n < window or int(v.shape[0]) != n:
        return z, mu, sig, vmu
    p_win = sliding_window_view(p, window)
    v_win = sliding_window_view(v, window)
    if include_i:
        sl = slice(window - 1, n)
        src = slice(None)
    else:
        sl = slice(window, n)
        src = slice(None, -1)
    mu[sl] = p_win[src].mean(axis=1)
    sig[sl] = p_win[src].std(axis=1, ddof=ddof)
    vmu[sl] = v_win[src].mean(axis=1)
    good = sig[sl] > 0.0
    z[sl] = np.where(good, (p[sl] - mu[sl]) / sig[sl], np.nan)
    return z, mu, sig, vmu


def ib_false_break_signals(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    mins: np.ndarray,
    keys: np.ndarray,
    dow: np.ndarray,
    or_h: np.ndarray,
    or_l: np.ndarray,
    ready: np.ndarray,
    *,
    entry_end_min: int,
    one_per_day: bool = True,
    exclude_forming: bool = True,
    friday_cutoff_min: int = 14 * 60,
) -> np.ndarray:
    """IB false-break fade. Signal on the *return* bar close; fill is next open.

    Sweep bar ``i`` (IB already complete): high > IBh or low < IBl, not both.
    Trigger on ``i+1`` only if that bar closes back inside. Same-bar close-back
    does not count. Friday cutoff and ``entry_end_min`` apply to the return bar.
    """
    h = np.asarray(high, dtype=float)
    lo = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    n = int(c.shape[0])
    out = np.zeros(n, dtype=np.int8)
    last = n - 1 if exclude_forming else n
    fired = -1
    i = 0
    while i < last - 1:
        if not bool(ready[i]):
            i += 1
            continue
        if int(mins[i]) >= int(entry_end_min):
            i += 1
            continue
        d = int(keys[i])
        if one_per_day and d == fired:
            i += 1
            continue
        oh = float(or_h[i])
        ol = float(or_l[i])
        if not (np.isfinite(oh) and np.isfinite(ol) and oh > ol):
            i += 1
            continue
        swept_h = float(h[i]) > oh
        swept_l = float(lo[i]) < ol
        if swept_h == swept_l:
            i += 1
            continue
        j = i + 1
        if j >= last or int(keys[j]) != d:
            i += 1
            continue
        if int(mins[j]) >= int(entry_end_min):
            i += 1
            continue
        if int(dow[j]) == 4 and int(mins[j]) >= friday_cutoff_min:
            i += 1
            continue
        cj = float(c[j])
        if not (ol <= cj <= oh):
            i += 1
            continue
        out[j] = np.int8(-1 if swept_h else 1)
        fired = d
        i = j + 1
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
