"""Live smoke tests — require terminal (+ file-bridge EA or mt5server).

Skipped by default. Set MT5_LIVE_SMOKE=1 to enable.

Uses the same backend routing as the shipped CLI (`MT5_BACKEND=file|rpyc`).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest

from mt5_arch.cli import _open_client
from mt5_arch.client import MT5ArchClient
from mt5_arch.config import Settings
from mt5_arch.file_bridge import FileBridgeError

pytestmark = pytest.mark.live


def _live_enabled() -> bool:
    return os.environ.get("MT5_LIVE_SMOKE", "").strip() in {"1", "true", "yes"}


@pytest.fixture
def live_client() -> Iterator[Any]:
    if not _live_enabled():
        pytest.skip("Set MT5_LIVE_SMOKE=1 with running terminal + file bridge (or mt5server)")
    settings = Settings()
    try:
        client = _open_client(settings)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Cannot open MT5 backend: {exc}")

    if isinstance(client, MT5ArchClient):
        try:
            client.initialize()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Cannot connect to MT5 (RPyC): {exc}")
        try:
            yield client
        finally:
            client.shutdown()
        return

    # File bridge: no session setup; probe immediately
    try:
        client.ensure_alive()
    except FileBridgeError as exc:
        pytest.skip(f"Cannot connect to MT5 (file bridge): {exc}")
    yield client


def test_live_ping(live_client: Any) -> None:
    info = live_client.ping()
    assert info.connected is True
    assert info.build > 0 or info.name


def test_live_account(live_client: Any) -> None:
    account = live_client.account_info()
    assert account.login > 0
    # Server is the reliable identity field under Wine file bridge.
    # Currency/leverage may be empty for some investor/partial sessions.
    assert account.server
    assert account.balance is not None
