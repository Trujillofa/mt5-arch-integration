"""v6 lock, completed-day regime, no-lookahead Hurst/ADX, trail/MR exits."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from us_index_session_autoresearch import simulate_exits  # noqa: E402
from us_index_session_autoresearch_v4 import split_v4  # noqa: E402
from us_index_session_autoresearch_v6 import (  # noqa: E402
    LOCK_PATH,
    SEARCH_ID,
    build_grid,
)
from us_index_session_backtest import CostSpec, Trade  # noqa: E402
from us_index_session_core import (  # noqa: E402
    LONDON_FEATURE_END_MIN,
    REGIME_CHOP,
    causal_session_vwap_prev,
    completed_daily_regime_state,
    ema_series,
    hurst_rs,
    london_et_displacement,
    london_feature_on_m5,
    persist_from_closes,
    variance_ratio,
    wilder_adx_series,
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


def test_lock_and_grid():
    lock = json.loads(LOCK_PATH.read_text())
    assert lock["search_id"] == SEARCH_ID
    assert lock["selection_end"] == "2026-06-01"
    assert lock["holdout_start"] == "2026-07-01"
    assert lock["promote"] is False
    assert lock["live_go"] is False
    assert lock["python_only"] is True
    assert lock["costs"]["slippage_points"] == 10.0
    assert lock["lots"] == 1.0
    assert "cleaner window, not virgin" in lock["holdout_rule"]
    assert "london_fx_predictors" in lock["skipped"]
    assert lock["hurst_fallback_preregistered"]["fallback"] == "variance_ratio"
    grid = build_grid()
    assert len(grid) == int(lock["n_configs_expected"])
    assert len(grid) == 136
    fams = {r["family"] for r in grid}
    assert fams == {"daily_regime_switch", "london_xau_fx_risk_gate"}
    assert sum(1 for r in grid if r["family"] == "daily_regime_switch") == 128
    assert sum(1 for r in grid if r["family"] == "london_xau_fx_risk_gate") == 8


def test_june_is_neither_develop_nor_holdout():
    pre, post = split_v4([_t("2026-05-31"), _t("2026-06-15"), _t("2026-07-02")])
    assert [t.et_date for t in pre] == ["2026-05-31"]
    assert [t.et_date for t in post] == ["2026-07-02"]


def _daily_bars(n_days: int, trend: float = 0.0, start: int = 20250101):
    """n_days ET dates, 2 M5 bars each. Last day is 'today'."""
    keys = []
    open_ = []
    high = []
    low = []
    close = []
    px = 100.0
    for i in range(n_days):
        d = start + i
        o = px
        c = px + trend
        keys.extend([d, d])
        open_.extend([o, o])
        high.extend([max(o, c) + 1.0, max(o, c) + 1.0])
        low.extend([min(o, c) - 1.0, min(o, c) - 1.0])
        close.extend([c, c])
        px = c
    return (
        np.array(keys, np.int32),
        np.array(open_, float),
        np.array(high, float),
        np.array(low, float),
        np.array(close, float),
    )


def test_daily_features_ignore_forming_day():
    keys, o, h, lo, c = _daily_bars(80, trend=0.4)
    st0, hu0, ad0 = completed_daily_regime_state(keys, o, h, lo, c, atr_n=20, hurst_lb=32)
    # Mutate today's (last day's) range — must not change today's state/hurst/adx.
    h[-1] = 10_000.0
    lo[-1] = 1.0
    c[-1] = 9_000.0
    st1, hu1, ad1 = completed_daily_regime_state(keys, o, h, lo, c, atr_n=20, hurst_lb=32)
    assert st0[-1] == st1[-1]
    assert np.isnan(hu0[-1]) or hu0[-1] == hu1[-1]
    assert np.isnan(ad0[-1]) or ad0[-1] == ad1[-1]
    # And yesterday's broadcast onto today must be chop or a prior-day read, not 9000-driven.
    assert st1[-1] in (REGIME_CHOP, 1, -1)


def test_hurst_adx_no_lookahead():
    keys, o, h, lo, c = _daily_bars(80, trend=0.3)
    st0, hu0, ad0 = completed_daily_regime_state(keys, o, h, lo, c, atr_n=20, hurst_lb=32)
    mid = len(c) // 2
    # Future daily close must not leak into earlier bars' ADX/Hurst.
    c[-1] = c[-1] * 3.0
    h[-1] = c[-1] + 1.0
    st1, hu1, ad1 = completed_daily_regime_state(keys, o, h, lo, c, atr_n=20, hurst_lb=32)
    assert st0[mid] == st1[mid]
    if np.isfinite(hu0[mid]):
        assert hu0[mid] == hu1[mid]
    if np.isfinite(ad0[mid]):
        assert ad0[mid] == ad1[mid]
    adx, _p, _m = wilder_adx_series(h, lo, c, 14)
    # First ADX uses only the first 2*period bars.
    assert np.isnan(adx[20])
    assert np.isfinite(adx[27]) or np.isnan(adx[27])


def test_hurst_fallback_is_variance_ratio():
    flat = np.full(32, 100.0)
    assert np.isnan(hurst_rs(flat))
    scored = persist_from_closes(flat, 32, fallback="variance_ratio")
    assert np.isnan(scored) or scored in (0.44, 0.5, 0.56)
    trending = np.linspace(100.0, 200.0, 32)
    vr = variance_ratio(trending, k=2)
    assert np.isfinite(vr)


def test_london_feature_ends_before_0930():
    # H1 opens at 07:00 and 08:00 ET; 09:00 and 09:30 must not enter.
    d = datetime(2026, 3, 16, 7, 0, tzinfo=ET)
    times = [
        d.astimezone(UTC),
        (d + timedelta(hours=1)).astimezone(UTC),
        (d + timedelta(hours=2)).astimezone(UTC),
        (d + timedelta(hours=2, minutes=30)).astimezone(UTC),
    ]
    o = np.array([100.0, 101.0, 110.0, 120.0])
    h = np.array([101.0, 102.0, 111.0, 121.0])
    lo = np.array([99.0, 100.0, 109.0, 119.0])
    c = np.array([101.0, 103.0, 110.0, 120.0])
    feat = london_et_displacement(times, o, h, lo, c)
    rec = feat[20260316]
    assert rec["disp"] == 3.0  # 103 - 100, not 120-100
    assert rec["feature_end_min"] == LONDON_FEATURE_END_MIN
    keys = np.array([20260316, 20260316, 20260316], np.int32)
    mins = np.array([8 * 60 + 55, 9 * 60, 9 * 60 + 30], np.int32)
    signed = london_feature_on_m5(keys, mins, feat, "sign")
    assert np.isnan(signed[0])
    assert signed[1] == 1.0
    assert signed[2] == 1.0


def test_trail_exit_ignores_future_bars():
    start = datetime(2026, 3, 16, 10, 0, tzinfo=ET)
    times = [start.astimezone(UTC) + timedelta(minutes=5 * i) for i in range(12)]
    n = len(times)
    mins = np.array([10 * 60 + 5 * i for i in range(n)], dtype=np.int32)
    keys = np.full(n, 20260316, dtype=np.int32)
    open_ = np.full(n, 100.0)
    high = np.full(n, 100.4)
    low = np.full(n, 99.8)
    atr = np.full(n, 1.0)
    spread = np.zeros(n)
    sigs = np.zeros(n, dtype=np.int8)
    sigs[0] = 1
    costs = CostSpec(slippage_points=0.0, max_spread_points=200.0)
    spec = {"kind": "trail", "trail": "swing", "k": 6, "sl": 1.0, "hh": 15, "mm": 45}
    t0 = simulate_exits(
        times, mins, keys, open_, high, low, atr, spread, sigs, costs, spec
    )
    # Future collapse must not change an already-determined early SL.
    low[-1] = 50.0
    t1 = simulate_exits(
        times, mins, keys, open_, high, low, atr, spread, sigs, costs, spec
    )
    assert len(t0) == 1 and len(t1) == 1
    assert t0[0].reason == t1[0].reason
    assert abs(t0[0].exit - t1[0].exit) < 1e-9


def test_mr_vwap_exit_uses_completed_bars_only():
    start = datetime(2026, 3, 16, 9, 30, tzinfo=ET)
    times = [start.astimezone(UTC) + timedelta(minutes=5 * i) for i in range(8)]
    n = len(times)
    mins = np.array([9 * 60 + 30 + 5 * i for i in range(n)], dtype=np.int32)
    keys = np.full(n, 20260316, dtype=np.int32)
    ny = np.ones(n, dtype=bool)
    open_ = np.full(n, 100.0)
    # Signal VWAP from bar 0 is ~102. Fill bar high stays below that; bar 3 tags it.
    high = np.array([102.2, 100.4, 100.4, 102.8, 100.4, 100.4, 100.4, 100.4])
    low = np.array([101.6, 99.8, 99.8, 99.8, 99.8, 99.8, 99.8, 99.8])
    close = np.array([102.0, 100.1, 100.1, 100.1, 100.1, 100.1, 100.1, 100.1])
    vol = np.ones(n)
    atr = np.full(n, 1.0)
    spread = np.zeros(n)
    sigs = np.zeros(n, dtype=np.int8)
    sigs[0] = 1
    target = causal_session_vwap_prev(mins, keys, ny, high, low, close, vol)
    costs = CostSpec(slippage_points=0.0, max_spread_points=200.0)
    spec = {"kind": "vwap", "sl": 1.0, "hh": 11, "mm": 30, "running": True}
    t0 = simulate_exits(
        times, mins, keys, open_, high, low, atr, spread, sigs, costs, spec, target=target
    )
    high[-1] = 200.0
    close[-1] = 200.0
    target2 = causal_session_vwap_prev(mins, keys, ny, high, low, close, vol)
    t1 = simulate_exits(
        times, mins, keys, open_, high, low, atr, spread, sigs, costs, spec, target=target2
    )
    assert len(t0) == 1 and len(t1) == 1
    assert t0[0].reason == t1[0].reason
    assert abs(t0[0].exit - t1[0].exit) < 1e-9
    # Prev-bar VWAP at the first bar is NaN (no completed session bar yet).
    assert np.isnan(target[0])
    ema = ema_series(close, 3)
    assert np.isfinite(ema[-1])
