"""Offline unit tests for FileBridgeClient using temp JSON snapshots."""

from __future__ import annotations

from pathlib import Path

import pytest
from bridge_fixtures import write_bridge_fixture

from mt5_arch.file_bridge import FileBridgeClient, FileBridgeError, default_bridge_dir


def test_default_bridge_dir_under_wineprefix(tmp_path: Path) -> None:
    d = default_bridge_dir(tmp_path / ".mt5")
    assert d.name == "mt5_arch"
    assert "MetaTrader 5" in str(d)
    assert "MQL5" in str(d)


def test_ping_account_symbols_candles_from_fixture(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    client = FileBridgeClient(bridge, max_age_seconds=30.0)

    term = client.ping()
    assert term.connected is True
    assert term.build == 6075
    assert term.trade_allowed is True

    account = client.account_info()
    assert account.login == 118248
    assert account.balance == 5000.25
    assert account.equity == 4980.5
    assert account.currency == "USD"
    assert account.server == "WSFmarkets-Server"
    assert account.leverage == 100

    sym = client.symbol_info("EURUSD")
    assert sym.symbol == "EURUSD"
    assert sym.min_lot == 0.01
    assert sym.lot_step == 0.01
    assert sym.trade_mode == "FULL"

    rates = client.copy_rates("EURUSD", timeframe="H1", count=2)
    assert rates.symbol == "EURUSD"
    assert rates.timeframe == "H1"
    assert len(rates.candles) == 2
    # last N bars
    assert rates.candles[-1].close == 1.165
    assert "T" in rates.candles[0].time


def test_missing_account_raises(tmp_path: Path) -> None:
    bridge = tmp_path / "empty"
    bridge.mkdir()
    client = FileBridgeClient(bridge, max_age_seconds=30.0)
    with pytest.raises(FileBridgeError, match="account.json"):
        client.account_info()


def test_stale_bridge_raises(tmp_path: Path) -> None:
    bridge = tmp_path / "stale"
    write_bridge_fixture(bridge, age_seconds=120.0)
    client = FileBridgeClient(bridge, max_age_seconds=10.0)
    with pytest.raises(FileBridgeError, match="stale"):
        client.ping()


def test_unknown_symbol_raises(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    client = FileBridgeClient(bridge, max_age_seconds=30.0)
    with pytest.raises(FileBridgeError, match="not in bridge"):
        client.symbol_info("NOTREAL")


def test_missing_candles_raises(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    client = FileBridgeClient(bridge, max_age_seconds=30.0)
    with pytest.raises(FileBridgeError, match="Missing"):
        client.copy_rates("EURUSD", timeframe="M5")
