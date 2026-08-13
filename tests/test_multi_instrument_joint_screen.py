"""Unit tests for dedicated multi-instrument joint screen harness.

Synthetic frames only for scoring paths — does **not** load develop package.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import xau_family_joint_london_open_cosign_fade_flat as fam  # noqa: E402
import xau_multi_instrument_joint_screen as screen  # noqa: E402
from xau_charter_protocol import load_charter  # noqa: E402
from xau_sealed_family_cycle import parse_harness_report_for_accounting  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
from test_joint_london_open_cosign_fade_flat import (  # noqa: E402
    _merge_warmup_signal,
    _signal_day_frames,
)

CHARTER = ROOT / "results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v4.json"
V4_SHA = "e29b26931b93443d7c903ddd034dfcabbeffde8761c41ad77b70e8292700b994"


def _aligned_zero_spread():
    aligned = _merge_warmup_signal(_signal_day_frames("2024-01-05", cosign="up"))
    for s in fam.SYMBOLS:
        aligned[s] = aligned[s].copy()
        aligned[s]["spread"] = 0.0
    return aligned


def test_dry_main_exits_zero_without_package_load(capsys):
    rc = screen.main(["--charter", str(CHARTER)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY PLAN" in out
    assert "develop screen not executed" in out.lower() or "not executed" in out


def test_assert_multi_instrument_refuses_wrong_family():
    ch = load_charter(CHARTER)
    ch = json.loads(json.dumps(ch))
    ch["family_id"] = "day_open_reclaim_flat"
    with pytest.raises(SystemExit, match="family_id"):
        screen.assert_multi_instrument_charter(ch)


def test_synthetic_flag_combos_refused():
    with pytest.raises(SystemExit, match="REFUSE"):
        screen.main(
            [
                "--charter",
                str(CHARTER),
                "--frames-parquet-dir",
                "/tmp/nope",
                "--write-registry",
            ]
        )
    with pytest.raises(SystemExit, match="REFUSE"):
        screen.main(
            [
                "--charter",
                str(CHARTER),
                "--frames-parquet-dir",
                "/tmp/nope",
                "--execute-develop-screen",
            ]
        )
    with pytest.raises(SystemExit, match="REFUSE"):
        screen.main(
            [
                "--charter",
                str(CHARTER),
                "--write-registry",
            ]
        )


def test_append_disposition_refuses_non_dispositional(tmp_path: Path):
    ch = load_charter(CHARTER)
    costs = screen.assert_costs_match_charter(ch)
    report = screen.run_joint_screen(
        _aligned_zero_spread(),
        ch,
        costs=costs,
        already_aligned=True,
        dispositional=False,
        non_dispositional_reason="unit_test",
    )
    with pytest.raises(SystemExit, match="REFUSE_REGISTRY_WRITE"):
        screen.append_disposition_registry(
            CHARTER, report, screen_artifact=str(tmp_path / "x.json")
        )


def test_run_joint_screen_canonical_screen_fail_schema():
    ch = load_charter(CHARTER)
    costs = screen.assert_costs_match_charter(ch)
    report = screen.run_joint_screen(
        _aligned_zero_spread(),
        ch,
        costs=costs,
        already_aligned=True,
        dispositional=True,
    )
    assert report["dispositional"] is True
    assert report["verdict"]["disposition"] == "SCREEN_FAIL"
    assert report["verdict"]["screen_status"] == "ZERO_PRIMARY_PASSERS"
    assert report["screen"]["zero_primary_passers"] is True
    assert report["real"]["n_passers"] == 0
    assert report["real"]["n_passers_classic_status"] == "not_evaluated"
    assert report["real"]["n_passers_classic"] is None
    assert report["null"]["n_null_executed"] == 0
    assert report["null"]["n_trials"] == 0
    assert report["null"]["trials"] == []
    assert report["null"]["skipped_reason"] == "ZERO_PRIMARY_PASSERS"
    assert report["null"]["base_seed"] == 20260813
    assert report["attempt_accounting"]["attempt_type"] == "DETERMINISTIC_SCREEN"
    assert report["attempt_accounting"]["r1_burned"] is False
    assert report["attempt_accounting"]["n_null_executed"] == 0
    assert report["real"]["n_trades"] == 3


def test_canonical_report_parses_ok_unburned(tmp_path: Path):
    """parse_harness_report_for_accounting → OK, r1_burned=false, exit 0."""
    ch = load_charter(CHARTER)
    costs = screen.assert_costs_match_charter(ch)
    report = screen.run_joint_screen(
        _aligned_zero_spread(),
        ch,
        costs=costs,
        already_aligned=True,
        dispositional=True,
    )
    out = tmp_path / "run"
    out.mkdir()
    path = screen.write_screen_report(report, out)
    # null_maxstat.json is the parser target
    result = out / "null_maxstat.json"
    assert result.is_file()
    assert path.name == "joint_screen.json"
    n_planned = int(report["null"]["n_null_planned"])
    acct = parse_harness_report_for_accounting(
        result_json=result,
        n_null_planned=n_planned,
        exit_code=0,
        expected_null_seed=int(report["null"]["base_seed"]),
    )
    assert acct["execution_state"] == "OK"
    assert acct["disposition"] == "SCREEN_FAIL"
    assert acct["r1_burned"] is False
    assert acct["n_null_executed"] == 0
    assert acct["attempt_type"] == "DETERMINISTIC_SCREEN"


def test_exit_code_two_would_fail_parser(tmp_path: Path):
    """Document that exit 2 is incomplete for fail-closed parser (main returns 0)."""
    ch = load_charter(CHARTER)
    costs = screen.assert_costs_match_charter(ch)
    report = screen.run_joint_screen(
        _aligned_zero_spread(),
        ch,
        costs=costs,
        already_aligned=True,
        dispositional=True,
    )
    out = tmp_path / "run2"
    out.mkdir()
    screen.write_screen_report(report, out)
    acct = parse_harness_report_for_accounting(
        result_json=out / "null_maxstat.json",
        n_null_planned=int(report["null"]["n_null_planned"]),
        exit_code=2,
        expected_null_seed=int(report["null"]["base_seed"]),
    )
    assert acct["execution_state"] == "UNKNOWN"
    assert acct["r1_burned"] is True


def test_cost_mismatch_refused():
    ch = load_charter(CHARTER)
    with pytest.raises(SystemExit, match="cost mismatch|identity"):
        screen.assert_costs_match_charter(
            ch,
            loaded={
                "account_type": "STANDARD_STP",
                "login": 27496181,
                "server": "VantageMarkets-Live 5",
                "commission_per_lot": 7.0,
                "slippage_points": 3.0,
                "spread_col": "spread",
                "point_size": 0.01,
            },
        )


def test_cost_identity_missing_refused():
    ch = load_charter(CHARTER)
    with pytest.raises(SystemExit, match="identity|missing"):
        screen.assert_costs_match_charter(
            ch,
            loaded={
                "commission_per_lot": 0.0,
                "slippage_points": 0.0,
                "spread_col": "spread",
                "point_size": 0.01,
            },
        )


def test_cost_identity_wrong_login_refused():
    ch = load_charter(CHARTER)
    with pytest.raises(SystemExit, match="identity mismatch login"):
        screen.assert_costs_match_charter(
            ch,
            loaded={
                "account_type": "STANDARD_STP",
                "login": 999,
                "server": "VantageMarkets-Live 5",
                "commission_per_lot": 0.0,
                "slippage_points": 0.0,
                "spread_col": "spread",
                "point_size": 0.01,
            },
        )


def test_positive_passer_report_parses_ok(tmp_path: Path):
    """Both screen outcomes: force n_passers=1 and prove parser OK unburned."""
    ch = load_charter(CHARTER)
    costs = screen.assert_costs_match_charter(ch)
    report = screen.run_joint_screen(
        _aligned_zero_spread(),
        ch,
        costs=costs,
        already_aligned=True,
        dispositional=True,
    )
    # Synthetically force the positive-screen shape (binary joint sole config)
    report["real"]["n_passers"] = 1
    report["real"]["primary_passers"] = 1
    report["real"]["n_passers_soft"] = 1
    report["verdict"]["disposition"] = "SCREEN_PASS_PENDING_NULL_REVIEW"
    report["verdict"]["screen_status"] = "PASSERS_GE_1_PENDING_NULL_REVIEW"
    report["verdict"]["fail_n_passers"] = False
    report["screen"]["zero_primary_passers"] = False
    report["null"]["skipped_reason"] = "SCREEN_ONLY"
    report["disposition"] = "SCREEN_PASS_PENDING_NULL_REVIEW"
    report["screen_status"] = "PASSERS_GE_1_PENDING_NULL_REVIEW"
    report["n_passers"] = 1
    out = tmp_path / "pass"
    out.mkdir()
    screen.write_screen_report(report, out)
    acct = parse_harness_report_for_accounting(
        result_json=out / "null_maxstat.json",
        n_null_planned=int(report["null"]["n_null_planned"]),
        exit_code=0,
        expected_null_seed=int(report["null"]["base_seed"]),
    )
    assert acct["execution_state"] == "OK"
    assert acct["disposition"] == "SCREEN_PASS_PENDING_NULL_REVIEW"
    assert acct["r1_burned"] is False
    assert acct["n_null_executed"] == 0


def test_freshness_before_package_load_and_score(tmp_path: Path, monkeypatch):
    """Occupied out-dir must refuse before loader or scorer run."""
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "joint_screen.json").write_text("{}\n")

    calls: list[str] = []

    def _load(*_a, **_k):
        calls.append("package_load")
        raise AssertionError("package_load must not run")

    def _score(*_a, **_k):
        calls.append("score")
        raise AssertionError("score must not run")

    monkeypatch.setattr(screen, "load_develop_frames_from_package", _load)
    monkeypatch.setattr(screen, "run_joint_screen", _score)

    with pytest.raises(SystemExit, match="refuse overwrite|not empty"):
        screen.main(
            [
                "--charter",
                str(CHARTER),
                "--execute-develop-screen",
                "--out-dir",
                str(occupied),
            ]
        )
    assert calls == []


def test_refuse_overwrite_artifacts(tmp_path: Path):
    ch = load_charter(CHARTER)
    costs = screen.assert_costs_match_charter(ch)
    report = screen.run_joint_screen(
        _aligned_zero_spread(),
        ch,
        costs=costs,
        already_aligned=True,
        dispositional=False,
        non_dispositional_reason="unit",
    )
    out = tmp_path / "once"
    out.mkdir()
    screen.write_screen_report(report, out)
    with pytest.raises(SystemExit, match="refuse overwrite"):
        screen.write_screen_report(report, out)
    with pytest.raises(SystemExit, match="refuse overwrite|not empty"):
        screen.ensure_fresh_artifacts(out)


def test_package_id_pin():
    ch = load_charter(CHARTER)
    assert screen.pin_package_id(ch) == (
        "4f44b452081041f39fc24f03248b8ca8-ee2a993fb5b1befd"
    )
    assert hashlib_sha(CHARTER) == V4_SHA


def hashlib_sha(p: Path) -> str:
    import hashlib

    return hashlib.sha256(p.read_bytes()).hexdigest()
