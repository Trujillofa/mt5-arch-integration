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


def test_jsonrpc_malformed_unknown_and_invalid_params() -> None:
    session = _session()
    stdin = io.StringIO(
        "{not-json\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"})
        + "\n"
    )
    stdout = io.StringIO()
    assert run_stdio(stdin, stdout, session) == 0
    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line]
    assert lines[0]["error"]["code"] == -32700
    assert lines[0]["id"] is None
    assert lines[1]["id"] == 2
    assert "result" in lines[1]

    missing_rpc = handle_message({"id": 3, "method": "ping"}, session)
    assert missing_rpc is not None
    assert missing_rpc["error"]["code"] == -32600

    bad_params = handle_message(
        {"jsonrpc": "2.0", "id": 4, "method": "initialize", "params": []},
        session,
    )
    assert bad_params is not None
    assert bad_params["error"]["code"] == -32602

    unknown = handle_message({"jsonrpc": "2.0", "id": 5, "method": "resources/list"}, session)
    assert unknown is not None
    assert unknown["error"]["code"] == -32601


def test_notifications_vs_requests() -> None:
    session = _session()
    assert handle_message({"jsonrpc": "2.0", "method": "ping"}, session) is None
    assert handle_message({"jsonrpc": "2.0", "method": "notifications/cancelled"}, session) is None

    null_id = handle_message({"jsonrpc": "2.0", "id": None, "method": "ping"}, session)
    assert null_id is not None
    assert null_id["id"] is None
    assert "result" in null_id


def test_batch_and_non_object_are_invalid_requests() -> None:
    session = _session()
    stdin = io.StringIO(
        json.dumps([{"jsonrpc": "2.0", "id": 1, "method": "ping"}]) + "\n"
        + "42\n"
    )
    stdout = io.StringIO()
    assert run_stdio(stdin, stdout, session) == 0
    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line]
    assert [row["error"]["code"] for row in lines] == [-32600, -32600]
    assert all(row["id"] is None for row in lines)


def test_tools_call_protocol_errors_are_jsonrpc() -> None:
    session = _session()
    missing_name = handle_message(
        {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {}},
        session,
    )
    assert missing_name is not None
    assert missing_name["error"]["code"] == -32602

    bad_args = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "ping", "arguments": ["nope"]},
        },
        session,
    )
    assert bad_args is not None
    assert bad_args["error"]["code"] == -32602


def test_count_rejects_bool_and_unknown_tool_is_iserror() -> None:
    session = _session()
    boom = call_tool("candles", {"symbol": "EURUSD", "count": True}, session)
    assert boom["isError"] is True
    unknown = call_tool("positions", {}, session)
    assert unknown["isError"] is True
    assert "isError" in unknown


def test_tool_errors_redact_password() -> None:
    class Boom:
        def ping(self) -> None:
            raise RuntimeError("cannot connect hunter2")

    settings = Settings(
        _env_file=None,
        mt5_backend="file",
        mt5_password="hunter2",
        mt5_login=118248,
        mt5_server="WSFmarkets-Server",
    )
    session = McpSession(settings, client=Boom())
    result = call_tool("ping", {}, session)
    assert result["isError"] is True
    text = _text(result)
    assert "hunter2" not in text
    assert "***" in text

    stdin = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "ping"}})
        + "\n"
    )
    stdout = io.StringIO()
    assert run_stdio(stdin, stdout, session) == 0
    wire = stdout.getvalue()
    assert "hunter2" not in wire
    reply = json.loads(wire.strip())
    assert reply["result"]["isError"] is True


def test_named_broker_exports_have_no_password() -> None:
    session = _session()
    payload = json.loads(_text(call_tool("brokers", {"name": "vantage"}, session)))
    blob = json.dumps(payload)
    assert "PASSWORD" not in blob
    assert "password" not in blob.lower()
