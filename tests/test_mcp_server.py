"""Offline unit tests for the read-only mt5-arch MCP server."""

from __future__ import annotations

import io
import json
from pathlib import Path

from mt5_arch.config import Settings
from mt5_arch.mcp_server import (
    MAX_CANDLE_COUNT,
    SERVER_INSTRUCTIONS,
    TOOL_NAMES,
    McpSession,
    call_tool,
    handle_message,
    initialize_result,
    read_message,
    run_stdio,
    write_message,
)
from mt5_arch.models import AccountInfo, Candle, CandlesResult, SymbolInfo, TerminalInfo


class FakeClient:
    def ping(self) -> TerminalInfo:
        return TerminalInfo(
            connected=True,
            name="MetaTrader 5",
            path=r"C:\Program Files\MetaTrader 5\terminal64.exe",
            company="MetaQuotes",
            build=6090,
            trade_allowed=True,
            tradeapi_disabled=False,
        )

    def account_info(self) -> AccountInfo:
        return AccountInfo(
            login=118248,
            balance=5000.0,
            equity=4980.5,
            margin=120.0,
            free_margin=4860.5,
            margin_level=4150.42,
            currency="USD",
            leverage=100,
            server="WSFmarkets-Server",
            name="Demo",
            company="WSFunded",
        )

    def symbol_info(self, symbol: str) -> SymbolInfo:
        return SymbolInfo(
            symbol=symbol.upper(),
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            contract_size=100000.0,
            digits=5,
            point=0.00001,
            tick_value=1.0,
            tick_size=0.00001,
            trade_mode="FULL",
        )

    def copy_rates(self, symbol: str, timeframe: str = "H1", count: int = 10) -> CandlesResult:
        candles = [
            Candle(
                time="2026-01-02T00:00:00+00:00",
                open=1.1,
                high=1.2,
                low=1.0,
                close=1.15,
                volume=100.0,
            )
        ]
        return CandlesResult(symbol=symbol, timeframe=timeframe.upper(), candles=candles[:count])


def _session(password: str | None = "secret-pass") -> McpSession:
    settings = Settings(
        _env_file=None,
        mt5_backend="file",
        mt5_password=password,
        mt5_login=118248,
        mt5_server="WSFmarkets-Server",
    )
    return McpSession(settings, client=FakeClient())


def _text(result: dict) -> str:
    return result["content"][0]["text"]


def test_initialize_echoes_supported_protocol() -> None:
    result = initialize_result({"protocolVersion": "2025-03-26"})
    assert result["protocolVersion"] == "2025-03-26"
    assert result["serverInfo"]["name"] == "mt5-arch"
    assert result["capabilities"]["tools"]["listChanged"] is False
    assert "read-only" in result["instructions"].lower()


def test_initialize_falls_back_on_unknown_protocol() -> None:
    result = initialize_result({"protocolVersion": "1999-01-01"})
    assert result["protocolVersion"] == "2024-11-05"


def test_handle_initialize_and_notification() -> None:
    session = _session()
    reply = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
        },
        session,
    )
    assert reply is not None
    assert reply["id"] == 1
    assert reply["result"]["serverInfo"]["name"] == "mt5-arch"
    assert handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}, session) is None


def test_tools_list_is_read_only() -> None:
    session = _session()
    reply = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, session)
    assert reply is not None
    names = {t["name"] for t in reply["result"]["tools"]}
    assert names == TOOL_NAMES
    assert names == {"ping", "account", "symbols", "candles", "config", "brokers", "resolve"}
    forbidden = {
        "order_send",
        "ordersend",
        "buy",
        "sell",
        "positions",
        "trade",
        "close",
    }
    assert names.isdisjoint(forbidden)
    blob = json.dumps(reply).lower()
    assert "ordersend" not in blob
    assert "order_send" not in blob


def test_ping_and_account_tools() -> None:
    session = _session()
    ping = call_tool("ping", {}, session)
    assert ping["isError"] is False
    assert json.loads(_text(ping))["build"] == 6090

    account = call_tool("account", {}, session)
    payload = json.loads(_text(account))
    assert payload["login"] == 118248
    assert payload["currency"] == "USD"


