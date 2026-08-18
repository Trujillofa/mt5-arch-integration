"""Playbook v2: RSI/MACD causality, fade/cross signals, lock, no holdout peek."""

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
from us_index_session_autoresearch_v2 import (  # noqa: E402
    LOCK_PATH,
    SEARCH_ID,
    bounce_signals,
    build_grid,
    macd_signals,
)
from us_index_session_backtest import CostSpec  # noqa: E402
from us_index_session_core import macd_series, rsi_series  # noqa: E402

TZ_ET = ZoneInfo("America/New_York")


def test_lock_matches_runner():
    lock = json.loads(LOCK_PATH.read_text())
    assert lock["search_id"] == SEARCH_ID
    assert lock["holdout_start"] == "2026-06-01"
    assert lock["promote"] is False
    g = build_grid()
    assert len(g) == int(lock["n_configs_expected"])
    assert {r["family"] for r in g} == {
        "ny_cash_vwap_bounce_rsi",
        "ny_cash_ema_macd",
    }


def test_rsi_ignores_future_bars():
    x = np.linspace(100.0, 120.0, 40)
    a = rsi_series(x, 14)
    y = x.copy()
    y[30:] = 50.0
    b = rsi_series(y, 14)
    assert np.isfinite(a[20])
    assert abs(a[20] - b[20]) < 1e-12
    assert a[35] > 70.0
    assert b[35] < a[35]


def test_macd_hist_positive_on_uptrend():
    x = np.concatenate([np.full(40, 100.0), 100.0 + np.linspace(0, 40, 40)])
    _m, _s, hist = macd_series(x, 12, 26, 9)
    assert np.isfinite(hist[70])
    assert hist[70] > 0.0


def test_bounce_fades_extension_not_chases():
    n = 40
    mins = np.array([9 * 60 + 30 + 5 * i for i in range(n)], dtype=np.int32)
    keys = np.full(n, 20260316, dtype=np.int32)
    dow = np.full(n, 0, dtype=np.int8)
    ny = mins >= 9 * 60 + 30
    close = np.full(n, 18000.0)
    close[3] = 18040.0  # 09:45 — 2 ATR above VWAP
    vwap = np.full(n, 18000.0)
    atr = np.full(n, 20.0)
    rsi = np.full(n, 50.0)
    rsi[3] = 80.0
    sigs = bounce_signals(
        close,
        mins,
        keys,
        dow,
        ny,
        vwap,
        atr,
        rsi,
        entry_end_min=10 * 60 + 30,
        atr_dev=1.0,
        rsi_ob=75.0,
        rsi_os=25.0,
        one_per_day=True,
        min_atr_pct=0.0,
    )
    assert int(sigs[3]) == -1
    assert int(np.count_nonzero(sigs)) == 1


def test_macd_needs_cross_and_hist():
    n = 20
    mins = np.array([9 * 60 + 40 + 5 * i for i in range(n)], dtype=np.int32)
    keys = np.full(n, 20260316, dtype=np.int32)
    dow = np.full(n, 0, dtype=np.int8)
    ny = np.ones(n, dtype=bool)
    ema_f = np.linspace(99.0, 101.0, n)
    ema_s = np.full(n, 100.0)
    hist = np.full(n, 0.5)
    sigs = macd_signals(
        mins,
        keys,
        dow,
        ny,
        ema_f,
        ema_s,
        hist,
        entry_end_min=12 * 60,
        one_per_day=True,
        cross_only=True,
    )
    crosses = np.where((ema_f > ema_s) & (np.roll(ema_f, 1) <= ema_s))[0]
    crosses = [int(i) for i in crosses if i > 0]
    assert crosses
    assert int(sigs[crosses[0]]) == 1
    assert int(np.count_nonzero(sigs)) == 1
    hist0 = np.full(n, -0.5)
    blocked = macd_signals(
        mins,
        keys,
        dow,
        ny,
        ema_f,
        ema_s,
        hist0,
        entry_end_min=12 * 60,
        one_per_day=True,
        cross_only=True,
    )
    assert int(np.count_nonzero(blocked)) == 0


def test_vwap_exit_hits_frozen_target_after_sl_priority():
    start = datetime(2026, 3, 16, 10, 0, tzinfo=TZ_ET)
    times = [start.astimezone(UTC) + timedelta(minutes=5 * i) for i in range(12)]
    n = len(times)
    mins = np.array([10 * 60 + 5 * i for i in range(n)], dtype=np.int32)
    keys = np.full(n, 20260316, dtype=np.int32)
    open_ = np.full(n, 100.0)
    high = np.full(n, 100.2)
    low = np.full(n, 99.8)
    high[3] = 101.0  # touch VWAP 100.5
    atr = np.full(n, 1.0)
    spread = np.zeros(n)
    sigs = np.zeros(n, dtype=np.int8)
    sigs[0] = 1
    target = np.full(n, 100.5)
    costs = CostSpec(slippage_points=0.0, max_spread_points=200.0)
    trades = simulate_exits(
        times,
        mins,
        keys,
        open_,
        high,
        low,
        atr,
        spread,
        sigs,
        costs,
        {"kind": "vwap", "sl": 2.0},
        target=target,
    )
    assert len(trades) == 1
    assert trades[0].reason == "vwap"
    assert abs(trades[0].exit - 100.5) < 1e-9
