"""FRED real-yield β: causality, as-of merge, lock, costs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from xau_exog_beta_realyield import (  # noqa: E402
    FAMILY_ID,
    FRED_DIR,
    HOLDOUT,
    WINDOW,
    aligned_panel,
    asof_on,
    continue_ok,
    load_lock,
    pred_at,
    simulate,
)
from xau_research_costs import load_research_costs, refuse_mutated_research_costs  # noqa: E402


def test_lock_new_family_not_reopen():
    lock = load_lock()
    assert lock["family_id"] == FAMILY_ID
    assert lock["frozen_before_metrics"] is True
    assert "exog_dxy_us10y_daily_tvbeta_xau_follow_flat_v1" in lock["not_a_reopen"]
    assert lock["drivers"]["primary"] == ["DFII10", "DTWEXBGS"]
    assert lock["beta"]["robustness_used_to_pick"] is False
    assert lock["score"]["window"] == "develop"
    assert lock["promote"] is False
    assert HOLDOUT.strftime("%Y-%m-%d") == "2026-01-01"
    assert lock["fred_auth"] == "env: FRED_API_KEY"


def test_fred_source_has_no_secret_material():
    src = (FRED_DIR / "SOURCE.json").read_text()
    assert "env: FRED_API_KEY" in src
    assert "e3a55" not in src
    body = json.loads(src)
    blob = json.dumps(body)
    assert "api_key=" not in blob.lower().replace("fred_api_key", "")


def test_asof_does_not_use_future_prints():
    gold = pd.Series(pd.to_datetime(["2024-01-06", "2024-01-07", "2024-01-08"], utc=True))
    fred = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-05", "2024-01-08"], utc=True).normalize(),
            "value": [1.0, 9.0],
        }
    )
    got = asof_on(gold, fred, "x")
    # 6th and 7th still see Jan 5 print; Jan 8 may see 9.0
    assert float(got.iloc[0]) == 1.0
    assert float(got.iloc[1]) == 1.0
    assert float(got.iloc[2]) == 9.0


def test_pred_causal_to_future_macro_and_gold():
    p = aligned_panel()
    i = 80
    a = pred_at(p, i, WINDOW)
    assert a is not None
    q = p.copy()
    q.loc[i + 1 :, "close"] *= 1.15
    q.loc[i + 1 :, "dfii10"] += 0.5
    q.loc[i + 1 :, "dtwex"] *= 1.05
    q["r_xau"] = np.log(q["close"] / q["close"].shift(1))
    q["d_real"] = q["dfii10"].diff()
    q["r_usd"] = np.log(q["dtwex"] / q["dtwex"].shift(1))
    b = pred_at(q, i, WINDOW)
    assert b == pytest.approx(a, rel=0, abs=1e-12)


def test_entry_is_next_bar():
    p = aligned_panel()
    costs = load_research_costs()
    refuse_mutated_research_costs(costs)
    trades = simulate(p, costs, window=WINDOW)
    assert trades
    for t in trades:
        assert t.entry_i >= 1
        assert t.exit_i >= t.entry_i


def test_continue_rule():
    assert continue_ok({"n": 40, "profit_factor": 1.2}, {"profit_factor": 1.0}) is True
    assert continue_ok({"n": 20, "profit_factor": 2.0}, {"profit_factor": 1.0}) is False