def test_symbols_accepts_array_or_string() -> None:
    session = _session()
    one = json.loads(_text(call_tool("symbols", {"symbol": "eurusd"}, session)))
    assert one["symbol"] == "EURUSD"
    many = json.loads(_text(call_tool("symbols", {"symbols": ["EURUSD", "XAUUSD"]}, session)))
    assert [row["symbol"] for row in many] == ["EURUSD", "XAUUSD"]


def test_candles_requires_symbol_and_caps_count() -> None:
    session = _session()
    missing = call_tool("candles", {}, session)
    assert missing["isError"] is True
    too_big = call_tool("candles", {"symbol": "EURUSD", "count": MAX_CANDLE_COUNT + 1}, session)
    assert too_big["isError"] is True
    ok = call_tool("candles", {"symbol": "EURUSD", "timeframe": "h1", "count": 1}, session)
    payload = json.loads(_text(ok))
    assert payload["symbol"] == "EURUSD"
    assert payload["timeframe"] == "H1"
    assert len(payload["candles"]) == 1


def test_config_redacts_password() -> None:
    session = _session(password="hunter2")
    payload = json.loads(_text(call_tool("config", {}, session)))
    assert payload["mt5_password"] == "***"
    assert "hunter2" not in json.dumps(payload)


def test_brokers_and_resolve_need_no_client() -> None:
    session = _session()
    listed = json.loads(_text(call_tool("brokers", {}, session)))
    names = {row["name"] for row in listed}
    assert {"vantage", "wsf", "fpmarkets"} <= names
    assert all("PASSWORD" not in row for row in listed)

    mapped = json.loads(
        _text(call_tool("resolve", {"broker": "fpmarkets", "symbol": "XAUUSD"}, session))
    )
    assert mapped["canonical"] == "XAUUSD"
    assert mapped["broker_symbol"] == "XAUUSD.r"


def test_unknown_tool_and_method() -> None:
    session = _session()
    tool = call_tool("order_send", {"symbol": "EURUSD"}, session)
    assert tool["isError"] is True
    reply = handle_message({"jsonrpc": "2.0", "id": 9, "method": "orders/create"}, session)
    assert reply is not None
    assert reply["error"]["code"] == -32601


def test_stdio_roundtrip() -> None:
    session = _session()
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "ping", "arguments": {}},
    }
    stdin = io.StringIO(json.dumps(req) + "\n")
    stdout = io.StringIO()
    assert run_stdio(stdin, stdout, session) == 0
    reply = json.loads(stdout.getvalue().strip())
    assert reply["id"] == 1
    assert json.loads(reply["result"]["content"][0]["text"])["connected"] is True


def test_read_content_length_frame() -> None:
    body = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping"})
    raw = f"Content-Length: {len(body.encode())}\r\n\r\n{body}"
    message = read_message(io.StringIO(raw))
    assert message is not None
    assert message["method"] == "ping"


def test_write_message_is_newline_json() -> None:
    buf = io.StringIO()
    write_message(buf, {"jsonrpc": "2.0", "id": 1, "result": {}})
    assert buf.getvalue().endswith("\n")
    assert json.loads(buf.getvalue())["id"] == 1


def test_mcp_source_never_places_orders() -> None:
    src = Path(__file__).resolve().parents[1] / "src" / "mt5_arch" / "mcp_server.py"
    text = src.read_text(encoding="utf-8")
    assert "OrderSend" not in text
    assert "order_send" not in text
    assert "backtest" not in text
    assert "live_trader" not in text
    assert SERVER_INSTRUCTIONS
    assert "no order" in SERVER_INSTRUCTIONS.lower() or "No order" in SERVER_INSTRUCTIONS


def test_cli_parser_has_mcp() -> None:
    from mt5_arch.cli import build_parser

    args = build_parser().parse_args(["mcp"])
    assert args.command == "mcp"
