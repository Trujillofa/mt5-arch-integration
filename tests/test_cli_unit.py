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


def test_config_command_exits_zero(capsys, monkeypatch) -> None:
    monkeypatch.setenv("MT5_BACKEND", "file")
    monkeypatch.delenv("MT5_PASSWORD", raising=False)
    code = main(["config", "--json"])
    assert code == 0
    out = capsys.readouterr().out
    assert "mt5_backend" in out
    assert "file" in out
    assert "mt5_rpyc_port" in out or "18812" in out
    # secrets never appear as plaintext password fields with real values
    assert '"mt5_password": null' in out or '"mt5_password": "***"' in out


def test_default_backend_is_file() -> None:
    from mt5_arch.config import Settings

    s = Settings(_env_file=None)
    assert (s.mt5_backend or "file").lower() == "file"
