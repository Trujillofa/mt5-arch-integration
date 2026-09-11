"""Index-session scan: frictionless refuse + holdout ignored by ranker."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from index_session_scan import (  # noqa: E402
    LOCK_PATH,
    SEARCH_ID,
    load_lock,
    pin_pf,
    rank_scan_rows,
    refuse_frictionless_lock,
    session_fit,
    trade_candidates,
)
from us_index_session_backtest import (  # noqa: E402
    HOLDOUT_START,
    CostSpec,
    refuse_mutated_frozen_book,
    require_frozen_cost_book,
)


def _row(rid: str, pf: float, n: int = 40, dd: float = -10.0, fit: str = "us_cash_0930"):
    return {
        "id": rid,
        "session_fit": fit,
        "develop": {
            "trades": n,
            "profit_factor": pf,
            "max_dd": dd,
            "expectancy": pf,
            "net_pnl": 1.0,
        },
        "holdout": {
            "trades": n,
            "profit_factor": 9.0,
            "max_dd": 0.0,
            "expectancy": 99.0,
            "net_pnl": 999.0,
        },
    }


def test_lock_is_pre_registered_and_not_frictionless():
    lock = json.loads(LOCK_PATH.read_text())
    assert lock["search_id"] == SEARCH_ID
    assert lock["holdout_start"] == HOLDOUT_START.isoformat() == "2026-06-01"
    assert lock["n_floor"] == 40
    assert lock["promote"] is False
    assert lock["live_go"] is False
    assert lock["costs"]["frictionless"] is False
    assert float(lock["costs"]["slippage_points"]) == 10.0
    assert float(lock["costs"]["assumed_spread_when_unmeasured"]) == 60.0
    load_lock(LOCK_PATH)


def test_frictionless_lock_is_refused():
    lock = json.loads(LOCK_PATH.read_text())
    bad = deepcopy(lock)
    bad["costs"] = dict(bad["costs"])
    bad["costs"]["frictionless"] = True
    with pytest.raises(SystemExit, match="frictionless"):
        refuse_frictionless_lock(bad)
    slip0 = deepcopy(lock)
    slip0["costs"] = dict(slip0["costs"])
    slip0["costs"]["slippage_points"] = 0.0
    with pytest.raises(SystemExit, match="frictionless"):
        refuse_frictionless_lock(slip0)
    with pytest.raises(SystemExit, match="slippage|frozen book"):
        refuse_mutated_frozen_book(slip0)
    with pytest.raises(SystemExit, match="frozen book"):
        require_frozen_cost_book(CostSpec(lots=1.0, slippage_points=0.0))
    assumed0 = deepcopy(lock)
    assumed0["costs"] = dict(assumed0["costs"])
    assumed0["costs"]["assumed_spread_when_unmeasured"] = 0.0
    with pytest.raises(SystemExit, match="frictionless"):
        refuse_frictionless_lock(assumed0)


def test_rank_ignores_holdout_and_eval_slice():
    lock = json.loads(LOCK_PATH.read_text())
    a = _row("a", 1.4, dd=-20.0)
    b = _row("b", 1.1, dd=-5.0)
    a["holdout"]["profit_factor"] = 0.1
    b["holdout"]["profit_factor"] = 9.0
    order1 = [r["id"] for r in rank_scan_rows([a, b], lock)]
    swapped = [deepcopy(a), deepcopy(b)]
    swapped[0]["holdout"], swapped[1]["holdout"] = (
        swapped[1]["holdout"],
        swapped[0]["holdout"],
    )
    order2 = [r["id"] for r in rank_scan_rows(swapped, lock)]
    assert order1 == order2 == ["a", "b"]


def test_n_floor_drops_short_develop():
    lock = json.loads(LOCK_PATH.read_text())
    short = _row("short", 2.5, n=10)
    ok = _row("ok", 1.05, n=40)
    ranked = rank_scan_rows([short, ok], lock)
    assert [r["id"] for r in ranked] == ["ok"]


def test_wrong_clock_is_not_a_trade_candidate():
    lock = json.loads(LOCK_PATH.read_text())
    ger = _row("ger", 2.0, fit="other_cash_open")
    us = _row("us", 1.1, fit="us_cash_0930")
    ranked = rank_scan_rows([ger, us], lock)
    assert ranked[0]["id"] == "ger"
    cands = trade_candidates(ranked)
    assert [r["id"] for r in cands] == ["us"]


def test_session_fit_us_cash_vs_other():
    assert session_fit("US500")[0] == "us_cash_0930"
    assert session_fit("US2000")[0] == "us_cash_0930"
    assert session_fit("DJ30.r")[0] == "us_cash_0930"
    assert session_fit("GER40")[0] == "other_cash_open"
    assert session_fit("UK100")[0] == "other_cash_open"
    assert session_fit("JP225")[0] == "other_cash_open"


def test_pin_pf_matches_stack():
    assert pin_pf(None) == 3.0
    assert pin_pf(1.2) == 1.2
