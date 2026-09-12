"""Oil session scalp core: clock, causality, family gates."""

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

import oil_session_scalp_core as core  # noqa: E402
from us_index_session_core import looks_like_us_index  # noqa: E402

LOCK = json.loads((ROOT / "results" / "oil_session_scalp_lock.json").read_text())


def _m5(n: int, start_et: datetime, step_min: int = 5, px: float = 80.0) -> core.M5Data:
    times_et = [start_et + pd.Timedelta(minutes=step_min * i) for i in range(n)]
    et = pd.DatetimeIndex(pd.to_datetime(times_et))
    utc = et.tz_convert("UTC")
    close = np.full(n, px, dtype=float)
    return core.pack_m5(
        open_=close.copy(),
        high=close + 0.40,
        low=close - 0.40,
        close=close,
        vol=np.ones(n),
        spread=np.full(n, 22.0),
        times_et=[t.to_pydatetime() for t in et],
        times_utc=[t.to_pydatetime() for t in utc],
    )


def test_looks_like_oil_and_not_us_index():
    assert core.looks_like_oil("XTIUSD")
    assert core.looks_like_oil("USOUSD")
    assert core.looks_like_oil("CL-OIL")
    assert core.looks_like_oil("cl-oil")
    assert core.looks_like_oil("usoil")
    assert core.looks_like_oil("WTI")
    assert not looks_like_us_index("XTIUSD")
    assert not core.looks_like_oil("EURUSD")
    assert not core.looks_like_oil("USDJPY")
    assert not core.looks_like_oil("UKOUSD")
    assert not core.looks_like_oil("UKOIL")
    assert not core.looks_like_oil("XBRUSD")


def test_holdout_refuses_sibling_defaults():
    with pytest.raises(SystemExit):
        core.assert_lane_holdout(date(2026, 1, 1))
    with pytest.raises(SystemExit):
        core.assert_lane_holdout(date(2026, 6, 1))
    with pytest.raises(SystemExit):
        core.assert_lane_holdout(date(2026, 3, 1))
    core.assert_lane_holdout(date(2026, 4, 1))
    assert LOCK["holdout"]["start"] == "2026-04-01"
    for forbidden in LOCK["holdout"]["assert_not"]:
        assert forbidden != LOCK["holdout"]["start"]


def test_et_from_server_jan_and_jul():
    jan = pd.Series(pd.to_datetime(["2026-01-15 22:00:00"]))
    jul = pd.Series(pd.to_datetime(["2026-07-15 22:00:00"]))
    et_j = core.et_from_server(jan)
    et_l = core.et_from_server(jul)
    assert str(et_j.dt.tz) == "America/New_York"
    assert int(et_j.dt.hour.iloc[0]) == 15
    assert int(et_l.dt.hour.iloc[0]) == 15
    assert et_j.dt.tz_convert("UTC").dt.hour.iloc[0] == 20
    assert et_l.dt.tz_convert("UTC").dt.hour.iloc[0] == 19


def test_london_entry_after_or_not_cash_open():
    # 08:00 London July = 03:00 ET
    start = pd.Timestamp("2026-07-15 02:55", tz="America/New_York")
    d = _m5(80, start)
    gate = core.entry_ok_mask(d, session="london")
    i_or = int(np.where(d.lon_min == 8 * 60 + 25)[0][0])
    i_ready = int(np.where(d.lon_min == 8 * 60 + 30)[0][0])
    i_end = int(np.where(d.lon_min == 11 * 60)[0][0])
    assert not gate[i_or]
    assert gate[i_ready]
    assert not gate[i_end]


def test_ny_box_includes_cme_0900_not_cash_wait():
    start = pd.Timestamp("2026-07-15 07:55", tz="America/New_York")
    d = _m5(50, start)
    gate = core.entry_ok_mask(d, session="ny")
    assert not gate[0]
    i08 = int(np.where(d.et_min == 8 * 60)[0][0])
    assert gate[i08]
    i0925 = int(np.where(d.et_min == 9 * 60 + 25)[0][0])
    assert gate[i0925]
    i1130 = int(np.where(d.et_min == 11 * 60 + 30)[0][0])
    assert not gate[i1130]


def test_eia_blackout_wednesday_only_when_flagged():
    # 2026-07-15 is Wednesday
    start = pd.Timestamp("2026-07-15 10:20", tz="America/New_York")
    d = _m5(8, start)
    i1030 = int(np.where(d.et_min == 10 * 60 + 30)[0][0])
    assert core.entry_ok_mask(d, eia_blackout=False, session="ny")[i1030]
    assert not core.entry_ok_mask(d, eia_blackout=True, session="ny")[i1030]


def test_globex_gap_blocks_2100_utc():
    start = pd.Timestamp("2026-07-15 16:55", tz="America/New_York")  # 20:55 UTC
    d = _m5(8, start)
    i21 = int(np.where(d.utc_hour == 21)[0][0])
    assert not core.entry_ok_mask(d, session="union")[i21]


def test_london_or_does_not_use_future_bars():
    start = pd.Timestamp("2026-07-15 02:55", tz="America/New_York")
    d = _m5(40, start)
    i0830 = int(np.where(d.lon_min == 8 * 60 + 30)[0][0])
    d.high[i0830 + 6] = 999.0
    ok, hi, _ = core.london_or_at(d, i0830, 30)
    assert ok
    assert hi < 900.0


def test_forming_bar_never_signals():
    start = pd.Timestamp("2026-07-15 03:00", tz="America/New_York")
    d = _m5(40, start)
    d.close = np.linspace(80.0, 82.0, 40)
    d.high = d.close + 0.3
    d.low = d.close - 0.3
    sig = core.london_orb_signals(d, min_atr_pct=0.0, eia_blackout=False)
    assert sig[-1] == 0


def test_one_signal_per_et_day():
    start = pd.Timestamp("2026-07-15 03:00", tz="America/New_York")
    n = 50
    d = _m5(n, start)
    d.close = np.linspace(80.0, 85.0, n)
    d.high = d.close + 0.5
    d.low = d.close - 0.1
    sig = core.london_orb_signals(d, min_atr_pct=0.0, eia_blackout=False, one_per_day=True)
    assert int(np.count_nonzero(sig)) <= 1


def test_lock_search_families_and_promote():
    assert LOCK["promote"] is False
    assert LOCK["live_go"] is False
    assert LOCK["families"]["search"] == list(core.SEARCH_FAMILIES)
    assert "index_transfer" in LOCK["families"]["transfer_never_ranked"]
    assert LOCK["a_priori_overlay_default"] == core.FAM_LONDON
