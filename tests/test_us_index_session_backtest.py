"""Flatten replay: costs, next-bar fill, no holdout selection."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from us_index_session_backtest import (  # noqa: E402
    HOLDOUT_START,
    LIVE_GO,
    PROMOTE,
    CostSpec,
    Trade,
    _round_trip_cost,
    metrics_from_trades,
    simulate_flatten,
    split_by_holdout,
)
from us_index_session_core import FLAT_WARN  # noqa: E402

TZ_ET = ZoneInfo("America/New_York")


def _session_times(et_day_open: datetime, n: int = 90) -> list[datetime]:
    """M5 bars starting at ``et_day_open`` (aware ET)."""
    t0 = et_day_open.astimezone(UTC)
    return [t0 + timedelta(minutes=5 * i) for i in range(n)]


def test_holdout_is_pre_registered_and_promote_is_false():
    assert HOLDOUT_START.isoformat() == "2026-06-01"
    assert PROMOTE is False
    assert LIVE_GO is False


def test_fill_is_next_open_flatten_is_1545():
    start = datetime(2026, 3, 16, 10, 0, tzinfo=TZ_ET)
    times = _session_times(start, n=80)  # 10:00 → ~16:35
    n = len(times)
    open_ = np.full(n, 100.0)
    # Price drifts +20 by flatten so a long should win before costs.
    for i, t in enumerate(times):
        et = t.astimezone(TZ_ET)
        minutes = et.hour * 60 + et.minute
        open_[i] = 100.0 + 0.05 * (minutes - 10 * 60)
    high = open_ + 1.0
    low = open_ - 1.0
    close = open_.copy()
    spread = np.zeros(n)
    signals = np.zeros(n, dtype=int)
    signals[0] = +1  # 10:00 ET close
    costs = CostSpec(point_size=0.01, contract_size=1.0, lots=1.0, slippage_points=0.0)
    trades = simulate_flatten(times, open_, high, low, close, spread, signals, costs)
    assert len(trades) == 1
    t = trades[0]
    assert t.fill_i == 1
    assert abs(t.entry - open_[1]) < 1e-12
    exit_et = times[t.exit_i].astimezone(TZ_ET)
    assert exit_et.hour == FLAT_WARN.hour and exit_et.minute == FLAT_WARN.minute
    assert t.reason == "flatten_1545"


def test_costs_can_turn_a_winner_into_a_loser():
    start = datetime(2026, 3, 16, 10, 0, tzinfo=TZ_ET)
    times = _session_times(start, n=80)
    n = len(times)
    open_ = np.full(n, 100.0)
    open_[-1] = 100.10  # tiny favorable move if we flattened last bar
    # Force flatten bar open only +0.10
    for i, t in enumerate(times):
        et = t.astimezone(TZ_ET)
        if et.hour == 15 and et.minute == 45:
            open_[i] = 100.10
    high = open_ + 0.01
    low = open_ - 0.01
    close = open_.copy()
    spread_free = np.zeros(n)
    spread_tax = np.full(n, 50.0)
    signals = np.zeros(n, dtype=int)
    signals[0] = +1
    free = CostSpec(point_size=0.01, contract_size=1.0, lots=1.0, slippage_points=0.0)
    taxed = CostSpec(
        point_size=0.01,
        contract_size=1.0,
        lots=1.0,
        slippage_points=10.0,
        commission_per_lot=0.0,
    )
    t_free = simulate_flatten(
        times, open_, high, low, close, spread_free, signals, free
    )
    t_tax = simulate_flatten(
        times, open_, high, low, close, spread_tax, signals, taxed
    )
    assert t_free[0].pnl > 0
    assert t_tax[0].pnl < t_free[0].pnl
    assert t_tax[0].cost == _round_trip_cost(50.0, taxed)


def test_spread_cap_skips_fill():
    start = datetime(2026, 3, 16, 10, 0, tzinfo=TZ_ET)
    times = _session_times(start, n=20)
    n = len(times)
    open_ = np.full(n, 100.0)
    high = open_ + 1
    low = open_ - 1
    close = open_.copy()
    spread = np.full(n, 250.0)
    signals = np.zeros(n, dtype=int)
    signals[0] = +1
    costs = CostSpec(max_spread_points=200.0, slippage_points=0.0)
    trades = simulate_flatten(times, open_, high, low, close, spread, signals, costs)
    assert trades == []


def test_holdout_split_does_not_drop_or_retune_trades():
    trades = [
        Trade(
            side=1,
            signal_i=0,
            fill_i=1,
            exit_i=2,
            entry=1,
            exit=2,
            reason="flatten_1545",
            et_date="2026-05-15",
            signal_time="",
            fill_time="",
            exit_time="",
            spread_pts=60,
            cost=1,
            pnl=10,
            mae=1,
            mfe=2,
        ),
        Trade(
            side=-1,
            signal_i=3,
            fill_i=4,
            exit_i=5,
            entry=2,
            exit=1,
            reason="flatten_1545",
            et_date="2026-07-01",
            signal_time="",
            fill_time="",
            exit_time="",
            spread_pts=60,
            cost=1,
            pnl=-4,
            mae=1,
            mfe=2,
        ),
    ]
    pre, post = split_by_holdout(trades)
    assert [t.et_date for t in pre] == ["2026-05-15"]
    assert [t.et_date for t in post] == ["2026-07-01"]
    assert metrics_from_trades(pre)["trades"] + metrics_from_trades(post)["trades"] == 2
