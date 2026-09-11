"""btc_trend_pullback screen — grid cardinality, rank blindness, lock freeze."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import btc_trend_pullback_autoresearch as ar  # noqa: E402
import lane_kit as lk  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOCK = json.loads((ROOT / "results" / "btc_trend_pullback_lock.json").read_text())


def test_search_id_and_grid_is_192():
    assert LOCK["search_id"] == ar.SEARCH_ID
    rows = lk.iter_product_grid(LOCK)
    assert len(rows) == 192
    lk.assert_cardinality(rows, LOCK)
    fams = {r["family"] for r in rows}
    assert fams == set(LOCK["families"]["search"])


def test_grid_ceiling_refuses_widening():
    lock = json.loads(json.dumps(LOCK))
    lock["grid"]["sl_atr"] = [1.0, 1.5, 2.0]
    with pytest.raises(SystemExit, match="exceeds max_configs"):
        lk.iter_product_grid(lock)


def test_score_gates_match_lock():
    m = {"trades": 40, "net_pnl": 1.0, "profit_factor": 1.5, "expectancy": 0.1}
    assert lk.score_pf_expectancy(m, min_trades=ar.MIN_TRADES) == pytest.approx(1500.1)
    m["trades"] = 39
    assert lk.score_pf_expectancy(m, min_trades=ar.MIN_TRADES) == -1e9


def test_rank_ignores_holdout_keys():
    rows = [
        {
            "develop": {"profit_factor": 1.1, "expectancy": 0.1},
            "holdout": {"profit_factor": 99.0, "expectancy": 10.0},
            "id": "a",
        },
        {
            "develop": {"profit_factor": 1.5, "expectancy": 0.1},
            "holdout": {"profit_factor": 0.1, "expectancy": -10.0},
            "id": "b",
        },
    ]
    order = [r["id"] for r in lk.rank_pf_expectancy(rows)]
    assert order == ["b", "a"]


def test_closed_theses_in_lock():
    closed = LOCK["closed_theses"]
    assert any("RegimeRouter" in t for t in closed)
    assert any("cash-open" in t or "ny_cash_orb" in t for t in closed)
    assert any("session boxes" in t for t in closed)


def test_require_locked_book_refuses_mutated_slip():
    costs = lk.costs_from_lock(LOCK)
    lk.require_locked_book(LOCK, costs)
    bad = json.loads(json.dumps(LOCK))
    bad["costs"]["slippage_points"] = 5.0
    with pytest.raises(SystemExit, match="slippage"):
        lk.require_locked_book(bad, costs)
