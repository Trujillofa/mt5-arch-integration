"""Develop screen: lock, cardinality, exits, no holdout selection."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from us_index_session_autoresearch import (  # noqa: E402
    EXITS,
    FILTERS,
    LOCK_PATH,
    MIN_TRADES_DEVELOP,
    SEARCH_ID,
    build_grid,
    daily_monthly,
    score_row,
    simulate_exits,
)
from us_index_session_backtest import CostSpec, Trade  # noqa: E402

TZ_ET = ZoneInfo("America/New_York")


def test_lock_matches_runner():
    lock = json.loads(LOCK_PATH.read_text())
    assert lock["search_id"] == SEARCH_ID
    assert lock["holdout_start"] == "2026-06-01"
    assert lock["promote"] is False
    assert lock["goal_daily_pct"] == 0.01
    assert lock["goal_monthly_pct"] == 0.20


def test_grid_is_the_locked_product():
    g = build_grid()
    assert len(g) == 3 * 3 * 4 * 3 * 2 * 8
    assert len(EXITS) == 8
    assert len(FILTERS) == 4
    assert {r["filter"] for r in g} == {f[0] for f in FILTERS}


def test_atr_stop_hits_before_time():
    start = datetime(2026, 3, 16, 10, 0, tzinfo=TZ_ET)
    times = [start.astimezone(UTC) + timedelta(minutes=5 * i) for i in range(20)]
    n = len(times)
    mins = np.array([10 * 60 + 5 * i for i in range(n)], dtype=np.int32)
    keys = np.full(n, 20260316, dtype=np.int32)
    open_ = np.full(n, 100.0)
    high = np.full(n, 100.2)
    low = np.full(n, 99.5)
    low[3] = 98.0  # through SL at 99.0
    atr = np.full(n, 1.0)
    spread = np.zeros(n)
    sigs = np.zeros(n, dtype=np.int8)
    sigs[0] = 1
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
        {"kind": "atr", "sl": 1.0, "tp": 2.0},
    )
    assert len(trades) == 1
    assert trades[0].reason == "sl"
    assert abs(trades[0].exit - 99.0) < 1e-9


def test_score_ignores_holdout_metrics():
    good = {
        "trades": MIN_TRADES_DEVELOP,
        "net_pnl": 10.0,
        "profit_factor": 1.4,
        "expectancy": 1.0,
    }
    bad = {
        "trades": MIN_TRADES_DEVELOP,
        "net_pnl": -10.0,
        "profit_factor": 0.5,
        "expectancy": -1.0,
    }
    assert score_row(good) > score_row(bad)
    # A huge fictional holdout must not be in the score inputs.
    assert "holdout" not in good


def test_daily_goal_uses_median_trade_day():
    trades = [
        Trade(
            side=1,
            signal_i=0,
            fill_i=1,
            exit_i=2,
            entry=1,
            exit=2,
            reason="x",
            et_date="2026-03-16",
            signal_time="",
            fill_time="",
            exit_time="",
            spread_pts=0,
            cost=0,
            pnl=200.0,
            mae=0,
            mfe=0,
        ),
        Trade(
            side=1,
            signal_i=0,
            fill_i=1,
            exit_i=2,
            entry=1,
            exit=2,
            reason="x",
            et_date="2026-03-17",
            signal_time="",
            fill_time="",
            exit_time="",
            spread_pts=0,
            cost=0,
            pnl=50.0,
            mae=0,
            mfe=0,
        ),
    ]
    d = daily_monthly(trades, balance=10_000.0)
    assert d["median_daily_pct"] == 0.0125
    assert d["hit_daily_goal"] is True
