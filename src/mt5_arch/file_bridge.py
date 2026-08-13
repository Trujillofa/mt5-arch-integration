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
        max_age_seconds: float = 10.0,
        wineprefix: Path | None = None,
    ) -> None:
        self.bridge_dir = Path(bridge_dir) if bridge_dir else default_bridge_dir(wineprefix)
        self.max_age_seconds = max_age_seconds

    def ensure_alive(self) -> None:
        hb = self.bridge_dir / "heartbeat.txt"
        account = self.bridge_dir / "account.json"
        if not account.exists():
            raise FileBridgeError(
                f"No account.json in {self.bridge_dir}. "
                "Attach Mt5ArchBridge EA to a chart and enable Algo Trading (green)."
            )
        # Prefer heartbeat; fall back to account mtime
        path = hb if hb.exists() else account
        age = time.time() - path.stat().st_mtime
        if age > self.max_age_seconds:
            raise FileBridgeError(
                f"Bridge data is stale ({age:.0f}s old). "
                "Is the EA running with Algo Trading enabled?"
            )

    def _read_json(self, name: str) -> Any:
        path = self.bridge_dir / name
        if not path.exists():
            raise FileBridgeError(f"Missing {path}")
        return json.loads(path.read_text(encoding="utf-8"))

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
        want = symbol.upper()
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
                    swap_long=float(row.get("swap_long", 0) or 0),
                    swap_short=float(row.get("swap_short", 0) or 0),
                    swap_mode=str(row.get("swap_mode", "") or ""),
                    swap_rollover3days=int(row.get("swap_rollover3days", 0) or 0),
                    bid=(float(row["bid"]) if row.get("bid") is not None else None),
                    ask=(float(row["ask"]) if row.get("ask") is not None else None),
                    requested=str(row.get("requested", "") or ""),
                )
        raise FileBridgeError(
            f"Symbol {symbol!r} not in bridge export. "
            "Add it to EA input InpSymbols and ensure it is in Market Watch."
        )

    def copy_rates(self, symbol: str, timeframe: str = "H1", count: int = 200) -> CandlesResult:
        self.ensure_alive()
        tf = timeframe.upper()
        path = self.bridge_dir / f"candles_{symbol}_{tf}.json"
        if not path.exists():
            # try case variants
            matches = list(self.bridge_dir.glob(f"candles_{symbol}_*.json"))
            raise FileBridgeError(
                f"Missing {path.name}. Available: {[p.name for p in matches[:10]]}"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
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
