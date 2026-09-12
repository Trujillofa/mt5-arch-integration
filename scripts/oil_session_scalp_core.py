#!/usr/bin/env python3
"""Oil session scalp core — causal clock, London/NY boxes, families.

Lock: results/oil_session_scalp_lock.json (frozen 2026-09-11, before any metric).
promote / live_go = false. Offline research only.

Hard rules:
- Clock is ET+7 localize America/New_York (ambiguous=NaT). NEVER
  us_index_session_backtest.load_m5_csv constant offset.
- Signals on the CLOSE of bar i; simulator fills at open of i+1.
- Forming bars never signal. Indicators at i use bars <= i only.
- London energy: OR = first 30m after 08:00 Europe/London; entries after
  OR through 11:00 London. NY energy: [08:00, 11:30) ET. Not cash 09:30.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from us_index_session_core import (  # noqa: E402
    ema_series,
    is_london_open,
    rsi_series,
    scalp_signal_series as index_scalp_signal_series,
    to_london,
    wilder_atr,
)

SERVER_MINUS_HOURS = 7
TZ_ET = "America/New_York"
TZ_LON = ZoneInfo("Europe/London")
TZ_UTC = ZoneInfo("UTC")

LONDON_START_MIN = 8 * 60
LONDON_OR_END_MIN = 8 * 60 + 30
LONDON_END_MIN = 11 * 60
NY_START_MIN = 8 * 60
NY_END_MIN = 11 * 60 + 30
NY_FLAT_MIN = 11 * 60 + 30
FRIDAY_CUTOFF_MIN = 14 * 60
EIA_LO_MIN = 10 * 60 + 25
EIA_HI_MIN = 10 * 60 + 40
GLOBEX_UTC_HOUR = 21

EMA_FAST = 9
EMA_SLOW = 21
ATR_PERIOD = 14
OR_MINUTES = 30
OR_BUFFER_ATR_FRAC = 0.10
OR_WIDTH_LO = 0.35
OR_WIDTH_HI = 2.5

XAU_HOLDOUT = date(2026, 1, 1)
INDEX_HOLDOUT = date(2026, 6, 1)
BTC_HOLDOUT = date(2026, 3, 1)

FAM_LONDON = "oil_london_orb_vwap_ema_flat"
FAM_NY = "oil_ny_inventory_drive"
FAM_RECLAIM = "oil_prior_day_reclaim"
SEARCH_FAMILIES = (FAM_LONDON, FAM_NY, FAM_RECLAIM)


@dataclass
class M5Data:
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    vol: np.ndarray
    spread: np.ndarray
    et_min: np.ndarray
    et_key: np.ndarray
    et_dow: np.ndarray
    lon_min: np.ndarray
    lon_key: np.ndarray
    utc_hour: np.ndarray
    times_et: list[datetime]
    times_utc: list[datetime]

    def __len__(self) -> int:
        return int(self.close.shape[0])


def et_from_server(server_naive: pd.Series) -> pd.Series:
    """DST-aware ET: (server wall - 7h) localized to New York. NaT on fold."""
    shifted = server_naive - pd.Timedelta(hours=SERVER_MINUS_HOURS)
    return shifted.dt.tz_localize(TZ_ET, ambiguous="NaT", nonexistent="shift_forward")


def clock_fields_from_times(
    times_et: list[datetime], times_utc: list[datetime]
) -> dict[str, np.ndarray]:
    et = pd.DatetimeIndex(pd.to_datetime(times_et))
    utc = pd.DatetimeIndex(pd.to_datetime(times_utc)).tz_convert("UTC")
    lon = utc.tz_convert("Europe/London")
    return {
        "et_min": (et.hour * 60 + et.minute).to_numpy(np.int32),
        "et_key": (et.year * 10000 + et.month * 100 + et.day).to_numpy(np.int32),
        "et_dow": et.weekday.to_numpy(np.int8),
        "lon_min": (lon.hour * 60 + lon.minute).to_numpy(np.int32),
        "lon_key": (lon.year * 10000 + lon.month * 100 + lon.day).to_numpy(np.int32),
        "utc_hour": utc.hour.to_numpy(np.int8),
    }


def pack_m5(
    *,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    vol: np.ndarray,
    spread: np.ndarray,
    times_et: list[datetime],
    times_utc: list[datetime],
) -> M5Data:
    clk = clock_fields_from_times(times_et, times_utc)
    return M5Data(
        open=np.asarray(open_, dtype=float),
        high=np.asarray(high, dtype=float),
        low=np.asarray(low, dtype=float),
        close=np.asarray(close, dtype=float),
        vol=np.asarray(vol, dtype=float),
        spread=np.asarray(spread, dtype=float),
        times_et=list(times_et),
        times_utc=list(times_utc),
        **clk,
    )


def assert_lane_holdout(holdout_start: date) -> None:
    if holdout_start == XAU_HOLDOUT:
        raise SystemExit("oil holdout must not equal XAU 2026-01-01")
    if holdout_start == INDEX_HOLDOUT:
        raise SystemExit("oil holdout must not equal US-index 2026-06-01")
    if holdout_start == BTC_HOLDOUT:
        raise SystemExit("oil holdout must not equal BTC 2026-03-01")


def looks_like_oil(symbol: str) -> bool:
    """WTI CFD names only. Brent is never the ranked book."""
    u = symbol.upper().replace(" ", "").replace("-", "").replace("/", "").replace(".", "")
    if any(k in u for k in ("UKOIL", "UKOUSD", "XBR", "BRENT")):
        return False
    if any(k in u for k in ("XTIUSD", "XTI", "USOIL", "USOUSD", "WTI", "CLOIL")):
        return True
    return u.startswith("USO") or u.endswith("USO")


def _impute_spread(spread: np.ndarray, et_key: np.ndarray, median: float) -> np.ndarray:
    out = spread.astype(float).copy()
    last = median
    prev_k = -1
    for i, v in enumerate(out):
        k = int(et_key[i])
        if k != prev_k:
            last = median
            prev_k = k
        if v <= 0.0:
            out[i] = last
        else:
            last = v
    return out


def load_oil_m5(csv_path: Path, *, expected_sha256: str | None = None) -> M5Data:
    """Load the locked Vantage USOUSD / XTIUSD M5 export. ET via the lock clock."""
    raw = Path(csv_path).read_bytes()
    if expected_sha256:
        got = hashlib.sha256(raw).hexdigest()
        if got != expected_sha256:
            raise SystemExit(f"sha256 mismatch {got} != {expected_sha256}")
    df = pd.read_csv(csv_path)
    if "server_epoch" in df.columns:
        server = pd.to_datetime(pd.to_numeric(df["server_epoch"], errors="coerce"), unit="s")
    else:
        server = pd.to_datetime(df["time"])
    et = et_from_server(server)
    keep = et.notna()
    df = df.loc[keep].reset_index(drop=True)
    et = et.loc[keep].reset_index(drop=True)
    utc = et.dt.tz_convert("UTC")
    et_key = (et.dt.year * 10000 + et.dt.month * 100 + et.dt.day).to_numpy(np.int32)
    spread = pd.to_numeric(df["spread"], errors="coerce").to_numpy(float)
    pos = spread[spread > 0]
    med = float(np.median(pos)) if len(pos) else 22.0
    spread = _impute_spread(spread, et_key, med)
    times_et = [t.to_pydatetime() for t in et]
    times_utc = [t.to_pydatetime() for t in utc]
    return pack_m5(
        open_=pd.to_numeric(df["open"], errors="coerce").to_numpy(float),
        high=pd.to_numeric(df["high"], errors="coerce").to_numpy(float),
        low=pd.to_numeric(df["low"], errors="coerce").to_numpy(float),
        close=pd.to_numeric(df["close"], errors="coerce").to_numpy(float),
        vol=pd.to_numeric(df.get("tick_volume", 1.0), errors="coerce").to_numpy(float),
        spread=spread,
        times_et=times_et,
        times_utc=times_utc,
    )


def _common_blocks(d: M5Data, *, eia_blackout: bool) -> np.ndarray:
    m = ~((d.et_dow == 4) & (d.et_min >= FRIDAY_CUTOFF_MIN))
    m &= d.utc_hour != GLOBEX_UTC_HOUR
    if eia_blackout:
        m &= ~((d.et_dow == 2) & (d.et_min >= EIA_LO_MIN) & (d.et_min < EIA_HI_MIN))
    return m


def in_london_entry(d: M5Data) -> np.ndarray:
    return (d.lon_min >= LONDON_OR_END_MIN) & (d.lon_min < LONDON_END_MIN)


def in_ny_entry(d: M5Data) -> np.ndarray:
    return (d.et_min >= NY_START_MIN) & (d.et_min < NY_END_MIN)


def entry_ok_mask(
    d: M5Data, *, eia_blackout: bool = False, session: str = "union"
) -> np.ndarray:
    m = _common_blocks(d, eia_blackout=eia_blackout)
    if session == "london":
        return m & in_london_entry(d)
    if session == "ny":
        return m & in_ny_entry(d)
    return m & (in_london_entry(d) | in_ny_entry(d))


def london_vwap_series(d: M5Data) -> np.ndarray:
    """London-date VWAP from the first [08:00, 11:00) London bar. Includes i."""
    n = len(d)
    out = np.full(n, np.nan)
    num = den = 0.0
    day = -1
    for i in range(n):
        k = int(d.lon_key[i])
        if k != day:
            day = k
            num = den = 0.0
        if LONDON_START_MIN <= int(d.lon_min[i]) < LONDON_END_MIN:
            typ = (d.high[i] + d.low[i] + d.close[i]) / 3.0
            v = max(float(d.vol[i]), 1.0)
            num += typ * v
            den += v
            out[i] = num / den if den > 0.0 else np.nan
    return out


def ny_vwap_series(d: M5Data) -> np.ndarray:
    """NY-energy VWAP from the first [08:00, 11:30) ET bar. Includes i."""
    n = len(d)
    out = np.full(n, np.nan)
    num = den = 0.0
    day = -1
    for i in range(n):
        k = int(d.et_key[i])
        if k != day:
            day = k
            num = den = 0.0
        if NY_START_MIN <= int(d.et_min[i]) < NY_END_MIN:
            typ = (d.high[i] + d.low[i] + d.close[i]) / 3.0
            v = max(float(d.vol[i]), 1.0)
            num += typ * v
            den += v
            out[i] = num / den if den > 0.0 else np.nan
    return out


def london_or_at(d: M5Data, i: int, or_minutes: int = OR_MINUTES) -> tuple[bool, float, float]:
    """Causal London opening range. Complete only when lon_min >= 08:00+OR."""
    if i < 0 or i >= len(d):
        return False, float("nan"), float("nan")
    end_min = LONDON_START_MIN + int(or_minutes)
    if int(d.lon_min[i]) < end_min:
        return False, float("nan"), float("nan")
    key = int(d.lon_key[i])
    hi = -np.inf
    lo = np.inf
    found = False
    for k in range(i + 1):
        if int(d.lon_key[k]) != key:
            continue
        mn = int(d.lon_min[k])
        if LONDON_START_MIN <= mn < end_min:
            found = True
            hi = max(hi, float(d.high[k]))
            lo = min(lo, float(d.low[k]))
        elif mn >= end_min:
            break
    if not found or not np.isfinite(hi):
        return False, float("nan"), float("nan")
    return True, float(hi), float(lo)


def ny_or_at(d: M5Data, i: int, or_minutes: int = OR_MINUTES) -> tuple[bool, float, float]:
    """Causal NY-energy opening range. Complete only when et_min >= 08:00+OR."""
    if i < 0 or i >= len(d):
        return False, float("nan"), float("nan")
    end_min = NY_START_MIN + int(or_minutes)
    if int(d.et_min[i]) < end_min:
        return False, float("nan"), float("nan")
    key = int(d.et_key[i])
    hi = -np.inf
    lo = np.inf
    found = False
    for k in range(i + 1):
        if int(d.et_key[k]) != key:
            continue
        mn = int(d.et_min[k])
        if NY_START_MIN <= mn < end_min:
            found = True
            hi = max(hi, float(d.high[k]))
            lo = min(lo, float(d.low[k]))
        elif mn >= end_min:
            break
    if not found or not np.isfinite(hi):
        return False, float("nan"), float("nan")
    return True, float(hi), float(lo)


def prior_et_day_hl(d: M5Data) -> tuple[np.ndarray, np.ndarray]:
    """Completed previous ET-day high/low at each bar (never today's forming day)."""
    n = len(d)
    hi_out = np.full(n, np.nan)
    lo_out = np.full(n, np.nan)
    day_hi: dict[int, float] = {}
    day_lo: dict[int, float] = {}
    last_done_key = None
    last_done_hi = last_done_lo = float("nan")
    prev_key = None
    cur_hi = -np.inf
    cur_lo = np.inf
    for i in range(n):
        k = int(d.et_key[i])
        if prev_key is None:
            prev_key = k
        if k != prev_key:
            day_hi[prev_key] = cur_hi
            day_lo[prev_key] = cur_lo
            last_done_key = prev_key
            last_done_hi = cur_hi
            last_done_lo = cur_lo
            prev_key = k
            cur_hi = -np.inf
            cur_lo = np.inf
        cur_hi = max(cur_hi, float(d.high[i]))
        cur_lo = min(cur_lo, float(d.low[i]))
        if last_done_key is not None:
            hi_out[i] = last_done_hi
            lo_out[i] = last_done_lo
    return hi_out, lo_out


def _dedupe_one_per_day(raw: np.ndarray, d: M5Data) -> np.ndarray:
    out = raw.astype(np.int8).copy()
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


def london_orb_signals(
    d: M5Data,
    *,
    min_atr_pct: float,
    eia_blackout: bool,
    one_per_day: bool = True,
) -> np.ndarray:
    c = d.close
    ema_f = ema_series(c, EMA_FAST)
    ema_s = ema_series(c, EMA_SLOW)
    vwap = london_vwap_series(d)
    atr = wilder_atr(d.high, d.low, d.close, ATR_PERIOD)
    gate = entry_ok_mask(d, eia_blackout=eia_blackout, session="london")
    n = len(d)
    raw = np.zeros(n, dtype=np.int8)
    last = n - 1
    or_cache: dict[int, tuple[bool, float, float]] = {}
    for i in range(last):
        if not gate[i]:
            continue
        px, ef, es, vw, at = c[i], ema_f[i], ema_s[i], vwap[i], atr[i]
        if not all(np.isfinite(v) for v in (px, ef, es, vw, at)) or px <= 0.0:
            continue
        if at / px < min_atr_pct:
            continue
        key = int(d.lon_key[i])
        if key not in or_cache:
            or_cache[key] = london_or_at(d, i, OR_MINUTES)
        ok, oh, ol = or_cache[key]
        if not ok:
            continue
        or_w = oh - ol
        if at > 0 and or_w > 0:
            w = or_w / at
            if w < OR_WIDTH_LO or w > OR_WIDTH_HI:
                continue
        buf = OR_BUFFER_ATR_FRAC * at
        if px > oh + buf and px > vw and ef > es:
            raw[i] = 1
        elif px < ol - buf and px < vw and ef < es:
            raw[i] = -1
    return _dedupe_one_per_day(raw, d) if one_per_day else raw


def ny_inventory_signals(
    d: M5Data,
    *,
    min_atr_pct: float,
    eia_blackout: bool,
    one_per_day: bool = True,
) -> np.ndarray:
    c = d.close
    ema_f = ema_series(c, EMA_FAST)
    ema_s = ema_series(c, EMA_SLOW)
    vwap = ny_vwap_series(d)
    atr = wilder_atr(d.high, d.low, d.close, ATR_PERIOD)
    gate = entry_ok_mask(d, eia_blackout=eia_blackout, session="ny")
    n = len(d)
    raw = np.zeros(n, dtype=np.int8)
    last = n - 1
    or_cache: dict[int, tuple[bool, float, float]] = {}
    for i in range(last):
        if not gate[i]:
            continue
        px, ef, es, vw, at = c[i], ema_f[i], ema_s[i], vwap[i], atr[i]
        if not all(np.isfinite(v) for v in (px, ef, es, vw, at)) or px <= 0.0:
            continue
        if at / px < min_atr_pct:
            continue
        key = int(d.et_key[i])
        if key not in or_cache:
            or_cache[key] = ny_or_at(d, i, OR_MINUTES)
        ok, oh, ol = or_cache[key]
        if not ok:
            continue
        buf = OR_BUFFER_ATR_FRAC * at
        if px > oh + buf and px > vw and ef > es:
            raw[i] = 1
        elif px < ol - buf and px < vw and ef < es:
            raw[i] = -1
    return _dedupe_one_per_day(raw, d) if one_per_day else raw


def prior_day_reclaim_signals(
    d: M5Data,
    *,
    min_atr_pct: float,
    eia_blackout: bool,
    one_per_day: bool = True,
) -> np.ndarray:
    c = d.close
    atr = wilder_atr(d.high, d.low, d.close, ATR_PERIOD)
    pri_h, pri_l = prior_et_day_hl(d)
    gate = entry_ok_mask(d, eia_blackout=eia_blackout, session="union")
    n = len(d)
    raw = np.zeros(n, dtype=np.int8)
    last = n - 1
    for i in range(last):
        if not gate[i]:
            continue
        px, at, ph, pl = c[i], atr[i], pri_h[i], pri_l[i]
        if not all(np.isfinite(v) for v in (px, at, ph, pl)) or px <= 0.0:
            continue
        if at / px < min_atr_pct:
            continue
        if float(d.low[i]) < pl and px > pl:
            raw[i] = 1
        elif float(d.high[i]) > ph and px < ph:
            raw[i] = -1
    return _dedupe_one_per_day(raw, d) if one_per_day else raw


def family_signals(
    d: M5Data,
    family: str,
    *,
    min_atr_pct: float,
    eia_blackout: bool,
    one_per_day: bool = True,
) -> np.ndarray:
    if family == FAM_LONDON:
        return london_orb_signals(
            d, min_atr_pct=min_atr_pct, eia_blackout=eia_blackout, one_per_day=one_per_day
        )
    if family == FAM_NY:
        return ny_inventory_signals(
            d, min_atr_pct=min_atr_pct, eia_blackout=eia_blackout, one_per_day=one_per_day
        )
    if family == FAM_RECLAIM:
        return prior_day_reclaim_signals(
            d, min_atr_pct=min_atr_pct, eia_blackout=eia_blackout, one_per_day=one_per_day
        )
    raise ValueError(f"unknown search family {family}")


def flatten_spec_for_family(family: str) -> tuple[str, int]:
    """Return (clock, flatten_min). clock is 'london' | 'et' | 'box'."""
    if family == FAM_LONDON:
        return "london", LONDON_END_MIN
    if family == FAM_NY:
        return "et", NY_FLAT_MIN
    if family == FAM_RECLAIM:
        return "box", 0
    raise ValueError(f"unknown search family {family}")


def index_transfer_signals(d: M5Data) -> np.ndarray:
    """Unmodified NY-cash ORB grammar on correctly clocked oil UTC times."""
    return index_scalp_signal_series(
        d.times_utc, d.high, d.low, d.close, d.vol, exclude_forming=True
    )


def _london_open(ldn_day: date) -> datetime:
    return datetime(ldn_day.year, ldn_day.month, ldn_day.day, 8, 0, tzinfo=TZ_LON)


def gold_transfer_signals(d: M5Data) -> np.ndarray:
    """Replica of frozen gold combo: London 30m OR + NY metals 08:00-11:00 ET."""
    n = len(d)
    ema_f = ema_series(d.close, EMA_FAST)
    ema_s = ema_series(d.close, EMA_SLOW)
    atr = wilder_atr(d.high, d.low, d.close, ATR_PERIOD)
    out = np.zeros(n, dtype=np.int8)
    fired: set[tuple[str, date]] = set()
    vday: date | None = None
    vnum = vden = 0.0
    or_h = or_l = float("nan")
    or_set = False
    last = n - 1
    for i in range(last):
        ts = d.times_utc[i]
        lon = to_london(ts)
        day = lon.date()
        if day != vday:
            vday = day
            vnum = vden = 0.0
            or_h = or_l = float("nan")
            or_set = False
        if is_london_open(ts):
            typ = (d.high[i] + d.low[i] + d.close[i]) / 3.0
            vnum += typ * max(float(d.vol[i]), 1.0)
            vden += max(float(d.vol[i]), 1.0)
        start = _london_open(day)
        end = start + timedelta(minutes=OR_MINUTES)
        if start <= lon < end:
            if not or_set:
                or_h, or_l = float(d.high[i]), float(d.low[i])
                or_set = True
            else:
                or_h = max(or_h, float(d.high[i]))
                or_l = min(or_l, float(d.low[i]))
        et = d.times_et[i]
        in_lon = or_set and lon >= end and lon.timetz().replace(tzinfo=None) < time(11, 0)
        in_ny = time(8, 0) <= et.timetz().replace(tzinfo=None) < time(11, 0)
        if (et.weekday() == 4) and (d.et_min[i] >= FRIDAY_CUTOFF_MIN):
            continue
        if not (in_lon or in_ny) or not or_set or lon < end:
            continue
        box = ("L", day) if in_lon else ("N", et.date())
        if box in fired:
            continue
        vwap = vnum / vden if vden > 0 else float("nan")
        px, ef, es, at = d.close[i], ema_f[i], ema_s[i], atr[i]
        if not all(np.isfinite(v) for v in (px, ef, es, at, vwap)) or px <= 0:
            continue
        if at / px < 0.00015:
            continue
        or_w = or_h - or_l
        if or_w > 0 and at > 0:
            w = or_w / at
            if w < OR_WIDTH_LO or w > OR_WIDTH_HI:
                continue
        buf = OR_BUFFER_ATR_FRAC * at
        if px > or_h + buf and px > vwap and ef > es:
            out[i] = 1
            fired.add(box)
        elif px < or_l - buf and px < vwap and ef < es:
            out[i] = -1
            fired.add(box)
    return out


def btc_transfer_signals(d: M5Data) -> np.ndarray:
    """BTC NY-desk VWAP+EMA grammar on the oil NY energy box. Never ranked."""
    c = d.close
    ema_f = ema_series(c, EMA_FAST)
    ema_s = ema_series(c, EMA_SLOW)
    vwap = ny_vwap_series(d)
    atr = wilder_atr(d.high, d.low, d.close, ATR_PERIOD)
    gate = entry_ok_mask(d, eia_blackout=False, session="ny")
    n = len(d)
    raw = np.zeros(n, dtype=np.int8)
    last = n - 1
    for i in range(last):
        if not gate[i]:
            continue
        px, ef, es, vw, at = c[i], ema_f[i], ema_s[i], vwap[i], atr[i]
        if not all(np.isfinite(v) for v in (px, ef, es, vw, at)) or px <= 0.0:
            continue
        if at / px < 0.00015:
            continue
        if px > vw and ef > es:
            raw[i] = 1
        elif px < vw and ef < es:
            raw[i] = -1
    return _dedupe_one_per_day(raw, d)


def eurusd_mr_transfer_signals(d: M5Data) -> np.ndarray:
    """EURUSD mean_reversion (BB20,2 + RSI7) on oil, FX NY [08:00,17:00). Never ranked."""
    from eurusd_ny_scalp_core import M5Data as FxM5
    from eurusd_ny_scalp_core import mean_reversion_signals

    fx = FxM5(
        open=d.open,
        high=d.high,
        low=d.low,
        close=d.close,
        vol=d.vol,
        spread=d.spread,
        et_min=d.et_min,
        et_key=d.et_key,
        et_dow=d.et_dow,
        times_et=d.times_et,
    )
    return mean_reversion_signals(fx, one_per_day=True)


def rotate_returns_within_days(d: M5Data, rng: np.random.Generator) -> M5Data:
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
        seg_c = c[i:j]
        r = np.empty(j - i)
        r[0] = np.log(max(seg_c[0], 1e-12) / max(o[i], 1e-12))
        r[1:] = np.diff(np.log(np.maximum(seg_c, 1e-12)))
        off = int(rng.integers(0, j - i))
        r = np.roll(r, off)
        new_c = o[i] * np.exp(np.cumsum(r))
        ratio = new_c / np.maximum(seg_c, 1e-12)
        h[i:j] *= ratio
        lo[i:j] *= ratio
        c[i:j] = new_c
        o[i + 1 : j] = new_c[:-1]
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
        lon_min=d.lon_min,
        lon_key=d.lon_key,
        utc_hour=d.utc_hour,
        times_et=d.times_et,
        times_utc=d.times_utc,
    )


__all__ = [
    "M5Data",
    "SERVER_MINUS_HOURS",
    "LONDON_START_MIN",
    "LONDON_OR_END_MIN",
    "LONDON_END_MIN",
    "NY_START_MIN",
    "NY_END_MIN",
    "NY_FLAT_MIN",
    "FRIDAY_CUTOFF_MIN",
    "EIA_LO_MIN",
    "EIA_HI_MIN",
    "FAM_LONDON",
    "FAM_NY",
    "FAM_RECLAIM",
    "SEARCH_FAMILIES",
    "et_from_server",
    "clock_fields_from_times",
    "pack_m5",
    "assert_lane_holdout",
    "looks_like_oil",
    "load_oil_m5",
    "entry_ok_mask",
    "london_vwap_series",
    "ny_vwap_series",
    "london_or_at",
    "ny_or_at",
    "prior_et_day_hl",
    "family_signals",
    "flatten_spec_for_family",
    "index_transfer_signals",
    "gold_transfer_signals",
    "btc_transfer_signals",
    "eurusd_mr_transfer_signals",
    "rotate_returns_within_days",
    "ema_series",
    "rsi_series",
    "wilder_atr",
]
