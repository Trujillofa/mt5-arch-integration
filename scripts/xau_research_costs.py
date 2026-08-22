#!/usr/bin/env python3
"""Research cost defaults for offline XAU sims.

Source of truth: ``results/xau_research_costs.json`` (Vantage account-type
commission + measured spread column). Falls back to ``strategy_params.json``
``costs`` when the research file is missing.

SAFETY: offline only — no live orders.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESEARCH_COSTS_PATH = ROOT / "results" / "xau_research_costs.json"
PARAMS_PATH = ROOT / "strategy_params.json"

# Re-export path for provenance hashing in harnesses.
__all__ = [
    "RESEARCH_COSTS_PATH",
    "PARAMS_PATH",
    "SIM_COST_KEYS",
    "load_research_costs",
    "load_research_costs_full",
    "refuse_mutated_research_costs",
    "FROZEN_POINT_SIZE",
    "FROZEN_COMMISSION_PER_LOT",
    "FROZEN_SLIPPAGE_POINTS",
    "FROZEN_SPREAD_COL",
]

# Keys accepted by backtest.simulate / lane simulators as cost kwargs.
SIM_COST_KEYS = (
    "spread_col",
    "point_size",
    "commission_per_lot",
    "slippage_points",
)

# Locked Standard STP book. slip=0 is UNMEASURED, not a claim of zero slip.
FROZEN_SPREAD_COL = "spread"
FROZEN_POINT_SIZE = 0.01
FROZEN_COMMISSION_PER_LOT = 0.0
FROZEN_SLIPPAGE_POINTS = 0.0


def load_research_costs_full() -> dict[str, Any]:
    """Load the full research-costs document (or a minimal fallback)."""
    if RESEARCH_COSTS_PATH.is_file():
        return json.loads(RESEARCH_COSTS_PATH.read_text())
    if PARAMS_PATH.is_file():
        saved = json.loads(PARAMS_PATH.read_text())
        costs = dict(saved.get("costs") or {})
        costs.setdefault("point_size", 0.01)
        costs.setdefault("commission_per_lot", 0.0)
        costs.setdefault("slippage_points", 0.0)
        return costs
    return {
        "spread_col": "spread",
        "point_size": 0.01,
        "commission_per_lot": 0.0,  # Standard STP default; ECN types set commission > 0
        "slippage_points": 0.0,
    }


def load_research_costs() -> dict[str, Any]:
    """Return cost kwargs for ``simulate`` / lane sims.

    Prefer ``results/xau_research_costs.json``; fall back to
    ``strategy_params.json`` costs. Only keys accepted by the simulators are
    returned so the dict can be splatted as ``**costs``.

    Live research account (Vantage 27496181) is **Standard STP**: commission 0;
    cost is measured spread. RAW/PRO ECN commission figures are stress alternatives.
    """
    raw = load_research_costs_full()
    out: dict[str, Any] = {k: raw[k] for k in SIM_COST_KEYS if k in raw}
    out.setdefault("point_size", 0.01)
    out.setdefault("commission_per_lot", 0.0)
    out.setdefault("slippage_points", 0.0)
    return out


def refuse_mutated_research_costs(costs: dict[str, Any]) -> None:
    """Refuse a book that is not the locked Standard STP / UNMEASURED-slip book.

    ``slippage_points=0`` is explicitly unmeasured, not a claim of zero slip.
    Sensitivity belongs in a dedicated script or ``--allow-cost-override``.
    """
    slip = costs.get("slippage_points")
    if slip is not None and float(slip) != FROZEN_SLIPPAGE_POINTS:
        raise SystemExit(
            "research cost book slippage_points must stay 0.0 "
            "(UNMEASURED, not a claim of zero slip)"
        )
    comm = costs.get("commission_per_lot")
    if comm is not None and float(comm) != FROZEN_COMMISSION_PER_LOT:
        raise SystemExit(
            "research cost book commission_per_lot must stay 0.0 (Standard STP)"
        )
    pt = costs.get("point_size")
    if pt is not None and abs(float(pt) - FROZEN_POINT_SIZE) > 1e-12:
        raise SystemExit(
            "research cost book point_size must stay 0.01 (MT5 point, not pip)"
        )
    col = costs.get("spread_col")
    if col is not None and str(col) != FROZEN_SPREAD_COL:
        raise SystemExit("research cost book spread_col must stay 'spread'")


if __name__ == "__main__":
    print(json.dumps(load_research_costs(), indent=2))
