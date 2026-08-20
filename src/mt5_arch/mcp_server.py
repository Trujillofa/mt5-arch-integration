"""Read-only MCP stdio server wrapping the existing mt5-arch CLI surface.

This is the Linux/Wine path for the MetaTrader 5 AI Assistant / MCP workflow
(build 6060+, see docs/HOWTO-MT5-AI-MCP.md). It is not MetaQuotes' in-terminal
assistant and it never places orders.

Transport: JSON-RPC 2.0, newline-delimited JSON on stdin/stdout (MCP stdio).
Content-Length (LSP-style) frames are accepted on read. Logs go to stderr.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import asdict
from typing import Any, TextIO

from mt5_arch import __version__
from mt5_arch.brokers import list_broker_profiles, load_broker_profile
from mt5_arch.client import MT5ArchClient, MT5ArchError
from mt5_arch.config import Settings
from mt5_arch.file_bridge import FileBridgeError
from mt5_arch.symbol_registry import (
    SymbolRegistryError,
    load_registry,
    resolve as resolve_symbol,
)

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
SUPPORTED_PROTOCOL_VERSIONS = frozenset(
    {"2024-11-05", "2025-03-26", "2025-06-18"}
)
MAX_CANDLE_COUNT = 500
SERVER_INSTRUCTIONS = (
    "Read-only mt5-arch tools over the file bridge (or RPyC). "
    "No order placement, no live trading, no password fields. "
    "Call ping before account/symbols/candles. "
    "config is redacted. Prefer --json-equivalent structured results."
)

_SPLIT_SYMBOLS = re.compile(r"[\s,]+")


def _tool(
    name: str,
    description: str,
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return {
        "name": name,
        "description": description,
        "inputSchema": schema,
    }


TOOL_DEFS: list[dict[str, Any]] = [
    _tool(
        "ping",
        "Check file-bridge or RPyC connectivity. Returns terminal name, build, "
        "and trade_allowed. Does not place orders.",
    ),
    _tool(
        "account",
        "Account snapshot: login, balance, equity, margin, currency, leverage, "
        "server, company. Read-only. Does not place orders.",
    ),
    _tool(
        "symbols",
        "Symbol specs (lots, digits, tick) for names in the EA InpSymbols export. "
        "Pass symbols as an array or a single symbol string.",
        {
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "description": "Symbol names, e.g. [\"EURUSD\", \"XAUUSD\"]",
            },
            "symbol": {
                "type": "string",
                "description": "Single symbol (alternative to symbols)",
            },
        },
    ),
    _tool(
        "candles",
        "Recent OHLCV bars from the file-bridge snapshot or RPyC copy_rates. "
        "Read-only. count is capped at 500.",
        {
            "symbol": {"type": "string", "description": "Symbol name, e.g. EURUSD"},
            "timeframe": {
                "type": "string",
                "description": "Timeframe (M1, M5, M15, H1, H4, D1, ...). Default: H1",
            },
            "count": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_CANDLE_COUNT,
                "description": "Number of bars (default 10, max 500)",
            },
        },
        required=["symbol"],
    ),
    _tool(
        "config",
        "Redacted mt5-arch settings. Password is never returned in plaintext.",
    ),
    _tool(
        "brokers",
        "List multi-broker profiles from config/brokers/*.env (no passwords, "
        "no MT5 connection). Optional name shows one profile.",
        {
            "name": {
                "type": "string",
                "description": "Optional profile name (vantage, wsf, fpmarkets, ...)",
            },
        },
    ),
    _tool(
        "resolve",
        "Map canonical ↔ broker symbol via config/symbols/registry.json. "
        "No MT5 connection.",
        {
            "broker": {"type": "string", "description": "vantage|fpmarkets|exness|wsf"},
            "symbol": {"type": "string", "description": "Canonical or broker symbol"},
        },
        required=["broker", "symbol"],
    ),
]

TOOL_NAMES = frozenset(t["name"] for t in TOOL_DEFS)


class McpSession:
    """Lazy client holder. config/brokers/resolve do not open a bridge."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: Any | None = None,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self._client = client
        self._client_factory = client_factory
        self._owns_client = client is None
        self._rpyc_entered = False

    def client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory()
            return self._client
        from mt5_arch.cli import _open_client

        opened = _open_client(self.settings)
        if isinstance(opened, MT5ArchClient):
            self._client = opened.__enter__()
            self._rpyc_entered = True
        else:
            self._client = opened
        return self._client

    def close(self) -> None:
        client = self._client
        self._client = None
        if not self._owns_client or client is None:
            return
        if self._rpyc_entered and isinstance(client, MT5ArchClient):
            client.__exit__(None, None, None)


def _rpc_result(msg_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _rpc_error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": code, "message": message},
    }


