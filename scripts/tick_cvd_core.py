"""True CVD from an MqlTick-shaped CSV. Not bar tick_volume. No Timescale client."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

TICK_FLAG_BID = 2
TICK_FLAG_ASK = 4
TICK_FLAG_LAST = 8
TICK_FLAG_VOLUME = 16
TICK_FLAG_BUY = 32
TICK_FLAG_SELL = 64

MQL_TICK_CSV_COLUMNS = (
    "time_msc",
    "seq",
    "bid",
    "ask",
    "last",
    "volume",
    "volume_real",
    "flags",
    "symbol",
    "broker",
    "source",
    "server_utc_offset_sec",
)

TRUE_KINDS = frozenset({"true_buy", "true_sell"})
INFERRED_KINDS = frozenset(
    {
        "inferred_last_at_or_above_ask",
        "inferred_last_at_or_below_bid",
        "inferred_last_above_mid",
        "inferred_last_below_mid",
    }
)


@dataclass(frozen=True)
class MqlTickRow:
    time_msc: int
    seq: int
    bid: float
    ask: float
    last: float
    volume: int
    volume_real: float
    flags: int
    symbol: str
    broker: str
    source: str
    server_utc_offset_sec: int

    @property
    def qty(self) -> float:
        if self.volume_real > 0:
            return float(self.volume_real)
        if self.volume > 0:
            return float(self.volume)
        return 0.0


@dataclass(frozen=True)
class SignedTick:
    time_msc: int
    seq: int
    signed: float
    kind: str
    cvd_true: float
    cvd_inferred: float


def refuse_bar_ohlcv_cvd(columns: list[str]) -> None:
    """Fail closed if someone feeds a rates CSV."""
    lower = {c.strip().lower() for c in columns}
    if "tick_volume" in lower and "flags" not in lower:
        raise ValueError(
            "OHLCV/rates CSV is not a tick tape. True CVD forbids tick_volume without flags."
        )
    if "open" in lower and "close" in lower and "flags" not in lower:
        raise ValueError("OHLC CSV is not a tick tape.")


def parse_mql_tick_csv(path: Path) -> list[MqlTickRow]:
    text = Path(path).read_text(encoding="utf-8")
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None:
        raise ValueError(f"empty tick csv: {path}")
    refuse_bar_ohlcv_cvd(list(reader.fieldnames))
    missing = [c for c in MQL_TICK_CSV_COLUMNS if c not in reader.fieldnames]
    if missing:
        raise ValueError(f"tick csv missing columns {missing}")
    rows: list[MqlTickRow] = []
    for i, raw in enumerate(reader):
        src = (raw.get("source") or "").strip()
        if src == "tkc":
            raise ValueError("source=tkc is forbidden; do not ingest Wine caches")
        rows.append(
            MqlTickRow(
                time_msc=int(raw["time_msc"]),
                seq=int(raw["seq"]),
                bid=float(raw["bid"]),
                ask=float(raw["ask"]),
                last=float(raw["last"]),
                volume=int(raw["volume"]),
                volume_real=float(raw["volume_real"]),
                flags=int(raw["flags"]),
                symbol=(raw.get("symbol") or "").strip(),
                broker=(raw.get("broker") or "").strip(),
                source=src,
                server_utc_offset_sec=int(raw["server_utc_offset_sec"] or 0),
            )
        )
        if rows[-1].source not in {"copyticks_csv", "synthetic"}:
            raise ValueError(f"row {i}: unknown source {rows[-1].source!r}")
    rows.sort(key=lambda r: (r.time_msc, r.seq))
    return rows


def classify_signed(row: MqlTickRow) -> tuple[float, str]:
    flags = int(row.flags)
    qty = row.qty
    buy = bool(flags & TICK_FLAG_BUY)
    sell = bool(flags & TICK_FLAG_SELL)
    if buy and sell:
        return 0.0, "ambiguous_buy_sell"
    if buy:
        if qty <= 0:
            return 0.0, "buy_flag_no_volume"
        return +qty, "true_buy"
    if sell:
        if qty <= 0:
            return 0.0, "sell_flag_no_volume"
        return -qty, "true_sell"
    last = float(row.last)
    if last > 0 and qty > 0:
        bid, ask = float(row.bid), float(row.ask)
        mid = (bid + ask) / 2.0
        if last >= ask:
            return +qty, "inferred_last_at_or_above_ask"
        if last <= bid:
            return -qty, "inferred_last_at_or_below_bid"
        if last > mid:
            return +qty, "inferred_last_above_mid"
        if last < mid:
            return -qty, "inferred_last_below_mid"
        return 0.0, "inferred_last_at_mid"
    if flags & (TICK_FLAG_BID | TICK_FLAG_ASK):
        return 0.0, "quote_only"
    return 0.0, "no_trade"


def cvd_series(rows: list[MqlTickRow]) -> list[SignedTick]:
    out: list[SignedTick] = []
    true_sum = 0.0
    inferred_sum = 0.0
    for row in rows:
        signed, kind = classify_signed(row)
        if kind in TRUE_KINDS:
            true_sum += signed
            inferred_sum += signed
        elif kind in INFERRED_KINDS:
            inferred_sum += signed
        out.append(
            SignedTick(
                time_msc=row.time_msc,
                seq=row.seq,
                signed=signed,
                kind=kind,
                cvd_true=true_sum,
                cvd_inferred=inferred_sum,
            )
        )
    return out
