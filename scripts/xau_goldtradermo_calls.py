#!/usr/bin/env python3
"""Replay GOLDTRADERMO XAUUSD text calls on recorded bars.

Research only. Reads a Telegram HTML export and an offline OHLC file.
Does not place orders, does not pass --live, and does not write
strategy_params.json.

Fill convention, fixed before any tape result is read:

* Export titles carry an explicit offset (this export is UTC-05:00).
  Bar times in ``xauusd_data.csv`` are UTC. The call is converted onto
  that clock and the offset is stored on the call.
* The first eligible bar is the first bar whose open is strictly after
  the call. The bar that contains the call is not used.
* Entry is the first touch of the stated zone, full size, 1.0 lot.
  Open inside the zone fills at the open. An open above the zone fills
  at the zone high. An open below the zone fills at the zone low.
* Exit is the nearest stated TP or the SL, whichever a later bar trades
  alone. Full size leaves at that single level. Later TPs are not a
  scale-out.
* One OHLC bar that trades both the SL and the nearest TP cannot order
  them. The call stays unresolved (``same_bar_sl_and_tp``).
* The fill bar is not an exit. If that bar also trades the SL, the
  nearest TP, or both, the call stays unresolved
  (``same_bar_entry_and_exit`` or ``same_bar_sl_and_tp``).
* No bar after the call, no touch of the zone, or neither exit before
  the tape ends: unresolved. Unresolved calls stay in the report.
* Cost uses the entry bar's positive spread when the tape has one.
  Otherwise it uses the recorded missing-spread assumption. Slippage
  and commission come from ``results/xau_research_costs.json``. The
  round trip matches ``backtest.py``: one spread, slippage on both
  fills, commission per lot per side.

A price that does not reconcile with the other levels in the same
message is excluded and counted. It is not rewritten. Marketing replies
(TP HIT, ALL TP Done) are not calls and are not a win count.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import re
import statistics
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta, timezone
from html import unescape
from pathlib import Path

CONTRACT_SIZE = 100.0  # backtest.CONTRACT_SIZE, standard XAUUSD
LOTS = 1.0
REL_BAND = 0.15
BAR_CLOCK = "UTC"
HOLDOUT_NAIVE_UTC = datetime(2026, 1, 1)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPORT = Path("/home/yderf/storage/Downloads/Telegram Desktop/ChatExport_2026-10-08")
DEFAULT_BARS = ROOT / "xauusd_data.csv"
DEFAULT_COSTS = ROOT / "results" / "xau_research_costs.json"
DEFAULT_HOLDOUT = ROOT / "results" / "xau_holdout_lock.json"
DEFAULT_OUT = ROOT / "results" / "xau_goldtradermo_calls_replay.json"
DEFAULT_NOTE = ROOT / "results" / "xau_goldtradermo_calls_replay.md"

_HEADER = re.compile(
    r"^\s*#?\s*(?:"
    r"(?P<side_a>buy|sell)\s+l?\s*(?:xauu?usd|gold)(?:\s+gold)?"
    r"|"
    r"(?:xauu?usd|gold)\s+(?P<side_b>buy|sell)"
    r")\s*"
    r"(?P<zone>\d+(?:\.\d+)?(?:/{1,2}\d+(?:\.\d+)?)*)"
    r"\s*$",
    re.IGNORECASE,
)
_TP_LINE = re.compile(r"^TP\.?\s*(\d+(?:\.\d+)?)\s*$", re.IGNORECASE)
_SL_LINE = re.compile(r"^SL\.?\s*(\d+(?:\.\d+)?)\s*$", re.IGNORECASE)
_TP_HIT = re.compile(r"\btp\b.{0,24}\bhit\b", re.IGNORECASE)
_ALL_TP = re.compile(r"\ball\s+tp\b", re.IGNORECASE)
_MSG_ID = re.compile(r'\bid="(message\d+)"')
_TITLE = re.compile(
    r'title="(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2}) UTC([+-]\d{2}:\d{2})"'
)
_TEXT = re.compile(r'<div class="text">(.*?)</div>', re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)

_INDICATOR_WORDS = (
    "ema",
    "rsi",
    "macd",
    "fib",
    "vwap",
    "bollinger",
    "donchian",
    "atr",
    "ichimoku",
)
_SESSION_WORDS = ("asia", "london", "new york", "sweep", "session")
_EXOGENOUS_WORDS = (
    "eurusd",
    "gbpusd",
    "dxy",
    "us10y",
    "tips",
    "dfii10",
    "cftc",
    "xagusd",
    "btcusd",
    "audjpy",
    "yield",
)


@dataclass(frozen=True)
class Bar:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    spread: float | None


@dataclass(frozen=True)
class CostSpec:
    point_size: float
    slippage_points: float
    commission_per_lot: float
    missing_spread_points: float
    lots: float = LOTS
    contract_size: float = CONTRACT_SIZE

    def round_trip(self, spread_pts: float) -> float:
        points = spread_pts + 2.0 * self.slippage_points
        traded = points * self.point_size * self.contract_size * self.lots
        commission = 2.0 * self.commission_per_lot * self.lots
        return traded + commission


@dataclass(frozen=True)
class Call:
    message_id: str
    source_file: str
    export_time: datetime
    export_offset: str
    bar_time: datetime
    side: str
    zone_lo: float
    zone_hi: float
    tps: tuple[float, ...]
    sl: float
    text: str

    @property
    def nearest_tp(self) -> float:
        if self.side == "buy":
            return min(self.tps)
        return max(self.tps)


@dataclass(frozen=True)
class Excluded:
    message_id: str
    source_file: str
    export_time: str | None
    reason: str
    text: str


@dataclass(frozen=True)
class ParseBatch:
    calls: tuple[Call, ...]
    excluded: tuple[Excluded, ...]
    tp_hit_messages: int
    messages_with_text: int


@dataclass(frozen=True)
class Fill:
    message_id: str
    status: str
    reason: str
    entry_price: float | None = None
    exit_price: float | None = None
    entry_bar_time: str | None = None
    exit_bar_time: str | None = None
    pnl: float | None = None
    cost: float | None = None
    spread_pts: float | None = None
    spread_source: str | None = None


def fold_math_alnum(text: str) -> str:
    """Map Mathematical Alphanumeric symbols back to ASCII letters and digits."""
    out: list[str] = []
    for ch in text:
        o = ord(ch)
        mapped = _fold_ord(o)
        out.append(mapped if mapped is not None else ch)
    return "".join(out)


def _fold_ord(o: int) -> str | None:
    if o == 0x210E:  # italic h lives outside the block
        return "h"
    blocks = (
        (0x1D400, 0x1D419, "A"),
        (0x1D41A, 0x1D433, "a"),
        (0x1D434, 0x1D44D, "A"),
        (0x1D44E, 0x1D467, "a"),
        (0x1D468, 0x1D481, "A"),
        (0x1D482, 0x1D49B, "a"),
        (0x1D5A0, 0x1D5B9, "A"),
        (0x1D5BA, 0x1D5D3, "a"),
        (0x1D5D4, 0x1D5ED, "A"),
        (0x1D5EE, 0x1D607, "a"),
        (0x1D608, 0x1D621, "A"),
        (0x1D622, 0x1D63B, "a"),
        (0x1D63C, 0x1D655, "A"),
        (0x1D656, 0x1D66F, "a"),
        (0x1D670, 0x1D689, "A"),
        (0x1D68A, 0x1D6A3, "a"),
        (0x1D7CE, 0x1D7D7, "0"),
        (0x1D7D8, 0x1D7E1, "0"),
        (0x1D7E2, 0x1D7EB, "0"),
        (0x1D7EC, 0x1D7F5, "0"),
        (0x1D7F6, 0x1D7FF, "0"),
    )
    for start, end, base in blocks:
        if start <= o <= end:
            return chr(ord(base) + (o - start))
    return None


def html_to_text(fragment: str) -> str:
    raw = _BR.sub("\n", fragment)
    raw = _TAG.sub("", raw)
    raw = unescape(raw).replace("\xa0", " ")
    return fold_math_alnum(raw).strip()


def _whole_digits(price: float) -> int:
    whole = abs(int(price))
    if whole == 0:
        return 1
    return len(str(whole))


def _zone_parts(token: str) -> list[float] | None:
    parts = [p for p in token.split("/") if p != ""]
    nums: list[float] = []
    for part in parts:
        if not re.fullmatch(r"\d+(?:\.\d+)?", part):
            return None
        nums.append(float(part))
    return nums


def _prices_share_scale(prices: Sequence[float]) -> str | None:
    if len(prices) < 3:
        return "incomplete"
    lengths = [_whole_digits(p) for p in prices]
    mode = Counter(lengths).most_common(1)[0][0]
    if any(n != mode for n in lengths):
        return "digit_length"
    med = statistics.median(prices)
    if med <= 0:
        return "price_band"
    if any(abs(p - med) / med > REL_BAND for p in prices):
        return "price_band"
    return None


def _geometry_reason(side: str, zone_lo: float, zone_hi: float, tps: Sequence[float], sl: float) -> str | None:
    if side == "buy":
        if not sl < zone_lo:
            return "side_geometry"
        if not all(tp > zone_hi for tp in tps):
            return "side_geometry"
        return None
    if not sl > zone_hi:
        return "side_geometry"
    if not all(tp < zone_lo for tp in tps):
        return "side_geometry"
    return None


def export_to_bar_time(export_time: datetime) -> datetime:
    """Convert an aware export timestamp onto naive UTC bar time."""
    if export_time.tzinfo is None:
        raise ValueError("export_time must carry the title offset")
    return export_time.astimezone(UTC).replace(tzinfo=None)


def _parse_title(title_stamp: str, offset: str) -> datetime:
    local = datetime.strptime(title_stamp, "%d.%m.%Y %H:%M:%S")
    sign = 1 if offset[0] == "+" else -1
    hours, minutes = offset[1:].split(":")
    delta = timedelta(hours=int(hours), minutes=int(minutes)) * sign
    return local.replace(tzinfo=timezone(delta))


def classify_body(text: str) -> tuple[str, dict | None, str | None]:
    """Return ('call', fields, None), ('excluded', None, reason), or ('other', None, None)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return "other", None, None
    header = _HEADER.match(lines[0])
    if header is None:
        return "other", None, None
    side = (header.group("side_a") or header.group("side_b")).lower()
    zone_nums = _zone_parts(header.group("zone"))
    if zone_nums is None or len(zone_nums) not in (1, 2):
        return "excluded", None, "zone_arity"
    tps: list[float] = []
    sl: float | None = None
    for line in lines[1:]:
        tp_m = _TP_LINE.match(line)
        if tp_m:
            tps.append(float(tp_m.group(1)))
            continue
        sl_m = _SL_LINE.match(line)
        if sl_m:
            if sl is not None:
                return "excluded", None, "duplicate_sl"
            sl = float(sl_m.group(1))
            continue
        return "excluded", None, "unexpected_line"
    if sl is None or not tps:
        return "excluded", None, "incomplete"
    zone_lo = min(zone_nums)
    zone_hi = max(zone_nums)
    prices = [*zone_nums, *tps, sl]
    scale = _prices_share_scale(prices)
    if scale is not None:
        return "excluded", None, scale
    geom = _geometry_reason(side, zone_lo, zone_hi, tps, sl)
    if geom is not None:
        return "excluded", None, geom
    return "call", {
        "side": side,
        "zone_lo": zone_lo,
        "zone_hi": zone_hi,
        "tps": tuple(tps),
        "sl": sl,
    }, None


