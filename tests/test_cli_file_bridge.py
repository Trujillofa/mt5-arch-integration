"""CLI exercises against file-bridge fixtures (no live MT5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from bridge_fixtures import write_bridge_fixture, write_deal_dump_fixture

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


def test_cli_missing_heartbeat_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bridge = tmp_path / "no-hb"
    write_bridge_fixture(bridge)
    (bridge / "heartbeat.txt").unlink()
    monkeypatch.setenv("MT5_BACKEND", "file")
    monkeypatch.setenv("MT5_BRIDGE_DIR", str(bridge))
    monkeypatch.setenv("MT5_BRIDGE_MAX_AGE", "60")
    code = main(["ping", "--json"])
    assert code == 1
    err = capsys.readouterr().err
    assert "heartbeat" in err.lower()


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


def test_cli_offline_cached_account_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """login+server without currency/leverage is treated as offline (not success)."""
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    # Simulate Wine offline shell: identity present, money meta empty
    account = json.loads((bridge / "account.json").read_text(encoding="utf-8"))
    account.update(
        {
            "balance": 0.0,
            "equity": 0.0,
            "currency": "",
            "leverage": 0,
            "name": "",
            "company": "",
            "terminal_connected": False,
        }
    )
    (bridge / "account.json").write_text(json.dumps(account), encoding="utf-8")
    terminal = json.loads((bridge / "terminal.json").read_text(encoding="utf-8"))
    terminal["connected"] = False
    (bridge / "terminal.json").write_text(json.dumps(terminal), encoding="utf-8")

    monkeypatch.setenv("MT5_BACKEND", "file")
    monkeypatch.setenv("MT5_BRIDGE_DIR", str(bridge))
    monkeypatch.setenv("MT5_BRIDGE_MAX_AGE", "60")

    code = main(["account", "--json"])
    assert code == 2
    err = capsys.readouterr().err
    assert "offline" in err.lower() or "cached" in err.lower()

    code = main(["ping", "--json"])
    assert code == 2
    err = capsys.readouterr().err
    assert "not trade-connected" in err.lower() or "connected=false" in err.lower()


def test_cli_deals_json(bridge_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_deal_dump_fixture(bridge_env)
    code = main(["deals", "--json"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["count"] == 2
    assert data["time_basis"] == "trade_server"
    assert data["deals"][0]["deal_id"] == 1001
    assert data["deals"][0]["time"] == "2026.08.20 10:00:00"
    assert "T" not in data["deals"][0]["time"]
    assert data["deals"][0]["comment"] == "scale;in"


def test_cli_deals_missing_done_exits_1(
    bridge_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_deal_dump_fixture(bridge_env, include_done=False)
    code = main(["deals", "--json"])
    assert code == 1
    err = capsys.readouterr().err
    assert "dump_deals.done" in err


def test_cli_deals_request_timeout_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    write_deal_dump_fixture(bridge, done_age_seconds=60.0)
    monkeypatch.setenv("MT5_BACKEND", "file")
    monkeypatch.setenv("MT5_BRIDGE_DIR", str(bridge))
    monkeypatch.setenv("MT5_BRIDGE_MAX_AGE", "60")
    code = main(["deals", "--request", "--timeout", "0.2", "--json"])
    assert code == 1
    err = capsys.readouterr().err.lower()
    assert "dump_deals.done" in err or "timeout" in err
    assert (bridge / "dump_deals.request").exists()


def test_cli_deals_empty_dump(bridge_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_deal_dump_fixture(bridge_env, csv_text="time,deal_id,order_id,position_id,symbol,type,entry,volume,price,profit,swap,commission,fee,reason,magic,comment\n", n_rows=0)
    code = main(["deals", "--json"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["count"] == 0
    assert data["deals"] == []
