#!/usr/bin/env python3
"""Write Mt5ArchBridge onto a branded Default chart. WSF / FTMO / FundedNext / Alpha.

Refuses a generic Program Files/MetaTrader 5 tree (FTMO's leftover can carry
another company's account.json). Does not touch vantage / fpmarkets / exness.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_RESTORE = ("wsf", "ftmo", "fundednext", "alphacapital")
SYMBOL = {
    "wsf": "EURUSDc",
    "ftmo": "EURUSD",
    "fundednext": "EURUSD",
    "alphacapital": "BTCUSD",
}
# Alpha quotes-first tries BTCUSD first. ACG's live names are often *.pro;
# bare BTCUSD/EURUSD charts stay blank (symbol sync timeout) while AUDCAD.pro
# already has history. Allow those so 21 can attach Mt5ArchBridge.
ALPHA_QUOTE_SYMBOLS = (
    "BTCUSD",
    "BTCUSDc",
    "BTCUSD.r",
    "BTCUSD.pro",
    "EURUSD",
    "EURUSD.pro",
    "AUDCAD.pro",
)
DEFAULT_FRESH_SEC = 60


class InjectError(ValueError):
    pass


def load_brand_dirs() -> dict[str, str]:
    raw = json.loads((REPO_ROOT / "config" / "broker_install_dirs.json").read_text())
    return {key: val for key, val in raw.items() if not key.startswith("_") and val}


def brand_dir_name(broker: str) -> str:
    if broker not in LIVE_RESTORE:
        raise InjectError(f"refusing broker {broker}")
    name = load_brand_dirs().get(broker, "")
    if not name or name == "MetaTrader 5":
        raise InjectError(f"no branded install dir for {broker}")
    return name


def is_generic_tree(term_dir: Path) -> bool:
    resolved = term_dir.resolve()
    return resolved.name == "MetaTrader 5"


def assert_branded_term_dir(broker: str, term_dir: Path) -> Path:
    resolved = term_dir.expanduser().resolve()
    if is_generic_tree(resolved):
        raise InjectError(
            f"{broker} generic MetaQuotes tree is not the live book — {resolved}"
        )
    expected = brand_dir_name(broker)
    if resolved.name != expected:
        raise InjectError(f"{broker} term dir must be {expected}, got {resolved.name}")
    return resolved


def chart_bytes(broker: str, *, with_expert: bool = True, symbol: str | None = None) -> bytes:
    symbol = symbol or SYMBOL[broker]
    # ACG build 6180 times out EA/script init (~5 min) if the chart symbol
    # has no quotes yet. Alpha starts quotes-first; skip the XAU dump.
    dump_history = "false" if broker == "alphacapital" else "true"
    symbols = (
        "BTCUSD,BTCUSDc,BTCUSD.r,EURUSD"
        if broker == "alphacapital"
        else "EURUSD,GBPUSD,USDJPY,XAUUSD,BTCUSD"
    )
    expert = ""
    if with_expert:
        expert = f"""
<expert>
name=Mt5ArchBridge
path=Experts\\Mt5ArchBridge.ex5
expertmode=5
<inputs>
InpTimerSec=5
InpBroker={broker}
InpSymbols={symbols}
InpTimeframes=H1,H4,D1
InpCandleCount=30
InpDumpHistory={dump_history}
</inputs>
</expert>
"""
    body = f"""<chart>
id=1
symbol={symbol}
period_type=1
period_size=1
digits=5
windows_total=1

<window>
height=100.000000
objects=0