def _is_tp_hit(text: str) -> bool:
    return _TP_HIT.search(text) is not None or _ALL_TP.search(text) is not None


def parse_html(html: str, *, source_file: str = "") -> ParseBatch:
    calls: list[Call] = []
    excluded: list[Excluded] = []
    tp_hits = 0
    with_text = 0
    for part in re.split(r'<div class="message ', html)[1:]:
        text_m = _TEXT.search(part)
        if text_m is None:
            continue
        with_text += 1
        text = html_to_text(text_m.group(1))
        if _is_tp_hit(text):
            tp_hits += 1
        kind, fields, reason = classify_body(text)
        id_m = _MSG_ID.search(part)
        message_id = id_m.group(1) if id_m else ""
        title_m = _TITLE.search(part)
        export_time = None
        offset = None
        if title_m:
            offset = title_m.group(2)
            export_time = _parse_title(title_m.group(1), offset)
        if kind == "other":
            continue
        if export_time is None or offset is None:
            excluded.append(
                Excluded(message_id, source_file, None, "undated", text)
            )
            continue
        if kind == "excluded":
            excluded.append(
                Excluded(
                    message_id,
                    source_file,
                    export_time.isoformat(),
                    reason or "excluded",
                    text,
                )
            )
            continue
        assert fields is not None
        calls.append(
            Call(
                message_id=message_id,
                source_file=source_file,
                export_time=export_time,
                export_offset=offset,
                bar_time=export_to_bar_time(export_time),
                side=fields["side"],
                zone_lo=fields["zone_lo"],
                zone_hi=fields["zone_hi"],
                tps=fields["tps"],
                sl=fields["sl"],
                text=text,
            )
        )
    return ParseBatch(tuple(calls), tuple(excluded), tp_hits, with_text)


