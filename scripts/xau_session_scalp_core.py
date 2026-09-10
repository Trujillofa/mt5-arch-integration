#!/usr/bin/env python3
"""Causal gold session-scalp helpers (offline research).

Frozen combo (not a search)
---------------------------
``xau_london_defined_r_be_flat_v1`` — XAUUSD scalp stack (supersedes ``xau_london_orb_overlap_vwap_ema_flat``):

Gold is a 23h CFD. It does **not** have a US cash-index print at 09:30 ET.
The index combo ``ny_cash_orb_vwap_ema_flat`` is therefore the wrong event
clock. This module uses the two liquidity injections that do exist:

1. **London open** (08:00 Europe/London) is the primary event.
2. **NY metals desk** (08:00-17:00 America/New_York) is the second box.
   That is not NY cash 09:30-16:00.
3. **Opening range** = first ``or_minutes`` of London (default 30).
   Knowable only on the first bar whose *open* is at or after
   ``08:00 + or_minutes`` London (last OR bar has then closed).
4. **London-date VWAP** from the first London bar of that London date
   (typical x tick_volume; volume floor 1).
5. **EMA 9 / 21** scalp stack.
6. **AND signal** on a closed bar in one of two session boxes:
   London continuation ``[OR end, 11:00)`` London, or NY drive
   ``[08:00, 11:00)`` ET once the London OR is complete.
   Close must confirm beyond OR + VWAP + EMA stack + ATR% floor.
7. **One signal per session box** (London date / NY ET date).
8. **Friday:** no new entries at or after 14:00 ET (weekend gap).
9. **OR-width gate:** completed London OR width / ATR must sit in
   ``[0.35, 2.5]``. Extreme ranges are skipped (garbage filter).
10. **Risk (replay / guides):** hard SL ``1.0 ATR``, TP = ``1.0 R``,
    6-bar time-stop, flatten at box end. Cost-to-TP is a fill-time
    gate in the simulator / live spread check, not a historical
    buffer rewrite.

SAFETY: offline research only. No orders. Consumers must not re-derive
the OR stamp at London 08:00 — that is lookahead.
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
OR_MINUTES = 30
LONDON_ENTRY_END = time(11, 0)
NY_ENTRY_START = time(8, 0)
NY_ENTRY_END = time(11, 0)
LONDON_FLAT = time(11, 0)
NY_FLAT = time(11, 0)
FRIDAY_CUTOFF = time(14, 0)
EMA_FAST = 9
EMA_SLOW = 21
ATR_PERIOD = 14
MIN_ATR_PCT = 0.00015
OR_BUFFER_ATR_FRAC = 0.10
OR_WIDTH_ATR_MIN = 0.35
OR_WIDTH_ATR_MAX = 2.5
FAMILY_ID = "xau_london_defined_r_be_flat_v1"
SUPERSEDED_FAMILY_ID = "xau_london_orb_overlap_vwap_ema_flat"
BASELINE_FAMILY_ID = "ny_cash_orb_vwap_ema_flat"


class GoldSessionId(IntEnum):
    NONE = 0
    TOKYO = 1
    LONDON = 2
    NY_METALS = 3
    OVERLAP = 4


class SessionBox(IntEnum):
    """Tradable scalp box (not the draw-session id)."""

    NONE = 0
    LONDON = 1
    NY = 2


@dataclass(frozen=True)
class OrState:
    complete: bool
    high: float
    low: float
    last_or_idx: int


@dataclass(frozen=True)
class ScalpSignal:
    value: int  # +1 / -1 / 0
    reason: str
    or_high: float
    or_low: float
    vwap: float
    box: SessionBox


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


def is_ny_metals(ts: datetime) -> bool:
    """US metals desk. Not US cash-index 09:30-16:00."""
    return _in_local_window(to_et(ts), time(8, 0), time(17, 0))


def session_id(ts: datetime) -> GoldSessionId:
    lon = is_london_open(ts)
    ny = is_ny_metals(ts)
    if lon and ny:
        return GoldSessionId.OVERLAP
    if ny:
        return GoldSessionId.NY_METALS
    if lon:
        return GoldSessionId.LONDON
    if is_tokyo_open(ts):
        return GoldSessionId.TOKYO
    return GoldSessionId.NONE


def session_name(sid: GoldSessionId) -> str:
    return {
        GoldSessionId.TOKYO: "Tokyo",
        GoldSessionId.LONDON: "London",
        GoldSessionId.NY_METALS: "NY metals",
        GoldSessionId.OVERLAP: "LDN+NY",
        GoldSessionId.NONE: "Off",
    }[sid]


def london_open_local(ldn_day: date) -> datetime:
    return datetime(ldn_day.year, ldn_day.month, ldn_day.day, 8, 0, tzinfo=TZ_LON)


def london_or_end(ldn_day: date, or_minutes: int = OR_MINUTES) -> datetime:
    return london_open_local(ldn_day) + timedelta(minutes=or_minutes)


def friday_entry_blocked(ts: datetime, cutoff: time = FRIDAY_CUTOFF) -> bool:
    et = to_et(ts)
    if et.weekday() != 4:
        return False
    return et.timetz().replace(tzinfo=None) >= cutoff


def in_london_entry(
    ts: datetime,
    or_minutes: int = OR_MINUTES,
    entry_end: time = LONDON_ENTRY_END,
) -> bool:
    lon = to_london(ts)
    t = lon.timetz().replace(tzinfo=None)
    start = london_or_end(lon.date(), or_minutes).timetz().replace(tzinfo=None)
    return start <= t < entry_end


def in_ny_entry(
    ts: datetime,
    start: time = NY_ENTRY_START,
    end: time = NY_ENTRY_END,
) -> bool:
    return _in_local_window(to_et(ts), start, end)


def session_box_at(
    ts: datetime,
    *,
    or_minutes: int = OR_MINUTES,
    allow_ny: bool = True,
) -> SessionBox:
    if in_london_entry(ts, or_minutes):
        return SessionBox.LONDON
    if allow_ny and in_ny_entry(ts):
        return SessionBox.NY
    return SessionBox.NONE


def box_key(ts: datetime, box: SessionBox) -> tuple[str, date] | None:
    if box == SessionBox.LONDON:
        return ("L", to_london(ts).date())
    if box == SessionBox.NY:
        return ("N", to_et(ts).date())
    return None


def looks_like_gold(symbol: str) -> bool:
    u = (
        symbol.upper()
        .replace(" ", "")
        .replace("-", "")
        .replace("/", "")
        .replace(".", "")
        .replace("_", "")
    )
    return "XAU" in u or u.startswith("GOLD") or "GOLD" in u


def _as_utc_array(times: np.ndarray | list) -> list[datetime]:
    out: list[datetime] = []
    for t in times:
        if isinstance(t, np.datetime64):
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
    """London OR as known on the *close* of bar ``i`` (no lookahead past ``i``)."""
    high_a = np.asarray(high, dtype=float)
    low_a = np.asarray(low, dtype=float)
    ts = _as_utc_array(times)
    if i < 0 or i >= len(ts):
        return OrState(False, float("nan"), float("nan"), -1)

    ldn_day = to_london(ts[i]).date()
    start = london_open_local(ldn_day)
    end = london_or_end(ldn_day, or_minutes)
    or_h = -np.inf
    or_l = np.inf
    last = -1
    for k in range(i + 1):
        lon = to_london(ts[k])
        if lon.date() != ldn_day:
            continue
        if start <= lon < end:
            or_h = max(or_h, float(high_a[k]))
            or_l = min(or_l, float(low_a[k]))
            last = k
    if last < 0:
        return OrState(False, float("nan"), float("nan"), -1)
    complete = to_london(ts[i]) >= end
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
    """London-date VWAP through closed bar ``i``. NaN if none."""
    high_a = np.asarray(high, dtype=float)
    low_a = np.asarray(low, dtype=float)
    close_a = np.asarray(close, dtype=float)
    vol_a = np.asarray(volume, dtype=float)
    ts = _as_utc_array(times)
    if i < 0 or i >= len(ts):
        return float("nan")
    ldn_day = to_london(ts[i]).date()
    num = 0.0
    den = 0.0
    for k in range(i + 1):
        if not is_london_open(ts[k]):
            continue
        if to_london(ts[k]).date() != ldn_day:
            continue
        typ = (high_a[k] + low_a[k] + close_a[k]) / 3.0
        vol = max(float(vol_a[k]), 1.0)
        num += typ * vol
        den += vol
    if den <= 0.0:
        return float("nan")
    return num / den


def ema_series(price: np.ndarray, period: int) -> np.ndarray:
    """Seed SMA then recursive EMA — index 0 = oldest."""
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


def wilder_atr(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = ATR_PERIOD,
) -> np.ndarray:
    """Wilder ATR — index 0 = oldest."""
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
    or_width_atr_min: float = OR_WIDTH_ATR_MIN,
    or_width_atr_max: float = OR_WIDTH_ATR_MAX,
    allow_ny: bool = True,
    one_per_box: bool = True,
    prior_boxes: set[tuple[str, date]] | None = None,
    ors: OrState | None = None,
    vwap: float | None = None,
    ts_utc: list[datetime] | None = None,
) -> ScalpSignal:
    """AND confluence on closed bar ``i``. No look-ahead past ``i``."""
    close_a = np.asarray(close, dtype=float)
    ts = ts_utc if ts_utc is not None else _as_utc_array(times)
    empty = ScalpSignal(
        0, "bad_index", float("nan"), float("nan"), float("nan"), SessionBox.NONE
    )
    if i < 0 or i >= len(ts):
        return empty

    if friday_entry_blocked(ts[i]):
        return ScalpSignal(
            0, "friday_cutoff", float("nan"), float("nan"), float("nan"), SessionBox.NONE
        )
    box = session_box_at(ts[i], or_minutes=or_minutes, allow_ny=allow_ny)
    if box == SessionBox.NONE:
        return ScalpSignal(
            0,
            "outside_entry_window",
            float("nan"),
            float("nan"),
            float("nan"),
            SessionBox.NONE,
        )

    if ors is None:
        ors = opening_range_at(times, high, low, i, or_minutes=or_minutes)
    if not ors.complete:
        return ScalpSignal(0, "or_incomplete", float("nan"), float("nan"), float("nan"), box)

    if vwap is None:
        vwap = session_vwap_at(times, high, low, close, volume, i)
    if not np.isfinite(vwap):
        return ScalpSignal(0, "no_vwap", ors.high, ors.low, float("nan"), box)

    if ema_fast is None:
        ema_fast = ema_series(close_a, EMA_FAST)
    if ema_slow is None:
        ema_slow = ema_series(close_a, EMA_SLOW)
    ef = float(np.asarray(ema_fast, dtype=float)[i])
    es = float(np.asarray(ema_slow, dtype=float)[i])
    if not (np.isfinite(ef) and np.isfinite(es)):
        return ScalpSignal(0, "ema_warmup", ors.high, ors.low, vwap, box)

    if atr is None:
        atr = wilder_atr(high, low, close, ATR_PERIOD)
    atr_i = float(np.asarray(atr, dtype=float)[i])
    px = float(close_a[i])
    if not np.isfinite(atr_i) or px <= 0.0:
        return ScalpSignal(0, "atr_warmup", ors.high, ors.low, vwap, box)
    if atr_i / px < min_atr_pct:
        return ScalpSignal(0, "dead_atr", ors.high, ors.low, vwap, box)

    or_w = float(ors.high) - float(ors.low)
    if or_w > 0.0 and atr_i > 0.0:
        width_atr = or_w / atr_i
        if width_atr < or_width_atr_min or width_atr > or_width_atr_max:
            return ScalpSignal(0, "or_width", ors.high, ors.low, vwap, box)

    if one_per_box:
        key = box_key(ts[i], box)
        if key is not None and prior_boxes and key in prior_boxes:
            return ScalpSignal(0, "already_signaled_box", ors.high, ors.low, vwap, box)

    buf = or_buffer_atr_frac * atr_i
    long_ok = px > ors.high + buf and px > vwap and ef > es
    short_ok = px < ors.low - buf and px < vwap and ef < es
    if long_ok:
        return ScalpSignal(+1, "london_orb_vwap_ema_long", ors.high, ors.low, vwap, box)
    if short_ok:
        return ScalpSignal(-1, "london_orb_vwap_ema_short", ors.high, ors.low, vwap, box)
    return ScalpSignal(0, "no_confluence", ors.high, ors.low, vwap, box)


def scalp_signal_series(
    times: np.ndarray | list,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    *,
    or_minutes: int = OR_MINUTES,
    min_atr_pct: float = MIN_ATR_PCT,
    or_buffer_atr_frac: float = OR_BUFFER_ATR_FRAC,
    or_width_atr_min: float = OR_WIDTH_ATR_MIN,
    or_width_atr_max: float = OR_WIDTH_ATR_MAX,
    allow_ny: bool = True,
    one_per_box: bool = True,
    exclude_forming: bool = True,
) -> np.ndarray:
    """Walk-forward signals. Forming last bar is 0 when ``exclude_forming``."""
    close_a = np.asarray(close, dtype=float)
    high_a = np.asarray(high, dtype=float)
    low_a = np.asarray(low, dtype=float)
    vol_a = np.asarray(volume, dtype=float)
    n = int(close_a.shape[0])
    ema_f = ema_series(close_a, EMA_FAST)
    ema_s = ema_series(close_a, EMA_SLOW)
    atr = wilder_atr(high, low, close, ATR_PERIOD)
    out = np.zeros(n, dtype=int)
    fired: set[tuple[str, date]] = set()
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
        lon = to_london(ts[i])
        day = lon.date()
        if day != vday:
            vday = day
            vnum = 0.0
            vden = 0.0
            or_h = float("nan")
            or_l = float("nan")
            or_set = False
            last_or = -1
        if is_london_open(ts[i]):
            typ = (high_a[i] + low_a[i] + close_a[i]) / 3.0
            vol = max(float(vol_a[i]), 1.0)
            vnum += typ * vol
            vden += vol
        start = london_open_local(day)
        end = london_or_end(day, or_minutes)
        if start <= lon < end:
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
            if or_set and lon >= end
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
            or_buffer_atr_frac=or_buffer_atr_frac,
            or_width_atr_min=or_width_atr_min,
            or_width_atr_max=or_width_atr_max,
            allow_ny=allow_ny,
            one_per_box=one_per_box,
            prior_boxes=fired,
            ors=ors,
            vwap=vwap_i,
            ts_utc=ts,
        )
        if sig.value != 0:
            out[i] = sig.value
            key = box_key(ts[i], sig.box)
            if key is not None:
                fired.add(key)
    return out


def flatten_time_for_box(ts: datetime, box: SessionBox) -> datetime:
    """Session-box flatten instant (local clock -> aware datetime)."""
    if box == SessionBox.LONDON:
        lon = to_london(ts)
        return datetime(
            lon.year, lon.month, lon.day, LONDON_FLAT.hour, LONDON_FLAT.minute, tzinfo=TZ_LON
        )
    et = to_et(ts)
    return datetime(et.year, et.month, et.day, NY_FLAT.hour, NY_FLAT.minute, tzinfo=TZ_ET)
