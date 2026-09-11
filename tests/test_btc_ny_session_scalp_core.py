"""BTC NY-desk overlap core: clock, causality, family gates."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import btc_ny_session_scalp_core as core  # noqa: E402
from us_index_session_core import looks_like_us_index  # noqa: E402

LOCK = json.loads((ROOT / "results" / "btc_ny_session_scalp_lock.json").read_text())


def _m5(n: int, start_et: datetime, step_min: int = 5, px: float = 100000.0) -> core.M5Data:
    """Build a synthetic M5 bundle. start_et must be tz-aware America/New_York."""
    times_et = [start_et + pd.Timedelta(minutes=step_min * i) for i in range(n)]
    # normalize to pandas timestamps
    et = pd.DatetimeIndex(pd.to_datetime(times_et))
    utc = et.tz_convert("UTC")
    close = np.full(n, px, dtype=float)
    high = close + 20.0
    low = close - 20.0
    open_ = close.copy()
    return core.M5Data(
        open=open_,
        high=high,
        low=low,
        close=close,
        vol=np.ones(n),
        spread=np.full(n, 1600.0),
        et_min=(et.hour * 60 + et.minute).to_numpy(np.int32),
        et_key=(et.year * 10000 + et.month * 100 + et.day).to_numpy(np.int32),
        et_dow=et.weekday.to_numpy(np.int8),
        times_et=[t.to_pydatetime() for t in et],
        times_utc=[t.to_pydatetime() for t in utc],
    )


def test_looks_like_btc_and_not_us_index():
    assert core.looks_like_btc("BTCUSD")
    assert core.looks_like_btc("btc/usd")
    assert not looks_like_us_index("BTCUSD")


def test_holdout_refuses_xau_and_index_defaults():
    with pytest.raises(SystemExit):
        core.assert_lane_holdout(date(2026, 1, 1))
    with pytest.raises(SystemExit):
        core.assert_lane_holdout(date(2026, 6, 1))
    core.assert_lane_holdout(date(2026, 3, 1))
    assert LOCK["holdout"]["start"] == "2026-03-01"


def test_et_from_server_jan_and_jul():
    # server = ET + 7h. 15:00 ET winter = 20:00 server; summer 15:00 ET = 20:00 server.
    jan = pd.Series(pd.to_datetime(["2026-01-15 22:00:00"]))
    jul = pd.Series(pd.to_datetime(["2026-07-15 22:00:00"]))
    et_j = core.et_from_server(jan)
    et_l = core.et_from_server(jul)
    assert et_j.dt.tz.zone == "America/New_York" or str(et_j.dt.tz) == "America/New_York"
    assert int(et_j.dt.hour.iloc[0]) == 15
    assert int(et_l.dt.hour.iloc[0]) == 15
    # winter EST is UTC-5; summer EDT UTC-4
    assert et_j.dt.tz_convert("UTC").dt.hour.iloc[0] == 20
    assert et_l.dt.tz_convert("UTC").dt.hour.iloc[0] == 19


def test_entry_window_is_overlap_not_cash_open():
    start = pd.Timestamp("2026-07-15 07:55", tz="America/New_York")
    d = _m5(50, start)  # 07:55 through ~12:00
    gate = core.entry_ok_mask(d)
    # 07:55 closed
    assert not gate[0]
    # 08:00 open
    i08 = int(np.where(d.et_min == 8 * 60)[0][0])
    assert gate[i08]
    # 09:25 still open (not a 09:30 cash OR wait)
    i0925 = int(np.where(d.et_min == 9 * 60 + 25)[0][0])
    assert gate[i0925]
    # 11:30 closed
    i1130 = int(np.where(d.et_min == 11 * 60 + 30)[0][0])
    assert not gate[i1130]


def test_nfp_blackout_only_when_flagged():
    start = pd.Timestamp("2026-07-15 08:20", tz="America/New_York")
    d = _m5(8, start)
    i830 = int(np.where(d.et_min == 8 * 60 + 30)[0][0])
    assert core.entry_ok_mask(d, nfp_blackout=False)[i830]
    assert not core.entry_ok_mask(d, nfp_blackout=True)[i830]


def test_or_incomplete_until_0830():
    start = pd.Timestamp("2026-07-15 08:00", tz="America/New_York")
    d = _m5(12, start)
    # last OR bar is 08:25; complete on 08:30
    i0825 = int(np.where(d.et_min == 8 * 60 + 25)[0][0])
    i0830 = int(np.where(d.et_min == 8 * 60 + 30)[0][0])
    ok25, _, _ = core.ny_desk_or_at(d, i0825, 30)
    ok30, hi, lo = core.ny_desk_or_at(d, i0830, 30)
    assert not ok25
    assert ok30
    assert hi >= lo


def test_or_does_not_use_future_bars():
    start = pd.Timestamp("2026-07-15 08:00", tz="America/New_York")
    d = _m5(20, start)
    d.high[15] = 999999.0  # 09:15 — after OR
    i0830 = int(np.where(d.et_min == 8 * 60 + 30)[0][0])
    ok, hi, _ = core.ny_desk_or_at(d, i0830, 30)
    assert ok
    assert hi < 900000.0


def test_vwap_resets_each_et_day():
    start = pd.Timestamp("2026-07-15 08:00", tz="America/New_York")
    d = _m5(300, start)  # spans into next day
    v = core.session_vwap_series(d)
    keys = d.et_key
    first_days = np.unique(keys)
    assert len(first_days) >= 2
    # first in-session bar of day 2 should not equal last of day 1 if price changes
    d.close[:] = np.linspace(100000, 101000, len(d))
    d.high = d.close + 1
    d.low = d.close - 1
    v = core.session_vwap_series(d)
    day2 = first_days[1]
    i2 = int(np.where((keys == day2) & (d.et_min >= 8 * 60))[0][0])
    i1_last = int(np.where((keys == first_days[0]) & np.isfinite(v))[0][-1])
    assert v[i2] != v[i1_last]


def test_forming_bar_never_signals():
    start = pd.Timestamp("2026-07-15 08:00", tz="America/New_York")
    d = _m5(40, start)
    d.close = np.linspace(100000, 101000, 40)
    d.high = d.close + 10
    d.low = d.close - 10
    sig = core.vwap_ema_signals(d, min_atr_pct=0.0, nfp_blackout=False)
    assert sig[-1] == 0


def test_one_signal_per_et_day():
    start = pd.Timestamp("2026-07-15 08:00", tz="America/New_York")
    n = 40
    d = _m5(n, start)
    d.close = np.linspace(100000, 102000, n)
    d.high = d.close + 30
    d.low = d.close - 5
    sig = core.vwap_ema_signals(d, min_atr_pct=0.0, nfp_blackout=False, one_per_day=True)
    assert int(np.count_nonzero(sig)) <= 1
