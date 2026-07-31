"""Typed models aligned with mt5-trading-agent bridge shapes where useful."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AccountInfo:
    """MT5 account snapshot."""

    login: int
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float
    currency: str
    leverage: int
    server: str = ""
    name: str = ""
    company: str = ""


@dataclass(frozen=True, slots=True)
class SymbolInfo:
    """MT5 symbol specification for lot sizing."""

    symbol: str
    min_lot: float
    max_lot: float
    lot_step: float
    contract_size: float
    digits: int
    point: float
    tick_value: float
    tick_size: float
    trade_mode: str


@dataclass(frozen=True, slots=True)
class Candle:
    """OHLCV bar."""

    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class CandlesResult:
    symbol: str
    timeframe: str
    candles: list[Candle]


@dataclass(frozen=True, slots=True)
class TerminalInfo:
    """Terminal / connection diagnostics."""

    connected: bool
    name: str
    path: str
    company: str
    build: int
    trade_allowed: bool
    tradeapi_disabled: bool
