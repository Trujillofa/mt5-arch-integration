"""DFII10 long-or-flat regime: causality, lock, no short, score window."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import pandas as pd  # noqa: E402
from xau_exog_beta_realyield import asof_on  # noqa: E402
from xau_exog_regime import (  # noqa: E402
    FAMILY_ID,
    HOLDOUT,
    LOOKBACK,
    aligned_panel,
    continue_ok,
    load_lock,
    regime_falling,
    simulate_regime,
)
from xau_research_costs import load_research_costs, refuse_mutated_research_costs  # noqa: E402


def test_lock_long_or_flat_not_reopen():
    lock = load_lock()
    assert lock["family_id"] == FAMILY_ID
    assert lock["frozen_before_metrics"] is True
    assert lock["regime_primary"]["never_short"] is True
    assert lock["regime_primary"]["lookback_days"] == 20
    assert lock["regime_robustness_not_pick"]["used_to_pick"] is False
    assert lock["n_floor"]["kind"] == "regime_on_days"
    assert lock["score"]["window"] == "develop"
    assert "exog_dfii10_dtwex_daily_tvbeta_xau_follow_flat_v1" in lock["not_a_reopen"]
    assert lock["costs"]["slippage_points"] == 0.0
    assert HOLDOUT.strftime("%Y-%m-%d") == "2026-01-01"


def test_falling_regime_causal():
    x = np.linspace(2.0, 0.5, 40)
    a = regime_falling(x, 20)
    y = x.copy()
    y[30:] += 3.0
    b = regime_falling(y, 20)
    assert a[20] == b[20]
    assert a[LOOKBACK] == b[LOOKBACK]


def test_regime_trades_are_long_only_and_next_open():
    p = aligned_panel()
    on = regime_falling(p["dfii10"].to_numpy(float), LOOKBACK)
    costs = load_research_costs()
    refuse_mutated_research_costs(costs)
    trades = simulate_regime(p, on, costs)
    assert trades
    assert all(t.side == 1 for t in trades)
    assert all(t.exit_i >= t.entry_i for t in trades)
    assert all(t.entry_i >= 1 for t in trades)


def test_continue_requires_on_days_pf_and_net():
    reg = {"regime_on_days": 40, "profit_factor": 1.2, "net_profit": 100.0}
    base = {"net_profit": 50.0}
    assert continue_ok(reg, base) is True
    assert continue_ok({**reg, "regime_on_days": 10}, base) is False
    assert continue_ok({**reg, "profit_factor": 0.9}, base) is False
    assert continue_ok({**reg, "net_profit": 10.0}, base) is False

def test_asof_does_not_use_future_prints():
    gold = pd.Series(pd.to_datetime(["2024-01-06", "2024-01-07", "2024-01-08"], utc=True))
    fred = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-05", "2024-01-08"], utc=True).normalize(),
            "value": [1.0, 9.0],
        }
    )
    got = asof_on(gold, fred, "x")
    assert float(got.iloc[0]) == 1.0
    assert float(got.iloc[1]) == 1.0
    assert float(got.iloc[2]) == 9.0


def test_regime_at_t_ignores_future_dfii10_on_panel():
    p = aligned_panel()
    x = p["dfii10"].to_numpy(float).copy()
    i = 80
    a = regime_falling(x, LOOKBACK)
    y = x.copy()
    y[i + 1 :] += 2.0
    b = regime_falling(y, LOOKBACK)
    assert a[i] == b[i]


def test_holdout_not_used_to_pick():
    lock = load_lock()
    assert lock["score"]["window"] == "develop"
    assert "use holdout to pick" in " ".join(lock["do_not"])
    # continue_ok never sees holdout metrics
    ho_bad = {"regime_on_days": 200, "profit_factor": 5.0, "net_profit": 1e9}
    _ = ho_bad
    assert continue_ok(
        {"regime_on_days": 10, "profit_factor": 2.0, "net_profit": 1.0},
        {"net_profit": 0.0},
    ) is False


def test_costs_applied_slip_hurts_net():
    p = aligned_panel().iloc[:180].reset_index(drop=True)
    on = regime_falling(p["dfii10"].to_numpy(float), LOOKBACK)
    costs0 = load_research_costs()
    refuse_mutated_research_costs(costs0)
    costs_slip = dict(costs0)
    costs_slip["slippage_points"] = 10.0
    n0 = sum(t.pnl for t in simulate_regime(p, on, costs0))
    n1 = sum(t.pnl for t in simulate_regime(p, on, costs_slip))
    assert n1 < n0
