"""Offline unit tests for FileBridgeClient using temp JSON snapshots."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from bridge_fixtures import write_bridge_fixture

from mt5_arch.config import Settings
from mt5_arch.file_bridge import (
    DEFAULT_MAX_AGE_SECONDS,
    FileBridgeClient,
    FileBridgeError,
    default_bridge_dir,
)


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


def test_default_max_age_matches_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MT5_BRIDGE_MAX_AGE", raising=False)
    assert DEFAULT_MAX_AGE_SECONDS == 15.0
    client = FileBridgeClient(Path("/unused"))
    assert client.max_age_seconds == DEFAULT_MAX_AGE_SECONDS
    assert Settings(_env_file=None).mt5_bridge_max_age == DEFAULT_MAX_AGE_SECONDS


def test_missing_account_raises(tmp_path: Path) -> None:
    bridge = tmp_path / "empty"
    bridge.mkdir()
    client = FileBridgeClient(bridge, max_age_seconds=30.0)
    with pytest.raises(FileBridgeError, match="account.json"):
        client.account_info()


def test_missing_heartbeat_raises_even_if_account_is_fresh(tmp_path: Path) -> None:
    """Detached EA / missing heartbeat must not inherit account.json mtime."""
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    (bridge / "heartbeat.txt").unlink()
    now = time.time()
    os.utime(bridge / "account.json", (now, now))
    client = FileBridgeClient(bridge, max_age_seconds=30.0)
    with pytest.raises(FileBridgeError, match="heartbeat"):
        client.ping()


def test_stale_bridge_raises(tmp_path: Path) -> None:
    bridge = tmp_path / "stale"
    write_bridge_fixture(bridge, age_seconds=120.0)
    client = FileBridgeClient(bridge, max_age_seconds=10.0)
    with pytest.raises(FileBridgeError, match="stale"):
        client.ping()


def test_corrupt_account_json_is_file_bridge_error(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    (bridge / "account.json").write_text("{not-json", encoding="utf-8")
    client = FileBridgeClient(bridge, max_age_seconds=30.0)
    with pytest.raises(FileBridgeError, match="Corrupt account.json"):
        client.account_info()


def test_corrupt_candles_json_is_file_bridge_error(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    (bridge / "candles_EURUSD_H1.json").write_text("[", encoding="utf-8")
    client = FileBridgeClient(bridge, max_age_seconds=30.0)
    with pytest.raises(FileBridgeError, match="Corrupt candles_EURUSD_H1.json"):
        client.copy_rates("EURUSD", timeframe="H1")


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


def test_wsf_unmapped_symbol_refuses(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    client = FileBridgeClient(bridge, max_age_seconds=30.0, broker="wsf")
    with pytest.raises(FileBridgeError, match="fail closed"):
        client.symbol_info("XAUUSD")
    with pytest.raises(FileBridgeError, match="fail closed"):
        client._mapped_symbol("XAUUSD")


def test_mapped_symbol_without_broker_keeps_exact_name(tmp_path: Path) -> None:
    client = FileBridgeClient(tmp_path, broker=None)
    assert client._mapped_symbol("XAUUSD") == "XAUUSD"
    empty = FileBridgeClient(tmp_path, broker="")
    assert empty._mapped_symbol("XAUUSD") == "XAUUSD"


def test_copy_rates_available_glob_uses_mapped_name(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    (bridge / "candles_XAUUSD.r_M15.json").write_text("{}", encoding="utf-8")
    client = FileBridgeClient(bridge, max_age_seconds=30.0, broker="fpmarkets")
    with pytest.raises(FileBridgeError, match="candles_XAUUSD.r_M15") as exc:
        client.copy_rates("XAUUSD", timeframe="H1")
    assert "candles_XAUUSD.r_M15.json" in str(exc.value)


def _rewrite_candles(bridge: Path, payload: object) -> None:
    (bridge / "candles_EURUSD_H1.json").write_text(json.dumps(payload), encoding="utf-8")


def test_candles_not_a_list_is_file_bridge_error(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    _rewrite_candles(bridge, {"symbol": "EURUSD", "candles": {"open": 1.0}})
    client = FileBridgeClient(bridge, max_age_seconds=30.0)
    with pytest.raises(FileBridgeError, match="'candles' is not a list"):
        client.copy_rates("EURUSD", timeframe="H1")


def test_candle_row_not_an_object_is_file_bridge_error(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    _rewrite_candles(bridge, {"symbol": "EURUSD", "candles": ["1.16"]})
    client = FileBridgeClient(bridge, max_age_seconds=30.0)
    with pytest.raises(FileBridgeError, match="candle 0 is not an object"):
        client.copy_rates("EURUSD", timeframe="H1")


def test_candle_missing_ohlc_field_is_file_bridge_error(tmp_path: Path) -> None:
    """Valid JSON with a truncated row must not surface a raw KeyError."""
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    _rewrite_candles(
        bridge,
        {"symbol": "EURUSD", "candles": [{"time": "2026.07.31 11:00:00", "open": 1.16}]},
    )
    client = FileBridgeClient(bridge, max_age_seconds=30.0)
    with pytest.raises(FileBridgeError, match="bad candle 0"):
        client.copy_rates("EURUSD", timeframe="H1")


def test_candle_non_numeric_ohlc_is_file_bridge_error(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    _rewrite_candles(
        bridge,
        {
            "symbol": "EURUSD",
            "candles": [
                {
                    "time": "2026.07.31 11:00:00",
                    "open": "nan-ish",
                    "high": 1.17,
                    "low": 1.15,
                    "close": 1.165,
                    "volume": 10,
                }
            ],
        },
    )
    client = FileBridgeClient(bridge, max_age_seconds=30.0)
    with pytest.raises(FileBridgeError, match="bad candle 0"):
        client.copy_rates("EURUSD", timeframe="H1")


def test_non_ascii_account_json_does_not_leak_unicode_error(tmp_path: Path) -> None:
    """EA writes JSON with FILE_ANSI too: a broker company name can be cp1252.

    UnicodeDecodeError is a ValueError - account_info() must not raise it raw.
    """
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    account = bridge / "account.json"
    raw = json.loads(account.read_text(encoding="utf-8"))
    raw["company"] = "CAFE_MARKER"
    account.write_bytes(
        json.dumps(raw).encode("ascii").replace(b"CAFE_MARKER", b"Caf\xe9 Markets")
    )
    info = FileBridgeClient(bridge, max_age_seconds=30.0).account_info()
    assert info.company == "Caf\u00e9 Markets"


def test_non_ascii_symbol_json_does_not_leak_unicode_error(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    symbols = bridge / "symbols.json"
    rows = json.loads(symbols.read_text(encoding="utf-8"))
    rows[0]["description"] = "DESC_MARKER"
    symbols.write_bytes(
        json.dumps(rows).encode("ascii").replace(b"DESC_MARKER", b"Euro vs Dollar \xe9")
    )
    spec = FileBridgeClient(bridge, max_age_seconds=30.0).symbol_info(rows[0]["symbol"])
    assert spec.symbol == rows[0]["symbol"]
