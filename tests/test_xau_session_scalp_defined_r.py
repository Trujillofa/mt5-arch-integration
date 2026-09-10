"""Defined-R gold scalp: lock, score, BE, time-stop, payoff reject."""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest

TZ_LON = ZoneInfo("Europe/London")

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from xau_session_scalp_backtest import (  # noqa: E402
    CONTRACT_SIZE,
    HOLDOUT_START,
    POINT_SIZE,
    gold_cost_book,
    refuse_frictionless,
)
from xau_session_scalp_core import FAMILY_ID as CORE_FAMILY  # noqa: E402
from xau_session_scalp_defined_r import (  # noqa: E402
    BE_R_GRID,
    FAMILY_ID,
    LOCK_PATH,
    SELECT_END,
    TIME_STOP_GRID,
    TP_R_GRID,
    eligible_select,
    frozen_grid,
    pick_primary,
    simulate_defined_r,
)


def _times(start: datetime, n: int) -> list:
    t0 = start.astimezone(UTC)
    return [t0 + timedelta(minutes=5 * i) for i in range(n)]


def _book(n: int, start: datetime, *, atr_v: float = 2.0):
    times = _times(start, n)
    open_ = np.full(n, 2400.0)
    high = open_ + 0.2
    low = open_ - 0.2
    close = open_.copy()
    spread = np.full(n, 6.0)
    signals = np.zeros(n, dtype=int)
    atr = np.full(n, atr_v)
    or_width = np.full(n, 2.0)  # 1.0 ATR — inside [0.35, 2.5]
    costs = refuse_frictionless(gold_cost_book(max_spread_points=40.0))
    return times, open_, high, low, close, spread, signals, atr, or_width, costs


def test_lock_frozen_before_search_and_holdout_not_select():
    lock = json.loads(LOCK_PATH.read_text())
    assert lock["family_id"] == FAMILY_ID == CORE_FAMILY
    assert lock["frozen_before_metrics"] is True
    assert lock["promote"] is False
    assert lock["live_go"] is False
    assert lock["holdout_start"] == "2026-01-01"
    assert HOLDOUT_START == date(2026, 1, 1)  # noqa: SIM300
    assert lock["select_end"] == "2025-10-31"
    assert date(2025, 10, 31) == SELECT_END
    assert lock["grid"]["cardinality"] == 16
    assert lock["grid"]["tp_r"] == [0.35, 0.5, 0.7, 1.0]
    assert "holdout" not in lock["score"]["window"]
    assert lock["score"]["window"] == "select"


def test_frozen_grid_matches_lock():
    cells = frozen_grid()
    assert len(cells) == 16
    tps = sorted({c["tp_r"] for c in cells})
    assert tps == list(TP_R_GRID)
    assert set(BE_R_GRID) == {c["be_r"] for c in cells}
    assert set(TIME_STOP_GRID) == {c["time_stop_bars"] for c in cells}


def test_eligible_rejects_degenerate_payoff_even_if_pf_ok():
    # One loser wipes >=5 winners (payoff 0.15) — always reject.
    assert eligible_select({"trades": 80, "profit_factor": 1.8, "payoff": 0.15}) is False
    assert eligible_select({"trades": 80, "profit_factor": 1.05, "payoff": 0.21}) is False
    assert eligible_select({"trades": 80, "profit_factor": 1.20, "payoff": 0.30}) is True
    assert eligible_select({"trades": 20, "profit_factor": 1.5, "payoff": 0.80}) is False


def test_pick_primary_uses_select_only_not_holdout():
    rows = [
        {
            "id": "pretty_holdout",
            "eligible": False,
            "select": {"trades": 50, "win_rate": 0.40, "profit_factor": 0.70},
            "holdout": {"trades": 40, "win_rate": 0.90, "profit_factor": 2.50},
        },
        {
            "id": "best_select_pf",
            "eligible": False,
            "select": {"trades": 50, "win_rate": 0.48, "profit_factor": 0.83},
            "holdout": {"trades": 40, "win_rate": 0.20, "profit_factor": 0.40},
        },
    ]
    pick = pick_primary(rows)
    assert pick["id"] == "best_select_pf"
    assert pick["pick_reason"] == "no_eligible_max_select_pf_n30"


def test_pick_max_wr_among_eligible():
    rows = [
        {
            "id": "hi_wr",
            "eligible": True,
            "select": {"trades": 50, "win_rate": 0.62, "profit_factor": 1.05},
        },
        {
            "id": "hi_pf",
            "eligible": True,
            "select": {"trades": 50, "win_rate": 0.55, "profit_factor": 1.40},
        },
    ]
    pick = pick_primary(rows)
    assert pick["id"] == "hi_wr"
    assert pick["pick_reason"] == "max_select_wr_among_eligible"


