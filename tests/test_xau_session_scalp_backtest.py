"""Gold scalp replay: costs, holdout lock, gold point sizing."""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest

TZ_LON = ZoneInfo("Europe/London")
TZ_ET = ZoneInfo("America/New_York")

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from xau_session_scalp_backtest import (  # noqa: E402
    CANDIDATES,
    CONTRACT_SIZE,
    HOLDOUT_START,
    LIVE_GO,
    POINT_SIZE,
    PRIMARY_CANDIDATE,
    PROMOTE,
    CostSpec,
    Trade,
    _round_trip_cost,
    gold_cost_book,
    metrics_from_trades,
    refuse_frictionless,
    simulate_scalp,
    split_by_holdout,
)


def _times(start: datetime, n: int, step_min: int = 5) -> list[datetime]:
    t0 = start.astimezone(UTC)
    return [t0 + timedelta(minutes=step_min * i) for i in range(n)]


def test_holdout_is_xau_lock_and_promote_is_false():
    lock = json.loads((ROOT / "results" / "xau_holdout_lock.json").read_text())
    assert str(lock["holdout_start"]).startswith("2026-01-01")
    assert HOLDOUT_START == date(2026, 1, 1)  # noqa: SIM300
    assert PROMOTE is False
    assert LIVE_GO is False


def test_primary_frozen_and_alternates_are_not_a_search_grid():
    ids = [c["id"] for c in CANDIDATES]
    assert ids[0] == PRIMARY_CANDIDATE == "london30_both_windows"
    assert len(CANDIDATES) == 3
    assert CANDIDATES[0]["or_minutes"] == 30
    assert CANDIDATES[0]["allow_ny"] is True


def test_gold_point_sizing_one_dollar_is_one_hundred_per_lot():
    costs = gold_cost_book()
    assert costs.point_size == POINT_SIZE == 0.01
    assert costs.contract_size == CONTRACT_SIZE == 100.0
    # $1 price move on 1.0 lot = $100; 1 MT5 point = $0.01 price = $1 / lot
    assert 1.0 * costs.contract_size * costs.lots == 100.0
    assert 1.0 * costs.point_size * costs.contract_size * costs.lots == 1.0


def test_round_trip_cost_uses_spread_and_slip():
    costs = gold_cost_book(slippage_points=10.0, commission_per_lot=0.0)
    # 20 spread + 2*10 slip = 40 points * 0.01 * 100 * 1 = $40
    assert _round_trip_cost(20.0, costs) == pytest.approx(40.0)


def test_refuse_zero_slip_book():
    with pytest.raises(SystemExit):
        refuse_frictionless(CostSpec(slippage_points=0.0, commission_per_lot=0.0))


def test_costs_can_turn_a_winner_into_a_loser():
    start = datetime(2026, 3, 16, 8, 30, tzinfo=TZ_LON)
    times = _times(start, n=20)
    n = len(times)
    open_ = np.full(n, 2400.0)
    open_[-1] = 2400.40  # +$0.40 * 100 = +$40 if flatten last (may not)
    # Drive a modest +0.30 by flatten so gross wins, taxed loses.
    for i, _t in enumerate(times):
        open_[i] = 2400.0 + 0.02 * i
    high = open_ + 0.05
    low = open_ - 0.05
    close = open_.copy()
    spread_free = np.zeros(n)
    spread_tax = np.full(n, 25.0)
    signals = np.zeros(n, dtype=int)
    signals[0] = +1
    atr = np.full(n, 0.50)  # wide so SL/TP do not clip the grind
    free = CostSpec(
        point_size=0.01,
        contract_size=100.0,
        lots=1.0,
        slippage_points=0.01,  # tiny so refuse_frictionless spirit, but allow
        max_spread_points=0.0,
    )
    taxed = gold_cost_book(max_spread_points=0.0)
    t_free = simulate_scalp(
        times, open_, high, low, close, spread_free, signals, free, atr=atr,
        sl_atr=10.0, tp_atr=10.0, allow_ny=False, or_minutes=30,
    )
    t_tax = simulate_scalp(
        times, open_, high, low, close, spread_tax, signals, taxed, atr=atr,
        sl_atr=10.0, tp_atr=10.0, allow_ny=False, or_minutes=30,
    )
    assert len(t_free) == 1 and len(t_tax) == 1
    assert t_tax[0].cost > t_free[0].cost
    assert t_tax[0].pnl < t_free[0].pnl


def test_spread_cap_skips_fill():
    start = datetime(2026, 3, 16, 8, 30, tzinfo=TZ_LON)
    times = _times(start, n=12)
    n = len(times)
    open_ = np.full(n, 2400.0)
    high = open_ + 1
    low = open_ - 1
    close = open_.copy()
    spread = np.full(n, 80.0)
    signals = np.zeros(n, dtype=int)
    signals[0] = +1
    costs = gold_cost_book(max_spread_points=40.0)
    trades = simulate_scalp(
        times, open_, high, low, close, spread, signals, costs,
        atr=np.full(n, 1.0), sl_atr=10.0, tp_atr=10.0, allow_ny=False,
    )
    assert trades == []


def test_same_bar_sl_and_tp_is_fail_closed():
    start = datetime(2026, 3, 16, 8, 30, tzinfo=TZ_LON)
    times = _times(start, n=8)
    n = len(times)
    open_ = np.full(n, 2400.0)
    high = open_ + 5.0
    low = open_ - 5.0
    close = open_.copy()
    spread = np.zeros(n)
    signals = np.zeros(n, dtype=int)
    signals[0] = +1
    atr = np.full(n, 1.0)
    costs = gold_cost_book(max_spread_points=0.0)
    trades = simulate_scalp(
        times, open_, high, low, close, spread, signals, costs,
        atr=atr, sl_atr=1.0, tp_atr=1.2, allow_ny=False,
    )
    assert len(trades) == 1
    assert trades[0].reason == "sl_tp_same_bar"
    assert trades[0].exit == pytest.approx(2400.0 - 1.0)


def test_split_by_holdout_does_not_use_et_june_index_lock():
    trades = [
        Trade(
            side=1, signal_i=0, fill_i=1, exit_i=2, entry=1, exit=2,
            reason="x", box="LONDON", utc_date="2025-12-31",
            signal_time="", fill_time="", exit_time="",
            spread_pts=0, cost=0, pnl=1, mae=0, mfe=0,
        ),
        Trade(
            side=1, signal_i=0, fill_i=1, exit_i=2, entry=1, exit=2,
            reason="x", box="LONDON", utc_date="2026-01-01",
            signal_time="", fill_time="", exit_time="",
            spread_pts=0, cost=0, pnl=2, mae=0, mfe=0,
        ),
    ]
    pre, post = split_by_holdout(trades)
    assert [t.utc_date for t in pre] == ["2025-12-31"]
    assert [t.utc_date for t in post] == ["2026-01-01"]
    # Index scalp used 2026-06-01; this track must not inherit that.
    assert HOLDOUT_START != date(2026, 6, 1)  # noqa: SIM300


def test_metrics_empty_book():
    m = metrics_from_trades([])
    assert m["trades"] == 0
    assert m["profit_factor"] == 0.0
