"""CLI entrypoint: mt5-arch ping | account | symbols | candles."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from mt5_arch import __version__
from mt5_arch.client import MT5ArchClient, MT5ArchError
from mt5_arch.config import Settings
from mt5_arch.file_bridge import FileBridgeClient, FileBridgeError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mt5-arch",
        description="MetaTrader 5 tools for Arch Linux (file bridge or mt5linux/RPyC)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase log verbosity (-v, -vv)",
    )

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON on stdout",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ping", parents=[common], help="Check file-bridge or RPyC connectivity")
    sub.add_parser("account", parents=[common], help="Print account snapshot")
    sub.add_parser("config", parents=[common], help="Show redacted settings (no secrets)")
    p_sym = sub.add_parser("symbols", parents=[common], help="Print symbol specs")
    p_sym.add_argument("symbols", nargs="+", help="Symbol names, e.g. EURUSD XAUUSD")

    p_candles = sub.add_parser("candles", parents=[common], help="Fetch recent OHLCV bars")
    p_candles.add_argument("symbol", help="Symbol name, e.g. EURUSD")
    p_candles.add_argument(
        "--tf",
        "--timeframe",
        dest="timeframe",
        default="H1",
        help="Timeframe (M1, M5, H1, H4, D1, ...). Default: H1",
    )
    p_candles.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of bars (default: 10)",
    )

    return parser


def _configure_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _print_result(data: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, default=str))
        return
    if isinstance(data, dict):
        for key, value in data.items():
            print(f"{key}: {value}")
        return
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                print("---")
                for key, value in item.items():
                    print(f"  {key}: {value}")
            else:
                print(item)
        return
    print(data)


def cmd_ping(client: Any, as_json: bool) -> int:
    info = client.ping()
    payload = asdict(info)
    _print_result(payload, as_json=as_json)
    if not info.connected:
        print("warning: terminal reports connected=false", file=sys.stderr)
        return 2
    return 0


def cmd_account(client: Any, as_json: bool) -> int:
    account = client.account_info()
    _print_result(asdict(account), as_json=as_json)
    return 0


def cmd_symbols(client: Any, symbols: Sequence[str], as_json: bool) -> int:
    rows = [asdict(client.symbol_info(s)) for s in symbols]
    _print_result(rows if len(rows) > 1 else rows[0], as_json=as_json)
    return 0


def cmd_candles(
    client: Any,
    symbol: str,
    timeframe: str,
    count: int,
    as_json: bool,
) -> int:
    result = client.copy_rates(symbol, timeframe=timeframe, count=count)
    payload = {
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "candles": [asdict(c) for c in result.candles],
    }
    if as_json:
        _print_result(payload, as_json=True)
        return 0
    print(f"{result.symbol} {result.timeframe} ({len(result.candles)} bars)")
    print(f"{'time':<28} {'open':>12} {'high':>12} {'low':>12} {'close':>12} {'vol':>10}")
    for c in result.candles:
        print(
            f"{c.time:<28} {c.open:>12.5f} {c.high:>12.5f} "
            f"{c.low:>12.5f} {c.close:>12.5f} {c.volume:>10.0f}"
        )
    return 0


def _open_client(settings: Settings) -> Any:
    backend = (settings.mt5_backend or "file").strip().lower()
    if backend in {"file", "ea", "bridge"}:
        return FileBridgeClient(
            bridge_dir=settings.mt5_bridge_dir,
            max_age_seconds=settings.mt5_bridge_max_age,
            wineprefix=settings.wineprefix,
        )
    if backend in {"rpyc", "mt5linux", "ipc"}:
        return MT5ArchClient(settings)
    raise MT5ArchError(f"Unknown MT5_BACKEND={settings.mt5_backend!r} (use file|rpyc)")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    _configure_logging(args.verbose)
    settings = Settings()

    if args.command == "config":
        _print_result(settings.redacted_summary(), as_json=args.json)
        return 0

    try:
        client = _open_client(settings)
        # Context manager only for RPyC client
        if isinstance(client, MT5ArchClient):
            client = client.__enter__()
            try:
                return _dispatch(args, client)
            finally:
                client.__exit__(None, None, None)
        return _dispatch(args, client)
    except (MT5ArchError, FileBridgeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        if isinstance(exc, FileBridgeError):
            print(
                "hint: ./scripts/06-install-file-bridge.sh then attach EA + green Algo Trading",
                file=sys.stderr,
            )
        return 1
    except ConnectionError as exc:
        print(
            f"error: cannot reach mt5server at "
            f"{settings.mt5_rpyc_host}:{settings.mt5_rpyc_port}: {exc}\n"
            "hint: start the terminal and ./scripts/05-start-mt5server.sh "
            "or set MT5_BACKEND=file",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(
            f"error: connection failed ({exc})\n"
            "hint: use MT5_BACKEND=file (default) with the MQL5 EA bridge",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).exception("unexpected error")
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _dispatch(args: argparse.Namespace, client: Any) -> int:
    if args.command == "ping":
        return cmd_ping(client, args.json)
    if args.command == "account":
        return cmd_account(client, args.json)
    if args.command == "symbols":
        return cmd_symbols(client, args.symbols, args.json)
    if args.command == "candles":
        return cmd_candles(
            client,
            args.symbol,
            args.timeframe,
            args.count,
            args.json,
        )
    print(f"error: unknown command {args.command!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
