"""Live smoke tests — require terminal + mt5server. Skipped by default."""

from __future__ import annotations

import os

import pytest

from mt5_arch.client import MT5ArchClient
from mt5_arch.config import Settings

pytestmark = pytest.mark.live


def _live_enabled() -> bool:
    return os.environ.get("MT5_LIVE_SMOKE", "").strip() in {"1", "true", "yes"}


@pytest.fixture
def live_client() -> MT5ArchClient:
    if not _live_enabled():
        pytest.skip("Set MT5_LIVE_SMOKE=1 with running terminal + mt5server")
    settings = Settings()
    client = MT5ArchClient(settings)
    try:
        client.initialize()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Cannot connect to MT5: {exc}")
    yield client
    client.shutdown()


def test_live_ping(live_client: MT5ArchClient) -> None:
    info = live_client.ping()
    assert info.connected is True


def test_live_account(live_client: MT5ArchClient) -> None:
    account = live_client.account_info()
    assert account.login > 0
    assert account.currency
    assert account.balance is not None
