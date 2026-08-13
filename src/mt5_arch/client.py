"""MT5 client wrapping mt5linux for native Linux Python."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, TypeVar

from mt5_arch.config import Settings
from mt5_arch.models import AccountInfo, Candle, CandlesResult, SymbolInfo, TerminalInfo

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Official MetaTrader5 timeframe constants (copied to avoid Windows-only import).
TIMEFRAME_MAP: dict[str, int] = {
    "M1": 1,
    "M2": 2,
    "M3": 3,
    "M4": 4,
    "M5": 5,
    "M6": 6,
    "M10": 10,
    "M12": 12,
    "M15": 15,
    "M20": 20,
    "M30": 30,
    "H1": 16385,
    "H2": 16386,
    "H3": 16387,
    "H4": 16388,
    "H6": 16390,
    "H8": 16392,
    "H12": 16396,
    "D1": 16408,
    "W1": 32769,
    "MN1": 49153,
}

# ORDER_MODE / SYMBOL_TRADE_MODE labels (subset used by lot sizing).
TRADE_MODE_LABELS: dict[int, str] = {
    0: "DISABLED",
    1: "LONGONLY",
    2: "SHORTONLY",
    3: "CLOSEONLY",
    4: "FULL",
}


class MT5ArchError(Exception):
    """Base error for the integration layer."""


class MT5NotConnectedError(MT5ArchError):
    """Raised when initialize() fails or session is not open."""


class MT5ArchClient:
    """Context-managed client over mt5linux.MetaTrader5."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        mt5_factory: Callable[[str, int], Any] | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self._mt5_factory = mt5_factory
        self._mt5: Any | None = None
        self._initialized = False

    def __enter__(self) -> MT5ArchClient:
        self.initialize()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.shutdown()

    @property
    def mt5(self) -> Any:
        if self._mt5 is None or not self._initialized:
            raise MT5NotConnectedError("MT5 session is not initialized; call initialize() first")
        return self._mt5

    def initialize(self) -> bool:
        """Connect to mt5server (RPyC) and optionally log into the account."""
        if self._initialized:
            return True

        host = self.settings.mt5_rpyc_host
        port = self.settings.mt5_rpyc_port

        if self._mt5_factory is not None:
            self._mt5 = self._mt5_factory(host, port)
        else:
            from mt5linux import MetaTrader5  # type: ignore[import-untyped]

            # mt5linux MetaTrader5(host, port) — host defaults to localhost
            self._mt5 = MetaTrader5(host=host, port=port)

        path = None
        if self.settings.mt5_terminal_path is not None:
            path = str(self.settings.mt5_terminal_path)

        kwargs: dict[str, Any] = {}
        if path:
            kwargs["path"] = path
        if self.settings.has_credentials():
            kwargs["login"] = int(self.settings.mt5_login)  # type: ignore[arg-type]
            kwargs["password"] = self.settings.mt5_password
            kwargs["server"] = self.settings.mt5_server

        logger.info(
            "Initializing MT5 via RPyC %s:%s (login=%s server=%s)",
            host,
            port,
            self.settings.mt5_login,
            self.settings.mt5_server,
        )

        mt5 = self._mt5
        if mt5 is None:
            raise MT5NotConnectedError("failed to construct MetaTrader5 client")

        ok = bool(mt5.initialize(**kwargs) if kwargs else mt5.initialize())
        if not ok:
            last: object = "unknown"
            with suppress(Exception):
                last = mt5.last_error()
            self._mt5 = None
            self._initialized = False
            raise MT5NotConnectedError(f"mt5.initialize() failed: {last}")

        self._initialized = True
        return True

    def shutdown(self) -> None:
        if self._mt5 is not None:
            try:
                self._mt5.shutdown()
            except Exception as exc:  # noqa: BLE001
                logger.warning("mt5.shutdown() raised: %s", exc)
        self._mt5 = None
        self._initialized = False

    def ping(self) -> TerminalInfo:
        """Lightweight connectivity check."""
        info = self.terminal_info()
        version = self.mt5.version()
        logger.debug("MT5 version: %s", version)
        return info

    def terminal_info(self) -> TerminalInfo:
        raw = self.mt5.terminal_info()
        if raw is None:
            raise MT5ArchError(f"terminal_info() returned None: {self.mt5.last_error()}")
        data = _as_dict(raw)
        return TerminalInfo(
            connected=bool(data.get("connected", False)),
            name=str(data.get("name", "")),
            path=str(data.get("path", "")),
            company=str(data.get("company", "")),
            build=int(data.get("build", 0) or 0),
            trade_allowed=bool(data.get("trade_allowed", False)),
            tradeapi_disabled=bool(data.get("tradeapi_disabled", False)),
        )

    def account_info(self) -> AccountInfo:
        raw = self.mt5.account_info()
        if raw is None:
            raise MT5ArchError(f"account_info() returned None: {self.mt5.last_error()}")
        data = _as_dict(raw)
        free_margin = data.get("margin_free", data.get("free_margin", 0.0))
        return AccountInfo(
            login=int(data.get("login", 0) or 0),
            balance=float(data.get("balance", 0.0) or 0.0),
            equity=float(data.get("equity", 0.0) or 0.0),
            margin=float(data.get("margin", 0.0) or 0.0),
            free_margin=float(free_margin or 0.0),
            margin_level=float(data.get("margin_level", 0.0) or 0.0),
            currency=str(data.get("currency", "") or ""),
            leverage=int(data.get("leverage", 0) or 0),
            server=str(data.get("server", "") or ""),
            name=str(data.get("name", "") or ""),
            company=str(data.get("company", "") or ""),
        )

    def symbol_info(self, symbol: str) -> SymbolInfo:
        if not self.mt5.symbol_select(symbol, True):
            raise MT5ArchError(f"symbol_select({symbol!r}) failed: {self.mt5.last_error()}")
        raw = self.mt5.symbol_info(symbol)
        if raw is None:
            raise MT5ArchError(f"symbol_info({symbol!r}) returned None: {self.mt5.last_error()}")
        data = _as_dict(raw)
        trade_mode_raw = data.get("trade_mode", 4)
        try:
            trade_mode = TRADE_MODE_LABELS.get(int(trade_mode_raw), str(trade_mode_raw))
        except (TypeError, ValueError):
            trade_mode = str(trade_mode_raw)
        return SymbolInfo(
            symbol=str(data.get("name", symbol) or symbol),
            min_lot=float(data.get("volume_min", 0.01) or 0.01),
            max_lot=float(data.get("volume_max", 100.0) or 100.0),
            lot_step=float(data.get("volume_step", 0.01) or 0.01),
            contract_size=float(data.get("trade_contract_size", 100000.0) or 100000.0),
            digits=int(data.get("digits", 5) or 5),
            point=float(data.get("point", 0.00001) or 0.00001),
            tick_value=float(data.get("trade_tick_value", 0.0) or 0.0),
            tick_size=float(data.get("trade_tick_size", 0.0) or 0.0),
            trade_mode=trade_mode,
            swap_long=float(data.get("swap_long", 0.0) or 0.0),
            swap_short=float(data.get("swap_short", 0.0) or 0.0),
            swap_mode=str(data.get("swap_mode", "") or ""),
            swap_rollover3days=int(data.get("swap_rollover3days", 0) or 0),
            bid=(float(data["bid"]) if data.get("bid") is not None else None),
            ask=(float(data["ask"]) if data.get("ask") is not None else None),
        )

    def copy_rates(
        self,
        symbol: str,
        timeframe: str = "H1",
        count: int = 200,
    ) -> CandlesResult:
        tf_key = timeframe.upper()
        if tf_key not in TIMEFRAME_MAP:
            raise MT5ArchError(
                f"Unknown timeframe {timeframe!r}; expected one of {sorted(TIMEFRAME_MAP)}"
            )
        if not self.mt5.symbol_select(symbol, True):
            raise MT5ArchError(f"symbol_select({symbol!r}) failed: {self.mt5.last_error()}")

        rates = self.mt5.copy_rates_from_pos(symbol, TIMEFRAME_MAP[tf_key], 0, count)
        if rates is None:
            raise MT5ArchError(
                f"copy_rates_from_pos({symbol!r}, {tf_key}) failed: {self.mt5.last_error()}"
            )

        candles: list[Candle] = []
        for row in rates:
            # numpy structured array or tuple-like
            try:
                ts = int(row["time"])
                o = float(row["open"])
                h = float(row["high"])
                low = float(row["low"])
                c = float(row["close"])
                vol = float(row["tick_volume"] if "tick_volume" in row.dtype.names else row["real_volume"])
            except (TypeError, ValueError, AttributeError, IndexError, KeyError):
                ts = int(row[0])
                o, h, low, c = float(row[1]), float(row[2]), float(row[3]), float(row[4])
                vol = float(row[5]) if len(row) > 5 else 0.0
            candles.append(
                Candle(
                    time=datetime.fromtimestamp(ts, tz=UTC).isoformat(),
                    open=o,
                    high=h,
                    low=low,
                    close=c,
                    volume=vol,
                )
            )
        return CandlesResult(symbol=symbol, timeframe=tf_key, candles=candles)


def _as_dict(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if hasattr(raw, "_asdict"):
        return dict(raw._asdict())
    if hasattr(raw, "_fields"):
        return {name: getattr(raw, name) for name in raw._fields}
    # NamedTuple-like from RPyC or SimpleNamespace
    try:
        return dict(raw)
    except Exception:  # noqa: BLE001
        pass
    result: dict[str, Any] = {}
    for key in dir(raw):
        if key.startswith("_"):
            continue
        try:
            value = getattr(raw, key)
        except Exception:  # noqa: BLE001
            continue
        if callable(value):
            continue
        result[key] = value
    return result
