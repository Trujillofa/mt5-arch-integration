"""Offline unit tests for MT5ArchClient (mocked mt5linux)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from mt5_arch.client import TIMEFRAME_MAP, MT5ArchClient, MT5ArchError, MT5NotConnectedError
from mt5_arch.config import Settings
from mt5_arch.models import AccountInfo


class FakeMT5:
    """Minimal stand-in for MetaTrader5 over RPyC."""

    def __init__(self) -> None:
        self._initialized = False
        self.init_kwargs: dict[str, Any] = {}
        self.shutdown_called = False

    def initialize(self, **kwargs: Any) -> bool:
        self.init_kwargs = kwargs
        self._initialized = True
        return True

    def shutdown(self) -> None:
        self.shutdown_called = True
        self._initialized = False

    def last_error(self) -> tuple[int, str]:
        return (1, "Success")

    def version(self) -> tuple[int, int, str]:
        return (500, 3815, "01 Jan 2024")

    def terminal_info(self) -> SimpleNamespace:
        return SimpleNamespace(
            connected=True,
            name="MetaTrader 5",
            path=r"C:\Program Files\MetaTrader 5\terminal64.exe",
            company="MetaQuotes",
            build=3815,
            trade_allowed=True,
            tradeapi_disabled=False,
        )

    def account_info(self) -> SimpleNamespace:
        return SimpleNamespace(
            login=118248,
            balance=5000.0,
            equity=4980.5,
            margin=120.0,
            margin_free=4860.5,
            margin_level=4150.42,
            currency="USD",
            leverage=100,
            server="WSFmarkets-Server",
            name="Demo",
            company="WSFunded",
        )

    def symbol_select(self, symbol: str, enable: bool) -> bool:
        return symbol.upper() in {"EURUSD", "XAUUSD"}

    def symbol_info(self, symbol: str) -> SimpleNamespace | None:
        if symbol.upper() not in {"EURUSD", "XAUUSD"}:
            return None
        return SimpleNamespace(
            name=symbol.upper(),
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            trade_contract_size=100000.0 if symbol.upper() == "EURUSD" else 100.0,
            digits=5 if symbol.upper() == "EURUSD" else 2,
            point=0.00001 if symbol.upper() == "EURUSD" else 0.01,
            trade_tick_value=1.0,
            trade_tick_size=0.00001 if symbol.upper() == "EURUSD" else 0.01,
            trade_mode=4,
        )

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start: int, count: int) -> list[tuple]:
        assert timeframe in TIMEFRAME_MAP.values()
        # (time, open, high, low, close, tick_volume, spread, real_volume)
        base = 1_700_000_000
        rows = []
        for i in range(count):
            rows.append((base + i * 3600, 1.1, 1.2, 1.0, 1.15, 100 + i, 0, 0))
        return rows


class FailingInitMT5(FakeMT5):
    def initialize(self, **kwargs: Any) -> bool:
        return False

    def last_error(self) -> tuple[int, str]:
        return (-10005, "IPC timeout")


def _settings(**overrides: Any) -> Settings:
    data = {
        "mt5_login": 118248,
        "mt5_password": "secret",
        "mt5_server": "WSFmarkets-Server",
        "mt5_rpyc_host": "localhost",
        "mt5_rpyc_port": 18812,
    }
    data.update(overrides)
    # Ignore ambient .env so unit tests are deterministic.
    return Settings(_env_file=None, **data)


def test_context_manager_initializes_and_shuts_down() -> None:
    fake = FakeMT5()

    def factory(host: str, port: int) -> FakeMT5:
        assert host == "localhost"
        assert port == 18812
        return fake

    with MT5ArchClient(_settings(), mt5_factory=factory) as client:
        info = client.ping()
        assert info.connected is True
        assert info.build == 3815
        assert fake.init_kwargs["login"] == 118248
        assert fake.init_kwargs["server"] == "WSFmarkets-Server"
        assert "password" in fake.init_kwargs

    assert fake.shutdown_called is True


def test_initialize_failure_raises() -> None:
    def factory(host: str, port: int) -> FailingInitMT5:
        return FailingInitMT5()

    client = MT5ArchClient(_settings(), mt5_factory=factory)
    with pytest.raises(MT5NotConnectedError, match="IPC timeout"):
        client.initialize()


def test_account_info_mapping() -> None:
    fake = FakeMT5()
    client = MT5ArchClient(_settings(), mt5_factory=lambda h, p: fake)
    client.initialize()
    account = client.account_info()
    assert isinstance(account, AccountInfo)
    assert account.login == 118248
    assert account.balance == 5000.0
    assert account.equity == 4980.5
    assert account.free_margin == 4860.5
    assert account.currency == "USD"
    assert account.server == "WSFmarkets-Server"
    client.shutdown()


def test_symbol_info_eurusd() -> None:
    fake = FakeMT5()
    with MT5ArchClient(_settings(), mt5_factory=lambda h, p: fake) as client:
        sym = client.symbol_info("EURUSD")
        assert sym.symbol == "EURUSD"
        assert sym.min_lot == 0.01
        assert sym.lot_step == 0.01
        assert sym.trade_mode == "FULL"
        assert sym.digits == 5


def test_symbol_unknown_raises() -> None:
    fake = FakeMT5()
    with (
        MT5ArchClient(_settings(), mt5_factory=lambda h, p: fake) as client,
        pytest.raises(MT5ArchError, match="symbol_select"),
    ):
        client.symbol_info("NOTREAL")


def test_copy_rates() -> None:
    fake = FakeMT5()
    with MT5ArchClient(_settings(), mt5_factory=lambda h, p: fake) as client:
        result = client.copy_rates("EURUSD", timeframe="H1", count=3)
        assert result.symbol == "EURUSD"
        assert result.timeframe == "H1"
        assert len(result.candles) == 3
        assert result.candles[0].open == 1.1
        assert "T" in result.candles[0].time  # ISO format


def test_unknown_timeframe() -> None:
    fake = FakeMT5()
    with (
        MT5ArchClient(_settings(), mt5_factory=lambda h, p: fake) as client,
        pytest.raises(MT5ArchError, match="Unknown timeframe"),
    ):
        client.copy_rates("EURUSD", timeframe="Z9")


def test_methods_require_initialize() -> None:
    client = MT5ArchClient(_settings(), mt5_factory=lambda h, p: FakeMT5())
    with pytest.raises(MT5NotConnectedError):
        client.account_info()


def test_settings_redacted_summary_hides_password() -> None:
    s = _settings()
    summary = s.redacted_summary()
    assert summary["mt5_password"] == "***"
    assert summary["mt5_login"] == 118248
