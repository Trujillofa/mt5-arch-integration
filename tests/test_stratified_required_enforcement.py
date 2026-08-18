"""Machine enforcement of gates.stratified_required (Phase B protocol follow-up).

The v2..v4 freeze chain introduced gates.stratified_required by declaration
only: nothing in xau_charter_protocol.py read it, so a family module could
evaluate pooled soft and be fully charter-compliant. These tests pin the
validator-side enforcement added in this branch:

- optional-but-validated: no block, no provenance -> legacy pooled-only path
- provenance.derived_from_observed_result declared -> block is mandatory
- block present -> full structural validation (strata partition, definition,
  resolution order, enforcement locus, metric basis)
- gates_from_charter carries the block so runners cannot be ignorable by
  construction

No develop package, no screen, no null, no holdout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from xau_charter_protocol import (  # noqa: E402
    EXOGENOUS_NULL_IMPLEMENTATION_ID,
    EXOGENOUS_PREDICTOR_HARNESS_KIND,
    gates_from_charter,
    make_pass_fns,
    validate_exogenous_predictor_charter,
)

CHARTER_DIR = ROOT / "results/xau_charters"
V1 = CHARTER_DIR / "2026-08-15_exog_london_fx_cosign_xau_follow_flat_v1.json"
V2 = CHARTER_DIR / "2026-08-15_exog_london_fx_cosign_xau_follow_flat_v2.json"
V3 = CHARTER_DIR / "2026-08-15_exog_london_fx_cosign_xau_follow_flat_v3.json"
V4 = CHARTER_DIR / "2026-08-15_exog_london_fx_cosign_xau_follow_flat_v4.json"


def _minimal_exogenous_charter() -> dict:
    return {
        "family_id": "exog_synth_stratified_enforcement_test",
        "n_free_knobs": 0,
        "free_knobs": [],
        "frozen_at": "2026-08-18",
        "protocol_version": 2.2,
        "harness": {"kind": EXOGENOUS_PREDICTOR_HARNESS_KIND},
        "instrument": {
            "symbols": ["XAUUSD", "EURUSD"],
            "traded_symbols": ["XAUUSD"],
            "predictor_symbols": ["EURUSD"],
            "multi_symbol_in_scope": True,
            "per_symbol_meta": {
                "XAUUSD": {"point_size": 0.01, "contract_size": 100.0, "digits": 2},
                "EURUSD": {
                    "point_size": 1e-5,
                    "contract_size": 100_000.0,
                    "digits": 5,
                },
            },
            "data_package": {"package_id": "synth_not_scored"},
        },
        "analysis_calendar": {"mode": "intersection_only"},
        "gates": {
            "primary_n_passers": "soft",
            "soft": {
                "n_trades_min": 1,
                "profit_factor_min": 1.0,
                "net_profit_gt": -1e9,
                "max_drawdown_pct_max": 99.0,
            },
        },
        "null": {
            "method": EXOGENOUS_NULL_IMPLEMENTATION_ID,
            "implementation_id": EXOGENOUS_NULL_IMPLEMENTATION_ID,
            "n_trials": 999,
            "base_seed": 20260818,
        },
        "multiplicity": {
            "method": "finite_catalog_bonferroni_open_catalog",
            "K_prior": 8,
            "K": 9,
            "alpha_uncorrected": 0.05,
            "alpha_adjusted": 0.05 / 9,
            "prior_scored_family_ids": [
                "tod_london_ny_flat",
                "server_hour_window_flat",
                "early_server_range_break_flat",
                "day_open_reclaim_flat",
                "joint_london_open_cosign_fade_flat",
                "bb_rsi",
                "Donchian",
                "prior_day_high_break",
            ],
            "pass_status": "provisional_while_catalog_open",
            "paper_live_while_open": False,
            "revalidation_on_K_increase": True,
            "identity_excluded_from_null_trials": True,
        },
        "fixed": {
            "costs": {
                "commission_per_lot": 0.0,
                "slippage_points": 0.0,
                "spread_col": "spread",
                "account_type": "STANDARD_STP",
                "login": 1,
                "server": "synthetic",
                "cost_label": "synthetic",
                "costs_document_sha256": "a" * 64,
            },
            "H": 3,
            "entry": "next_bar_open",
            "same_day_hold": True,
        },
        "rule": {
            "intraday_flat": True,
            "exit": "sl_tp_time_h3",
            "hold_bars": 3,
            "entry": "next_bar_open",
            "same_day_hold": True,
        },
    }


def _full_stratified_block() -> dict:
    return {
        "strata": ["xau_cosign_at_tstar", "xau_not_cosign_at_tstar"],
        "rule": "soft primary must pass on the xau_not_cosign_at_tstar stratum",
        "scope": "traded_book_only",
        "rationale": "xau_cosign stratum is the sign-inverse of an observed result",
        "used_for": "freeze_gate_primary",
        "stratum_definition": {
            "variable": "sign(close_XAU(T*) - open_XAU(T*))",
            "s_reference": "s is the FX predictor cosign of the same event",
            "xau_cosign_at_tstar": "nonzero and sign equals s",
            "xau_not_cosign_at_tstar": "everything else including zero",
            "ternary_note": "zero assigned to not_cosign",
            "predicate_isolation": "Reporting label ONLY.",
        },
        "resolution_order": {
            "rule": "soft pass requires BOTH pooled AND fresh stratum",
            "on_stratum_fail": "SCREEN_FAIL; null not armed; r1 unburned",
            "on_both_pass": "proceed to sealed null",
            "note": "pooled-only is not a passer",
        },
        "enforced_by": {
            "locus": "scripts/xau_family_synth_stratified_test.py",
            "reason": "primary_n_passers protocol-locked to soft",
            "module_obligation": "evaluate both strata; fail closed",
            "report_obligation": "emit n/PF/NP/DD per stratum plus pooled",
        },
        "metric_basis": {
            "stratum_dd_method": "stratum_ordered_pnl_subsequence_rebased_to_start_balance",
            "pooled_dd_method": "full_mark_to_market_equity_path",
            "asymmetry_declared": "different bases, same threshold",
            "expected_bindingness": "stratum path shorter",
            "n_trades_min_applies_to_stratum": True,
            "n_trades_min_consequence": "fewer than n_trades_min -> stratum fail",
            "declared_before_scoring": "fixed before any screen",
        },
    }


def _with_block(**overrides: object) -> dict:
    ch = _minimal_exogenous_charter()
    block = _full_stratified_block()
    for k, v in overrides.items():
        block[k] = v
    ch["gates"]["stratified_required"] = block
    return ch


def _mutate(path: str, value: object) -> dict:
    ch = _with_block()
    node: dict = ch["gates"]["stratified_required"]
    parts = path.split(".")
    for p in parts[:-1]:
        node = node[p]
    if value is _DELETE:
        del node[parts[-1]]
    else:
        node[parts[-1]] = value
    return ch


class _Delete:
    pass


_DELETE = _Delete()


# ---------------------------------------------------------------------------
# Frozen charters on disk
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [V1, V3, V4])
def test_frozen_charters_still_validate(path: Path):
    charter = json.loads(path.read_text())
    assert validate_exogenous_predictor_charter(charter) == []


def test_superseded_v2_partial_block_now_rejected():
    """v2 introduced stratified_required without the v3 sub-blocks.

    Intended behavior change: the interim half-block is rejected so nothing
    can freeze against a stratified gate that is documentation-only. v2 is
    superseded and never scored; v1 (no block) and v3/v4 (complete blocks)
    remain valid.
    """
    charter = json.loads(V2.read_text())
    errs = validate_exogenous_predictor_charter(charter)
    assert any("stratum_definition" in e for e in errs)
    assert any("resolution_order" in e for e in errs)
    assert any("enforced_by" in e for e in errs)


# ---------------------------------------------------------------------------
# Legacy path + provenance cross-rule
# ---------------------------------------------------------------------------


def test_no_block_no_provenance_still_valid():
    assert validate_exogenous_predictor_charter(_minimal_exogenous_charter()) == []


def test_outcome_derived_provenance_requires_block():
    ch = _minimal_exogenous_charter()
    ch["provenance"] = {
        "derived_from_observed_result": "prior_family_v4 SCREEN_FAIL",
        "relation": "sign_inversion_on_overlapping_event_subset",
        "observed_artifact": "results/xau_runs/synth/",
    }
    errs = validate_exogenous_predictor_charter(ch)
    assert any(
        "stratified_required required" in e and "derived_from_observed_result" in e
        for e in errs
    )


def test_outcome_derived_with_complete_block_valid():
    ch = _with_block()
    ch["provenance"] = {
        "derived_from_observed_result": "prior_family_v4 SCREEN_FAIL",
        "relation": "sign_inversion_on_overlapping_event_subset",
        "observed_artifact": "results/xau_runs/synth/",
    }
    assert validate_exogenous_predictor_charter(ch) == []


def test_empty_provenance_string_does_not_trigger_requirement():
    ch = _minimal_exogenous_charter()
    ch["provenance"] = {"derived_from_observed_result": "   "}
    assert validate_exogenous_predictor_charter(ch) == []


# ---------------------------------------------------------------------------
# Structural validation of the block
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "value", "needle"),
    [
        ("strata", [], "strata"),
        ("strata", ["a"], "strata"),
        ("strata", ["a", "a"], "strata"),
        ("strata", ["a", ""], "strata"),
        ("strata", "not-a-list", "strata"),
        ("rule", "", "rule"),
        ("rule", _DELETE, "rule"),
        ("scope", 5, "scope"),
        ("rationale", "", "rationale"),
        ("used_for", "something_else", "used_for"),
        ("used_for", _DELETE, "used_for"),
        ("stratum_definition", _DELETE, "stratum_definition"),
        ("stratum_definition", "str", "stratum_definition"),
        ("stratum_definition.variable", _DELETE, "variable"),
        ("stratum_definition.predicate_isolation", "", "predicate_isolation"),
        ("stratum_definition.xau_not_cosign_at_tstar", _DELETE, "xau_not_cosign_at_tstar"),
        ("resolution_order", _DELETE, "resolution_order"),
        ("resolution_order.on_stratum_fail", "", "on_stratum_fail"),
        ("resolution_order.on_both_pass", _DELETE, "on_both_pass"),
        ("resolution_order.rule", 7, "resolution_order.rule"),
        ("enforced_by", _DELETE, "enforced_by"),
        ("enforced_by.locus", "not_a_module", "locus"),
        ("enforced_by.locus", 42, "locus"),
        ("enforced_by.module_obligation", "", "module_obligation"),
        ("enforced_by.report_obligation", _DELETE, "report_obligation"),
        ("metric_basis", "str", "metric_basis"),
        ("metric_basis.stratum_dd_method", "", "stratum_dd_method"),
        ("metric_basis.pooled_dd_method", _DELETE, "pooled_dd_method"),
        ("metric_basis.n_trades_min_applies_to_stratum", False, "n_trades_min_applies_to_stratum"),
        ("metric_basis.n_trades_min_applies_to_stratum", "yes", "n_trades_min_applies_to_stratum"),
    ],
)
def test_structural_mutations_fail_closed(path: str, value: object, needle: str):
    errs = validate_exogenous_predictor_charter(_mutate(path, value))
    assert any(needle in e for e in errs), f"no error mentions {needle!r}; got {errs}"


def test_complete_block_validates_clean():
    assert validate_exogenous_predictor_charter(_with_block()) == []


def test_block_without_metric_basis_still_valid():
    """metric_basis is v4+; a v3-shaped complete block must stay valid."""
    ch = _with_block()
    del ch["gates"]["stratified_required"]["metric_basis"]
    assert validate_exogenous_predictor_charter(ch) == []


def test_empty_block_rejected():
    ch = _minimal_exogenous_charter()
    ch["gates"]["stratified_required"] = {}
    errs = validate_exogenous_predictor_charter(ch)
    assert any("non-empty object" in e for e in errs)


# ---------------------------------------------------------------------------
# Resolver exposure
# ---------------------------------------------------------------------------


def test_resolver_carries_stratified_required_for_v4():
    charter = json.loads(V4.read_text())
    g = gates_from_charter(charter)
    sr = g["stratified_required"]
    assert sr["strata"] == ["xau_cosign_at_tstar", "xau_not_cosign_at_tstar"]
    assert g["primary_n_passers"] == "soft"


def test_resolver_omits_key_when_absent():
    g = gates_from_charter(_minimal_exogenous_charter())
    assert "stratified_required" not in g
    assert g["primary_n_passers"] == "soft"


def test_make_pass_fns_unchanged_shape_for_v4():
    charter = json.loads(V4.read_text())
    classic_pass, soft_fn, primary = make_pass_fns(charter)
    assert callable(classic_pass)
    assert callable(soft_fn)
    assert primary == "soft"
