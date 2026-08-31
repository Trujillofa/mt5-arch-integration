"""Shared file-bridge JSON fixture builder for offline tests."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


def write_bridge_fixture(bridge: Path, *, age_seconds: float = 0.0) -> None:
    """Write representative Mt5ArchBridge JSON snapshots into bridge dir."""
    bridge.mkdir(parents=True, exist_ok=True)
    account = {
        "login": 118248,
        "balance": 5000.25,
        "equity": 4980.5,
        "margin": 120.0,
        "free_margin": 4860.5,
        "margin_level": 4150.42,
        "currency": "USD",
        "leverage": 100,
        "server": "WSFmarkets-Server",
        "name": "Demo",
        "company": "WSFunded",
        "trade_allowed": True,
        "algo_allowed": True,
        "terminal_connected": True,
    }
    terminal = {
        "connected": True,
        "name": "MetaTrader 5",
        "path": r"C:\Program Files\MetaTrader 5",
        "company": "MetaQuotes Ltd.",
        "build": 6075,
        "trade_allowed": True,
        "tradeapi_disabled": False,
    }
    symbols = [
        {
            "symbol": "EURUSD",
            "min_lot": 0.01,
            "max_lot": 500.0,
            "lot_step": 0.01,
            "contract_size": 100000.0,
            "digits": 5,
            "point": 0.00001,
            "tick_value": 1.0,
            "tick_size": 0.00001,
            "trade_mode": "FULL",
        },
        {
            "symbol": "GBPUSD",
            "min_lot": 0.01,
            "max_lot": 100.0,
            "lot_step": 0.01,
            "contract_size": 100000.0,
            "digits": 5,
            "point": 0.00001,
            "tick_value": 1.0,
            "tick_size": 0.00001,
            "trade_mode": "FULL",
        },
    ]
    candles = {
        "symbol": "EURUSD",
        "timeframe": "H1",
        "candles": [
            {
                "time": "2026.07.31 10:00:00",
                "open": 1.1,
                "high": 1.2,
                "low": 1.0,
                "close": 1.15,
                "volume": 100,
            },
            {
                "time": "2026.07.31 11:00:00",
                "open": 1.15,
                "high": 1.18,
                "low": 1.14,
                "close": 1.16,
                "volume": 200,
            },
            {
                "time": "2026.07.31 12:00:00",
                "open": 1.16,
                "high": 1.17,
                "low": 1.15,
                "close": 1.165,
                "volume": 150,
            },
        ],
    }
    (bridge / "account.json").write_text(json.dumps(account), encoding="utf-8")
    (bridge / "terminal.json").write_text(json.dumps(terminal), encoding="utf-8")
    (bridge / "symbols.json").write_text(json.dumps(symbols), encoding="utf-8")
    (bridge / "candles_EURUSD_H1.json").write_text(json.dumps(candles), encoding="utf-8")
    (bridge / "heartbeat.txt").write_text(str(int(time.time())), encoding="utf-8")
    if age_seconds > 0:
        past = time.time() - age_seconds
        for p in bridge.iterdir():
            if p.is_file():
                os.utime(p, (past, past))


# Mt5ArchBridge.mq5 DumpDealsIfRequested() header — 16 columns, exact.
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
DEAL_CSV_HEADER = ",".join(DEAL_CSV_COLUMNS)

# EA formats: volume 4dp, price 8dp, profit/swap/commission/fee 2dp.
# comment has "," → ";" and newlines → space; other fields are unsanitised.
_DEFAULT_DEAL_LINES = (
    "2026.08.20 10:00:00,1001,2001,3001,EURUSD,buy,in,0.1000,1.08500000,"
    "0.00,0.00,-0.70,0.00,0,12345,scale;in",
    "2026.08.20 12:00:00,1002,2001,3001,EURUSD,sell,out,0.1000,1.08600000,"
    "10.00,0.00,-0.70,0.00,0,12345,tp",
)


def default_deals_csv(*, n_rows: int = 2) -> str:
    """CSV body matching the EA dump (header + n data rows, trailing newline)."""
    lines = _DEFAULT_DEAL_LINES[:n_rows]
    if n_rows > len(_DEFAULT_DEAL_LINES):
        raise ValueError(f"n_rows={n_rows} exceeds fixture sample size")
    return DEAL_CSV_HEADER + "\n" + "".join(line + "\n" for line in lines)


def default_dump_deals_done(*, rows: int) -> str:
    """dump_deals.done body: rows=<N> from=<ts> to=<ts> at=<ts>."""
    return (
        f"rows={rows} from=2026.08.17 10:00:00 to=2026.08.31 10:00:00 "
        f"at=2026.08.31 12:00:00"
    )


def write_deal_dump_fixture(
    bridge: Path,
    *,
    csv_text: str | None = None,
    n_rows: int = 2,
    done_body: str | None = None,
    include_csv: bool = True,
    include_done: bool = True,
    done_age_seconds: float = 0.0,
) -> None:
    """Write deals_export.csv + dump_deals.done as the EA would after a dump."""
    bridge.mkdir(parents=True, exist_ok=True)
    if csv_text is None:
        csv_text = default_deals_csv(n_rows=n_rows)
    if include_csv:
        (bridge / "deals_export.csv").write_text(csv_text, encoding="utf-8")
    if done_body is None:
        done_body = default_dump_deals_done(rows=n_rows)
    if include_done:
        done = bridge / "dump_deals.done"
        done.write_text(done_body, encoding="utf-8")
        if done_age_seconds > 0:
            past = time.time() - done_age_seconds
            os.utime(done, (past, past))
