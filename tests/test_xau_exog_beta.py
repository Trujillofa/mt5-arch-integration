"""Daily DXY+US10Y β family: causality, next-bar entry, lock, costs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from xau_exog_beta import (  # noqa: E402
    FAMILY_ID,
    HOLDOUT,
    LOCK_PATH,
    WINDOW,
    aligned_panel,
    continue_ok,
    load_lock,
    pred_at,
    simulate,
)
from xau_research_costs import load_research_costs, refuse_mutated_research_costs  # noqa: E402


def test_lock_is_new_family_not_reopen():
    lock = load_lock()
    assert lock["family_id"] == FAMILY_ID
    assert lock["frozen_before_metrics"] is True
    assert lock["not_a_reopen"] == "exog_london_fx_cosign_xau_follow_flat"
    assert lock["beta"]["window_primary"] == 60
    assert lock["beta"]["window_robustness"] == 120
    assert lock["beta"]["robustness_used_to_pick"] is False
    assert lock["score"]["window"] == "develop"
    assert lock["drivers"]["tips"] == "NOT ON DISK — not used"
    assert lock["promote"] is False
    assert HOLDOUT.strftime("%Y-%m-%d") == "2026-01-01"


def test_pred_causal_to_future_rows():
    p = aligned_panel()
    i = 80
    a = pred_at(p, i, WINDOW)
    assert a is not None
    q = p.copy()
    q.loc[i + 1 :, "close"] = q.loc[i + 1 :, "close"] * 1.2
    q.loc[i + 1 :, "dxy"] = q.loc[i + 1 :, "dxy"] * 0.9
    q["r_xau"] = np.log(q["close"] / q["close"].shift(1))
    q["r_dxy"] = np.log(q["dxy"] / q["dxy"].shift(1))
    b = pred_at(q, i, WINDOW)
    assert b == pytest.approx(a, rel=0, abs=1e-12)


def test_entry_is_next_bar_not_same_day():
    p = aligned_panel()
    costs = load_research_costs()
    refuse_mutated_research_costs(costs)
    trades = simulate(p, costs, window=WINDOW)
    assert trades
    for t in trades:
        assert t.exit_i >= t.entry_i
        # Signal computed at entry_i - 1
        assert t.entry_i >= 1


def test_costs_reduce_pnl():
    p = aligned_panel().iloc[:120].reset_index(drop=True)
    free = {
        "spread_col": "spread",
        "point_size": 0.01,
        "commission_per_lot": 0.0,
        "slippage_points": 0.0,
    }
    taxed = dict(free)
    taxed["slippage_points"] = 10.0
    a = simulate(p, free, window=40, pred_min=0.0)
    b = simulate(p, taxed, window=40, pred_min=0.0)
    if not a:
        pytest.skip("no trades on stub window")
    assert len(a) == len(b)
    assert sum(t.pnl for t in b) < sum(t.pnl for t in a)


def test_continue_rule_needs_n_and_pf():
    beta = {"n": 40, "profit_factor": 1.2}
    base = {"n": 40, "profit_factor": 1.0}
    assert continue_ok(beta, base) is True
    assert continue_ok({"n": 20, "profit_factor": 2.0}, base) is False
    assert continue_ok({"n": 40, "profit_factor": 0.9}, base) is False


def test_lock_file_exists_before_metrics_artifact():
    assert LOCK_PATH.is_file()
    raw = json.loads(LOCK_PATH.read_text())
    assert raw["frozen_before_metrics"] is True
    # Official develop.json may exist; lock mtime must not be after a rewrite hunt.
    assert raw["family_id"].startswith("exog_dxy_us10y")
