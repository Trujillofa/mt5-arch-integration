"""Read snapshots written by the Mt5ArchBridge.mq5 Expert Advisor.

Works under Wine when the official MetaTrader5 Python IPC channel fails
with (-10005, 'IPC timeout').
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mt5_arch.models import AccountInfo, Candle, CandlesResult, Deal, SymbolInfo, TerminalInfo
from mt5_arch.symbol_registry import SymbolRegistryError, load_registry, resolve

# Must match Settings.mt5_bridge_max_age (MT5_BRIDGE_MAX_AGE) and AGENTS.md.
DEFAULT_MAX_AGE_SECONDS = 15.0

# Exact header written by Mt5ArchBridge.mq5 DumpDealsIfRequested().
DEAL_CSV_COLUMNS = (
    "time",
    "deal_id",
    "order_id",
    "position_id",
    "symbol",
    "type",
    "entry",
    "volume",
    "price",
    "profit",
    "swap",
    "commission",
    "fee",
    "reason",
    "magic",
    "comment",
)

# dump_deals.done body: rows=<N> from=<ts> to=<ts> at=<ts>
_DUMP_DEALS_DONE_RE = re.compile(
    r"^rows=(?P<rows>\d+)\s+"
    r"from=(?P<from>\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"to=(?P<to>\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"at=(?P<at>\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2})\s*$"
)

DEFAULT_DEAL_DUMP_TIMEOUT_SECONDS = 30.0


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
        if not isinstance(candles_raw, list):
            raise FileBridgeError(f"{path.name}: 'candles' is not a list")
        if count and len(candles_raw) > count:
            candles_raw = candles_raw[-count:]
        candles: list[Candle] = []
        for i, c in enumerate(candles_raw):
            if not isinstance(c, dict):
                raise FileBridgeError(f"{path.name}: candle {i} is not an object")
            t = str(c.get("time", ""))
            # normalize to ISO-ish
            if t and "T" not in t:
                try:
                    dt = datetime.strptime(t, "%Y.%m.%d %H:%M:%S").replace(tzinfo=UTC)
                    t = dt.isoformat()
                except ValueError:
                    pass
            # A torn or truncated EA write can still parse as JSON; a missing or
            # non-numeric OHLC field is bridge data being unusable, not a bug here.
            try:
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
            except (KeyError, TypeError, ValueError) as exc:
                raise FileBridgeError(f"{path.name}: bad candle {i}: {exc}") from exc
        return CandlesResult(symbol=symbol, timeframe=tf, candles=candles)

    def deals(self) -> list[Deal]:
        """Read deals_export.csv. Completeness is dump_deals.done only — not heartbeat.

        WriteAll() writes heartbeat.txt last, then OnTimer calls DumpDealsIfRequested()
        *after* WriteAll(). A fresh heartbeat therefore does not mean the CSV is
        complete. Put() is a truncate-write with no temp+rename, so a torn CSV or
        torn .done raises FileBridgeError.
        """
        done_path = self.bridge_dir / "dump_deals.done"
        csv_path = self.bridge_dir / "deals_export.csv"
        if not done_path.exists():
            raise FileBridgeError(
                f"Missing dump_deals.done in {self.bridge_dir}. "
                "A fresh heartbeat does not mean deals_export.csv is complete "
                "(the EA writes heartbeat.txt in WriteAll() before the dump). "
                "Use mt5-arch deals --request to touch dump_deals.request and wait."
            )
        done_text = _read_bridge_text(done_path, label="dump_deals.done")
        expected_rows = _parse_dump_deals_done(done_text)
        if not csv_path.exists():
            raise FileBridgeError(f"Missing deals_export.csv in {self.bridge_dir}")
        csv_text = _read_bridge_text(csv_path, label="deals_export.csv")
        rows = _parse_deals_csv(csv_text)
        if len(rows) != expected_rows:
            raise FileBridgeError(
                f"deals_export.csv row count {len(rows)} != dump_deals.done rows={expected_rows}"
            )
        return rows

    def request_deals(
        self,
        *,
        timeout: float = DEFAULT_DEAL_DUMP_TIMEOUT_SECONDS,
        poll_interval: float = 0.05,
    ) -> list[Deal]:
        """Touch dump_deals.request, wait for a *fresh* dump_deals.done, then read.

        A stale .done from a previous dump is not completion. Fail closed on timeout.
        Writes into the live Wine prefix — callers must opt in (CLI --request).

        Requires a live EA: ensure_alive() first, so a detached EA reports "bridge
        down" now instead of after the whole timeout. Reading (deals()) deliberately
        does not, so a dump stays readable post-mortem.

        On timeout the request file is left in place on purpose — the EA picks it up
        whenever it next runs, and a later plain ``deals()`` reads the result.
        """
        self.ensure_alive()
        done_path = self.bridge_dir / "dump_deals.done"
        req_path = self.bridge_dir / "dump_deals.request"
        prev_mtime_ns = done_path.stat().st_mtime_ns if done_path.exists() else -1
        prev_content = done_path.read_bytes() if done_path.exists() else b""
        req_path.write_text("", encoding="utf-8")
        req_mtime_ns = req_path.stat().st_mtime_ns
        deadline = time.monotonic() + timeout
        while True:
            if _fresh_deal_dump_ready(
                req_path,
                done_path,
                req_mtime_ns=req_mtime_ns,
                prev_mtime_ns=prev_mtime_ns,
                prev_content=prev_content,
            ):
                return self.deals()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise FileBridgeError(
                    f"Timed out after {timeout}s waiting for dump_deals.done newer than "
                    f"dump_deals.request in {self.bridge_dir}. The request file is left "
                    "in place: the EA dumps on its next timer tick, so re-run "
                    "'mt5-arch deals' (without --request) to read it."
                )
            time.sleep(min(poll_interval, remaining))


def _read_bridge_text(path: Path, *, label: str) -> str:
    """Read a file the EA wrote with FILE_TXT|FILE_ANSI.

    ANSI is the Wine host codepage, not UTF-8, so a broker-set deal comment or a
    non-ASCII symbol name is not valid UTF-8. Decode strict UTF-8 first (correct if
    the EA ever switches), fall back to cp1252 so one accented byte does not cost the
    whole dump. Never let UnicodeDecodeError — a ValueError — escape as a raw error.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise FileBridgeError(f"Cannot read {label}: {exc}") from exc
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _parse_dump_deals_done(text: str) -> int:
    match = _DUMP_DEALS_DONE_RE.match(text.strip())
    if not match:
        raise FileBridgeError(f"Corrupt dump_deals.done: {text!r}")
    return int(match.group("rows"))


