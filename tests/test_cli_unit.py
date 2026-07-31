"""CLI unit tests without live MT5."""

from __future__ import annotations

from mt5_arch.cli import build_parser, main


def test_parser_ping() -> None:
    args = build_parser().parse_args(["ping", "--json"])
    assert args.command == "ping"
    assert args.json is True


def test_parser_candles() -> None:
    args = build_parser().parse_args(["candles", "EURUSD", "--tf", "M15", "--count", "5"])
    assert args.symbol == "EURUSD"
    assert args.timeframe == "M15"
    assert args.count == 5


def test_config_command_exits_zero(capsys) -> None:
    code = main(["config", "--json"])
    assert code == 0
    out = capsys.readouterr().out
    assert "mt5_rpyc_port" in out or "18812" in out
