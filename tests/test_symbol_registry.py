"""Explicit broker symbol registry: no suffix walk, no first-match."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mt5_arch.cli import main
from mt5_arch.symbol_registry import (
    SymbolRegistryError,
    canonical_from_broker_symbol,
    include_path,
    load_registry,
    render_mql5_include,
    resolve,
    verify_capability_dump,
)

ROOT = Path(__file__).resolve().parents[1]
INDICATOR = ROOT / "mql5" / "Indicators" / "ForexHtfPivotsFib.mq5"
BRIDGE = ROOT / "mql5" / "Mt5ArchBridge.mq5"
EXPORTER = ROOT / "mql5" / "Scripts" / "ExportInstrumentHistory.mq5"
CAP_SCRIPT = ROOT / "mql5" / "Scripts" / "ExportSymbolCapabilities.mq5"
AUDIT_SCRIPT = ROOT / "mql5" / "Scripts" / "ExportSymbolSyncAudit.mq5"
OFFLINE = ROOT / "tests" / "fixtures" / "symbol_registry" / "offline_ok"


def test_shipped_registry_loads():
    reg = load_registry()
    assert "vantage" in reg.brokers()
    assert "fpmarkets" in reg.brokers()
    assert "exness" in reg.brokers()
    assert "wsf" in reg.brokers()
    assert resolve(reg, "vantage", "XAUUSD").broker_symbol == "XAUUSD"
    assert resolve(reg, "fpmarkets", "XAUUSD").broker_symbol == "XAUUSD.r"
    assert resolve(reg, "fpmarkets", "XAUUSD.r").canonical == "XAUUSD"
    assert resolve(reg, "exness", "XAUUSD").broker_symbol == "XAUUSDm"


def test_unknown_and_unmapped_refuse():
    reg = load_registry()
    with pytest.raises(SymbolRegistryError, match="unknown broker"):
        resolve(reg, "acme", "XAUUSD")
    with pytest.raises(SymbolRegistryError, match="no mapping"):
        resolve(reg, "wsf", "XAUUSD")
    with pytest.raises(SymbolRegistryError, match="no mapping"):
        resolve(reg, "vantage", "GOLD")
    with pytest.raises(SymbolRegistryError, match="no mapping"):
        resolve(reg, "vantage", "XAUUSDm")


def test_no_suffix_walk_in_mql5_consumers():
    for path in (BRIDGE, EXPORTER, INDICATOR, CAP_SCRIPT, AUDIT_SCRIPT):
        text = path.read_text()
        assert "OrderSend(" not in text
        assert 'suffixes[] = {"m"' not in text
        assert 'suffixes[0] = "m"' not in text
        assert ".RAW" not in text
    assert "FxResolveSymbol" in BRIDGE.read_text()
    assert "FxResolveSymbol" in EXPORTER.read_text()
    assert "FxCanonicalFromBrokerSymbolAny" in INDICATOR.read_text()
    assert "InpBroker" in BRIDGE.read_text()
    assert "InpBroker" in EXPORTER.read_text()
    assert "InpBroker" in CAP_SCRIPT.read_text()
    assert "InpBroker" in AUDIT_SCRIPT.read_text()


def test_include_lockstep_with_json():
    reg = load_registry()
    assert include_path().read_text(encoding="utf-8") == render_mql5_include(reg)
    assert "SymbolSelect(base + " not in include_path().read_text()
    assert "first-match" in include_path().read_text() or "No first-match" in include_path().read_text()


def test_duplicate_broker_symbol_refused(tmp_path: Path):
    raw = json.loads((ROOT / "config" / "symbols" / "registry.json").read_text())
    raw["brokers"]["vantage"]["EURUSD"]["broker_symbol"] = "XAUUSD"
    dest = tmp_path / "bad.json"
    dest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SymbolRegistryError, match="ambiguous"):
        load_registry(dest)


def test_canonical_broker_symbol_swap_refused(tmp_path: Path):
    raw = json.loads((ROOT / "config" / "symbols" / "registry.json").read_text())
    raw["brokers"]["vantage"]["EURUSD"]["broker_symbol"] = "GBPUSD"
    raw["brokers"]["vantage"]["GBPUSD"]["broker_symbol"] = "EURUSD"
    dest = tmp_path / "swap.json"
    dest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SymbolRegistryError, match="ambiguous"):
        load_registry(dest)
    # Same-name identity remains valid on the shipped registry.
    assert resolve(load_registry(), "vantage", "EURUSD").broker_symbol == "EURUSD"


def test_inverse_unique_without_broker():
    reg = load_registry()
    assert canonical_from_broker_symbol(reg, "XAUUSD.r") == "XAUUSD"
    assert canonical_from_broker_symbol(reg, "XAUUSDm") == "XAUUSD"
    with pytest.raises(SymbolRegistryError, match="no inverse"):
        canonical_from_broker_symbol(reg, "NZDCHF.r")


def test_offline_capability_fixture():
    report = verify_capability_dump(OFFLINE)
    assert report["ok"] is True
    assert report["broker"] == "vantage"


def test_capability_wrong_broker_symbol_fails(tmp_path: Path):
    dest = tmp_path / "manifest.json"
    raw = json.loads(OFFLINE.joinpath("manifest.json").read_text())
    raw["symbols"][0]["broker_symbol"] = "XAUUSD.r"
    dest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SymbolRegistryError, match="broker_symbol"):
        verify_capability_dump(dest)


def test_capability_expect_digits_fails(tmp_path: Path):
    dest = tmp_path / "manifest.json"
    raw = json.loads(OFFLINE.joinpath("manifest.json").read_text())
    raw["symbols"][0]["digits"] = 5
    dest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SymbolRegistryError, match="digits"):
        verify_capability_dump(dest)


def test_capability_mql5_export_missing_mapped_canonical_fails(tmp_path: Path):
    dest = tmp_path / "manifest.json"
    raw = json.loads(OFFLINE.joinpath("manifest.json").read_text())
    raw["source"] = "mql5_export"
    dest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SymbolRegistryError, match="EURUSD"):
        verify_capability_dump(dest)


def test_cli_resolve(capsys: pytest.CaptureFixture[str]):
    assert main(["resolve", "fpmarkets", "XAUUSD", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["broker_symbol"] == "XAUUSD.r"
    assert main(["resolve", "vantage", "GOLD"]) == 1
