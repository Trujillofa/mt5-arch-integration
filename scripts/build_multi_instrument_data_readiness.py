#!/usr/bin/env python3
"""Phase-0 multi-instrument data readiness (no signals / PF / grids).

Reads Wine Vantage history_*.csv (+ optional symbol_meta_*.csv), normalizes to
repo data/instruments/, freezes per-symbol manifests, and writes a joint
common-window report.

SAFETY: offline data QA only. Does not score strategies.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HOLDOUT_LOCK = ROOT / "results" / "xau_holdout_lock.json"
COSTS_XAU = ROOT / "results" / "xau_research_costs.json"
# Under results/ (not gitignored data/) so manifests + CSVs stay reviewable in-repo.
OUT_DIR = ROOT / "results" / "instrument_data"
MANIFEST_DIR = ROOT / "results" / "instrument_data_manifests"
REPORT_PATH = ROOT / "results" / "multi_instrument_data_readiness.md"

SYMBOLS = ("XAUUSD", "EURUSD", "GBPUSD")
PRIMARY_TF = "H1"
DEVELOP_END = pd.Timestamp("2026-01-01T00:00:00+00:00")

# House defaults when SymbolInfo meta is unavailable (documented as fallback).
FALLBACK_META: dict[str, dict[str, Any]] = {
    "XAUUSD": {
        "point_size": 0.01,
        "contract_size": 100.0,
        "digits": 2,
        "notes": "XAU CFD house convention (matches research costs + backtest.CONTRACT_SIZE)",
    },
    "EURUSD": {
        "point_size": 0.00001,
        "contract_size": 100_000.0,
        "digits": 5,
        "notes": "standard FX lot (fallback if meta missing)",
    },
    "GBPUSD": {
        "point_size": 0.00001,
        "contract_size": 100_000.0,
        "digits": 5,
        "notes": "standard FX lot (fallback if meta missing)",
    },
}


def _wine_bridge_dir() -> Path:
    prefix = Path(os.environ.get("WINEPREFIX", Path.home() / ".mt5-vantage"))
    for brand in (
        "Vantage International MT5",
        "MetaTrader 5",
    ):
        p = prefix / "drive_c/Program Files" / brand / "MQL5/Files/mt5_arch"
        if p.is_dir():
            return p
    return prefix / "drive_c/Program Files/Vantage International MT5/MQL5/Files/mt5_arch"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_meta_csv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    df = pd.read_csv(path, header=None, names=["key", "value"])
    return {str(r.key): str(r.value) for r in df.itertuples(index=False)}


def _parse_history(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    need = [
        "time",
        "timeframe",
        "symbol",
        "open",
        "high",
        "low",
        "close",
        "tick_volume",
        "spread",
    ]
    for c in need:
        if c not in df.columns:
            raise RuntimeError(f"{path}: missing column {c}")
    df = df[need].copy()
    df["time"] = pd.to_datetime(df["time"], format="%Y.%m.%d %H:%M", utc=True)
    for c in ("open", "high", "low", "close", "spread"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["tick_volume"] = pd.to_numeric(df["tick_volume"], errors="coerce").fillna(0).astype(int)
    return df


def _fill_zero_spreads(h1: pd.DataFrame) -> tuple[pd.DataFrame, int, float]:
    """Fill non-positive spreads with H1 median (same policy as fetch_data bridge dump)."""
    out = h1.copy()
    pos = out["spread"] > 0
    if not pos.any():
        return out, int((~pos).sum()), float("nan")
    median = float(out.loc[pos, "spread"].median())
    zero_n = int((out["spread"] <= 0).sum())
    if zero_n:
        out.loc[out["spread"] <= 0, "spread"] = median
    return out, zero_n, median


def _h1_gaps(times: pd.Series) -> dict[str, Any]:
    """Detect large gaps on H1 develop series (weekends expected)."""
    t = times.sort_values().reset_index(drop=True)
    if len(t) < 2:
        return {"n_gaps_gt_3h": 0, "max_gap_hours": 0.0, "large_gaps": []}
    deltas = t.diff().dt.total_seconds() / 3600.0
    # Weekends ~48h+; flag gaps > 72h as unusual (holiday / missing data)
    large = []
    for i in range(1, len(t)):
        g = float(deltas.iloc[i])
        if g > 72:
            large.append(
                {
                    "after": t.iloc[i - 1].isoformat(),
                    "before": t.iloc[i].isoformat(),
                    "gap_hours": round(g, 2),
                }
            )
    return {
        "n_gaps_gt_72h": len(large),
        "max_gap_hours": float(np.nanmax(deltas.to_numpy())) if len(deltas) else 0.0,
        "large_gaps_sample": large[:20],
    }


@dataclass
class SymbolManifest:
    symbol: str
    status: str
    source_path: str
    source_sha256: str
    research_csv: str
    research_csv_sha256: str
    timeframe: str
    n_rows_raw: int
    n_rows_h1: int
    n_rows_h1_develop: int
    time_min: str
    time_max: str
    develop_time_min: str
    develop_time_max: str
    develop_rule: str
    holdout_start: str
    missing_duplicate_bars: dict[str, Any]
    gap_report: dict[str, Any]
    spread: dict[str, Any]
    point_size: float
    contract_size: float
    digits: int | None
    commission_per_lot: float
    commission_notes: str
    slippage_points: float
    slippage_notes: str
    spread_source: str
    broker: str
    account_type: str
    server: str
    login: int | None
    meta_source: str
    meta_raw: dict[str, str]
    quality_flags: list[str]
    frozen_at_utc: str


def build_symbol(
    symbol: str,
    *,
    bridge_dir: Path,
    costs: dict[str, Any],
    holdout_start: pd.Timestamp,
) -> tuple[SymbolManifest, pd.DataFrame | None]:
    src = bridge_dir / f"history_{symbol}.csv"
    meta_path = bridge_dir / f"symbol_meta_{symbol}.csv"
    flags: list[str] = []
    if not src.is_file():
        flags.append("MISSING_SOURCE_CSV")
        fb = FALLBACK_META[symbol]
        m = SymbolManifest(
            symbol=symbol,
            status="FAIL",
            source_path=str(src),
            source_sha256="",
            research_csv="",
            research_csv_sha256="",
            timeframe=PRIMARY_TF,
            n_rows_raw=0,
            n_rows_h1=0,
            n_rows_h1_develop=0,
            time_min="",
            time_max="",
            develop_time_min="",
            develop_time_max="",
            develop_rule="time < holdout_start",
            holdout_start=holdout_start.isoformat(),
            missing_duplicate_bars={},
            gap_report={},
            spread={},
            point_size=float(fb["point_size"]),
            contract_size=float(fb["contract_size"]),
            digits=int(fb["digits"]),
            commission_per_lot=0.0,
            commission_notes="Standard STP: commission 0; cost in spread",
            slippage_points=0.0,
            slippage_notes="UNMEASURED — left at 0; not a claim of zero slip",
            spread_source="MqlRates.spread via Wine Vantage export",
            broker=str(costs.get("broker", "Vantage")),
            account_type=str(costs.get("account_type", "STANDARD_STP")),
            server=str(costs.get("server", "")),
            login=costs.get("login"),
            meta_source="fallback",
            meta_raw={},
            quality_flags=flags,
            frozen_at_utc=datetime.now(UTC).isoformat(),
        )
        return m, None

    raw = _parse_history(src)
    h1 = raw.loc[raw["timeframe"] == PRIMARY_TF].copy()
    h1 = h1.sort_values("time").reset_index(drop=True)

    # Duplicates
    n_dup = int(h1["time"].duplicated().sum())
    if n_dup:
        flags.append(f"DUPLICATE_TIMESTAMPS={n_dup}")
        h1 = h1.drop_duplicates(subset=["time"], keep="last").reset_index(drop=True)

    # OHLC sanity
    bad_ohlc = int(
        (
            (h1["high"] < h1[["open", "close", "low"]].max(axis=1))
            | (h1["low"] > h1[["open", "close", "high"]].min(axis=1))
            | h1[["open", "high", "low", "close"]].isna().any(axis=1)
        ).sum()
    )
    if bad_ohlc:
        flags.append(f"BAD_OHLC_ROWS={bad_ohlc}")

    h1, zero_spread_n, spread_median = _fill_zero_spreads(h1)
    if zero_spread_n:
        flags.append(f"ZERO_SPREAD_FILLED={zero_spread_n}")

    develop = h1.loc[h1["time"] < holdout_start].reset_index(drop=True)
    if develop.empty:
        flags.append("EMPTY_DEVELOP_WINDOW")

    gaps = _h1_gaps(develop["time"]) if len(develop) else {}
    if gaps.get("n_gaps_gt_72h", 0) > 0:
        flags.append(f"LARGE_GAPS_GT_72H={gaps['n_gaps_gt_72h']}")

    # Meta
    meta_raw = _load_meta_csv(meta_path)
    fb = FALLBACK_META[symbol]
    if meta_raw.get("point"):
        point = float(meta_raw["point"])
        contract = float(meta_raw.get("contract_size") or fb["contract_size"])
        digits = int(float(meta_raw.get("digits") or fb["digits"]))
        meta_source = str(meta_path)
    else:
        point = float(fb["point_size"])
        contract = float(fb["contract_size"])
        digits = int(fb["digits"])
        meta_source = f"fallback:{fb['notes']}"
        flags.append("SYMBOL_META_FALLBACK")

    # Write research CSV (full H1 with filled spreads; develop subset also noted)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    research_path = OUT_DIR / f"{symbol.lower()}_h1.csv"
    h1_out = h1.copy()
    h1_out["time"] = h1_out["time"].dt.strftime("%Y-%m-%d %H:%M:%S%z")
    # normalize +00:00 style
    h1_out.to_csv(research_path, index=False)

    develop_path = OUT_DIR / f"{symbol.lower()}_h1_develop.csv"
    dev_out = develop.copy()
    if len(dev_out):
        dev_out["time"] = dev_out["time"].dt.strftime("%Y-%m-%d %H:%M:%S%z")
    dev_out.to_csv(develop_path, index=False)

    spread_stats = {
        "n": int(len(h1)),
        "median_pts": float(h1["spread"].median()) if len(h1) else None,
        "mean_pts": float(h1["spread"].mean()) if len(h1) else None,
        "min_pts": float(h1["spread"].min()) if len(h1) else None,
        "max_pts": float(h1["spread"].max()) if len(h1) else None,
        "zero_bars_filled": zero_spread_n,
        "fill_median_pts": spread_median if zero_spread_n else None,
        "unit": "points (MqlRates.spread)",
    }

    status = "OK" if not any(f.startswith("MISSING") or f.startswith("EMPTY") for f in flags) else "FAIL"
    # Soft warnings don't fail status unless develop empty/missing
    if "EMPTY_DEVELOP_WINDOW" in flags or "MISSING_SOURCE_CSV" in flags:
        status = "FAIL"
    elif flags:
        status = "OK_WITH_FLAGS"

    m = SymbolManifest(
        symbol=symbol,
        status=status,
        source_path=str(src),
        source_sha256=_sha256_file(src),
        research_csv=str(research_path.relative_to(ROOT)),
        research_csv_sha256=_sha256_file(research_path),
        timeframe=PRIMARY_TF,
        n_rows_raw=int(len(raw)),
        n_rows_h1=int(len(h1)),
        n_rows_h1_develop=int(len(develop)),
        time_min=h1["time"].min().isoformat() if len(h1) else "",
        time_max=h1["time"].max().isoformat() if len(h1) else "",
        develop_time_min=develop["time"].min().isoformat() if len(develop) else "",
        develop_time_max=develop["time"].max().isoformat() if len(develop) else "",
        develop_rule="time < holdout_start",
        holdout_start=holdout_start.isoformat(),
        missing_duplicate_bars={
            "duplicate_timestamps_dropped": n_dup,
            "bad_ohlc_rows": bad_ohlc,
            "develop_csv": str(develop_path.relative_to(ROOT)),
            "develop_csv_sha256": _sha256_file(develop_path) if develop_path.is_file() else "",
        },
        gap_report=gaps,
        spread=spread_stats,
        point_size=point,
        contract_size=contract,
        digits=digits,
        commission_per_lot=0.0,
        commission_notes=(
            "Standard STP: no separate commission; trading cost is in the measured spread. "
            f"Account type={costs.get('account_type', 'STANDARD_STP')}."
        ),
        slippage_points=0.0,
        slippage_notes="UNMEASURED — left at 0 until demo/live fill sample. Not a claim of zero slip.",
        spread_source="MqlRates.spread from Vantage terminal export (Wine file bridge / ExportInstrumentHistory)",
        broker=str(costs.get("broker", "Vantage")),
        account_type=str(costs.get("account_type", "STANDARD_STP")),
        server=str(costs.get("server", "")),
        login=costs.get("login"),
        meta_source=meta_source,
        meta_raw=meta_raw,
        quality_flags=flags,
        frozen_at_utc=datetime.now(UTC).isoformat(),
    )
    return m, develop


def common_window(develops: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Calendar overlap + session-aware alignment.

    FX vs XAU H1 bar counts differ by design (session calendars). Equality is
    *not* required. We require:
      - all three symbols present with non-empty develop
      - overlapping calendar interval with each series ≥ MIN_DEVELOP_BARS
      - timestamp *intersection* size ≥ MIN_INTERSECTION_BARS (joint analysis pool)
    """
    min_develop = 10_000
    min_intersection = 8_000
    if not develops:
        return {"status": "FAIL", "reason": "no develop series"}
    starts = {s: df["time"].min() for s, df in develops.items() if len(df)}
    ends = {s: df["time"].max() for s, df in develops.items() if len(df)}
    if len(starts) < 3:
        return {
            "status": "FAIL",
            "reason": "fewer than 3 symbols with develop bars",
            "starts": {k: v.isoformat() for k, v in starts.items()},
        }
    common_start = max(starts.values())
    common_end = min(ends.values())
    if common_start >= common_end:
        return {
            "status": "FAIL",
            "reason": "no overlapping develop interval",
            "starts": {k: v.isoformat() for k, v in starts.items()},
            "ends": {k: v.isoformat() for k, v in ends.items()},
        }
    counts: dict[str, int] = {}
    sets: dict[str, set[pd.Timestamp]] = {}
    for s, df in develops.items():
        sub = df.loc[(df["time"] >= common_start) & (df["time"] <= common_end)]
        counts[s] = int(len(sub))
        sets[s] = set(sub["time"].tolist())
    vals = list(counts.values())
    inter = sets[SYMBOLS[0]]
    for s in SYMBOLS[1:]:
        inter = inter.intersection(sets[s])
    n_inter = len(inter)
    # Equal bar counts are NOT expected across FX vs XAU sessions.
    bar_count_equal = max(vals) - min(vals) <= max(5, int(0.001 * max(vals)))
    enough_each = all(c >= min_develop for c in vals)
    enough_joint = n_inter >= min_intersection
    if enough_each and enough_joint:
        status = "OK"
    else:
        status = "FAIL"
    return {
        "status": status,
        "common_start": common_start.isoformat(),
        "common_end": common_end.isoformat(),
        "holdout_start": DEVELOP_END.isoformat(),
        "n_bars_per_symbol": counts,
        "bar_count_range": {"min": min(vals), "max": max(vals)},
        "bar_counts_equal": bar_count_equal,
        "bar_count_note": (
            "FX vs XAU H1 counts differ by session calendar; not a hard fail. "
            "Joint work uses timestamp intersection."
        ),
        "n_intersection_timestamps": n_inter,
        "min_develop_bars_required": min_develop,
        "min_intersection_required": min_intersection,
        "enough_each_symbol": enough_each,
        "enough_joint_intersection": enough_joint,
        "per_symbol_develop_start": {k: v.isoformat() for k, v in starts.items()},
        "per_symbol_develop_end": {k: v.isoformat() for k, v in ends.items()},
    }


