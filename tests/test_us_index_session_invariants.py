"""Holdout rank, frozen-book refuse, and v1 vs v4 split invariants."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from us_index_session_autoresearch import (  # noqa: E402
    LOCK_PATH,
    MIN_TRADES_DEVELOP,
    rank_develop_rows,
    score_row,
)
from us_index_session_autoresearch_v4 import split_v4  # noqa: E402
from us_index_session_backtest import (  # noqa: E402
    CostSpec,
    Trade,
    refuse_mutated_frozen_book,
    require_frozen_cost_book,
    slim_committed_report,
    split_by_holdout,
)


def _t(d: str, pnl: float = 1.0) -> Trade:
    return Trade(
        side=1,
        signal_i=0,
        fill_i=1,
        exit_i=2,
        entry=1,
        exit=2,
        reason="x",
        et_date=d,
        signal_time="",
        fill_time="",
        exit_time="",
        spread_pts=0,
        cost=0,
        pnl=pnl,
        mae=0,
        mfe=0,
    )


def _develop(pf: float = 1.4, expectancy: float = 1.0) -> dict:
    return {
        "trades": MIN_TRADES_DEVELOP,
        "net_pnl": 10.0,
        "profit_factor": pf,
        "expectancy": expectancy,
    }


def test_rank_ignores_swapped_holdout():
    develop = _develop()
    ho_good = {
        "trades": MIN_TRADES_DEVELOP,
        "net_pnl": 999.0,
        "profit_factor": 9.0,
        "expectancy": 50.0,
        "median_daily_pct": 0.5,
    }
    ho_bad = {
        "trades": MIN_TRADES_DEVELOP,
        "net_pnl": -999.0,
        "profit_factor": 0.1,
        "expectancy": -50.0,
        "median_daily_pct": -0.5,
    }
    a = {
        "params": {"id": "a"},
        "develop": develop,
        "holdout": ho_good,
        "develop_score": score_row(develop),
    }
    b = {
        "params": {"id": "b"},
        "develop": dict(develop),
        "holdout": ho_bad,
        "develop_score": score_row(develop),
    }
    order1 = [r["params"]["id"] for r in rank_develop_rows([a, b])]
    swapped = [
        {**a, "holdout": ho_bad},
        {**b, "holdout": ho_good},
    ]
    order2 = [r["params"]["id"] for r in rank_develop_rows(swapped)]
    assert order1 == order2 == ["a", "b"]


def test_better_develop_ranks_first_despite_fantasy_holdout():
    ho_fantasy = {
        "trades": MIN_TRADES_DEVELOP,
        "net_pnl": 999.0,
        "profit_factor": 9.0,
        "expectancy": 50.0,
        "median_daily_pct": 0.5,
    }
    ho_bad = {
        "trades": MIN_TRADES_DEVELOP,
        "net_pnl": -999.0,
        "profit_factor": 0.1,
        "expectancy": -50.0,
        "median_daily_pct": -0.5,
    }
    a_dev = _develop(2.0, 2.0)
    b_dev = _develop(1.05, 0.1)
    a = {
        "params": {"id": "a"},
        "develop": a_dev,
        "holdout": ho_bad,
        "develop_score": score_row(a_dev),
    }
    b = {
        "params": {"id": "b"},
        "develop": b_dev,
        "holdout": ho_fantasy,
        "develop_score": score_row(b_dev),
    }
    assert [r["params"]["id"] for r in rank_develop_rows([a, b])] == ["a", "b"]


def test_score_row_none_pf_pins_to_three():
    base = {
        "trades": MIN_TRADES_DEVELOP,
        "net_pnl": 10.0,
        "expectancy": 1.0,
    }
    assert score_row({**base, "profit_factor": None}) == score_row(
        {**base, "profit_factor": 3.0}
    )


def test_promote_true_is_refused():
    lock = json.loads(LOCK_PATH.read_text())
    lock["promote"] = True
    with pytest.raises(SystemExit, match="promote"):
        refuse_mutated_frozen_book(lock)


def test_slippage_not_10_is_refused():
    lock = json.loads(LOCK_PATH.read_text())
    lock["costs"] = dict(lock["costs"])
    lock["costs"]["slippage_points"] = 0.0
    with pytest.raises(SystemExit, match="slippage"):
        refuse_mutated_frozen_book(lock)
    with pytest.raises(SystemExit, match="frozen book"):
        require_frozen_cost_book(CostSpec(lots=1.0, slippage_points=0.0))


def test_lots_not_1_is_refused():
    lock = json.loads(LOCK_PATH.read_text())
    lock["lots"] = 5.0
    with pytest.raises(SystemExit, match="lots"):
        refuse_mutated_frozen_book(lock)
    with pytest.raises(SystemExit, match="frozen book"):
        require_frozen_cost_book(CostSpec(lots=2.0, slippage_points=10.0))


def test_honest_lock_is_accepted():
    lock = json.loads(LOCK_PATH.read_text())
    refuse_mutated_frozen_book(lock)
    require_frozen_cost_book(CostSpec(lots=1.0, slippage_points=10.0))


def test_june_v4_trade_is_in_neither_split():
    june = _t("2026-06-15")
    may = _t("2026-05-31")
    july = _t("2026-07-02")
    trades = [may, june, july]
    v1_pre, v1_post = split_by_holdout(trades)
    v4_pre, v4_post = split_v4(trades)
    assert [t.et_date for t in v4_pre] == ["2026-05-31"]
    assert [t.et_date for t in v4_post] == ["2026-07-02"]
    assert june not in v4_pre and june not in v4_post
    assert june in v1_post
    assert {t.et_date for t in v1_post} != {t.et_date for t in v4_post}


def test_slim_report_drops_trades_and_grids():
    slim = slim_committed_report(
        {
            "n_configs": 3,
            "best_develop": {"params": {"or_minutes": 15}},
            "trades": [{"pnl": 1.0}],
            "top10_develop": [{"index": 0}],
            "top20": [{"index": 1}],
            "top5_by_family": {"x": []},
        }
    )
    assert "trades" not in slim
    assert "top10_develop" not in slim
    assert "top20" not in slim
    assert "top5_by_family" not in slim
    assert slim["n_configs"] == 3
    assert slim["best_develop"]["params"]["or_minutes"] == 15
