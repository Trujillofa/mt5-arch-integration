"""Freeze-only tests for joint_london_open_cosign_fade_flat (v2; no develop metrics)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from xau_charter_protocol import (  # noqa: E402
    gates_from_charter,
    validate_charter,
)

V1 = ROOT / "results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v1.json"
V2 = ROOT / "results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v2.json"
V1_SHA = "2d3fda48f5b43ce6620656844e42394fb5fb1b27737354d6f662285836673e81"
V2_SHA = "935534e262b986a6236e393a54147d66c66aa360f404df2ee4e330a73e5a5f18"
REG = ROOT / "results/xau_charter_disposition_registry.jsonl"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_v1_bytes_immutable_and_superseded_in_registry():
    assert V1.is_file()
    assert _sha(V1) == V1_SHA
    rows = [json.loads(ln) for ln in REG.read_text().splitlines() if ln.strip()]
    supers = [
        r
        for r in rows
        if r.get("charter_sha256") == V1_SHA and r.get("disposition") == "SUPERSEDED"
    ]
    assert supers, "v1 must be SUPERSEDED in append-only registry"
    assert any(
        "v2" in str(r.get("superseded_by", "")).lower()
        or "fade_flat_v2" in str(r.get("superseded_by", ""))
        for r in supers
    )


def test_v2_charter_validates_and_pins_sha():
    assert V2.is_file()
    assert _sha(V2) == V2_SHA
    ch = json.loads(V2.read_text())
    errs = validate_charter(ch)
    assert errs == [], errs
    assert ch["charter_version"] == 2
    assert ch["n_free_knobs"] == 0
    assert ch["harness"]["kind"] == "multi_instrument_joint_v1"
    assert ch["analysis_calendar"]["mode"] == "intersection_only"
    assert ch["null"]["base_seed"] == 20260813
    assert ch["null"]["shared_k_spec"]["trial_seed"]
    assert ch["gates"]["primary_n_passers"] == "soft"
    assert ch["gates"]["soft"]["n_trades_min"] == 60
    assert ch["gates"]["multi_instrument"]["n_passers_definition"] == "binary_joint_gate_success"
    assert ch["kill"]["on_screen_zero_passers"]["disposition"] == "SCREEN_FAIL"
    assert ch["kill"]["on_screen_zero_passers"]["screen_status"] == "ZERO_PRIMARY_PASSERS"
    # package pin
    pkg = ch["instrument"]["data_package"]
    assert pkg["package_id"] == "4f44b452081041f39fc24f03248b8ca8-ee2a993fb5b1befd"
    meta = ch["instrument"]["per_symbol_meta"]
    assert meta["XAUUSD"]["point_size"] == 0.01
    assert meta["EURUSD"]["point_size"] == 1e-5
    assert meta["GBPUSD"]["point_size"] == 1e-5


def test_v2_top_level_soft_visible_to_gates_from_charter():
    ch = json.loads(V2.read_text())
    g = gates_from_charter(ch)
    assert g["soft"]["profit_factor_min"] == 1.1
    assert g["soft"]["n_trades_min"] == 60
    assert g["primary_n_passers"] == "soft"
    # joint multi_instrument block still present for dedicated harness
    assert ch["gates"]["multi_instrument"]["require_all_symbols_soft_pass"] is True


def test_nested_joint_gates_without_top_level_soft_rejected():
    """v1-shaped nested gates must not validate (would silently fall back)."""
    ch = json.loads(V1.read_text())
    # Ensure nested shape
    assert "per_symbol" in ch["gates"] or "joint" in (ch.get("gates") or {})
    errs = validate_charter(ch)
    assert any("top-level gates.soft" in e or "multi_instrument" in e for e in errs), errs


def test_multi_instrument_without_dedicated_harness_rejected():
    ch = json.loads(V2.read_text())
    ch = json.loads(json.dumps(ch))  # deep copy
    ch["harness"] = {"kind": "single_frame"}
    errs = validate_charter(ch)
    assert any("multi_instrument_joint_v1" in e for e in errs), errs


def test_multi_instrument_without_intersection_calendar_rejected():
    ch = json.loads(json.dumps(json.loads(V2.read_text())))
    ch["analysis_calendar"] = {"mode": "full_per_symbol"}
    errs = validate_charter(ch)
    assert any("intersection_only" in e for e in errs), errs


def test_v2_execution_pins_entry_next_bar_and_exit_priority():
    ch = json.loads(V2.read_text())
    ec = ch["execution_contract"]
    assert "T*+1" in ec["entry_fill"] or "next joint bar" in ec["entry_fill"]
    assert ec["exit_start_bar"].startswith("T*+1")
    assert ec["exit_priority_per_subsequent_bar"] == ["SL", "TP", "time_flat"]
    assert ec["time_flat"]["if_no_hour_16_bar"]
    assert ec["sizing"]["lot_step"] == 0.01
    assert ch["fixed"]["costs"]["forbid_xau_point_on_fx"] is True