def _export_files(directory: Path) -> list[Path]:
    found = [p for p in directory.glob("messages*.html") if p.is_file()]

    def sort_key(path: Path) -> tuple[int, str]:
        match = re.fullmatch(r"messages(\d*)", path.stem)
        if match is None:
            return (10_000, path.name)
        raw = match.group(1)
        return (int(raw) if raw else 1, path.name)

    return sorted(found, key=sort_key)


def parse_export_dir(directory: Path) -> ParseBatch:
    calls: list[Call] = []
    excluded: list[Excluded] = []
    tp_hits = 0
    with_text = 0
    files = _export_files(directory)
    if not files:
        raise FileNotFoundError(f"no messages*.html under {directory}")
    for path in files:
        html = path.read_text(encoding="utf-8", errors="replace")
        batch = parse_html(html, source_file=path.name)
        calls.extend(batch.calls)
        excluded.extend(batch.excluded)
        tp_hits += batch.tp_hit_messages
        with_text += batch.messages_with_text
    return ParseBatch(tuple(calls), tuple(excluded), tp_hits, with_text)


def _spread_value(raw: object) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if value != value or value <= 0.0:
        return None
    return value


def load_m15_bars(path: Path) -> list[Bar]:
    """Load XAUUSD M15 rows. Timestamps become naive UTC."""
    import pandas as pd

    frame = pd.read_csv(path)
    needed = {"time", "open", "high", "low", "close"}
    missing = needed.difference(frame.columns)
    if missing:
        raise ValueError(f"{path} missing columns {sorted(missing)}")
    if "timeframe" in frame.columns:
        frame = frame[frame["timeframe"].astype(str) == "M15"]
    if "symbol" in frame.columns:
        frame = frame[frame["symbol"].astype(str).str.upper() == "XAUUSD"]
    stamps = pd.to_datetime(frame["time"], utc=True)
    bars: list[Bar] = []
    spreads = frame["spread"] if "spread" in frame.columns else [None] * len(frame)
    for stamp, op, hi, lo, cl, sp in zip(
        stamps,
        frame["open"],
        frame["high"],
        frame["low"],
        frame["close"],
        spreads,
        strict=True,
    ):
        py = stamp.to_pydatetime().replace(tzinfo=None)
        high = float(hi)
        low = float(lo)
        if high < low:
            continue
        bars.append(
            Bar(
                time=py,
                open=float(op),
                high=high,
                low=low,
                close=float(cl),
                spread=_spread_value(sp),
            )
        )
    bars.sort(key=lambda bar: bar.time)
    dedup: list[Bar] = []
    for bar in bars:
        if dedup and dedup[-1].time == bar.time:
            continue
        dedup.append(bar)
    return dedup


