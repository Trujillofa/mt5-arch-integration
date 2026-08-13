"""Freeze-only tests for joint_london_open_cosign_fade_flat (v3; no develop metrics)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from xau_charter_protocol import (  # noqa: E402
    gates_from_charter,
    multi_instrument_single_frame_refuse_message,
    validate_charter,
)

V1 = ROOT / "results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v1.json"
V2 = ROOT / "results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v2.json"
V3 = ROOT / "results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v3.json"
V1_SHA = "2d3fda48f5b43ce6620656844e42394fb5fb1b27737354d6f662285836673e81"
V2_SHA = "935534e262b986a6236e393a54147d66c66aa360f404df2ee4e330a73e5a5f18"
V3_SHA = "e88161be27ab09542e2c49b96da32781454436791666570bc6b06d3eecb51c65"
REG = ROOT / "results/xau_charter_disposition_registry.jsonl"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _load(p: Path) -> dict:
    return json.loads(p.read_text())


def _deepcopy(ch: dict) -> dict:
    return json.loads(json.dumps(ch))


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


def test_v2_bytes_immutable_and_superseded_in_registry():
    assert V2.is_file()
    assert _sha(V2) == V2_SHA
    rows = [json.loads(ln) for ln in REG.read_text().splitlines() if ln.strip()]
    supers = [
        r
        for r in rows
        if r.get("charter_sha256") == V2_SHA and r.get("disposition") == "SUPERSEDED"
    ]
    assert supers, "v2 must be SUPERSEDED in append-only registry"
    assert any(
        "fade_flat_v3" in str(r.get("superseded_by", ""))
        or str(r.get("superseded_by_sha256", "")) == V3_SHA
        for r in supers
    )
    # SUPERSEDED v2 is intentionally incomplete vs current multi-instrument contract
    # (missing PF zero-denominator pin); do not require validate_charter([]) for v2.


def test_v3_charter_validates_and_pins_sha():
    assert V3.is_file()
    assert _sha(V3) == V3_SHA
    ch = _load(V3)
    errs = validate_charter(ch)
    assert errs == [], errs
    assert ch["charter_version"] == 3
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
    pkg = ch["instrument"]["data_package"]
    assert pkg["package_id"] == "4f44b452081041f39fc24f03248b8ca8-ee2a993fb5b1befd"
    meta = ch["instrument"]["per_symbol_meta"]
    assert meta["XAUUSD"]["point_size"] == 0.01
    assert meta["XAUUSD"]["contract_size"] == 100.0
    assert meta["EURUSD"]["point_size"] == 1e-5
    assert meta["EURUSD"]["contract_size"] == 100000.0
    assert meta["GBPUSD"]["point_size"] == 1e-5
    assert meta["GBPUSD"]["contract_size"] == 100000.0


def test_v3_sizing_all_or_none_and_usd_units():
    ch = _load(V3)
    sz = ch["execution_contract"]["sizing"]
    formula = sz["formula"]
    assert "raw_lots = risk_cash_USD / (sl_distance_price * contract_size)" in formula
    assert "NEVER round up to lot_min" in formula or "never" in formula.lower()
    assert "cancel entire joint signal" in formula or "leg_invalid" in formula
    assert sz.get("forbid_point_value_per_lot_term") is True
    assert sz.get("forbid_double_multiply_contract") is True
    assert ch["fixed"]["account_currency"] == "USD"
    assert ch["fixed"]["pnl_units"] == "USD"
    assert ch["rule"]["all_or_none_basket"] is True
    assert ch["rule"]["partial_basket_forbidden"] is True
    assert "never_force_lot_min" in ch["fixed"]["lot_floor"]
    assert "force lots up to lot_min" in " ".join(ch["explicitly_forbidden"])


def test_v3_pf_zero_denominator_house_convention():
    ch = _load(V3)
    pzd = ch["joint_statistics"]["profit_factor_zero_denominator"]
    assert float(pzd["no_trades"]) == 0.0
    assert float(pzd["gross_loss_zero_and_gross_profit_positive"]) == 99.0
    assert "null_max_pf" in pzd["applies_to"]


def test_v3_top_level_soft_visible_to_gates_from_charter():
    ch = _load(V3)
    g = gates_from_charter(ch)
    assert g["soft"]["profit_factor_min"] == 1.1
    assert g["soft"]["n_trades_min"] == 60
    assert g["primary_n_passers"] == "soft"
    assert ch["gates"]["multi_instrument"]["require_all_symbols_soft_pass"] is True


def test_nested_joint_gates_without_top_level_soft_rejected():
    """v1-shaped nested gates must not validate (would silently fall back)."""
    ch = _load(V1)
    assert "per_symbol" in ch["gates"] or "joint" in (ch.get("gates") or {})
    errs = validate_charter(ch)
    assert any("top-level gates.soft" in e or "multi_instrument" in e for e in errs), errs


def test_multi_instrument_missing_soft_rejected():
    ch = _deepcopy(_load(V3))
    del ch["gates"]["soft"]
    errs = validate_charter(ch)
    assert any("gates.soft" in e for e in errs), errs


def test_multi_instrument_primary_classic_rejected():
    ch = _deepcopy(_load(V3))
    ch["gates"]["primary_n_passers"] = "classic"
    errs = validate_charter(ch)
    assert any("primary_n_passers" in e and "soft" in e for e in errs), errs


def test_multi_instrument_missing_multi_instrument_block_rejected():
    ch = _deepcopy(_load(V3))
    del ch["gates"]["multi_instrument"]
    errs = validate_charter(ch)
    assert any("gates.multi_instrument" in e for e in errs), errs


def test_multi_instrument_without_dedicated_harness_rejected():
    ch = _deepcopy(_load(V3))
    ch["harness"] = {"kind": "single_frame"}
    errs = validate_charter(ch)
    assert any("multi_instrument_joint_v1" in e for e in errs), errs


def test_multi_instrument_without_intersection_calendar_rejected():
    ch = _deepcopy(_load(V3))
    ch["analysis_calendar"] = {"mode": "full_per_symbol"}
    errs = validate_charter(ch)
    assert any("intersection_only" in e for e in errs), errs


def test_multi_instrument_missing_pf_zero_denom_rejected():
    ch = _deepcopy(_load(V3))
    del ch["joint_statistics"]["profit_factor_zero_denominator"]
    errs = validate_charter(ch)
    assert any("profit_factor_zero_denominator" in e for e in errs), errs


def test_v3_execution_pins_entry_next_bar_and_exit_priority():
    ch = _load(V3)
    ec = ch["execution_contract"]
    assert "T*+1" in ec["entry_fill"] or "next joint bar" in ec["entry_fill"]
    assert ec["exit_start_bar"].startswith("T*+1")
    assert ec["exit_priority_per_subsequent_bar"] == ["SL", "TP", "time_flat"]
    assert ec["time_flat"]["if_no_hour_16_bar"]
    assert ec["sizing"]["lot_step"] == 0.01
    assert ch["fixed"]["costs"]["forbid_xau_point_on_fx"] is True


def test_multi_instrument_refuse_helper_pure():
    """Fail-closed helper: no I/O; unit-testable without pandas/plugin."""
    ch = _load(V3)
    msg = multi_instrument_single_frame_refuse_message(ch)
    assert msg is not None
    assert "REFUSE_SINGLE_FRAME_RUNNER" in msg
    single = {
        "harness": {"kind": "single_frame"},
        "instrument": {"multi_symbol_in_scope": False, "symbols": ["XAUUSD"]},
    }
    assert multi_instrument_single_frame_refuse_message(single) is None


def _host_python_and_env() -> tuple[str, dict[str, str]]:
    """Research runners need host site-packages (pandas).

    Under ``uv run``, PATH puts the project venv first so bare ``python3`` has no
    pandas. Prefer absolute system interpreters and a PATH that does not lead with
    the project ``.venv``.
    """
    import os
    import shutil

    env = os.environ.copy()
    # Drop project venv from PATH so env python3 is host/system.
    path_parts = [
        p
        for p in env.get("PATH", "").split(":")
        if p and ".venv" not in p and "mt5-arch-integration" not in p
    ]
    # Keep /usr/bin early for system python3 + site-packages.
    env["PATH"] = ":".join(["/usr/bin", "/bin", *path_parts])
    # Avoid VIRTUAL_ENV steering shebangs / tooling.
    env.pop("VIRTUAL_ENV", None)

    candidates = [
        "/usr/bin/python3",
        shutil.which("python3", path=env["PATH"]) or "",
        "/home/yderf/bin/python3",
    ]
    for cand in candidates:
        if not cand or not Path(cand).is_file():
            continue
        try:
            r = subprocess.run(
                [cand, "-c", "import pandas"],
                env=env,
                capture_output=True,
                check=False,
            )
            if r.returncode == 0:
                return cand, env
        except OSError:
            continue
    # Fallback: pure-unit path still covered; subprocess may skip if no pandas.
    return "/usr/bin/python3", env


def test_null_maxstat_refuses_multi_instrument_charter_before_plugin():
    py, env = _host_python_and_env()
    proc = subprocess.run(
        [
            py,
            str(ROOT / "scripts/xau_family_null_maxstat.py"),
            "--charter",
            str(V3),
            "--family",
            "joint_london_open_cosign_fade_flat",
            "--quick",
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    blob = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode != 0, blob
    assert "REFUSE_SINGLE_FRAME_RUNNER" in blob, blob
    # Must not reach "Unknown family" / family plugin load
    assert "Unknown family" not in blob


def test_sealed_cycle_refuses_multi_instrument_before_fixtures():
    py, env = _host_python_and_env()
    proc = subprocess.run(
        [
            py,
            str(ROOT / "scripts/xau_sealed_family_cycle.py"),
            "--charter",
            str(V3),
            "--family",
            "joint_london_open_cosign_fade_flat",
            "--dry-fixture-only",
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    blob = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode != 0, blob
    assert "REFUSE_SINGLE_FRAME_RUNNER" in blob, blob
    assert "Synthetic fixture smoke" not in blob
    assert "ModuleNotFoundError" not in blob
