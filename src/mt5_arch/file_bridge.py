"""Read snapshots written by the Mt5ArchBridge.mq5 Expert Advisor.

Works under Wine when the official MetaTrader5 Python IPC channel fails
with (-10005, 'IPC timeout').
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mt5_arch.models import AccountInfo, Candle, CandlesResult, SymbolInfo, TerminalInfo
from mt5_arch.symbol_registry import SymbolRegistryError, load_registry, resolve

# Must match Settings.mt5_bridge_max_age (MT5_BRIDGE_MAX_AGE) and AGENTS.md.
DEFAULT_MAX_AGE_SECONDS = 15.0


class FileBridgeError(Exception):
    """Raised when the EA file bridge is unavailable or stale."""


def default_bridge_dir(wineprefix: Path | None = None) -> Path:
    """Portable-mode default: <prefix>/drive_c/Program Files/MetaTrader 5/MQL5/Files/mt5_arch."""
    prefix = (wineprefix or Path.home() / ".mt5").expanduser()
    return (
        prefix
        / "drive_c"
        / "Program Files"
        / "MetaTrader 5"
        / "MQL5"
        / "Files"
        / "mt5_arch"
    )


class FileBridgeClient:
    """Poll JSON snapshots from Mt5ArchBridge.mq5."""

    def __init__(
        self,
        bridge_dir: Path | None = None,
        *,
        max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
        wineprefix: Path | None = None,
        broker: str | None = None,
    ) -> None:
        self.bridge_dir = Path(bridge_dir) if bridge_dir else default_bridge_dir(wineprefix)
        self.max_age_seconds = max_age_seconds
        self.broker = broker

    def _mapped_symbol(self, symbol: str) -> str:
        if not self.broker:
            return symbol
        try:
            return resolve(load_registry(), self.broker, symbol).broker_symbol
        except SymbolRegistryError as exc:
            raise FileBridgeError(
                f"unmapped symbol {symbol!r} on broker {self.broker!r} "
                f"(fail closed; no raw-name fallback): {exc}"
            ) from exc

    def ensure_alive(self) -> None:
        hb = self.bridge_dir / "heartbeat.txt"
        account = self.bridge_dir / "account.json"
        if not account.exists():
            raise FileBridgeError(
                f"No account.json in {self.bridge_dir}. "
                "Attach Mt5ArchBridge EA to a chart and enable Algo Trading (green)."
            )
        if not hb.exists():
            raise FileBridgeError(
                f"No heartbeat.txt in {self.bridge_dir}. "
                "Attach Mt5ArchBridge EA to a chart and enable Algo Trading (green)."
            )
        age = time.time() - hb.stat().st_mtime
        if age > self.max_age_seconds:
            raise FileBridgeError(
                f"Bridge data is stale ({age:.0f}s old). "
                "Is the EA running with Algo Trading enabled?"
            )

    def _read_json(self, name: str) -> Any:
        path = self.bridge_dir / name
        if not path.exists():
            raise FileBridgeError(f"Missing {path}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise FileBridgeError(f"Corrupt {path.name}: {exc}") from exc

    def ping(self) -> TerminalInfo:
        self.ensure_alive()
        data = self._read_json("terminal.json")
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
        self.ensure_alive()
        data = self._read_json("account.json")
        return AccountInfo(
            login=int(data.get("login", 0) or 0),
            balance=float(data.get("balance", 0) or 0),
            equity=float(data.get("equity", 0) or 0),
            margin=float(data.get("margin", 0) or 0),
            free_margin=float(data.get("free_margin", 0) or 0),
            margin_level=float(data.get("margin_level", 0) or 0),
            currency=str(data.get("currency", "") or ""),
            leverage=int(data.get("leverage", 0) or 0),
            server=str(data.get("server", "") or ""),
            name=str(data.get("name", "") or ""),
            company=str(data.get("company", "") or ""),
        )

    def symbol_info(self, symbol: str) -> SymbolInfo:
        self.ensure_alive()
        rows = self._read_json("symbols.json")
        if not isinstance(rows, list):
            raise FileBridgeError("symbols.json is not a list")
        want = self._mapped_symbol(symbol).upper()
        for row in rows:
            if str(row.get("symbol", "")).upper() == want:
                return SymbolInfo(
                    symbol=str(row["symbol"]),
                    min_lot=float(row.get("min_lot", 0.01)),
                    max_lot=float(row.get("max_lot", 100)),
                    lot_step=float(row.get("lot_step", 0.01)),
                    contract_size=float(row.get("contract_size", 100000)),
                    digits=int(row.get("digits", 5)),
                    point=float(row.get("point", 0.00001)),
                    tick_value=float(row.get("tick_value", 0)),
                    tick_size=float(row.get("tick_size", 0)),
                    trade_mode=str(row.get("trade_mode", "FULL")),
                )
        raise FileBridgeError(
            f"Symbol {symbol!r} not in bridge export. "
            "Add it to EA input InpSymbols and ensure it is in Market Watch."
        )

    def copy_rates(self, symbol: str, timeframe: str = "H1", count: int = 200) -> CandlesResult:
        self.ensure_alive()
        tf = timeframe.upper()
        file_symbol = self._mapped_symbol(symbol)
        path = self.bridge_dir / f"candles_{file_symbol}_{tf}.json"
        if not path.exists():
            # try case variants
            matches = list(self.bridge_dir.glob(f"candles_{file_symbol}_*.json"))
            raise FileBridgeError(
                f"Missing {path.name}. Available: {[p.name for p in matches[:10]]}"
            )
        data = self._read_json(path.name)
        if not isinstance(data, dict):
            raise FileBridgeError(f"{path.name} is not an object")
        candles_raw = data.get("candles", [])
        if count and len(candles_raw) > count:
            candles_raw = candles_raw[-count:]
        candles: list[Candle] = []
        for c in candles_raw:
            t = str(c.get("time", ""))
            # normalize to ISO-ish
            if t and "T" not in t:
                try:
                    dt = datetime.strptime(t, "%Y.%m.%d %H:%M:%S").replace(tzinfo=UTC)
                    t = dt.isoformat()
                except ValueError:
                    pass
            candles.append(
                Candle(
                    time=t,
                    open=float(c["open"]),
                    high=float(c["high"]),
                    low=float(c["low"]),
                    close=float(c["close"]),
                    volume=float(c.get("volume", 0)),
                )
            )
        return CandlesResult(symbol=symbol, timeframe=tf, candles=candles)