def _tool_text(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


def _as_symbols(args: Mapping[str, Any]) -> list[str]:
    if "symbols" in args and args["symbols"] is not None:
        raw = args["symbols"]
        if isinstance(raw, str):
            parts = [s for s in _SPLIT_SYMBOLS.split(raw) if s]
        elif isinstance(raw, list):
            parts = [str(s).strip() for s in raw if str(s).strip()]
        else:
            raise ValueError("symbols must be an array or a string")
        if parts:
            return parts
    symbol = args.get("symbol")
    if isinstance(symbol, str) and symbol.strip():
        return [symbol.strip()]
    raise ValueError("symbols is required (array or symbol string)")


def _as_count(raw: Any, default: int = 10) -> int:
    if raw is None:
        return default
    try:
        count = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("count must be an integer") from exc
    if count < 1 or count > MAX_CANDLE_COUNT:
        raise ValueError(f"count must be between 1 and {MAX_CANDLE_COUNT}")
    return count


def call_tool(name: str, arguments: Mapping[str, Any] | None, session: McpSession) -> dict[str, Any]:
    """Dispatch a tool. Returns MCP tools/call result (never a JSON-RPC error)."""
    args = dict(arguments or {})
    try:
        if name == "ping":
            return _tool_text(asdict(session.client().ping()))
        if name == "account":
            return _tool_text(asdict(session.client().account_info()))
        if name == "symbols":
            rows = [asdict(session.client().symbol_info(s)) for s in _as_symbols(args)]
            return _tool_text(rows if len(rows) > 1 else rows[0])
        if name == "candles":
            symbol = str(args.get("symbol") or "").strip()
            if not symbol:
                raise ValueError("symbol is required")
            timeframe = str(args.get("timeframe") or "H1")
            count = _as_count(args.get("count"))
            result = session.client().copy_rates(symbol, timeframe=timeframe, count=count)
            return _tool_text(
                {
                    "symbol": result.symbol,
                    "timeframe": result.timeframe,
                    "candles": [asdict(c) for c in result.candles],
                }
            )
        if name == "config":
            return _tool_text(session.settings.redacted_summary())
        if name == "brokers":
            name_arg = args.get("name")
            if name_arg:
                profile = load_broker_profile(str(name_arg))
                return _tool_text(
                    {
                        "name": profile.name,
                        "path": str(profile.path),
                        **profile.as_exports(),
                    }
                )
            rows = [
                {
                    "name": p.name,
                    "login": p.login,
                    "server": p.server,
                    "wineprefix": p.wineprefix,
                    "backend": p.backend,
                }
                for p in list_broker_profiles()
            ]
            return _tool_text(rows)
        if name == "resolve":
            broker = str(args.get("broker") or "").strip()
            symbol = str(args.get("symbol") or "").strip()
            if not broker or not symbol:
                raise ValueError("broker and symbol are required")
            mapping = resolve_symbol(load_registry(), broker, symbol)
            return _tool_text(
                {
                    "broker": mapping.broker,
                    "canonical": mapping.canonical,
                    "broker_symbol": mapping.broker_symbol,
                    "expect": mapping.expect,
                }
            )
        return _tool_text(f"Unknown tool: {name}", is_error=True)
    except (
        FileBridgeError,
        FileNotFoundError,
        ValueError,
        OSError,
        MT5ArchError,
        SymbolRegistryError,
    ) as exc:
        return _tool_text(str(exc), is_error=True)
    except Exception as exc:  # noqa: BLE001
        logger.exception("mcp tool %s failed", name)
        return _tool_text(str(exc), is_error=True)


def initialize_result(params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    requested = ""
    if params:
        requested = str(params.get("protocolVersion") or "")
    version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
    return {
        "protocolVersion": version,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "mt5-arch", "version": __version__},
        "instructions": SERVER_INSTRUCTIONS,
    }


def handle_message(message: Mapping[str, Any], session: McpSession) -> dict[str, Any] | None:
    """Handle one JSON-RPC message. Notifications return None."""
    method = message.get("method")
    msg_id = message.get("id")
    if not isinstance(method, str):
        if msg_id is None:
            return None
        return _rpc_error(msg_id, -32600, "Invalid Request")
    if method.startswith("notifications/") or msg_id is None:
        return None
    params = message.get("params")
    if params is None:
        params = {}
    if not isinstance(params, Mapping):
        return _rpc_error(msg_id, -32602, "Invalid params")
    if method == "initialize":
        return _rpc_result(msg_id, initialize_result(params))
    if method == "ping":
        return _rpc_result(msg_id, {})
    if method == "tools/list":
        return _rpc_result(msg_id, {"tools": TOOL_DEFS})
    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or not name:
            return _rpc_error(msg_id, -32602, "tools/call requires name")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, Mapping):
            return _rpc_error(msg_id, -32602, "arguments must be an object")
        return _rpc_result(msg_id, call_tool(name, arguments, session))
    return _rpc_error(msg_id, -32601, f"Method not found: {method}")


def read_message(stdin: TextIO) -> dict[str, Any] | None:
    """Read one MCP message. Returns None on EOF."""
    header_len: int | None = None
    while True:
        line = stdin.readline()
        if line == "":
            return None
        if line.lower().startswith("content-length:"):
            try:
                header_len = int(line.split(":", 1)[1].strip())
            except ValueError:
                header_len = None
            continue
        if header_len is not None:
            if line.strip() == "":
                body = stdin.read(header_len)
                if body == "":
                    return None
                return json.loads(body)
            continue
        stripped = line.strip()
        if not stripped:
            continue
        return json.loads(stripped)


def write_message(stdout: TextIO, message: Mapping[str, Any]) -> None:
    stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    stdout.flush()


def run_stdio(stdin: TextIO, stdout: TextIO, session: McpSession) -> int:
    while True:
        try:
            message = read_message(stdin)
        except json.JSONDecodeError as exc:
            write_message(stdout, _rpc_error(None, -32700, f"Parse error: {exc}"))
            continue
        if message is None:
            return 0
        reply = handle_message(message, session)
        if reply is not None:
            write_message(stdout, reply)


def run_stdio_server(settings: Settings | None = None) -> int:
    session = McpSession(settings)
    try:
        return run_stdio(sys.stdin, sys.stdout, session)
    except KeyboardInterrupt:
        return 130
    finally:
        session.close()


def main() -> int:
    return run_stdio_server(Settings())


if __name__ == "__main__":
    raise SystemExit(main())
