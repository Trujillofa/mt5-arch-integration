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


def last_trade_ratio(rows: list[MqlTickRow]) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if r.last > 0) / len(rows)


def volume_populated_ratio(rows: list[MqlTickRow]) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if r.volume_real > 0 or r.volume > 0) / len(rows)


def flag_direction_ratio(rows: list[MqlTickRow]) -> float:
    if not rows:
        return 0.0
    mask = TICK_FLAG_BUY | TICK_FLAG_SELL
    return sum(1 for r in rows if int(r.flags) & mask) / len(rows)


def feed_populate_audit(rows: list[MqlTickRow]) -> dict:
    """Qualify/disqualify a CopyTicks tape for true CVD. No tick_volume fallback."""
    n = len(rows)
    last_n = sum(1 for r in rows if r.last > 0)
    vol_n = sum(1 for r in rows if r.volume_real > 0 or r.volume > 0)
    flag_n = sum(1 for r in rows if int(r.flags) & (TICK_FLAG_BUY | TICK_FLAG_SELL))
    last_ratio = last_trade_ratio(rows)
    vol_ratio = volume_populated_ratio(rows)
    flag_ratio = flag_direction_ratio(rows)
    if n == 0:
        verdict = "DISQUALIFY"
        reason = "empty tape; true CVD impossible"
    elif last_n == 0:
        verdict = "DISQUALIFY"
        reason = "last==0 on all rows; true CVD impossible; no tick_volume fallback"
    elif vol_n == 0 and flag_n == 0:
        verdict = "DISQUALIFY"
        reason = (
            "last>0 but no volume and no BUY/SELL flags; "
            "true signed-volume CVD impossible"
        )
    else:
        verdict = "QUALIFY"
        reason = "last-trade fields populate with volume and/or BUY/SELL flags"
    return {
        "n_ticks": n,
        "last_n": last_n,
        "volume_n": vol_n,
        "flag_direction_n": flag_n,
        "last_trade_ratio": last_ratio,
        "volume_populated_ratio": vol_ratio,
        "flag_direction_ratio": flag_ratio,
        "verdict": verdict,
        "reason": reason,
    }


def _cli(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="True-CVD tick tape helpers")
    parser.add_argument("--audit", type=Path, help="MqlTick CSV path")
    args = parser.parse_args(argv)
    if args.audit is None:
        parser.error("pass --audit PATH")
    rows = parse_mql_tick_csv(args.audit)
    print(json.dumps(feed_populate_audit(rows), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