def test_defined_r_hard_sl_and_tp():
    start = datetime(2025, 6, 16, 8, 30, tzinfo=TZ_LON)
    times, open_, high, low, close, spread, signals, atr, or_w, costs = _book(12, start)
    signals[0] = +1
    high[1] = 2400.0 + 2.5  # 1.0R TP at +2.0
    low[1] = 2399.8
    trades, _ = simulate_defined_r(
        times, open_, high, low, close, spread, signals, costs,
        atr=atr, tp_r=1.0, be_r=0.0, time_stop_bars=6, or_width=or_w,
    )
    assert len(trades) == 1
    assert trades[0].reason == "tp"
    # SL path
    signals = np.zeros(12, dtype=int)
    signals[0] = +1
    high = open_ + 0.2
    low = open_.copy()
    low[1] = 2400.0 - 2.5
    trades, _ = simulate_defined_r(
        times, open_, high, low, close, spread, signals, costs,
        atr=atr, tp_r=1.0, be_r=0.0, time_stop_bars=6, or_width=or_w,
    )
    assert len(trades) == 1
    assert trades[0].reason == "sl"
    assert trades[0].pnl < 0


def test_same_bar_sl_wins():
    start = datetime(2025, 6, 16, 8, 30, tzinfo=TZ_LON)
    times, open_, high, low, close, spread, signals, atr, or_w, costs = _book(8, start)
    signals[0] = +1
    high[1] = 2410.0
    low[1] = 2390.0
    trades, _ = simulate_defined_r(
        times, open_, high, low, close, spread, signals, costs,
        atr=atr, tp_r=1.0, be_r=0.0, time_stop_bars=6, or_width=or_w,
    )
    assert len(trades) == 1
    assert trades[0].reason == "sl_tp_same_bar"
    assert trades[0].exit < trades[0].entry


def test_breakeven_scratch_after_costs():
    start = datetime(2025, 6, 16, 8, 30, tzinfo=TZ_LON)
    times, open_, high, low, close, spread, signals, atr, or_w, costs = _book(
        10, start, atr_v=2.0
    )
    signals[0] = +1
    # 0.4R trigger = 0.8 price; then return through entry on next bar.
    # Arm BE on bar 1 without tagging the new stop; tag it on bar 2.
    high[1] = 2400.0 + 0.85
    low[1] = 2400.30
    high[2] = 2400.10
    low[2] = 2399.00
    trades, _ = simulate_defined_r(
        times, open_, high, low, close, spread, signals, costs,
        atr=atr, tp_r=1.0, be_r=0.40, time_stop_bars=6, or_width=or_w,
    )
    assert len(trades) == 1
    assert trades[0].reason == "be"
    # True scratch after costs: price offset equals RT cost / contract.
    assert trades[0].pnl == pytest.approx(0.0, abs=1e-6)


def test_time_stop_exits_before_flatten():
    start = datetime(2025, 6, 16, 8, 30, tzinfo=TZ_LON)
    times, open_, high, low, close, spread, signals, atr, or_w, costs = _book(20, start)
    signals[0] = +1
    # Stay inside SL/TP corridor.
    trades, _ = simulate_defined_r(
        times, open_, high, low, close, spread, signals, costs,
        atr=atr, tp_r=1.0, be_r=0.0, time_stop_bars=6, or_width=or_w,
    )
    assert len(trades) == 1
    assert trades[0].reason == "time_stop"
    assert trades[0].exit_i - trades[0].fill_i == 6


def test_or_width_and_cost_to_tp_skip():
    start = datetime(2025, 6, 16, 8, 30, tzinfo=TZ_LON)
    times, open_, high, low, close, spread, signals, atr, or_w, costs = _book(8, start)
    signals[0] = +1
    or_wide = np.full(8, 20.0)  # 10 ATR
    trades, _ = simulate_defined_r(
        times, open_, high, low, close, spread, signals, costs,
        atr=atr, tp_r=1.0, be_r=0.0, time_stop_bars=6, or_width=or_wide,
    )
    assert trades == []
    # Tiny TP vs $26 RT cost.
    or_ok = np.full(8, 2.0)
    tiny_atr = np.full(8, 0.05)
    trades, _ = simulate_defined_r(
        times, open_, high, low, close, spread, signals, costs,
        atr=tiny_atr, tp_r=0.35, be_r=0.0, time_stop_bars=6, or_width=or_ok,
    )
    assert trades == []


def test_gold_point_sizing_unchanged():
    costs = gold_cost_book()
    assert costs.point_size == POINT_SIZE == 0.01
    assert costs.contract_size == CONTRACT_SIZE == 100.0


def test_official_pareto_does_not_claim_80_and_pf1():
    pareto = ROOT / "results" / "xau_session_scalp" / "defined_r_v1_pareto.json"
    if not pareto.is_file():
        pytest.skip("pareto not written yet")
    r = json.loads(pareto.read_text())
    assert r["family_id"] == FAMILY_ID
    assert r["primary"]["pick_reason"].startswith("no_eligible")
    assert r["wr80_verdict"]["hit_80_and_pf1_on_select"] is False
    # Selection used select only.
    assert r["primary"]["id"] == "tpr1_be0_ts6"