def _fresh_deal_dump_ready(
    req_path: Path,
    done_path: Path,
    *,
    req_mtime_ns: int,
    prev_mtime_ns: int,
    prev_content: bytes,
) -> bool:
    if req_path.exists():
        return False
    if not done_path.exists():
        return False
    try:
        st = done_path.stat()
        content = done_path.read_bytes()
    except OSError:
        return False
    # Spec: do not accept a .done *older* than the request. Equal mtime is ok
    # if the EA also deleted the request file (it deletes request, then Put .done).
    if st.st_mtime_ns < req_mtime_ns:
        return False
    stale_previous = (
        prev_mtime_ns >= 0
        and st.st_mtime_ns <= prev_mtime_ns
        and content == prev_content
    )
    return not stale_previous


def _parse_deals_csv(text: str) -> list[Deal]:
    try:
        raw_rows = list(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        raise FileBridgeError(f"Corrupt deals_export.csv: {exc}") from exc
    if not raw_rows:
        raise FileBridgeError("deals_export.csv is empty (missing header)")
    header = tuple(raw_rows[0])
    if header != DEAL_CSV_COLUMNS:
        raise FileBridgeError(
            f"deals_export.csv header {list(header)!r} does not match {list(DEAL_CSV_COLUMNS)!r}"
        )
    deals: list[Deal] = []
    for i, row in enumerate(raw_rows[1:]):
        if not row or (len(row) == 1 and row[0] == ""):
            continue
        if len(row) != len(DEAL_CSV_COLUMNS):
            raise FileBridgeError(
                f"deals_export.csv: torn/truncated row {i} "
                f"({len(row)} columns, expected {len(DEAL_CSV_COLUMNS)})"
            )
        try:
            deals.append(_deal_from_row(row))
        except (TypeError, ValueError) as exc:
            raise FileBridgeError(f"deals_export.csv: bad deal {i}: {exc}") from exc
    return deals


def _deal_from_row(row: list[str]) -> Deal:
    return Deal(
        time=row[0],
        deal_id=int(row[1]),
        order_id=int(row[2]),
        position_id=int(row[3]),
        symbol=row[4],
        type=row[5],
        entry=row[6],
        volume=float(row[7]),
        price=float(row[8]),
        profit=float(row[9]),
        swap=float(row[10]),
        commission=float(row[11]),
        fee=float(row[12]),
        reason=int(row[13]),
        magic=int(row[14]),
        comment=row[15],
    )