<indicator>
name=Main
path=
apply=1
show_data=1
expertmode=0
fixed_height=-1
</indicator>
</window>
{expert}
</chart>
"""
    text = body.replace("\r\n", "\n").replace("\n", "\r\n")
    return b"\xff\xfe" + text.encode("utf-16-le")


def chart_paths(term_dir: Path) -> list[Path]:
    return [
        term_dir / "MQL5" / "Profiles" / "Charts" / "Default" / "chart01.chr",
        term_dir / "Profiles" / "Charts" / "Default" / "chart01.chr",
    ]


def heartbeat_path(term_dir: Path) -> Path:
    return term_dir / "MQL5" / "Files" / "mt5_arch" / "heartbeat.txt"


def heartbeat_age_seconds(term_dir: Path) -> float | None:
    path = heartbeat_path(term_dir)
    if not path.is_file():
        return None
    return max(0.0, time.time() - path.stat().st_mtime)


def heartbeat_is_fresh(term_dir: Path, max_age: float = DEFAULT_FRESH_SEC) -> bool:
    age = heartbeat_age_seconds(term_dir)
    return age is not None and age <= max_age


def _path_matches_symbol(path: Path, symbol: str) -> bool:
    """Match BTCUSD to a BTCUSD.pro history folder (ACG suffix), not EURUSD."""
    sym = symbol.upper()
    name = path.name.upper()
    if name == sym or name.startswith(f"{sym}."):
        return True
    for part in (part.upper() for part in path.parts):
        if part == sym:
            return True
        if part.startswith(f"{sym}."):
            return True
    return False


def quotes_ready(term_dir: Path, symbol: str | None = None) -> bool:
    """True when portable Bases has downloaded history/ticks for the chart symbol."""
    resolved = Path(term_dir).expanduser().resolve()
    sym = (symbol or "EURUSD").upper()
    bases = resolved / "Bases"
    if not bases.is_dir():
        return False
    for path in bases.rglob("*"):
        if not path.is_file() or path.stat().st_size <= 0:
            continue
        parts = [part.upper() for part in path.parts]
        if not _path_matches_symbol(path, sym):
            continue
        if path.suffix.lower() in {".hcc", ".hc", ".tkc"}:
            return True
        if "HISTORY" in parts or "TICKS" in parts:
            return True
    return False


def alpha_ready_symbol(term_dir: Path) -> str | None:
    """First Alpha allowlist symbol that already has Bases history."""
    resolved = Path(term_dir).expanduser().resolve()
    for symbol in ALPHA_QUOTE_SYMBOLS:
        if quotes_ready(resolved, symbol):
            return symbol
    return None


def prune_default_chart_siblings(term_dir: Path, broker: str = "") -> None:
    """Alpha-only: Default profile must be one chart.

    Leftover AUDCAD.pro tabs steal focus on ACG. WSF / FTMO / FundedNext
    locked books keep leftover Default tabs — do not rewrite order.wnd there.
    """
    if broker != "alphacapital":
        return
    for chart in chart_paths(term_dir):
        parent = chart.parent
        if parent.name != "Default" or not parent.is_dir():
            continue
        for extra in parent.glob("chart*.chr"):
            if extra.name != chart.name:
                extra.unlink()
        order = parent / "order.wnd"
        order.write_bytes(b"\xff\xfe" + "chart01.chr\r\n".encode("utf-16-le"))


def inject_charts(
    broker: str,
    term_dir: Path,
    *,
    require_ex5: bool = True,
    with_expert: bool = True,
) -> list[Path]:
    resolved = assert_branded_term_dir(broker, term_dir)
    ex5 = resolved / "MQL5" / "Experts" / "Mt5ArchBridge.ex5"
    if with_expert and require_ex5 and not ex5.is_file():
        raise InjectError(f"Mt5ArchBridge.ex5 missing under {resolved}")
    symbol = SYMBOL[broker]
    if broker == "alphacapital" and with_expert:
        ready = alpha_ready_symbol(resolved)
        if ready:
            symbol = ready
    payload = chart_bytes(broker, with_expert=with_expert, symbol=symbol)
    written: list[Path] = []
    for path in chart_paths(resolved):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        written.append(path)
    # Leftover Default tabs steal focus on ACG (AUDCAD.pro vs BTCUSD).
    # Do not prune WSF/FTMO/FundedNext — those locked books keep extra tabs.
    if broker == "alphacapital":
        prune_default_chart_siblings(resolved, broker)
    return written


def stop_branded_terminal(broker: str, term_dir: Path) -> list[int]:
    resolved = assert_branded_term_dir(broker, term_dir)
    prefix = os.environ.get("WINEPREFIX", "")
    if not prefix:
        raise InjectError("WINEPREFIX is required to stop a branded terminal")
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from mt5_arch.hypr_geometry import list_terminal64_pids

    brand = brand_dir_name(broker)
    killed: list[int] = []
    for pid in list_terminal64_pids(wineprefix=prefix):
        try:
            cwd = os.readlink(f"/proc/{pid}/cwd")
        except OSError:
            continue
        if brand not in cwd:
            continue
        if Path(cwd).name == "MetaTrader 5":
            continue
        if resolved.name not in cwd:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except ProcessLookupError:
            continue
    time.sleep(1.5)
    for pid in list(killed):
        try:
            os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    lock = resolved / "MQL5" / "Files" / "mt5_arch" / "writer.lock"
    if lock.is_file():
        lock.unlink()
    return killed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker", required=True, choices=LIVE_RESTORE)
    parser.add_argument("--term-dir", required=True)
    parser.add_argument("--fresh", action="store_true", help="exit 0 if heartbeat is fresh")
    parser.add_argument("--quotes-ready", action="store_true", help="exit 0 if Bases has symbol history")
    parser.add_argument("--no-expert", action="store_true", help="write Default chart without Mt5ArchBridge")
    parser.add_argument("--max-age", type=float, default=DEFAULT_FRESH_SEC)
    parser.add_argument("--stop-branded", action="store_true")
    parser.add_argument("--allow-missing-ex5", action="store_true")
    args = parser.parse_args(argv)
    term_dir = Path(args.term_dir)
    try:
        if args.fresh:
            return 0 if heartbeat_is_fresh(term_dir, args.max_age) else 1
        if args.quotes_ready:
            if args.broker == "alphacapital":
                ready = any(quotes_ready(term_dir, symbol) for symbol in ALPHA_QUOTE_SYMBOLS)
                return 0 if ready else 1
            symbol = SYMBOL.get(args.broker, "EURUSD")
            return 0 if quotes_ready(term_dir, symbol) else 1
        if args.stop_branded:
            pids = stop_branded_terminal(args.broker, term_dir)
            print("stopped", " ".join(str(p) for p in pids) if pids else "none")
            return 0
        written = inject_charts(
            args.broker,
            term_dir,
            require_ex5=not args.allow_missing_ex5,
            with_expert=not args.no_expert,
        )
        for path in written:
            print(path)
        return 0
    except InjectError as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
