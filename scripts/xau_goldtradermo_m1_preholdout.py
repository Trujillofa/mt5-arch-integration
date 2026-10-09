#!/usr/bin/env python3
"""Rescore pre-holdout GOLDTRADERMO calls on M1. Descriptive only.

The 38 kept calls whose bar time is before 2026-01-01 are replayed with
the same ``fill_call`` as the M15 tape. Calls on or after that instant
are counted and then left unread. No knob is chosen. Outcome is
``NO_NEW_FAMILY``.

Clock, measured before any fill: the M1 file's meta records a trade-server
offset of +3h at the September 2026 fetch. December 2025 and January 2026
M1 OHLC reproduce ``xauusd_data.csv`` M15 at offset 0. That CSV is the UTC
clock the call times already use. This script applies offset 0 and refuses
to score if a compared bar disagrees.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import xau_goldtradermo_calls as gtm  # noqa: E402

DEFAULT_M1 = Path("/home/yderf/Projects/trading/mt5-arch-integration/data/xauusd_m1_mcp.csv")
WINDOW_START = datetime(2025, 12, 1)
WINDOW_END = datetime(2026, 8, 8)
OHLC_TOLERANCE = 1e-6


def rows_before_holdout(rows: list[dict], holdout: datetime) -> list[dict]:
    """Keep rows whose bar time is strictly before the holdout."""
    kept: list[dict] = []
    for row in rows:
        if datetime.fromisoformat(row["bar_time_utc"]) < holdout:
            kept.append(row)
    return kept


def call_from_row(row: dict) -> gtm.Call:
    return gtm.Call(
        message_id=row["message_id"],
        source_file=row["source_file"],
        export_time=datetime.fromisoformat(row["export_time"]),
        export_offset=row["export_offset"],
        bar_time=datetime.fromisoformat(row["bar_time_utc"]),
        side=row["side"],
        zone_lo=float(row["zone_lo"]),
        zone_hi=float(row["zone_hi"]),
        tps=tuple(float(level) for level in row["tps"]),
        sl=float(row["sl"]),
        text="",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_m1(frame, to_datetime):
    renamed = {column: column.strip("<>").lower() for column in frame.columns}
    out = frame.rename(columns=renamed)
    needed = {"date", "time", "open", "high", "low", "close"}
    missing = needed.difference(out.columns)
    if missing:
        raise ValueError(f"M1 file missing columns {sorted(missing)}")
    date = out["date"].astype(str).str.replace(".", "-", regex=False)
    stamps = date + " " + out["time"].astype(str)
    out = out.copy()
    out["stamp"] = to_datetime(stamps)
    return out


def read_m1(path: Path, *, start: datetime, end: datetime):
    import pandas as pd

    frame = _normalize_m1(pd.read_csv(path, sep="\t"), pd.to_datetime)
    mask = (frame["stamp"] >= start) & (frame["stamp"] < end)
    return frame.loc[mask].sort_values("stamp")


def read_m15(path: Path, *, start: datetime, end: datetime):
    import pandas as pd

    frame = pd.read_csv(path)
    if "timeframe" in frame.columns:
        frame = frame[frame["timeframe"].astype(str) == "M15"]
    if "symbol" in frame.columns:
        frame = frame[frame["symbol"].astype(str).str.upper() == "XAUUSD"]
    frame = frame.copy()
    frame["stamp"] = pd.to_datetime(frame["time"], utc=True).dt.tz_localize(None)
    mask = (frame["stamp"] >= start) & (frame["stamp"] < end)
    return frame.loc[mask]


def clock_agreement(m1, m15, *, min_minutes: int) -> dict:
    """Compare M1 aggregated at offset 0 with M15. Raise if any OHLC disagrees."""
    grouped = (
        m1.groupby(m1["stamp"].dt.floor("15min"), sort=True)
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            n=("open", "size"),
        )
    )
    full = grouped[grouped["n"] >= min_minutes]
    compared = 0
    for stamp, bar in m15.set_index("stamp").iterrows():
        if stamp not in full.index:
            continue
        minute = full.loc[stamp]
        compared += 1
        for column in ("open", "high", "low", "close"):
            if abs(float(bar[column]) - float(minute[column])) > OHLC_TOLERANCE:
                raise ValueError(
                    f"M1 offset 0 disagrees with M15 at {stamp} {column}: "
                    f"M15 {float(bar[column])} M1 {float(minute[column])}"
                )
    if compared == 0:
        raise ValueError("no M15 bar overlapped a full M1 bucket")
    return {
        "offset_hours": 0,
        "min_minutes": min_minutes,
        "m15_bars_in_window": int(len(m15)),
        "compared": compared,
        "exact": compared,
    }


def bars_from_m1(frame) -> list[gtm.Bar]:
    bars: list[gtm.Bar] = []
    spreads = frame["spread"] if "spread" in frame.columns else [None] * len(frame)
    for stamp, op, hi, lo, cl, sp in zip(
        frame["stamp"],
        frame["open"],
        frame["high"],
        frame["low"],
        frame["close"],
        spreads,
        strict=True,
    ):
        high = float(hi)
        low = float(lo)
        if high < low:
            continue
        bars.append(
            gtm.Bar(
                time=stamp.to_pydatetime(),
                open=float(op),
                high=high,
                low=low,
                close=float(cl),
                spread=gtm._spread_value(sp),
            )
        )
    bars.sort(key=lambda bar: bar.time)
    dedup: list[gtm.Bar] = []
    for bar in bars:
        if dedup and dedup[-1].time == bar.time:
            continue
        dedup.append(bar)
    return dedup


def transition_bucket(m15_status: str, m15_reason: str, m1_status: str, m1_reason: str) -> str:
    if m15_status == "unresolved" and m1_status == "unresolved":
        return "unresolved_stays_unresolved"
    if m15_status == "unresolved" and m1_reason == "tp":
        return "unresolved_to_tp"
    if m15_status == "unresolved" and m1_reason == "sl":
        return "unresolved_to_sl"
    if m15_status == "unresolved":
        return "unresolved_to_other"
    if m15_reason == m1_reason:
        return f"m15_{m15_reason}_unchanged"
    if m1_status == "unresolved":
        return f"m15_{m15_reason}_to_unresolved"
    return f"m15_{m15_reason}_to_{m1_reason}"


def _walk_has_key(obj: object, key: str) -> bool:
    if isinstance(obj, dict):
        return key in obj or any(_walk_has_key(value, key) for value in obj.values())
    if isinstance(obj, list):
        return any(_walk_has_key(value, key) for value in obj)
    return False


def assert_descriptive(report: dict, *, holdout: datetime, n_pre: int) -> None:
    if report["outcome"] != "NO_NEW_FAMILY":
        raise RuntimeError("refusing to write a family from a finer bar")
    if report["family_id"] is not None or report["knobs"] is not None:
        raise RuntimeError("refusing to write a family_id or a knob")
    if _walk_has_key(report, "profit_factor"):
        raise RuntimeError("refusing a profit_factor key on a descriptive rescore")
    if len(report["calls"]) != n_pre:
        raise RuntimeError("rescore call count does not match the pre-holdout set")
    if report["counts"]["scored"] + report["counts"]["unresolved"] != n_pre:
        raise RuntimeError("scored + unresolved != pre-holdout calls")
    for row in report["calls"]:
        if datetime.fromisoformat(row["bar_time_utc"]) >= holdout:
            raise RuntimeError(f"{row['message_id']} is on or after the holdout")


def build_report(
    pre_rows: list[dict],
    fills: list[gtm.Fill],
    *,
    holdout: datetime,
    post_holdout_unread: int,
    clock: dict,
    m1_meta: dict,
    cost_meta: dict,
    replay_sha: str,
) -> dict:
    if len(pre_rows) != len(fills):
        raise ValueError("fill count does not match the pre-holdout calls")
    rows: list[dict] = []
    buckets: Counter[str] = Counter()
    m1_reasons: Counter[str] = Counter()
    for source, fill in zip(pre_rows, fills, strict=True):
        bar_time = datetime.fromisoformat(source["bar_time_utc"])
        if bar_time >= holdout:
            raise ValueError(f"{source['message_id']} is on or after the holdout")
        bucket = transition_bucket(source["status"], source["reason"], fill.status, fill.reason)
        buckets[bucket] += 1
        m1_reasons[fill.reason] += 1
        exit_on_holdout = False
        if fill.exit_bar_time is not None:
            exit_on_holdout = datetime.fromisoformat(fill.exit_bar_time) >= holdout
        entry_on_holdout = False
        if fill.entry_bar_time is not None:
            entry_on_holdout = datetime.fromisoformat(fill.entry_bar_time) >= holdout
        rows.append(
            {
                "message_id": source["message_id"],
                "export_time": source["export_time"],
                "bar_time_utc": source["bar_time_utc"],
                "side": source["side"],
                "zone_lo": source["zone_lo"],
                "zone_hi": source["zone_hi"],
                "sl": source["sl"],
                "nearest_tp": source["nearest_tp"],
                "m15_status": source["status"],
                "m15_reason": source["reason"],
                "m15_pnl": source["pnl"],
                "m1_status": fill.status,
                "m1_reason": fill.reason,
                "m1_entry_bar_time": fill.entry_bar_time,
                "m1_entry_price": fill.entry_price,
                "m1_exit_bar_time": fill.exit_bar_time,
                "m1_exit_price": fill.exit_price,
                "m1_pnl": fill.pnl,
                "m1_cost": fill.cost,
                "m1_spread_pts": fill.spread_pts,
                "m1_spread_source": fill.spread_source,
                "entry_on_or_after_holdout": entry_on_holdout,
                "exit_on_or_after_holdout": exit_on_holdout,
                "transition": bucket,
            }
        )
    scored = [row for row in rows if row["m1_status"] == "scored"]
    before = [row for row in scored if not row["entry_on_or_after_holdout"]]
    after = [row for row in scored if row["entry_on_or_after_holdout"]]
    net = sum(row["m1_pnl"] for row in scored)
    return {
        "kind": "goldtradermo_preholdout_m1_rescore",
        "outcome": "NO_NEW_FAMILY",
        "family_id": None,
        "knobs": None,
        "promote": False,
        "live_go": False,
        "PAPER_GO": "no",
        "role": (
            "Path order for calls already stated before the holdout. "
            "Not a selection set and not a new occupancy."
        ),
        "source_replay_sha256": replay_sha,
        "post_holdout_calls_left_unread": post_holdout_unread,
        "clock": clock,
        "m1": m1_meta,
        "costs": cost_meta,
        "counts": {
            "preholdout_calls": len(rows),
            "scored": len(scored),
            "unresolved": len(rows) - len(scored),
            "m15_scored": sum(1 for row in rows if row["m15_status"] == "scored"),
            "m15_unresolved": sum(1 for row in rows if row["m15_status"] == "unresolved"),
            "entries_on_or_after_holdout": sum(
                1 for row in rows if row["entry_on_or_after_holdout"]
            ),
            "scored_entries_on_or_after_holdout": len(after),
            "exits_on_or_after_holdout": sum(1 for row in rows if row["exit_on_or_after_holdout"]),
        },
        "transitions": dict(sorted(buckets.items())),
        "m1_reasons": dict(sorted(m1_reasons.items())),
        "scored_net": net,
        "scored_net_entry_before_holdout": sum(row["m1_pnl"] for row in before),
        "scored_net_entry_on_or_after_holdout": sum(row["m1_pnl"] for row in after),
        "calls": rows,
    }


def _px(value: object) -> str:
    if value is None:
        return ""
    text = f"{float(value):.5f}".rstrip("0").rstrip(".")
    return text


def _money(value: object) -> str:
    if value is None:
        return ""
    number = float(value)
    sign = "-" if number < 0 else ""
    return sign + f"{abs(number):,.2f}"


def render_note(report: dict) -> str:
    counts = report["counts"]
    clock = report["clock"]
    lines = [
        "# GOLDTRADERMO pre-holdout calls on M1",
        "",
        "**Outcome:** NO_NEW_FAMILY",
        "",
        "**promote / live_go / PAPER_GO:** no / false / no",
        "",
        "This note rescores the kept calls whose bar time is before the sealed "
        "holdout, on M1, with the same fill rule as the M15 replay. It does not "
        "open a family, choose a knob, or read the later calls as a selection set.",
        "",
        "## Who was rescored",
        "",
        f"Pre-holdout calls: {counts['preholdout_calls']}. "
        f"Post-holdout calls left unread: {report['post_holdout_calls_left_unread']}.",
        "",
        f"On M15, {counts['m15_scored']} of these calls had an ordered exit and "
        f"{counts['m15_unresolved']} stayed unresolved because one 15-minute bar "
        "contained the fill and a level, or both the stop and the nearest TP.",
        "",
        f"On M1, {counts['scored']} have an ordered exit and "
        f"{counts['unresolved']} stay unresolved. "
        f"Entries on or after 2026-01-01 UTC: {counts['entries_on_or_after_holdout']}. "
        f"Exits on or after that instant: {counts['exits_on_or_after_holdout']}. "
        "A fill after the holdout is the later life of a call placed before it. "
        "It was not used to choose a rule.",
        "",
        "## Clock",
        "",
        "The M1 file is official MT5 `get_chart_history` for Vantage XAUUSD. "
        f"Its meta records trade-server offset {clock['trade_server_offset_at_fetch_h']}h "
        f"at {clock['fetched_at_utc']}. That offset was not applied.",
        "",
        f"Offset 0 reproduces the UTC M15 tape: {clock['compared']} bars with at least "
        f"{clock['min_minutes']} M1 rows inside the bucket, {clock['exact']} exact OHLC matches, "
        f"window {clock['window_start']} through {clock['window_end']}. "
        "A disagreement aborts the rescore before any fill.",
        "",
        "## What the finer bar changed",
        "",
        "| Transition | Calls |",
        "| --- | ---: |",
    ]
    for name, count in report["transitions"].items():
        lines.append(f"| {name} | {count} |")
    lines.extend(
        [
            "",
            "M1 reasons: " + ", ".join(f"{key}={value}" for key, value in report["m1_reasons"].items()) + ".",
            "",
            "## Money on the M1-ordered trades",
            "",
            f"Ordered on M1: {counts['scored']}. "
            f"Net with the entry still before 2026-01-01: "
            f"{_money(report['scored_net_entry_before_holdout'])}. "
            f"Net with the entry on or after that instant: "
            f"{_money(report['scored_net_entry_on_or_after_holdout'])} "
            f"across {counts['scored_entries_on_or_after_holdout']} ordered calls. "
            "Size is 1.0 lot after the entry minute's spread. "
            "The M1 spread field is the minimum tick spread inside that minute. "
            "Unresolved calls are absent from both nets.",
            "",
            "This net describes the channel's already-stated calls. It is not a "
            "develop profit factor and it did not keep a family.",
            "",
            "## Each pre-holdout call",
            "",
            "| Export time | Message | Side | Zone | Stop | Nearest TP | M15 | M1 | M1 entry UTC | M1 exit UTC | M1 PnL |",
            "| --- | --- | --- | --- | ---: | ---: | --- | --- | --- | --- | ---: |",
        ]
    )
    for row in report["calls"]:
        zone = f"{_px(row['zone_lo'])}/{_px(row['zone_hi'])}"
        export = row["export_time"].replace("T", " ").replace("-05:00", "")
        lines.append(
            "| "
            + " | ".join(
                [
                    export,
                    row["message_id"],
                    row["side"],
                    zone,
                    _px(row["sl"]),
                    _px(row["nearest_tp"]),
                    row["m15_reason"],
                    row["m1_reason"],
                    row["m1_entry_bar_time"] or "",
                    row["m1_exit_bar_time"] or "",
                    _money(row["m1_pnl"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Why this is still not a family",
            "",
            "M1 orders some paths that one M15 bar could not. The messages are "
            "still a zone, a stop, and a TP ladder on XAUUSD, with no indicator, "
            "session, or outside series named. That shape is already closed. "
            "The other calls in the export sit on or after 2026-01-01 UTC and "
            "were not used here.",
            "",
            "**NO_NEW_FAMILY.** promote / live_go / PAPER_GO stay no / false / no.",
            "",
        ]
    )
    return "\n".join(lines)


def run(
    *,
    replay_path: Path,
    m1_path: Path,
    m15_path: Path,
    costs_path: Path,
    holdout_path: Path,
    out_path: Path,
    note_path: Path,
    min_minutes: int,
    min_clock_bars: int,
) -> dict:
    meta_path = Path(str(m1_path) + ".meta.json")
    if not meta_path.is_file():
        raise FileNotFoundError(f"missing M1 meta {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    digest = _sha256(m1_path)
    if digest != meta.get("sha256"):
        raise ValueError("M1 sha256 does not match its meta file")
    holdout = gtm.load_holdout_utc(holdout_path)
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    pre_rows = rows_before_holdout(replay["calls"], holdout)
    post_unread = len(replay["calls"]) - len(pre_rows)
    m1 = read_m1(m1_path, start=WINDOW_START, end=WINDOW_END)
    m15 = read_m15(m15_path, start=WINDOW_START, end=WINDOW_END)
    agreement = clock_agreement(m1, m15, min_minutes=min_minutes)
    if agreement["compared"] < min_clock_bars:
        raise ValueError(
            f"clock check compared {agreement['compared']} bars, below {min_clock_bars}"
        )
    bars = bars_from_m1(m1)
    missing = gtm.positive_spread_median(bars)
    cost, cost_meta = gtm.load_cost_book(costs_path, missing_spread_points=missing)
    cost_meta["missing_spread_rule"] = (
        "median of positive M1 spreads on the rescore window, used only when a "
        "minute has no positive spread"
    )
    fills = gtm.replay([call_from_row(row) for row in pre_rows], bars, cost)
    clock = {
        "measured_offset_hours": 0,
        "fetch_offset_applied": False,
        "trade_server_offset_at_fetch_h": meta.get("server_utc_offset_h"),
        "fetched_at_utc": meta.get("fetched_at_utc"),
        "window_start": WINDOW_START.isoformat(sep=" "),
        "window_end": WINDOW_END.isoformat(sep=" "),
        **agreement,
    }
    m1_meta = {
        "path": str(m1_path),
        "sha256": digest,
        "symbol": meta.get("symbol"),
        "period": meta.get("period"),
        "rows_in_window": int(len(m1)),
        "spread_note": meta.get("spread_note"),
    }
    report = build_report(
        pre_rows,
        fills,
        holdout=holdout,
        post_holdout_unread=post_unread,
        clock=clock,
        m1_meta=m1_meta,
        cost_meta=cost_meta,
        replay_sha=_sha256(replay_path),
    )
    assert_descriptive(report, holdout=holdout, n_pre=len(pre_rows))
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    note_path.write_text(render_note(report), encoding="utf-8")
    return report


def _print_report(report: dict) -> None:
    counts = report["counts"]
    print(f"preholdout_calls={counts['preholdout_calls']}")
    print(f"m1_scored={counts['scored']}")
    print(f"m1_unresolved={counts['unresolved']}")
    print(f"m15_scored={counts['m15_scored']}")
    print(f"m15_unresolved={counts['m15_unresolved']}")
    print(f"post_holdout_left_unread={report['post_holdout_calls_left_unread']}")
    print(f"clock_offset_hours={report['clock']['measured_offset_hours']}")
    print(f"clock_exact={report['clock']['exact']}")
    print(f"entries_on_or_after_holdout={counts['entries_on_or_after_holdout']}")
    print(f"exits_on_or_after_holdout={counts['exits_on_or_after_holdout']}")
    print(f"outcome={report['outcome']}")
    print("profit_factor_key=absent")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--replay",
        type=Path,
        default=ROOT / "results" / "xau_goldtradermo_calls_replay.json",
    )
    parser.add_argument("--m1", type=Path, default=DEFAULT_M1)
    parser.add_argument("--m15", type=Path, default=ROOT / "xauusd_data.csv")
    parser.add_argument(
        "--costs",
        type=Path,
        default=ROOT / "results" / "xau_research_costs.json",
    )
    parser.add_argument(
        "--holdout",
        type=Path,
        default=ROOT / "results" / "xau_holdout_lock.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "results" / "xau_goldtradermo_m1_preholdout.json",
    )
    parser.add_argument(
        "--note",
        type=Path,
        default=ROOT / "results" / "xau_goldtradermo_m1_preholdout.md",
    )
    parser.add_argument("--min-minutes", type=int, default=14)
    parser.add_argument("--min-clock-bars", type=int, default=1000)
    args = parser.parse_args(argv)
    report = run(
        replay_path=args.replay,
        m1_path=args.m1,
        m15_path=args.m15,
        costs_path=args.costs,
        holdout_path=args.holdout,
        out_path=args.out,
        note_path=args.note,
        min_minutes=args.min_minutes,
        min_clock_bars=args.min_clock_bars,
    )
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
