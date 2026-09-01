"""Offline tests for EA version reporting via heartbeat.txt.

Motivation: `deals --request` against the live Vantage prefix blocked for the
full 30s and then reported "the EA dumps on its next timer tick" — which was
false. The deployed EA predated the feature entirely, and nothing in the
heartbeat let Python tell that from a slow EA.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from bridge_fixtures import write_bridge_fixture

from mt5_arch.file_bridge import (
    MIN_DEAL_DUMP_VERSION,
    FileBridgeClient,
    FileBridgeError,
    parse_bridge_version,
)

_LIVE_HEARTBEAT = "1788251227 connected=1 writer_chart=26180515069381 symbol=EURUSD"


def _client(bridge: Path) -> FileBridgeClient:
    return FileBridgeClient(bridge, max_age_seconds=30.0)


def _set_heartbeat(bridge: Path, text: str) -> None:
    (bridge / "heartbeat.txt").write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (f"{_LIVE_HEARTBEAT} version=1.24", (1, 24)),
        (f"{_LIVE_HEARTBEAT} version=1.25", (1, 25)),
        (f"{_LIVE_HEARTBEAT} version=2.0.1", (2, 0, 1)),
        # Real pre-1.24 heartbeat from the live Vantage prefix: no version field.
        (_LIVE_HEARTBEAT, None),
        ("", None),
        # Must not match a symbol that merely contains the substring.
        ("123 connected=1 symbol=XVERSION=9", None),
    ],
)
def test_parse_bridge_version(text: str, expected: tuple[int, ...] | None) -> None:
    assert parse_bridge_version(text) == expected


def test_bridge_version_reads_live_format(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    _set_heartbeat(bridge, f"{_LIVE_HEARTBEAT} version=1.24")
    assert _client(bridge).bridge_version() == (1, 24)


def test_bridge_version_none_for_pre_1_24_ea(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    _set_heartbeat(bridge, _LIVE_HEARTBEAT)
    assert _client(bridge).bridge_version() is None


def test_bridge_version_none_when_no_heartbeat(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    bridge.mkdir(parents=True)
    assert _client(bridge).bridge_version() is None


def test_request_deals_fails_fast_on_old_ea(tmp_path: Path) -> None:
    """The whole point: an EA that cannot serve the request must not cost 30s."""
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    _set_heartbeat(bridge, f"{_LIVE_HEARTBEAT} version=1.23")
    started = time.monotonic()
    with pytest.raises(FileBridgeError) as exc:
        _client(bridge).request_deals(timeout=30.0)
    assert time.monotonic() - started < 1.0, "did not fail fast"
    msg = str(exc.value)
    assert "v1.23" in msg and "1.24" in msg
    assert "06-install-file-bridge.sh" in msg


def test_request_deals_writes_no_request_file_when_ea_too_old(tmp_path: Path) -> None:
    """Do not leave a request an old EA will never consume."""
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    _set_heartbeat(bridge, f"{_LIVE_HEARTBEAT} version=1.23")
    with pytest.raises(FileBridgeError):
        _client(bridge).request_deals(timeout=30.0)
    assert not (bridge / "dump_deals.request").exists()


def test_request_deals_still_waits_when_version_unknown(tmp_path: Path) -> None:
    """FP Markets runs a pre-1.24 build that *does* serve the dump.

    Unknown must mean unknown: still try, but say so on timeout.
    """
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    _set_heartbeat(bridge, _LIVE_HEARTBEAT)
    with pytest.raises(FileBridgeError) as exc:
        _client(bridge).request_deals(timeout=0.2, poll_interval=0.01)
    msg = str(exc.value)
    assert "Timed out" in msg
    assert "reports no version" in msg
    assert (bridge / "dump_deals.request").exists(), "request must be left for the EA"


def test_request_deals_proceeds_on_current_version(tmp_path: Path) -> None:
    """A current EA is not blocked by the capability check."""
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    version = ".".join(str(p) for p in MIN_DEAL_DUMP_VERSION)
    _set_heartbeat(bridge, f"{_LIVE_HEARTBEAT} version={version}")
    with pytest.raises(FileBridgeError) as exc:
        _client(bridge).request_deals(timeout=0.2, poll_interval=0.01)
    assert "Timed out" in str(exc.value), "should reach the wait, not the version gate"
    assert "reports no version" not in str(exc.value)
