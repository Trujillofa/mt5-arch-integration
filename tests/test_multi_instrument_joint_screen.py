"""Unit tests for dedicated multi-instrument joint screen harness.

Synthetic frames only — does **not** load the develop package or score live data.
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

# Reuse synthetic builders from fixture tests
sys.path.insert(0, str(ROOT / "tests"))
from test_joint_london_open_cosign_fade_flat import (  # noqa: E402
    _merge_warmup_signal,
    _signal_day_frames,
)

CHARTER = ROOT / "results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v4.json"


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


def test_run_joint_screen_zero_passers_synthetic():
    """Short synthetic path → binary joint gate fails → SCREEN_FAIL shape."""
    ch = load_charter(CHARTER)
    day = "2024-01-05"
    aligned = _merge_warmup_signal(_signal_day_frames(day, cosign="up"))
    # Explicit zero spreads (finite)
    for s in fam.SYMBOLS:
        aligned[s] = aligned[s].copy()
        aligned[s]["spread"] = 0.0
    report = screen.run_joint_screen(
        aligned,
        ch,
        costs={"commission_per_lot": 0.0, "slippage_points": 0.0, "spread_col": "spread"},
        already_aligned=True,
    )
    assert report["screen_only"] is True
    assert report["null_trials_executed"] == 0
    assert report["r1_burned"] is False
    assert report["n_passers"] in (0, 1)
    # With one signal day, soft n>=60 cannot pass
    assert report["n_passers"] == 0
    assert report["disposition"] == "SCREEN_FAIL"
    assert report["screen_status"] == "ZERO_PRIMARY_PASSERS"
    assert report["metrics_real_grid_develop"]["n_trades"] == 3


def test_run_joint_screen_gate_helpers_wired():
    ch = load_charter(CHARTER)
    aligned = _merge_warmup_signal(_signal_day_frames("2024-01-05", cosign="up"))
    for s in fam.SYMBOLS:
        aligned[s] = aligned[s].copy()
        aligned[s]["spread"] = 0.0
    report = screen.run_joint_screen(aligned, ch, already_aligned=True)
    assert set(report["per_symbol_soft_pass"]) == set(fam.SYMBOLS)
    assert "joint_soft_pass" in report
    assert report["n_passers_definition"] == "binary_joint_gate_success"


def test_write_screen_report(tmp_path: Path):
    ch = load_charter(CHARTER)
    aligned = _merge_warmup_signal(_signal_day_frames("2024-01-05", cosign="up"))
    for s in fam.SYMBOLS:
        aligned[s] = aligned[s].copy()
        aligned[s]["spread"] = 0.0
    report = screen.run_joint_screen(aligned, ch, already_aligned=True)
    path = screen.write_screen_report(report, tmp_path)
    assert path.is_file()
    body = json.loads(path.read_text())
    assert body["disposition"] == report["disposition"]
    mirror = json.loads((tmp_path / "null_maxstat.json").read_text())
    assert mirror["screen_only"] is True
    assert mirror["n_null_executed"] == 0


def test_package_id_pin():
    ch = load_charter(CHARTER)
    assert screen.pin_package_id(ch) == (
        "4f44b452081041f39fc24f03248b8ca8-ee2a993fb5b1befd"
    )