def positive_spread_median(bars: Sequence[Bar]) -> float:
    present = [bar.spread for bar in bars if bar.spread is not None]
    if not present:
        raise ValueError("tape has no positive spread; refusing a silent zero cost")
    return float(statistics.median(present))


def _require_sorted(bars: Sequence[Bar]) -> None:
    for i in range(1, len(bars)):
        if bars[i].time < bars[i - 1].time:
            raise ValueError("bars must be sorted by open time")


def _touches(level: float, bar: Bar) -> bool:
    return bar.low - 1e-9 <= level <= bar.high + 1e-9


def _touches_zone(bar: Bar, zone_lo: float, zone_hi: float) -> bool:
    return bar.high >= zone_lo - 1e-9 and bar.low <= zone_hi + 1e-9


def _first_touch_price(bar: Bar, zone_lo: float, zone_hi: float) -> float:
    if zone_lo <= bar.open <= zone_hi:
        return bar.open
    if bar.open > zone_hi:
        return zone_hi
    return zone_lo


def _gap_price(side: str, kind: str, open_: float, level: float) -> float:
    if kind == "sl":
        if side == "buy" and open_ < level:
            return open_
        if side == "sell" and open_ > level:
            return open_
        return level
    if side == "buy" and open_ > level:
        return open_
    if side == "sell" and open_ < level:
        return open_
    return level


def _pnl(side: str, entry: float, exit_px: float, cost_paid: float, cost: CostSpec) -> float:
    direction = 1.0 if side == "buy" else -1.0
    gross = (exit_px - entry) * cost.contract_size * cost.lots * direction
    return gross - cost_paid


def fill_call(call: Call, bars: Sequence[Bar], cost: CostSpec) -> Fill:
    """Replay one call. ``bars`` must be sorted by open time on ``call.bar_time``'s clock."""
    times = [bar.time for bar in bars]
    start = bisect.bisect_right(times, call.bar_time)
    if start >= len(bars):
        return Fill(call.message_id, "unresolved", "no_bar_after_call")

    fill_at: int | None = None
    entry_px: float | None = None
    for i in range(start, len(bars)):
        bar = bars[i]
        if not _touches_zone(bar, call.zone_lo, call.zone_hi):
            continue
        fill_at = i
        entry_px = _first_touch_price(bar, call.zone_lo, call.zone_hi)
        break
    if fill_at is None or entry_px is None:
        return Fill(call.message_id, "unresolved", "no_fill")

    target = call.nearest_tp
    entry_bar = bars[fill_at]
    sl_in = _touches(call.sl, entry_bar)
    tp_in = _touches(target, entry_bar)
    if sl_in and tp_in:
        return Fill(
            call.message_id,
            "unresolved",
            "same_bar_sl_and_tp",
            entry_price=entry_px,
            entry_bar_time=entry_bar.time.isoformat(sep=" "),
        )
    if sl_in or tp_in:
        return Fill(
            call.message_id,
            "unresolved",
            "same_bar_entry_and_exit",
            entry_price=entry_px,
            entry_bar_time=entry_bar.time.isoformat(sep=" "),
        )

    for bar in bars[fill_at + 1 :]:
        sl_in = _touches(call.sl, bar)
        tp_in = _touches(target, bar)
        if sl_in and tp_in:
            return Fill(
                call.message_id,
                "unresolved",
                "same_bar_sl_and_tp",
                entry_price=entry_px,
                entry_bar_time=entry_bar.time.isoformat(sep=" "),
                exit_bar_time=bar.time.isoformat(sep=" "),
            )
        if not sl_in and not tp_in:
            continue
        kind = "sl" if sl_in else "tp"
        level = call.sl if sl_in else target
        exit_px = _gap_price(call.side, kind, bar.open, level)
        if entry_bar.spread is None:
            spread_pts = cost.missing_spread_points
            source = "assumption"
        else:
            spread_pts = entry_bar.spread
            source = "bar"
        paid = cost.round_trip(spread_pts)
        return Fill(
            call.message_id,
            "scored",
            kind,
            entry_price=entry_px,
            exit_price=exit_px,
            entry_bar_time=entry_bar.time.isoformat(sep=" "),
            exit_bar_time=bar.time.isoformat(sep=" "),
            pnl=_pnl(call.side, entry_px, exit_px, paid, cost),
            cost=paid,
            spread_pts=spread_pts,
            spread_source=source,
        )
    return Fill(
        call.message_id,
        "unresolved",
        "open_at_tape_end",
        entry_price=entry_px,
        entry_bar_time=entry_bar.time.isoformat(sep=" "),
    )


