"""Bridge reader integrity: torn writes, empty candle files, stale series, zero specs.

Each test pins one failure mode that could hand a stale/empty/zero series to a
consumer as if it were live market data.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from bridge_fixtures import write_bridge_fixture

from mt5_arch import file_bridge
from mt5_arch.file_bridge import FileBridgeClient, FileBridgeError


def _client(bridge: Path, *, max_age: float = 30.0) -> FileBridgeClient:
    return FileBridgeClient(bridge, max_age_seconds=max_age)


def test_torn_json_is_retried_then_succeeds(tmp_path: Path, monkeypatch) -> None:
    """A truncate-in-place write exposes a prefix; the next tick rewrites it."""
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    path = bridge / "account.json"
    good = path.read_text(encoding="utf-8")

    calls = {"n": 0}

    def fake_read(p: Path, *, label: str) -> str:
        if p == path:
            calls["n"] += 1
            if calls["n"] == 1:
                return good[: len(good) // 3]  # torn prefix: not valid JSON
        return good

    monkeypatch.setattr(file_bridge, "_read_bridge_text", fake_read)
    account = _client(bridge).account_info()
    assert account.login == 118248
    assert calls["n"] >= 2


def test_persistently_torn_json_fails_closed(tmp_path: Path, monkeypatch) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    monkeypatch.setattr(
        file_bridge,
        "_read_bridge_text",
        lambda p, *, label: '{"login": 118248, "balance"',  # always torn
    )
    with pytest.raises(FileBridgeError, match="Corrupt account.json"):
        _client(bridge).account_info()


def test_empty_candle_file_is_refused(tmp_path: Path) -> None:
    """CopyRates<=0 must not be published as a valid empty market."""
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    (bridge / "candles_EURUSD_H1.json").write_text(
        json.dumps({"symbol": "EURUSD", "timeframe": "H1", "candles": []}), encoding="utf-8"
    )
    with pytest.raises(FileBridgeError, match="zero candles"):
        _client(bridge).copy_rates("EURUSD", "H1", count=5)


def test_stale_candle_file_is_refused_even_with_fresh_heartbeat(tmp_path: Path) -> None:
    """A symbol dropped from InpSymbols keeps its old file while the heartbeat ticks."""
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    candles = bridge / "candles_EURUSD_H1.json"
    old = candles.stat().st_mtime - 3600
    os.utime(candles, (old, old))
    with pytest.raises(FileBridgeError, match="stale"):
        _client(bridge, max_age=30.0).copy_rates("EURUSD", "H1", count=5)


def test_zero_contract_size_is_refused_not_defaulted(tmp_path: Path) -> None:
    """An unsynchronised XAUUSD spec must not become FX's 100000 contract size."""
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    rows = json.loads((bridge / "symbols.json").read_text(encoding="utf-8"))
    rows[0]["contract_size"] = 0.0
    (bridge / "symbols.json").write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(FileBridgeError, match="spec is zero/incomplete"):
        _client(bridge).symbol_info("EURUSD")


def test_cold_start_account_is_refused(tmp_path: Path) -> None:
    """Snapshot written before the terminal synced reads as a total loss downstream."""
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    cold = {
        "login": 0,
        "balance": 0.0,
        "equity": 0.0,
        "currency": "",
        "server": "",
    }
    (bridge / "account.json").write_text(json.dumps(cold), encoding="utf-8")
    with pytest.raises(FileBridgeError, match="no login yet"):
        _client(bridge).account_info()
