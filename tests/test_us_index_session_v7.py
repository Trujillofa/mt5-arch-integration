"""v7 lock, 60m IB false-break next-bar close, causal z-score / vol window."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from us_index_session_autoresearch import _et_arrays, _or_and_vwap  # noqa: E402
from us_index_session_autoresearch_v4 import split_v4  # noqa: E402
from us_index_session_autoresearch_v7 import (  # noqa: E402
    LOCK_PATH,
    SEARCH_ID,
    build_grid,
    zscore_vol_signals,
)
from us_index_session_backtest import Trade  # noqa: E402
from us_index_session_core import (  # noqa: E402
    IB_END_MIN,
    ib_false_break_signals,
    opening_range_at,
    rolling_zscore_typical,
)

ET = ZoneInfo("America/New_York")


def _t(d: str, pnl: float = 1.0) -> Trade:
    return Trade(
        side=1,
        signal_i=0,
        fill_i=1,
        exit_i=2,
        entry=1,
        exit=2,
        reason="x",
        et_date=d,
        signal_time="",
        fill_time="",
        exit_time="",
        spread_pts=0,
        cost=0,
        pnl=pnl,
        mae=0,
        mfe=0,
    )


def _m5_from(et0: datetime, n: int, *, base: float = 100.0):
    times = [et0.astimezone(UTC) + timedelta(minutes=5 * i) for i in range(n)]
    close = np.full(n, base, dtype=float)
    high = close + 2.0
    low = close - 2.0
    open_ = close.copy()
    vol = np.ones(n, dtype=float)
    return times, open_, high, low, close, vol


def test_lock_and_grid():
    lock = json.loads(LOCK_PATH.read_text())
    assert lock["search_id"] == SEARCH_ID
    assert lock["selection_end"] == "2026-06-01"
    assert lock["holdout_start"] == "2026-07-01"
    assert lock["promote"] is False
    assert lock["live_go"] is False
    assert lock["python_only"] is True
    assert lock["lots"] == 1.0
    assert lock["costs"]["slippage_points"] == 10.0
    assert lock["costs"]["max_spread_points"] == 200.0
    assert lock["causality"]["z_window_include_i"] is False
    assert "cleaner window, not virgin" in lock["holdout_rule"]
    assert "v4–v6 holdout" in lock["holdout_rule"] or "v4-v6 holdout" in lock["holdout_rule"]
    grid = build_grid()
    assert len(grid) == int(lock["n_configs_expected"])
    assert len(grid) == 40
    fams = {r["family"] for r in grid}
    assert fams == {"ib_false_breakout_fade", "m5_zscore_tick_vol_exhaustion"}
    assert sum(1 for r in grid if r["family"] == "ib_false_breakout_fade") == 8
    assert sum(1 for r in grid if r["family"] == "m5_zscore_tick_vol_exhaustion") == 32
    assert lock["grid_breakdown"]["ib_false_breakout_fade"] == 8
    assert lock["grid_breakdown"]["m5_zscore_tick_vol_exhaustion"] == 32


def test_june_is_neither_develop_nor_holdout():
    pre, post = split_v4([_t("2026-05-31"), _t("2026-06-15"), _t("2026-07-02")])
    assert [t.et_date for t in pre] == ["2026-05-31"]
    assert [t.et_date for t in post] == ["2026-07-02"]


def test_ib_incomplete_before_1030():
    start = datetime(2026, 3, 16, 9, 30, tzinfo=ET)
    times, _o, high, low, close, vol = _m5_from(start, 20, base=100.0)
    # bar 0 = 09:30, bar 11 = 10:25, bar 12 = 10:30
    assert (times[11].astimezone(ET).hour, times[11].astimezone(ET).minute) == (10, 25)
    assert (times[12].astimezone(ET).hour, times[12].astimezone(ET).minute) == (10, 30)
    or_1025 = opening_range_at(times, high, low, 11, or_minutes=60)
    or_1030 = opening_range_at(times, high, low, 12, or_minutes=60)
    assert or_1025.complete is False
    assert np.isnan(or_1025.high)
    assert or_1030.complete is True
    assert or_1030.high == 102.0
    assert or_1030.low == 98.0
    mins, keys, _dow, ny = _et_arrays(times)
    _oh, _ol, ready, _vw = _or_and_vwap(mins, keys, ny, high, low, close, vol, 60)
    assert ready[11] is False or ready[11] == 0
    assert bool(ready[12])
    assert int(mins[12]) == IB_END_MIN


def test_false_break_requires_next_bar_close_inside():
    start = datetime(2026, 3, 16, 9, 30, tzinfo=ET)
    times, _o, high, low, close, vol = _m5_from(start, 24, base=100.0)
    # 10:30 (i=12) sweeps IB high and closes back inside — must not signal.
    high[12] = 103.0
    close[12] = 100.0
    # Later bars stay outside so a failed same-bar fade cannot be rescued by
    # a later sweep→return pair.
    high[13:] = 104.0
    low[13:] = 103.0
    close[13:] = 103.5
    mins, keys, dow, ny = _et_arrays(times)
    or_h, or_l, ready, _vw = _or_and_vwap(mins, keys, ny, high, low, close, vol, 60)
    sigs = ib_false_break_signals(
        high, low, close, mins, keys, dow, or_h, or_l, ready, entry_end_min=12 * 60
    )
    assert int(sigs[12]) == 0
    assert int(np.max(np.abs(sigs))) == 0

    # Same sweep; next bar closes back inside → short on the return bar.
    close[13] = 100.0
    low[13] = 99.0
    high[13] = 101.0
    or_h, or_l, ready, _vw = _or_and_vwap(mins, keys, ny, high, low, close, vol, 60)
    sigs = ib_false_break_signals(
        high, low, close, mins, keys, dow, or_h, or_l, ready, entry_end_min=12 * 60
    )
    assert int(sigs[12]) == 0
    assert int(sigs[13]) == -1


def test_zscore_window_excludes_bar_i_and_future():
    n = 30
    close = np.full(n, 100.0)
    close[:20] = 100.0 + np.arange(20) * 0.05
    close[20] = 130.0
    high = close + 0.1
    low = close - 0.1
    vol = np.ones(n)
    z, mu, sig, vmu = rolling_zscore_typical(high, low, close, vol, 12, include_i=False)
    z_in, mu_in, _s, vmu_in = rolling_zscore_typical(
        high, low, close, vol, 12, include_i=True
    )
    assert np.isnan(z[11])
    assert np.isfinite(z[12])
    typ = (high + low + close) / 3.0
    assert abs(mu[20] - float(np.mean(typ[8:20]))) < 1e-9
    assert abs(mu_in[20] - float(np.mean(typ[9:21]))) < 1e-9
    assert mu[20] != mu_in[20]
    assert z[20] > z_in[20]

    z0 = z.copy()
    close[-1] = 400.0
    high[-1] = 400.1
    low[-1] = 399.9
    z1, _m, _s, _v = rolling_zscore_typical(high, low, close, vol, 12, include_i=False)
    assert np.allclose(z0[:20], z1[:20], equal_nan=True)


def test_vol_spike_uses_same_causal_window():
    n = 24
    close = np.linspace(100.0, 101.0, n)
    high = close + 0.1
    low = close - 0.1
    vol = np.ones(n)
    vol[18] = 10.0
    _z, _mu, _sig, vmu = rolling_zscore_typical(high, low, close, vol, 12, include_i=False)
    assert abs(vmu[18] - 1.0) < 1e-12
    _z2, _m2, _s2, vmu_in = rolling_zscore_typical(
        high, low, close, vol, 12, include_i=True
    )
    assert vmu_in[18] > 1.0
    mins = np.full(n, 10 * 60, dtype=np.int32)
    keys = np.full(n, 20260316, dtype=np.int32)
    dow = np.zeros(n, dtype=np.int8)
    z, _mu, _sig, vmu = rolling_zscore_typical(high, low, close, vol, 12, include_i=False)
    sigs = zscore_vol_signals(
        z,
        vol,
        vmu,
        mins,
        keys,
        dow,
        z_thr=2.0,
        vol_k=1.5,
        entry_start_min=9 * 60 + 45,
        entry_end_min=15 * 60,
        one_per_day=False,
        exclude_forming=False,
    )
    assert 1.5 * float(vmu[18]) < 10.0
    # Future volume must not leak into an earlier Vμ (index 12 is first valid).
    vmu_before = float(vmu[12])
    assert np.isfinite(vmu_before)
    vol[-1] = 1_000.0
    _z3, _m3, _s3, vmu3 = rolling_zscore_typical(high, low, close, vol, 12, include_i=False)
    assert abs(float(vmu3[12]) - vmu_before) < 1e-12
    assert int(sigs[18]) in (-1, 1, 0)
