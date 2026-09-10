"""GARCH size overlay: causality, frozen host trades, costs, holdout-not-pick."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from xau_garch_size import (  # noqa: E402
    HOLDOUT_START,
    LOCK_PATH,
    OVERLAY_ID,
    HostTrade,
    collect_host_trades,
    fit_garch11,
    garch11_filter,
    garch_beats_atr,
    load_host_params,
    load_lock,
    log_returns,
    pick_winner,
    replay_sized,
    walkforward_sigma,
)
from xau_research_costs import load_research_costs, refuse_mutated_research_costs  # noqa: E402

import backtest as bt  # noqa: E402


def test_lock_frozen_before_metrics_and_not_a_family_search():
    lock = load_lock()
    assert lock["overlay_id"] == OVERLAY_ID
    assert lock["frozen_before_metrics"] is True
    assert lock["kind"] == "size_overlay"
    assert lock["not_a_search_family"] is True
    assert lock["promote"] is False
    assert lock["live_go"] is False
    assert lock["model"]["name"] == "GARCH(1,1)"
    assert lock["model"]["egarch_searched"] is False
    assert lock["score"]["window"] == "develop_slice_to_window"
    assert "holdout" not in lock["score"]["window"]
    assert str(HOLDOUT_START.date()) == "2026-01-01"


def test_garch_persistence_and_filter_positive():
    rng = np.random.default_rng(7)
    r = rng.normal(0.0, 0.01, size=800)
    omega, alpha, beta = fit_garch11(r)
    assert alpha > 0 and beta > 0
    assert alpha + beta < 0.999
    var = garch11_filter(r, omega, alpha, beta, float(np.var(r)))
    assert np.all(var > 0)


def test_walkforward_sigma_causal_to_future_returns():
    rng = np.random.default_rng(3)
    close = 2000.0 * np.exp(np.cumsum(rng.normal(0, 0.002, size=700)))
    close = np.maximum(close, 1.0)
    sig = walkforward_sigma(close, min_lookback=200, recal_every=80)
    t = 400
    assert np.isfinite(sig[t])
    close2 = close.copy()
    close2[t + 1 :] *= 1.25
    sig2 = walkforward_sigma(close2, min_lookback=200, recal_every=80)
    assert sig2[t] == pytest.approx(sig[t], rel=0, abs=1e-12)


def test_pick_winner_uses_develop_only():
    rows = {
        "atr_lot_host": {"profit_factor": 1.50, "net_profit": 100.0},
        "garch11_invvol": {"profit_factor": 1.20, "net_profit": 9999.0},
        "constant_lot_0.10": {"profit_factor": 1.40, "net_profit": 50.0},
    }
    assert pick_winner(rows) == "atr_lot_host"
    assert garch_beats_atr(rows["garch11_invvol"], rows["atr_lot_host"]) is False
    assert garch_beats_atr({"profit_factor": 1.51, "net_profit": 1.0}, rows["atr_lot_host"]) is True


def test_host_trades_match_saved_window_count():
    host = load_host_params()
    costs = load_research_costs()
    refuse_mutated_research_costs(costs)
    d = bt.indicators(bt.slice_to_window(bt.load_h1(), host["window"]))
    trades = collect_host_trades(d, host["params"], costs)
    assert len(trades) == 42
    assert all(t.side in (-1, 1) for t in trades)
    times = [t.time for t in trades]
    assert times == sorted(times)
    # Host window ends 2025-12-31 — no holdout entries in the slice.
    assert all(t.utc_date < "2026-01-01" for t in trades)


def test_replay_applies_costs():
    d = _tiny_frame()
    trades = [
        HostTrade(
            entry_i=1,
            exit_i=2,
            side=1,
            entry=2000.0,
            exit=2010.0,
            atr=5.0,
            spread_pts=20.0,
            time="2024-06-01T12:00:00+00:00",
            utc_date="2024-06-01",
        )
    ]
    from xau_garch_size import atr_lots

    free = {"spread_col": "spread", "point_size": 0.01, "commission_per_lot": 0.0, "slippage_points": 0.0}
    taxed = dict(free)
    taxed["slippage_points"] = 10.0
    m0 = replay_sized(trades, d, free, sl_atr=1.0, lot_fn=atr_lots)
    m1 = replay_sized(trades, d, taxed, sl_atr=1.0, lot_fn=atr_lots)
    assert m0["n_taken"] == m1["n_taken"] == 1
    assert m1["net_profit"] < m0["net_profit"]


def test_log_returns_length():
    c = np.array([100.0, 101.0, 100.0])
    r = log_returns(c)
    assert r.shape == (3,)
    assert np.isnan(r[0])
    assert r[1] == pytest.approx(np.log(1.01))


def _tiny_frame():
    import pandas as pd

    n = 5
    return pd.DataFrame(
        {
            "time": pd.date_range("2024-06-01", periods=n, freq="h", tz="UTC"),
            "close": np.full(n, 2000.0),
            "high": np.full(n, 2001.0),
            "low": np.full(n, 1999.0),
            "spread": np.full(n, 20.0),
        }
    )


def test_lock_path_is_the_pre_registered_file():
    assert LOCK_PATH.is_file()
    assert LOCK_PATH.name == "lock.json"
    raw = json.loads(LOCK_PATH.read_text())
    assert raw["frozen_before_metrics"] is True