def replay(calls: Sequence[Call], bars: Sequence[Bar], cost: CostSpec) -> list[Fill]:
    _require_sorted(bars)
    return [fill_call(call, bars, cost) for call in calls]


def count_identity(
    n_calls: int,
    n_excluded: int,
    n_scored: int,
    n_unresolved: int,
) -> dict[str, int]:
    """Disjoint partition: excluded + scored + unresolved = parsed_total.

    ``parsed_calls`` is the kept set and equals scored + unresolved.
    """
    if n_scored + n_unresolved != n_calls:
        raise ValueError(
            f"kept calls {n_calls} != scored {n_scored} + unresolved {n_unresolved}"
        )
    parsed_total = n_calls + n_excluded
    if n_excluded + n_scored + n_unresolved != parsed_total:
        raise ValueError("excluded + scored + unresolved != parsed_total")
    return {
        "parsed_total": parsed_total,
        "parsed_calls": n_calls,
        "excluded_malformed": n_excluded,
        "scored": n_scored,
        "unresolved": n_unresolved,
    }


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def _word_in(text: str, words: Sequence[str]) -> bool:
    low = text.lower()
    return any(re.search(rf"\b{re.escape(word)}\b", low) for word in words)


def signature(calls: Sequence[Call], *, holdout_utc: datetime) -> dict:
    """Describe the call messages. These numbers are not knobs and not a fit."""
    hours = [0] * 24
    widths: list[float] = []
    sl_dist: list[float] = []
    tp_dist: list[float] = []
    spacings: list[float] = []
    sides: Counter[str] = Counter()
    offsets: Counter[str] = Counter()
    n_pre = 0
    indicator_n = 0
    session_n = 0
    exogenous_n = 0
    for call in calls:
        hours[call.export_time.hour] += 1
        sides[call.side] += 1
        offsets[call.export_offset] += 1
        if call.bar_time < holdout_utc:
            n_pre += 1
        widths.append(call.zone_hi - call.zone_lo)
        if call.side == "buy":
            sl_dist.append(call.zone_lo - call.sl)
            tp_dist.append(call.nearest_tp - call.zone_hi)
            ordered = tuple(sorted(call.tps))
        else:
            sl_dist.append(call.sl - call.zone_hi)
            tp_dist.append(call.zone_lo - call.nearest_tp)
            ordered = tuple(sorted(call.tps, reverse=True))
        spacings.extend(abs(b - a) for a, b in zip(ordered, ordered[1:], strict=False))
        if _word_in(call.text, _INDICATOR_WORDS):
            indicator_n += 1
        if _word_in(call.text, _SESSION_WORDS):
            session_n += 1
        if _word_in(call.text, _EXOGENOUS_WORDS):
            exogenous_n += 1
    distinct_hours = sum(1 for n in hours if n)
    return {
        "n": len(calls),
        "n_before_holdout": n_pre,
        "n_on_or_after_holdout": len(calls) - n_pre,
        "holdout_start_utc": holdout_utc.isoformat(sep=" "),
        "export_timezone": "UTC-05:00" if set(offsets) <= {"-05:00"} else "mixed",
        "export_offsets": dict(sorted(offsets.items())),
        "hour_counts_export_clock": hours,
        "distinct_hours_export_clock": distinct_hours,
        "side_buy": int(sides["buy"]),
        "side_sell": int(sides["sell"]),
        "zone_width": _dist(widths),
        "sl_distance": _dist(sl_dist),
        "nearest_tp_distance": _dist(tp_dist),
        "tp_spacing": _dist(spacings),
        "indicator_messages": indicator_n,
        "session_word_messages": session_n,
        "exogenous_messages": exogenous_n,
    }


def _dist(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "median": None, "min": None, "max": None}
    return {
        "n": len(values),
        "median": _median(values),
        "min": min(values),
        "max": max(values),
    }


