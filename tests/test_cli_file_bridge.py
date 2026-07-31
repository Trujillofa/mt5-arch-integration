"""CLI exercises against file-bridge fixtures (no live MT5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from bridge_fixtures import write_bridge_fixture

from mt5_arch.cli import main


@pytest.fixture
def bridge_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    monkeypatch.setenv("MT5_BACKEND", "file")
    monkeypatch.setenv("MT5_BRIDGE_DIR", str(bridge))
    monkeypatch.setenv("MT5_BRIDGE_MAX_AGE", "60")
    # Avoid ambient credentials noise in config
    monkeypatch.delenv("MT5_PASSWORD", raising=False)
    return bridge


def test_config_json_file_first(bridge_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["config", "--json"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["mt5_backend"] == "file"
    assert data["mt5_password"] in (None, "***")
    assert "mt5_rpyc_port" in data


def test_cli_account_against_fixture(bridge_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["account", "--json"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["login"] == 118248
    assert data["balance"] == 5000.25
    assert data["currency"] == "USD"
    assert data["server"] == "WSFmarkets-Server"


def test_cli_ping_against_fixture(bridge_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["ping", "--json"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["connected"] is True
    assert data["build"] == 6075


def test_cli_symbols_and_candles(bridge_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["symbols", "EURUSD", "--json"])
    assert code == 0
    sym = json.loads(capsys.readouterr().out)
    assert sym["symbol"] == "EURUSD"
    assert sym["min_lot"] == 0.01

    code = main(["candles", "EURUSD", "--tf", "H1", "--count", "2", "--json"])
    assert code == 0
    bars = json.loads(capsys.readouterr().out)
    assert bars["symbol"] == "EURUSD"
    assert bars["timeframe"] == "H1"
    assert len(bars["candles"]) == 2
    assert "open" in bars["candles"][0]


def test_cli_stale_bridge_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    bridge = tmp_path / "old"
    write_bridge_fixture(bridge, age_seconds=200)
    monkeypatch.setenv("MT5_BACKEND", "file")
    monkeypatch.setenv("MT5_BRIDGE_DIR", str(bridge))
    monkeypatch.setenv("MT5_BRIDGE_MAX_AGE", "5")
    code = main(["account", "--json"])
    assert code == 1
    err = capsys.readouterr().err
    assert "stale" in err.lower() or "error" in err.lower()
