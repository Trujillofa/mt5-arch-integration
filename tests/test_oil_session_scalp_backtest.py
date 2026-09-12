"""Oil session scalp backtest: lock book, fill rules, holdout split."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import oil_session_scalp_backtest as bt  # noqa: E402
import oil_session_scalp_core as core  # noqa: E402
from us_index_session_backtest import CostSpec, Trade  # noqa: E402

LOCK = json.loads((ROOT / "results" / "oil_session_scalp_lock.json").read_text())


def _costs() -> CostSpec:
    return CostSpec(
        point_size=0.01,
        contract_size=1000.0,
        lots=1.0,
        commission_per_lot=0.0,
        slippage_points=2.0,
        max_spread_points=50.0,
    )


def test_lock_refuses_promote_and_mutated_slip():
    lock = json.loads(json.dumps(LOCK))
    costs = bt.costs_from_lock(lock)
    bt.require_oil_cost_book(lock, costs)
    lock["promote"] = True
    with pytest.raises(SystemExit):
        bt.require_oil_cost_book(lock, costs, allow_pending=True)
    lock = json.loads(json.dumps(LOCK))
    costs2 = CostSpec(
        point_size=costs.point_size,
        contract_size=costs.contract_size,
        lots=costs.lots,
        slippage_points=10.0,
        max_spread_points=costs.max_spread_points,
    )
    with pytest.raises(SystemExit):
        bt.require_oil_cost_book(lock, costs2)


def test_holdout_split_does_not_use_sibling_dates():
    hs = bt.holdout_start_from_lock(LOCK)
    assert hs == date(2026, 4, 1)
    trades = [
        Trade(1, 0, 1, 2, 1, 2, "tp", "2026-03-31", "", "", "", 1, 0, 1, 0, 0),
        Trade(1, 0, 1, 2, 1, 2, "tp", "2026-04-01", "", "", "", 1, 0, 1, 0, 0),
    ]
    pre, post = bt.split_by_holdout(trades, hs)
    assert [t.et_date for t in pre] == ["2026-03-31"]
    assert [t.et_date for t in post] == ["2026-04-01"]


def test_fill_is_next_bar_open_and_sl_first():
    start = pd.Timestamp("2026-07-15 08:00", tz="America/New_York")
    n = 40
    et = pd.date_range(start, periods=n, freq="5min")
    utc = et.tz_convert("UTC")
    close = np.full(n, 80.0)
    high = close + 1.0
    low = close - 1.0
    open_ = close.copy()
    sig_i, fill_i = 20, 21
    open_[fill_i] = 80.10
    low[fill_i] = 78.00
    d = core.pack_m5(
        open_=open_,
        high=high,
        low=low,
        close=close,
        vol=np.ones(n),
        spread=np.full(n, 22.0),
        times_et=[t.to_pydatetime() for t in et],
        times_utc=[t.to_pydatetime() for t in utc],
    )
    sigs = np.zeros(n, dtype=np.int8)
    sigs[sig_i] = 1
    trades = bt.simulate_exits(d, sigs, _costs(), sl_atr=1.0, tp_r=1.0, time_stop_bars=6)
    assert trades
    assert trades[0].fill_i == fill_i
    assert trades[0].entry == 80.10
    assert trades[0].reason == "sl"


def test_spread_cap_skips_fill():
    start = pd.Timestamp("2026-07-15 08:00", tz="America/New_York")
    n = 10
    et = pd.date_range(start, periods=n, freq="5min")
    utc = et.tz_convert("UTC")
    px = np.full(n, 80.0)
    d = core.pack_m5(
        open_=px.copy(),
        high=px + 0.2,
        low=px - 0.2,
        close=px.copy(),
        vol=np.ones(n),
        spread=np.full(n, 90.0),
        times_et=[t.to_pydatetime() for t in et],
        times_utc=[t.to_pydatetime() for t in utc],
    )
    sigs = np.zeros(n, dtype=np.int8)
    sigs[2] = 1
    trades = bt.simulate_exits(d, sigs, _costs(), sl_atr=1.0, tp_r=1.0, time_stop_bars=6)
    assert trades == []
