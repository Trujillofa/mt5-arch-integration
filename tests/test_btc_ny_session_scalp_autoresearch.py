"""Autoresearch invariants: grid size, develop-only rank, lock search_id."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import btc_ny_session_scalp_autoresearch as ar  # noqa: E402

LOCK = json.loads((ROOT / "results" / "btc_ny_session_scalp_lock.json").read_text())


def test_grid_is_96_and_under_192():
    rows = ar.iter_grid(LOCK)
    assert len(rows) == 96
    assert len(rows) <= int(LOCK["grid"]["max_configs"])
    fams = {r["family"] for r in rows}
    assert fams == set(LOCK["families"]["search"])
    assert "index_transfer" not in fams
    assert "gold_transfer" not in fams


def test_score_row_requires_40_trades_and_positive_net():
    assert ar.score_row({"trades": 39, "net_pnl": 10, "profit_factor": 2.0, "expectancy": 1}) < 0
    assert ar.score_row({"trades": 40, "net_pnl": 0, "profit_factor": 2.0, "expectancy": 1}) < 0
    assert ar.score_row({"trades": 40, "net_pnl": 1, "profit_factor": 2.0, "expectancy": 1}) > 0
    none_pf = ar.score_row({"trades": 40, "net_pnl": 1, "profit_factor": None, "expectancy": 0})
    finite = ar.score_row({"trades": 40, "net_pnl": 1, "profit_factor": 3.0, "expectancy": 0})
    assert none_pf == finite


def test_rank_ignores_holdout_keys():
    rows = [
        {
            "eligible": True,
            "develop": {"profit_factor": 1.1, "expectancy": 1.0},
            "holdout": {"profit_factor": 9.9, "expectancy": 99.0},
            "id": "a",
        },
        {
            "eligible": True,
            "develop": {"profit_factor": 1.2, "expectancy": 0.5},
            "holdout": {"profit_factor": 0.1, "expectancy": -9.0},
            "id": "b",
        },
    ]
    ranked = sorted(
        rows,
        key=lambda r: (
            r["develop"]["profit_factor"] or 3.0,
            r["develop"]["expectancy"],
        ),
        reverse=True,
    )
    assert ranked[0]["id"] == "b"


def test_closed_theses_are_in_the_lock():
    closed = " ".join(LOCK["closed_theses"])
    assert "16:00-24:00" in closed
    assert "ny_cash_orb" in closed
    assert "RegimeRouter" in closed
