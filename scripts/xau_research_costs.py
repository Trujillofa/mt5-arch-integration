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

# Keys accepted by backtest.simulate / lane simulators as cost kwargs.
SIM_COST_KEYS = (
    "spread_col",
    "point_size",
    "commission_per_lot",
    "slippage_points",
)


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
        "commission_per_lot": 3.0,
        "slippage_points": 0.0,
    }


def load_research_costs() -> dict[str, Any]:
    """Return cost kwargs for ``simulate`` / lane sims.

    Prefer ``results/xau_research_costs.json``; fall back to
    ``strategy_params.json`` costs. Only keys accepted by the simulators are
    returned so the dict can be splatted as ``**costs``.
    """
    raw = load_research_costs_full()
    out: dict[str, Any] = {k: raw[k] for k in SIM_COST_KEYS if k in raw}
    out.setdefault("point_size", 0.01)
    out.setdefault("commission_per_lot", 3.0)
    out.setdefault("slippage_points", 0.0)
    return out


if __name__ == "__main__":
    print(json.dumps(load_research_costs(), indent=2))
