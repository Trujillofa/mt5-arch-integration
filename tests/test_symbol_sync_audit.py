"""Offline multi-symbol H1 sync audit: registry floor + comparison rules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mt5_arch.symbol_registry import SymbolRegistryError
from mt5_arch.symbol_sync_audit import verify_sync_audit_dump

ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = ROOT / "mql5" / "Scripts" / "ExportSymbolSyncAudit.mq5"
INSTALLER = ROOT / "scripts" / "18-install-forex-indicator.sh"
OFFLINE = ROOT / "tests" / "fixtures" / "symbol_sync_audit" / "offline_ok"
PACKAGE = ROOT / "tests" / "fixtures" / "symbol_sync_audit" / "package_ok.json"


def _clone(tmp_path: Path) -> tuple[Path, dict]:
    raw = json.loads(OFFLINE.joinpath("manifest.json").read_text(encoding="utf-8"))
    dest = tmp_path / "manifest.json"
    dest.write_text(json.dumps(raw), encoding="utf-8")
    return dest, raw


def test_offline_sync_audit_fixture():
    report = verify_sync_audit_dump(OFFLINE, package=PACKAGE)
    assert report["ok"] is True
    assert report["broker"] == "vantage"
    assert report["n_mapped"] == 6
    assert report["n_intersection_timestamps"] == 4


def test_sync_audit_script_is_read_only_and_installed():
    text = AUDIT_SCRIPT.read_text(encoding="utf-8")
    assert "OrderSend(" not in text
    assert "InpBroker" in text
    assert "FxRegistryLookup" in text
    assert "FxResolveSymbol" in text
    assert 'suffixes[] = {"m"' not in text
    assert INSTALLER.read_text(encoding="utf-8").count("ExportSymbolSyncAudit.mq5") >= 1


def test_mql5_export_missing_mapped_canonical_fails(tmp_path: Path):
    dest, raw = _clone(tmp_path)
    raw["source"] = "mql5_export"
    raw["symbols"] = [row for row in raw["symbols"] if row["canonical"] != "GBPUSD"]
    dest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SymbolRegistryError, match="GBPUSD"):
        verify_sync_audit_dump(dest)


def test_dump_omitting_mapped_canonical_refuses(tmp_path: Path):
    """Coverage floor applies to verify_sync_audit_dump alone (no package)."""
    dest, raw = _clone(tmp_path)
    raw["symbols"] = [row for row in raw["symbols"] if row["canonical"] != "GBPUSD"]
    dest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SymbolRegistryError, match="GBPUSD"):
        verify_sync_audit_dump(dest)


def test_mismatched_first_last_fails(tmp_path: Path):
    dest, raw = _clone(tmp_path)
    raw["symbols"][0]["first_time"] = "2025.01.01 00:00:00"
    dest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SymbolRegistryError, match="EURUSD"):
        verify_sync_audit_dump(dest)


def test_intersection_count_wrong_fails(tmp_path: Path):
    dest, raw = _clone(tmp_path)
    raw["joint"]["n_intersection_timestamps"] = 99
    dest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SymbolRegistryError, match="intersection count"):
        verify_sync_audit_dump(dest)


def test_package_intersection_mismatch_fails(tmp_path: Path):
    dest, _raw = _clone(tmp_path)
    pkg = json.loads(PACKAGE.read_text(encoding="utf-8"))
    pkg["n_intersection_timestamps"] = 1
    pkg_path = tmp_path / "package.json"
    pkg_path.write_text(json.dumps(pkg), encoding="utf-8")
    with pytest.raises(SymbolRegistryError, match="intersection count"):
        verify_sync_audit_dump(dest, package=pkg_path)


def test_forming_bar_not_flagged_refuses(tmp_path: Path):
    dest, raw = _clone(tmp_path)
    raw["server_time"] = "2026.01.05 11:15:00"
    raw["symbols"][4]["last_forming"] = False
    dest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SymbolRegistryError, match="forming"):
        verify_sync_audit_dump(dest)


def test_unmapped_without_error_refuses(tmp_path: Path):
    dest, raw = _clone(tmp_path)
    raw["symbols"].append(
        {
            "canonical": "GOLD",
            "requested": "GOLD",
            "broker_symbol": "",
            "selected": False,
            "bars_h1": 0,
            "error": "",
        }
    )
    dest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SymbolRegistryError, match="not_in_registry"):
        verify_sync_audit_dump(dest)


def test_differing_count_missing_timestamp_refuses(tmp_path: Path):
    """HIGH-1: dropping EURUSD timestamps and bumping bars_h1 4→5 must fail.

    The old equal-count-only guard returned ok=True because the other
    symbols still formed a non-empty intersection without EURUSD.
    """
    dest, raw = _clone(tmp_path)
    raw["source"] = "mql5_export"
    for row in raw["symbols"]:
        if row.get("canonical") == "EURUSD":
            row.pop("timestamps", None)
            row["bars_h1"] = 5
    dest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SymbolRegistryError, match="EURUSD"):
        verify_sync_audit_dump(dest)