def closed_shape_outcome(calls: Sequence[Call], *, holdout_utc: datetime) -> dict:
    """Return NO_NEW_FAMILY or, only for a structure the messages state that is not closed, knobs.

    Zone + SL + TP on XAUUSD, with or without an indicator word, is the
    intraday own-price class. Session words would restate the closed
    session / sweep / fade books. Exogenous words restate the closed
    FX-lead, COT, and yield books. Calls on or after the holdout cannot
    choose a knob. This function does not invent a rule the text does not state.
    """
    sig = signature(calls, holdout_utc=holdout_utc)
    reasons: list[str] = []
    matched: list[str] = []
    bare_zone = (
        sig["n"] > 0
        and sig["indicator_messages"] == 0
        and sig["session_word_messages"] == 0
        and sig["exogenous_messages"] == 0
    )
    if bare_zone or sig["indicator_messages"]:
        matched.append("intraday_own_price")
        reasons.append(
            "Kept calls are an XAUUSD entry zone, a stop, and a TP ladder on the "
            "instrument's own price. docs/research/XAU-THESIS-PASS-2026-10-03.md "
            "already closes intraday own-price, including an indicator on XAUUSD itself."
        )
    if sig["session_word_messages"] or bare_zone:
        matched.append("session_books_closed_not_restated")
        reasons.append(
            "results/xau_loop_status.md closes session timing, Asia-box, and London "
            "sweep/fade (xau_gold_session_study SCREEN_FAIL, plus server_hour_window_flat, "
            "tod_london_ny_flat, and asia_box_london_sweep_fade_flat). The call text does "
            "not state a session rule. The hour-of-day counts are a description of the "
            "export clock, not a new occupancy."
        )
    if sig["exogenous_messages"]:
        matched.append("exogenous_already_closed")
        reasons.append(
            "Some messages name an exogenous series. FX-lead, log-spread, COT, and "
            "real-yield books in the thesis pass are already closed."
        )
    n_post = int(sig["n_on_or_after_holdout"])
    n_pre = int(sig["n_before_holdout"])
    if n_post:
        reasons.append(
            f"{n_post} of {sig['n']} kept calls have bar time on or after "
            f"{holdout_utc.date().isoformat()} UTC. That window is the sealed holdout "
            "and is not a selection set. A knob chosen from those calls is forbidden."
        )
    if n_pre and (bare_zone or sig["indicator_messages"]):
        reasons.append(
            f"The {n_pre} calls before the holdout use the same zone, stop, and TP "
            "template. They are not a different occupancy, so they do not open a family."
        )
    if not reasons:
        reasons.append("No kept call states a structure that is outside the closed books.")
    return {
        "outcome": "NO_NEW_FAMILY",
        "family_id": None,
        "knobs": None,
        "matched_shapes": matched,
        "reasons": reasons,
        "promote": False,
        "live_go": False,
        "PAPER_GO": "no",
    }


def load_holdout_utc(path: Path) -> datetime:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stamp = datetime.fromisoformat(payload["holdout_start"])
    if stamp.tzinfo is None:
        raise ValueError("holdout_start must be timezone-aware")
    return stamp.astimezone(UTC).replace(tzinfo=None)


def load_cost_book(path: Path, *, missing_spread_points: float) -> tuple[CostSpec, dict]:
    book = json.loads(path.read_text(encoding="utf-8"))
    spec = CostSpec(
        point_size=float(book["point_size"]),
        slippage_points=float(book["slippage_points"]),
        commission_per_lot=float(book["commission_per_lot"]),
        missing_spread_points=float(missing_spread_points),
    )
    meta = {
        "path": _rel(path),
        "sha256": _sha256(path),
        "point_size": spec.point_size,
        "slippage_points": spec.slippage_points,
        "commission_per_lot": spec.commission_per_lot,
        "missing_spread_points": spec.missing_spread_points,
        "missing_spread_rule": (
            "median of positive M15 spreads on the tape, used only when a bar "
            "spread is missing or non-positive"
        ),
        "lots": spec.lots,
        "contract_size": spec.contract_size,
    }
    return spec, meta


