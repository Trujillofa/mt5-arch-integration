#!/usr/bin/env python3
"""BTC NY-desk overlap scalp core — causal clock, session, families.

Lock: results/btc_ny_session_scalp_lock.json (frozen 2026-09-11, before any metric).
promote / live_go = false. Offline research only.

Hard rules:
- Clock is ET+7 localize America/New_York (ambiguous=NaT). NEVER
  us_index_session_backtest.load_m5_csv constant offset.
- Signals on the CLOSE of bar i; simulator fills at open of i+1.
- Forming bars never signal. Indicators at i use bars <= i only.
- NY desk overlap [08:00, 11:30) ET. Not cash 09:30. Not London gold.
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
    to_london,
    wilder_atr,
)
from us_index_session_core import scalp_signal_series as index_scalp_signal_series  # noqa: E402

SERVER_MINUS_HOURS = 7
TZ_ET = "America/New_York"
TZ_LON = ZoneInfo("Europe/London")

SESSION_START_MIN = 8 * 60
SESSION_END_MIN = 11 * 60 + 30
FLAT_MIN = 11 * 60 + 30
FRIDAY_CUTOFF_MIN = 14 * 60
NFP_LO_MIN = 8 * 60 + 25
NFP_HI_MIN = 8 * 60 + 40

EMA_FAST = 9
EMA_SLOW = 21
ATR_PERIOD = 14
OR_MINUTES = 30
OR_BUFFER_ATR_FRAC = 0.10
HTF_FAST = 50
HTF_SLOW = 200
PULLBACK_PCT = 0.003
EXTENSION_PCT = 0.005
XAU_HOLDOUT = date(2026, 1, 1)
INDEX_HOLDOUT = date(2026, 6, 1)

FAM_VWAP_EMA = "btc_ny_overlap_vwap_ema_flat"
FAM_ATR_DRIVE = "btc_ny_overlap_atr_drive"
FAM_HTF_PULLBACK = "btc_ny_overlap_htf_pullback"
SEARCH_FAMILIES = (FAM_VWAP_EMA, FAM_ATR_DRIVE, FAM_HTF_PULLBACK)


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
    times_et: list[datetime]
    times_utc: list[datetime]

    def __len__(self) -> int:
        return int(self.close.shape[0])


def et_from_server(server_naive: pd.Series) -> pd.Series:
    """DST-aware ET: (server wall - 7h) localized to New York. NaT on fold."""
    shifted = server_naive - pd.Timedelta(hours=SERVER_MINUS_HOURS)
    return shifted.dt.tz_localize(TZ_ET, ambiguous="NaT", nonexistent="shift_forward")


def assert_lane_holdout(holdout_start: date) -> None:
    if holdout_start == XAU_HOLDOUT:
        raise SystemExit("BTC holdout must not equal XAU 2026-01-01")
    if holdout_start == INDEX_HOLDOUT:
        raise SystemExit("BTC holdout must not equal US-index 2026-06-01")


def looks_like_btc(symbol: str) -> bool:
    u = symbol.upper().replace(" ", "").replace("-", "").replace("/", "")
    return "BTC" in u


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


def load_btc_m5(csv_path: Path, *, expected_sha256: str | None = None) -> M5Data:
    """Load the locked FP M5 export. ET via the lock clock. Spread imputed."""
    raw = Path(csv_path).read_bytes()
    if expected_sha256 is not None:
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
    med = float(np.median(pos)) if len(pos) else 1600.0
    spread = _impute_spread(spread, et_key, med)
    return M5Data(
        open=pd.to_numeric(df["open"], errors="coerce").to_numpy(float),
        high=pd.to_numeric(df["high"], errors="coerce").to_numpy(float),
        low=pd.to_numeric(df["low"], errors="coerce").to_numpy(float),
        close=pd.to_numeric(df["close"], errors="coerce").to_numpy(float),
        vol=pd.to_numeric(df.get("tick_volume", 1.0), errors="coerce").to_numpy(float),
        spread=spread,
        et_min=(et.dt.hour * 60 + et.dt.minute).to_numpy(np.int32),
        et_key=et_key,
        et_dow=et.dt.weekday.to_numpy(np.int8),
        times_et=[t.to_pydatetime() for t in et],
        times_utc=[t.to_pydatetime() for t in utc],
    )


def entry_ok_mask(d: M5Data, *, nfp_blackout: bool = False) -> np.ndarray:
    m = (d.et_min >= SESSION_START_MIN) & (d.et_min < SESSION_END_MIN)
    m &= ~((d.et_dow == 4) & (d.et_min >= FRIDAY_CUTOFF_MIN))
    if nfp_blackout:
        m &= ~((d.et_min >= NFP_LO_MIN) & (d.et_min < NFP_HI_MIN))
    return m


def session_vwap_series(d: M5Data) -> np.ndarray:
    """NY-desk VWAP from the first [08:00, 11:30) bar of the ET date. Includes i."""
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


def ny_desk_or_at(d: M5Data, i: int, or_minutes: int = OR_MINUTES) -> tuple[bool, float, float]:
    """Causal NY-desk opening range. Complete only when bar open >= 08:00+OR."""
    if i < 0 or i >= len(d):
        return False, float("nan"), float("nan")
    end_min = SESSION_START_MIN + int(or_minutes)
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
        if SESSION_START_MIN <= mn < end_min:
            found = True
            hi = max(hi, float(d.high[k]))
            lo = min(lo, float(d.low[k]))
        elif mn >= end_min:
            break
    if not found or not np.isfinite(hi):
        return False, float("nan"), float("nan")
    return True, float(hi), float(lo)


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


def vwap_ema_signals(
    d: M5Data,
    *,
    min_atr_pct: float,
    nfp_blackout: bool,
    one_per_day: bool = True,
) -> np.ndarray:
    c = d.close
    ema_f = ema_series(c, EMA_FAST)
    ema_s = ema_series(c, EMA_SLOW)
    vwap = session_vwap_series(d)
    atr = wilder_atr(d.high, d.low, d.close, ATR_PERIOD)
    gate = entry_ok_mask(d, nfp_blackout=nfp_blackout)
    n = len(d)
    raw = np.zeros(n, dtype=np.int8)
    last = n - 1
    for i in range(last):
        if not gate[i]:
            continue
        px, ef, es, vw, at = c[i], ema_f[i], ema_s[i], vwap[i], atr[i]
        if not all(np.isfinite(v) for v in (px, ef, es, vw, at)) or px <= 0.0:
            continue
        if at / px < min_atr_pct:
            continue
        if px > vw and ef > es:
            raw[i] = 1
        elif px < vw and ef < es:
            raw[i] = -1
    return _dedupe_one_per_day(raw, d) if one_per_day else raw


def atr_drive_signals(
    d: M5Data,
    *,
    min_atr_pct: float,
    nfp_blackout: bool,
    or_minutes: int = OR_MINUTES,
    or_buffer_atr_frac: float = OR_BUFFER_ATR_FRAC,
    one_per_day: bool = True,
) -> np.ndarray:
    c = d.close
    ema_f = ema_series(c, EMA_FAST)
    ema_s = ema_series(c, EMA_SLOW)
    vwap = session_vwap_series(d)
    atr = wilder_atr(d.high, d.low, d.close, ATR_PERIOD)
    gate = entry_ok_mask(d, nfp_blackout=nfp_blackout)
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
            or_cache[key] = ny_desk_or_at(d, i, or_minutes)
        ok, oh, ol = or_cache[key]
        if not ok:
            continue
        buf = or_buffer_atr_frac * at
        if px > oh + buf and px > vw and ef > es:
            raw[i] = 1
        elif px < ol - buf and px < vw and ef < es:
            raw[i] = -1
    return _dedupe_one_per_day(raw, d) if one_per_day else raw


def completed_h1_bias(d: M5Data) -> np.ndarray:
    """+1/-1/0 from the last *completed* UTC H1 bar (never the forming hour)."""
    n = len(d)
    hours = np.array([t.replace(minute=0, second=0, microsecond=0) for t in d.times_utc])
    uniq: list[datetime] = []
    seen: dict[datetime, int] = {}
    h_open: list[float] = []
    h_high: list[float] = []
    h_low: list[float] = []
    h_close: list[float] = []
    for i in range(n):
        h = hours[i]
        if h not in seen:
            seen[h] = len(uniq)
            uniq.append(h)
            h_open.append(float(d.open[i]))
            h_high.append(float(d.high[i]))
            h_low.append(float(d.low[i]))
            h_close.append(float(d.close[i]))
        else:
            j = seen[h]
            h_high[j] = max(h_high[j], float(d.high[i]))
            h_low[j] = min(h_low[j], float(d.low[i]))
            h_close[j] = float(d.close[i])
    closes = np.asarray(h_close, dtype=float)
    e50 = ema_series(closes, HTF_FAST)
    e200 = ema_series(closes, HTF_SLOW)
    bias_h = np.zeros(len(uniq), dtype=np.int8)
    for j in range(len(uniq)):
        c, a, b = closes[j], e50[j], e200[j]
        if not (np.isfinite(c) and np.isfinite(a) and np.isfinite(b)):
            continue
        if c > b and a > b:
            bias_h[j] = 1
        elif c < b and a < b:
            bias_h[j] = -1
    out = np.zeros(n, dtype=np.int8)
    for i in range(n):
        j = seen[hours[i]]
        if j >= 1:
            out[i] = bias_h[j - 1]
    return out


def htf_pullback_signals(
    d: M5Data,
    *,
    min_atr_pct: float,
    nfp_blackout: bool,
    one_per_day: bool = True,
) -> np.ndarray:
    c = d.close
    ema_s = ema_series(c, EMA_SLOW)
    atr = wilder_atr(d.high, d.low, d.close, ATR_PERIOD)
    bias = completed_h1_bias(d)
    gate = entry_ok_mask(d, nfp_blackout=nfp_blackout)
    n = len(d)
    raw = np.zeros(n, dtype=np.int8)
    last = n - 1
    for i in range(1, last):
        if not gate[i]:
            continue
        px, es, at = c[i], ema_s[i], atr[i]
        if not all(np.isfinite(v) for v in (px, es, at)) or px <= 0.0 or es <= 0.0:
            continue
        if at / px < min_atr_pct:
            continue
        dist = (px - es) / px
        b = int(bias[i])
        if b == 1 and -PULLBACK_PCT <= 0.0 and abs(dist) <= PULLBACK_PCT:
            if px > es and px > c[i - 1] and dist <= EXTENSION_PCT:
                raw[i] = 1
        elif (
            b == -1
            and abs(dist) <= PULLBACK_PCT
            and px < es
            and px < c[i - 1]
            and -dist <= EXTENSION_PCT
        ):
            raw[i] = -1
    return _dedupe_one_per_day(raw, d) if one_per_day else raw


def family_signals(
    d: M5Data,
    family: str,
    *,
    min_atr_pct: float,
    nfp_blackout: bool,
    one_per_day: bool = True,
) -> np.ndarray:
    if family == FAM_VWAP_EMA:
        return vwap_ema_signals(
            d, min_atr_pct=min_atr_pct, nfp_blackout=nfp_blackout, one_per_day=one_per_day
        )
    if family == FAM_ATR_DRIVE:
        return atr_drive_signals(
            d, min_atr_pct=min_atr_pct, nfp_blackout=nfp_blackout, one_per_day=one_per_day
        )
    if family == FAM_HTF_PULLBACK:
        return htf_pullback_signals(
            d, min_atr_pct=min_atr_pct, nfp_blackout=nfp_blackout, one_per_day=one_per_day
        )
    raise ValueError(f"unknown search family {family}")


def index_transfer_signals(d: M5Data) -> np.ndarray:
    """Unmodified NY-cash ORB grammar on correctly clocked BTC UTC times."""
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
            if w < 0.35 or w > 2.5:
                continue
        buf = OR_BUFFER_ATR_FRAC * at
        if px > or_h + buf and px > vwap and ef > es:
            out[i] = 1
            fired.add(box)
        elif px < or_l - buf and px < vwap and ef < es:
            out[i] = -1
            fired.add(box)
    return out


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
        times_et=d.times_et,
        times_utc=d.times_utc,
    )


__all__ = [
    "M5Data",
    "SERVER_MINUS_HOURS",
    "SESSION_START_MIN",
    "SESSION_END_MIN",
    "FLAT_MIN",
    "FRIDAY_CUTOFF_MIN",
    "FAM_VWAP_EMA",
    "FAM_ATR_DRIVE",
    "FAM_HTF_PULLBACK",
    "SEARCH_FAMILIES",
    "et_from_server",
    "assert_lane_holdout",
    "looks_like_btc",
    "load_btc_m5",
    "entry_ok_mask",
    "session_vwap_series",
    "ny_desk_or_at",
    "family_signals",
    "index_transfer_signals",
    "gold_transfer_signals",
    "rotate_returns_within_days",
    "completed_h1_bias",
    "ema_series",
    "rsi_series",
    "wilder_atr",
]