def write_report(
    manifests: list[SymbolManifest],
    common: dict[str, Any],
    gate: str,
) -> None:
    lines = [
        "# Multi-instrument data readiness (Phase 0)",
        "",
        f"**Frozen at (UTC):** {datetime.now(UTC).isoformat()}",
        f"**Gate:** `{gate}`",
        f"**Holdout / develop rule:** `time < {DEVELOP_END.isoformat()}`",
        f"**Account:** Vantage Standard STP (from `results/xau_research_costs.json`)",
        "",
        "## Per-symbol",
        "",
        "| Symbol | Status | H1 rows | Develop H1 | Range (full) | Spread median (pts) | Point | Contract | Flags |",
        "|--------|--------|---------|------------|--------------|---------------------|-------|----------|-------|",
    ]
    for m in manifests:
        lines.append(
            f"| {m.symbol} | {m.status} | {m.n_rows_h1} | {m.n_rows_h1_develop} | "
            f"{m.time_min[:10] if m.time_min else '—'} → {m.time_max[:10] if m.time_max else '—'} | "
            f"{m.spread.get('median_pts', '—')} | {m.point_size} | {m.contract_size} | "
            f"{','.join(m.quality_flags) if m.quality_flags else '—'} |"
        )
    lines += [
        "",
        "## Costs (frozen assumptions)",
        "",
        "- **Commission:** 0.0 (Standard STP)",
        "- **Spread:** measured per-bar `MqlRates.spread` (points)",
        "- **Slippage:** **UNMEASURED** (0.0 placeholder; sensitivity points 0/5/10/20 later)",
        "",
        "## Common develop window",
        "",
        "```json",
        json.dumps(common, indent=2),
        "```",
        "",
        "## Gate rule",
        "",
        "- `PASS_CLEAN` → freeze multi-instrument family charter next (0–1 knob, joint null).",
        "- `FAIL_DATA` → repair exports/meta only; no thesis scoring.",
        "",
        "## Explicitly not done",
        "",
        "- No signals, PF, grids, parameter inspection, holdout selection, paper, or live.",
        "",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> int:
    bridge = _wine_bridge_dir()
    print(f"Bridge dir: {bridge}")
    costs: dict[str, Any] = {}
    if COSTS_XAU.is_file():
        costs = json.loads(COSTS_XAU.read_text())
    holdout = DEVELOP_END
    if HOLDOUT_LOCK.is_file():
        hs = json.loads(HOLDOUT_LOCK.read_text()).get("holdout_start")
        if hs:
            holdout = pd.Timestamp(hs)
            if holdout.tzinfo is None:
                holdout = holdout.tz_localize("UTC")

    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    manifests: list[SymbolManifest] = []
    develops: dict[str, pd.DataFrame] = {}
    for sym in SYMBOLS:
        m, dev = build_symbol(sym, bridge_dir=bridge, costs=costs, holdout_start=holdout)
        manifests.append(m)
        path = MANIFEST_DIR / f"{sym.lower()}_h1_manifest.json"
        path.write_text(json.dumps(asdict(m), indent=2) + "\n")
        print(f"{sym}: status={m.status} h1={m.n_rows_h1} develop={m.n_rows_h1_develop} flags={m.quality_flags}")
        if dev is not None and len(dev):
            develops[sym] = dev

    common = common_window(develops)
    joint_path = MANIFEST_DIR / "common_develop_window.json"
    joint_path.write_text(json.dumps(common, indent=2) + "\n")

    hard_fail = any(m.status == "FAIL" for m in manifests) or common.get("status") == "FAIL"
    if hard_fail:
        gate = "FAIL_DATA"
    else:
        gate = "PASS_CLEAN"

    # Unresolved instrument costs: missing meta for FX is a soft flag; still PASS_CLEAN
    # if history OK, but record for review.
    write_report(manifests, common, gate)
    print(f"Gate: {gate}")
    print(f"Report: {REPORT_PATH}")
    print(f"Manifests: {MANIFEST_DIR}")
    return 0 if gate == "PASS_CLEAN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