def _rel(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_report(
    batch: ParseBatch,
    fills: Sequence[Fill],
    *,
    export_dir: Path,
    bars_path: Path,
    bars: Sequence[Bar],
    cost_meta: dict,
    holdout_utc: datetime,
) -> dict:
    if len(fills) != len(batch.calls):
        raise ValueError("fills must align with kept calls")
    n_scored = sum(1 for fill in fills if fill.status == "scored")
    n_unresolved = sum(1 for fill in fills if fill.status == "unresolved")
    counts = count_identity(
        len(batch.calls),
        len(batch.excluded),
        n_scored,
        n_unresolved,
    )
    reasons = Counter(fill.reason for fill in fills)
    excluded_reasons = Counter(row.reason for row in batch.excluded)
    sig = signature(batch.calls, holdout_utc=holdout_utc)
    outcome = closed_shape_outcome(batch.calls, holdout_utc=holdout_utc)
    scored_from_bars = n_scored
    rows = []
    for call, fill in zip(batch.calls, fills, strict=True):
        rows.append(
            {
                "message_id": call.message_id,
                "source_file": call.source_file,
                "export_time": call.export_time.isoformat(),
                "export_offset": call.export_offset,
                "bar_time_utc": call.bar_time.isoformat(sep=" "),
                "side": call.side,
                "zone_lo": call.zone_lo,
                "zone_hi": call.zone_hi,
                "tps": list(call.tps),
                "sl": call.sl,
                "nearest_tp": call.nearest_tp,
                "status": fill.status,
                "reason": fill.reason,
                "entry_price": fill.entry_price,
                "exit_price": fill.exit_price,
                "entry_bar_time": fill.entry_bar_time,
                "exit_bar_time": fill.exit_bar_time,
                "pnl": fill.pnl,
                "cost": fill.cost,
                "spread_pts": fill.spread_pts,
                "spread_source": fill.spread_source,
            }
        )
    tape_first = bars[0].time.isoformat(sep=" ") if bars else None
    tape_last = bars[-1].time.isoformat(sep=" ") if bars else None
    return {
        "kind": "goldtradermo_call_replay",
        "outcome": outcome["outcome"],
        "family_id": None,
        "promote": False,
        "live_go": False,
        "PAPER_GO": "no",
        "tp_hit_messages": batch.tp_hit_messages,
        "tp_hit_is_not_the_win_count": True,
        "scored_exits_from_bars": scored_from_bars,
        "messages_with_text": batch.messages_with_text,
        "counts": counts,
        "identity": (
            "excluded_malformed + scored + unresolved = parsed_total; "
            "parsed_calls = scored + unresolved"
        ),
        "fill_reasons": dict(sorted(reasons.items())),
        "excluded_reasons": dict(sorted(excluded_reasons.items())),
        "clock": {
            "export": "offset in each message title; this export is UTC-05:00",
            "bars": BAR_CLOCK,
            "conversion": "bar_time_utc = export_time converted to UTC; tzinfo then dropped",
            "eligible_bar": "first bar whose open is strictly after bar_time_utc",
        },
        "fill_convention": {
            "entry": "first touch of the zone; open inside fills at open; "
            "open above fills at zone high; open below fills at zone low",
            "size": "full size, 1.0 lot, contract 100",
            "exit": "nearest stated TP or SL on a later bar, full size, one exit",
            "same_bar_sl_and_tp": "unresolved",
            "fill_bar_also_trades_sl_or_tp": "unresolved",
            "no_bar_after_call": "unresolved",
        },
        "costs": cost_meta,
        "tape": {
            "path": _rel(bars_path),
            "sha256": _sha256(bars_path) if bars_path.is_file() else None,
            "timeframe": "M15",
            "symbol": "XAUUSD",
            "bars": len(bars),
            "first_open_utc": tape_first,
            "last_open_utc": tape_last,
        },
        "export_dir": _rel(export_dir),
        "signature": sig,
        "closed_shape": outcome,
        "excluded": [asdict(row) for row in batch.excluded],
        "calls": rows,
    }


def _fmt(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))
        return f"{value:.2f}"
    return str(value)


def _dist_phrase(block: dict) -> str:
    if not block or block.get("n") in (0, None):
        return "no values"
    return (
        f"n={block['n']}, median={_fmt(block['median'])}, "
        f"min={_fmt(block['min'])}, max={_fmt(block['max'])}"
    )


def render_note(report: dict) -> str:
    counts = report["counts"]
    sig = report["signature"]
    outcome = report["closed_shape"]
    hours = sig["hour_counts_export_clock"]
    hour_bits = [f"{hour:02d}:{hours[hour]}" for hour in range(24) if hours[hour]]
    reason_bits = ", ".join(
        f"{name}={n}" for name, n in sorted(report["fill_reasons"].items())
    )
    excluded_bits = ", ".join(
        f"{name}={n}" for name, n in sorted(report["excluded_reasons"].items())
    ) or "none"
    reason_lines = "\n".join(f"- {line}" for line in outcome["reasons"])
    shapes = ", ".join(outcome["matched_shapes"]) or "none"
    costs = report["costs"]
    tape = report["tape"]
    return f"""# GOLDTRADERMO call tape

**Outcome:** {outcome["outcome"]}

**promote / live_go / PAPER_GO:** no / false / no

**family_id:** none. No charter. No develop screen. No second tune.

## What was counted

Text in the Telegram export was split into kept calls, excluded malformed prices, and everything else. A kept call has a side, an entry zone, at least one TP, and one SL, and every price in that message shares a scale and sits on the correct side of the zone. A price that cannot be reconciled is excluded and left as written.

Marketing replies are not calls. The export contains {report["tp_hit_messages"]} messages that say TP HIT or ALL TP Done. That count is the channel's advertisement. It is not the win count. Scored exits below were read off bar highs and lows.

| Count | Value |
| --- | ---: |
| parsed_total | {counts["parsed_total"]} |
| parsed_calls | {counts["parsed_calls"]} |
| excluded_malformed | {counts["excluded_malformed"]} |
| scored | {counts["scored"]} |
| unresolved | {counts["unresolved"]} |
| tp_hit_messages (not wins) | {report["tp_hit_messages"]} |
| scored_exits_from_bars | {report["scored_exits_from_bars"]} |

Identity: excluded_malformed + scored + unresolved = parsed_total ({counts["excluded_malformed"]} + {counts["scored"]} + {counts["unresolved"]} = {counts["parsed_total"]}). parsed_calls = scored + unresolved ({counts["parsed_calls"]} = {counts["scored"]} + {counts["unresolved"]}).

Excluded reasons: {excluded_bits}.

Fill reasons: {reason_bits}.

## Clock

Export titles are offset {sig["export_timezone"]}. The price file `{tape["path"]}` stamps M15 bars in UTC ({tape["bars"]} bars, {tape["first_open_utc"]} through {tape["last_open_utc"]}). `bar_time` is the export instant converted to UTC. The bar that contains the call is not used. The first eligible bar is the next open after that instant.

## Fill convention

Entry is the first touch of the zone on an eligible bar. Full size is 1.0 lot, contract size 100. The position leaves at the nearest stated TP or the SL, whichever a later bar trades by itself. A bar that trades both stays unresolved. The fill bar is not an exit: if it also reaches the SL or the nearest TP, the call stays unresolved, because one OHLC bar cannot order the touch against the fill. No bar after the call, no touch of the zone, or neither level before the file ends: unresolved.

Cost is the entry bar's spread in points when that spread is positive, plus the cost book slippage {costs["slippage_points"]} points and commission {costs["commission_per_lot"]} per lot per side (`{costs["path"]}`). When the bar has no positive spread, the charge uses the recorded assumption of {costs["missing_spread_points"]} points, the median of the positive M15 spreads on this file. Round trip matches the research book: one spread, slippage on both fills, commission per lot per side.

## Signature of the messages

These figures describe the kept calls. They were not used to choose a rule or a knob.

* Time of day is the export clock {sig["export_timezone"]}. Calls fall in {sig["distinct_hours_export_clock"]} distinct hours. Counts by hour: {", ".join(hour_bits)}.
* Side mix: buy {sig["side_buy"]}, sell {sig["side_sell"]}.
* Zone width in price units (high minus low): {_dist_phrase(sig["zone_width"])}.
* Stop distance beyond the zone: {_dist_phrase(sig["sl_distance"])}.
* Distance from the zone to the nearest TP: {_dist_phrase(sig["nearest_tp_distance"])}.
* Spacing between consecutive stated TPs: {_dist_phrase(sig["tp_spacing"])}.
* Messages that name an indicator word: {sig["indicator_messages"]}. Messages that name a session word: {sig["session_word_messages"]}. Messages that name an exogenous series: {sig["exogenous_messages"]}.
* Bar time before {sig["holdout_start_utc"]} UTC: {sig["n_before_holdout"]}. On or after that instant: {sig["n_on_or_after_holdout"]}.

The messages state a zone, a stop, and a TP ladder. They do not state an indicator rule.

## Closed-shape verdict

Matched shapes: {shapes}.

{reason_lines}

**{outcome["outcome"]}.** promote / live_go / PAPER_GO stay no / false / no. Holdout dates were not used to pick or keep a family. `strategy_params.json` was not rewritten.
"""


def _print_counts(report: dict) -> None:
    counts = report["counts"]
    print(f"parsed_total={counts['parsed_total']}")
    print(f"parsed_calls={counts['parsed_calls']}")
    print(f"excluded_malformed={counts['excluded_malformed']}")
    print(f"scored={counts['scored']}")
    print(f"unresolved={counts['unresolved']}")
    print(f"tp_hit_messages={report['tp_hit_messages']}")
    print(f"scored_exits_from_bars={report['scored_exits_from_bars']}")
    print(
        "check_partition="
        + (
            "ok"
            if counts["excluded_malformed"] + counts["scored"] + counts["unresolved"]
            == counts["parsed_total"]
            else "FAIL"
        )
    )
    print(
        "check_kept="
        + (
            "ok"
            if counts["parsed_calls"] == counts["scored"] + counts["unresolved"]
            else "FAIL"
        )
    )
    print(f"outcome={report['outcome']}")
    print("tp_hit_messages_are_not_wins=yes")


def run(
    export_dir: Path,
    bars_path: Path,
    costs_path: Path,
    holdout_path: Path,
    out_path: Path,
    note_path: Path,
) -> dict:
    batch = parse_export_dir(export_dir)
    bars = load_m15_bars(bars_path)
    missing = positive_spread_median(bars)
    cost, cost_meta = load_cost_book(costs_path, missing_spread_points=missing)
    holdout_utc = load_holdout_utc(holdout_path)
    fills = replay(batch.calls, bars, cost)
    report = build_report(
        batch,
        fills,
        export_dir=export_dir,
        bars_path=bars_path,
        bars=bars,
        cost_meta=cost_meta,
        holdout_utc=holdout_utc,
    )
    if report["outcome"] != "NO_NEW_FAMILY":
        raise RuntimeError("refusing to write a screen from this tape")
    if "profit_factor" in report or "profit_factor" in report["closed_shape"]:
        raise RuntimeError("replay report must not carry a profit factor")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    note_path.write_text(render_note(report), encoding="utf-8")
    _print_counts(report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, default=DEFAULT_EXPORT)
    parser.add_argument("--bars", type=Path, default=DEFAULT_BARS)
    parser.add_argument("--costs", type=Path, default=DEFAULT_COSTS)
    parser.add_argument("--holdout", type=Path, default=DEFAULT_HOLDOUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--note", type=Path, default=DEFAULT_NOTE)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    run(
        args.export,
        args.bars,
        args.costs,
        args.holdout,
        args.out,
        args.note,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
