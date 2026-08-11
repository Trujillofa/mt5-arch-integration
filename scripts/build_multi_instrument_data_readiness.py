#!/usr/bin/env python3
"""Phase-0 multi-instrument data readiness — fail-closed (no signals / PF / grids).

Reads Wine Vantage history_*.csv + symbol_meta_*.csv + export_run.json,
normalizes to results/instrument_data/ with auditable spread columns, freezes
per-symbol manifests, and writes a joint common-window report.

Clock: bar times are broker **server** timestamps (offset-free). They are
stored as timezone-naive pandas timestamps and labeled ``server_clock_as_stored``
— never silently claimed as UTC.

SAFETY: offline data QA only.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HOLDOUT_LOCK = ROOT / "results" / "xau_holdout_lock.json"
COSTS_XAU = ROOT / "results" / "xau_research_costs.json"
OUT_DIR = ROOT / "results" / "instrument_data"
MANIFEST_DIR = ROOT / "results" / "instrument_data_manifests"
REPORT_PATH = ROOT / "results" / "multi_instrument_data_readiness.md"
EXPORT_RUN_REPO = MANIFEST_DIR / "export_run.json"

SYMBOLS = ("XAUUSD", "EURUSD", "GBPUSD")
PRIMARY_TF = "H1"
# Holdout boundary as **server-clock calendar** label (not a UTC conversion).
DEVELOP_END_SERVER = pd.Timestamp("2026-01-01 00:00:00")
CLOCK_CONTRACT = "server_clock_as_stored"

# Fail-closed thresholds
MAX_ZERO_SPREAD_IMPUTE_FRAC = 0.10  # >10% imputed → FAIL
MIN_DEVELOP_BARS = 10_000


def _wine_bridge_dir() -> Path:
    prefix = Path(os.environ.get("WINEPREFIX", Path.home() / ".mt5-vantage")).expanduser().resolve()
    for brand in ("Vantage International MT5", "MetaTrader 5"):
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
    out: dict[str, str] = {}
    for row in df.itertuples(index=False):
        out[str(row[0])] = str(row[1])
    return out


def _parse_history(path: Path) -> pd.DataFrame:
    """Parse export CSV. Times are naive server-clock (not UTC)."""
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
    # Offset-free MT5 TimeToString → naive Timestamp. Do NOT attach UTC.
    df["time"] = pd.to_datetime(df["time"], format="%Y.%m.%d %H:%M")
    for c in ("open", "high", "low", "close", "spread"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    tv = pd.to_numeric(df["tick_volume"], errors="coerce")
    df["tick_volume"] = tv.fillna(0).astype(int)
    return df


def _apply_spread_imputation(h1: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Preserve raw spread; impute non-positive with positive-only median.

    Output columns:
      - spread_raw_pts
      - spread_effective_pts  (used for cost modeling)
      - spread_imputed        (bool)
    """
    out = h1.copy()
    raw = out["spread"].astype(float)
    out["spread_raw_pts"] = raw
    pos = raw > 0
    if not bool(pos.any()):
        out["spread_effective_pts"] = raw
        out["spread_imputed"] = True
        return out, {
            "n_imputed": int(len(out)),
            "frac_imputed": 1.0,
            "fill_median_pts": None,
            "error": "no_positive_spreads",
        }
    median = float(raw.loc[pos].median())
    imputed = ~pos
    effective = raw.copy()
    effective.loc[imputed] = median
    out["spread_effective_pts"] = effective
    out["spread_imputed"] = imputed
    # Keep legacy column as effective for drop-in readers
    out["spread"] = effective
    n_imp = int(imputed.sum())
    return out, {
        "n_imputed": n_imp,
        "frac_imputed": float(n_imp / len(out)) if len(out) else 0.0,
        "fill_median_pts": median,
        "error": None,
    }


def _h1_gaps(times: pd.Series) -> dict[str, Any]:
    t = times.sort_values().reset_index(drop=True)
    if len(t) < 2:
        return {"n_gaps_gt_72h": 0, "max_gap_hours": 0.0, "large_gaps_sample": []}
    deltas = t.diff().dt.total_seconds() / 3600.0
    large: list[dict[str, Any]] = []
    for i in range(1, len(t)):
        g = float(deltas.iloc[i])
        if g > 72:
            large.append(
                {
                    "after": str(t.iloc[i - 1]),
                    "before": str(t.iloc[i]),
                    "gap_hours": round(g, 2),
                }
            )
    return {
        "n_gaps_gt_72h": len(large),
        "max_gap_hours": float(np.nanmax(deltas.to_numpy())),
        "large_gaps_sample": large[:20],
    }


@dataclass
class SymbolManifest:
    symbol: str
    status: str
    clock_contract: str
    source_path: str
    source_sha256: str
    research_csv: str
    research_csv_sha256: str
    timeframe: str
    n_rows_raw: int
    n_rows_h1: int
    n_rows_h1_develop: int
    time_min_server: str
    time_max_server: str
    develop_time_min_server: str
    develop_time_max_server: str
    develop_rule: str
    holdout_start_server: str
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
    export_run_id: str | None
    meta_source: str
    meta_raw: dict[str, str]
    hard_errors: list[str] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)
    frozen_at_utc: str = ""


def _load_export_run(bridge: Path) -> dict[str, Any] | None:
    for p in (bridge / "export_run.json", EXPORT_RUN_REPO):
        if p.is_file():
            return json.loads(p.read_text())
    return None


def build_symbol(
    symbol: str,
    *,
    bridge_dir: Path,
    costs: dict[str, Any],
    export_run: dict[str, Any] | None,
    holdout_start: pd.Timestamp,
) -> tuple[SymbolManifest, pd.DataFrame | None]:
    src = bridge_dir / f"history_{symbol}.csv"
    meta_path = bridge_dir / f"symbol_meta_{symbol}.csv"
    hard: list[str] = []
    flags: list[str] = []

    login = export_run.get("login") if export_run else costs.get("login")
    server = str(export_run.get("server") if export_run else costs.get("server") or "")
    run_id = export_run.get("run_id") if export_run else None

    if not src.is_file():
        hard.append("MISSING_SOURCE_CSV")
    if not meta_path.is_file():
        hard.append("MISSING_SYMBOL_META")

    if hard:
        m = SymbolManifest(
            symbol=symbol,
            status="FAIL",
            clock_contract=CLOCK_CONTRACT,
            source_path=str(src),
            source_sha256="",
            research_csv="",
            research_csv_sha256="",
            timeframe=PRIMARY_TF,
            n_rows_raw=0,
            n_rows_h1=0,
            n_rows_h1_develop=0,
            time_min_server="",
            time_max_server="",
            develop_time_min_server="",
            develop_time_max_server="",
            develop_rule="server_time < holdout_start_server",
            holdout_start_server=str(holdout_start),
            missing_duplicate_bars={},
            gap_report={},
            spread={},
            point_size=float("nan"),
            contract_size=float("nan"),
            digits=None,
            commission_per_lot=0.0,
            commission_notes="Standard STP: commission 0; cost in spread",
            slippage_points=0.0,
            slippage_notes="UNMEASURED — left at 0; not a claim of zero slip",
            spread_source="MqlRates.spread via Wine Vantage export",
            broker=str(costs.get("broker", "Vantage")),
            account_type=str(costs.get("account_type", "STANDARD_STP")),
            server=server,
            login=int(login) if login is not None else None,
            export_run_id=run_id,
            meta_source="",
            meta_raw={},
            hard_errors=hard,
            quality_flags=flags,
            frozen_at_utc=datetime.now(UTC).isoformat(),
        )
        return m, None

    raw = _parse_history(src)
    h1 = raw.loc[raw["timeframe"] == PRIMARY_TF].copy()
    h1 = h1.sort_values("time").reset_index(drop=True)

    n_dup = int(h1["time"].duplicated().sum())
    if n_dup:
        hard.append(f"DUPLICATE_TIMESTAMPS={n_dup}")
        h1 = h1.drop_duplicates(subset=["time"], keep="last").reset_index(drop=True)

    # Ordered hourly uniqueness
    if len(h1) >= 2:
        diffs = h1["time"].diff().dt.total_seconds()
        if bool((diffs.iloc[1:] < 0).any()):
            hard.append("TIME_NOT_MONOTONE")

    bad_ohlc = (
        (h1["high"] < h1[["open", "close", "low"]].max(axis=1))
        | (h1["low"] > h1[["open", "close", "high"]].min(axis=1))
        | h1[["open", "high", "low", "close"]].isna().any(axis=1)
    )
    n_bad = int(bad_ohlc.sum())
    if n_bad:
        hard.append(f"BAD_OHLC_ROWS={n_bad}")

    h1, imp = _apply_spread_imputation(h1)
    if imp.get("error"):
        hard.append(f"SPREAD_IMPUTE_ERROR={imp['error']}")
    frac_imp = float(imp.get("frac_imputed") or 0.0)
    if frac_imp > MAX_ZERO_SPREAD_IMPUTE_FRAC:
        hard.append(f"SPREAD_IMPUTE_FRAC={frac_imp:.4f}>{MAX_ZERO_SPREAD_IMPUTE_FRAC}")
    elif imp["n_imputed"]:
        flags.append(f"ZERO_SPREAD_IMPUTED={imp['n_imputed']}")

    develop = h1.loc[h1["time"] < holdout_start].reset_index(drop=True)
    if develop.empty:
        hard.append("EMPTY_DEVELOP_WINDOW")
    elif len(develop) < MIN_DEVELOP_BARS:
        hard.append(f"DEVELOP_BARS={len(develop)}<{MIN_DEVELOP_BARS}")

    gaps = _h1_gaps(develop["time"]) if len(develop) else {}
    if gaps.get("n_gaps_gt_72h", 0):
        flags.append(f"LARGE_GAPS_GT_72H={gaps['n_gaps_gt_72h']}")

    meta_raw = _load_meta_csv(meta_path)
    required_meta = ("point", "contract_size", "digits", "resolved")
    missing_meta = [k for k in required_meta if k not in meta_raw or not str(meta_raw[k]).strip()]
    if missing_meta:
        hard.append(f"INCOMPLETE_SYMBOL_META={missing_meta}")
        point = float("nan")
        contract = float("nan")
        digits = None
        meta_source = str(meta_path)
    else:
        point = float(meta_raw["point"])
        contract = float(meta_raw["contract_size"])
        digits = int(float(meta_raw["digits"]))
        meta_source = str(meta_path)
        if point <= 0 or contract <= 0:
            hard.append("INVALID_POINT_OR_CONTRACT")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    research_path = OUT_DIR / f"{symbol.lower()}_h1.csv"
    # Write auditable columns; times as server-clock strings (no Z/offset)
    h1_out = h1[
        [
            "time",
            "timeframe",
            "symbol",
            "open",
            "high",
            "low",
            "close",
            "tick_volume",
            "spread_raw_pts",
            "spread_effective_pts",
            "spread_imputed",
            "spread",
        ]
    ].copy()
    h1_out["time"] = h1_out["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    h1_out["clock"] = CLOCK_CONTRACT
    h1_out.to_csv(research_path, index=False)

    develop_path = OUT_DIR / f"{symbol.lower()}_h1_develop.csv"
    dev_out = develop.copy()
    if len(dev_out):
        dev_out = dev_out[
            [
                "time",
                "timeframe",
                "symbol",
                "open",
                "high",
                "low",
                "close",
                "tick_volume",
                "spread_raw_pts",
                "spread_effective_pts",
                "spread_imputed",
                "spread",
            ]
        ].copy()
        dev_out["time"] = dev_out["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        dev_out["clock"] = CLOCK_CONTRACT
    dev_out.to_csv(develop_path, index=False)

    n_imp_dev = int(develop["spread_imputed"].sum()) if len(develop) else 0
    frac_imp_dev = float(n_imp_dev / len(develop)) if len(develop) else 0.0

    spread_stats = {
        "n": int(len(h1)),
        "median_effective_pts": float(h1["spread_effective_pts"].median()) if len(h1) else None,
        "mean_effective_pts": float(h1["spread_effective_pts"].mean()) if len(h1) else None,
        "min_raw_pts": float(h1["spread_raw_pts"].min()) if len(h1) else None,
        "max_raw_pts": float(h1["spread_raw_pts"].max()) if len(h1) else None,
        "n_imputed_full": int(imp["n_imputed"]),
        "frac_imputed_full": float(imp["frac_imputed"]),
        "n_imputed_develop": n_imp_dev,
        "frac_imputed_develop": frac_imp_dev,
        "fill_median_pts": imp.get("fill_median_pts"),
        "unit": "points (MqlRates.spread)",
        "columns": ["spread_raw_pts", "spread_effective_pts", "spread_imputed"],
    }

    status = "FAIL" if hard else ("OK_WITH_IMPUTATION" if imp["n_imputed"] else "OK")

    m = SymbolManifest(
        symbol=symbol,
        status=status,
        clock_contract=CLOCK_CONTRACT,
        source_path=str(src),
        source_sha256=_sha256_file(src),
        research_csv=str(research_path.relative_to(ROOT)),
        research_csv_sha256=_sha256_file(research_path),
        timeframe=PRIMARY_TF,
        n_rows_raw=int(len(raw)),
        n_rows_h1=int(len(h1)),
        n_rows_h1_develop=int(len(develop)),
        time_min_server=str(h1["time"].min()) if len(h1) else "",
        time_max_server=str(h1["time"].max()) if len(h1) else "",
        develop_time_min_server=str(develop["time"].min()) if len(develop) else "",
        develop_time_max_server=str(develop["time"].max()) if len(develop) else "",
        develop_rule="server_time < holdout_start_server",
        holdout_start_server=str(holdout_start),
        missing_duplicate_bars={
            "duplicate_timestamps": n_dup,
            "bad_ohlc_rows": n_bad,
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
            "Standard STP: no separate commission; trading cost is in measured spread. "
            f"Account type={costs.get('account_type', 'STANDARD_STP')}."
        ),
        slippage_points=0.0,
        slippage_notes="UNMEASURED — left at 0 until demo/live fill sample. Not a claim of zero slip.",
        spread_source="MqlRates.spread from Vantage terminal export (ExportInstrumentHistory)",
        broker=str(costs.get("broker", "Vantage")),
        account_type=str(costs.get("account_type", "STANDARD_STP")),
        server=server,
        login=int(login) if login is not None else None,
        export_run_id=run_id,
        meta_source=meta_source,
        meta_raw=meta_raw,
        hard_errors=hard,
        quality_flags=flags,
        frozen_at_utc=datetime.now(UTC).isoformat(),
    )
    return m, develop if not hard else None


def common_window(develops: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Fail-closed joint calendar relationships.

    Expected (observed on Vantage STP H1):
      - EURUSD and GBPUSD develop calendars are identical
      - XAUUSD timestamps are a subset of the FX calendar
      - intersection size == XAU develop bar count
    """
    if len(develops) < 3:
        return {"status": "FAIL", "reason": "fewer than 3 develop series"}
    for s in SYMBOLS:
        if s not in develops or develops[s].empty:
            return {"status": "FAIL", "reason": f"missing develop series {s}"}

    sets = {s: set(develops[s]["time"].tolist()) for s in SYMBOLS}
    counts = {s: len(sets[s]) for s in SYMBOLS}
    starts = {s: develops[s]["time"].min() for s in SYMBOLS}
    ends = {s: develops[s]["time"].max() for s in SYMBOLS}

    eurusd, gbpusd, xau = sets["EURUSD"], sets["GBPUSD"], sets["XAUUSD"]
    fx_equal = eurusd == gbpusd
    xau_subset = xau.issubset(eurusd)
    inter = eurusd & gbpusd & xau
    n_inter = len(inter)
    inter_eq_xau = n_inter == counts["XAUUSD"]

    hard: list[str] = []
    if not fx_equal:
        hard.append("EURUSD_GBPUSD_CALENDARS_DIFFER")
        hard.append(
            f"only_eur={len(eurusd - gbpusd)} only_gbp={len(gbpusd - eurusd)}"
        )
    if not xau_subset:
        hard.append("XAU_NOT_SUBSET_OF_FX")
        hard.append(f"xau_only={len(xau - eurusd)}")
    if not inter_eq_xau:
        hard.append(f"INTERSECTION_NE_XAU:{n_inter}!={counts['XAUUSD']}")
    if n_inter < MIN_DEVELOP_BARS:
        hard.append(f"INTERSECTION_TOO_SMALL:{n_inter}")

    common_start = max(starts.values())
    common_end = min(ends.values())
    status = "FAIL" if hard else "OK"
    return {
        "status": status,
        "clock_contract": CLOCK_CONTRACT,
        "common_start_server": str(common_start),
        "common_end_server": str(common_end),
        "holdout_start_server": str(DEVELOP_END_SERVER),
        "n_bars_per_symbol": counts,
        "n_intersection_timestamps": n_inter,
        "fx_calendars_identical": fx_equal,
        "xau_subset_of_fx": xau_subset,
        "intersection_equals_xau_count": inter_eq_xau,
        "hard_errors": hard,
        "bar_count_note": (
            "FX vs XAU bar counts differ by session; joint pool is timestamp intersection "
            "(must equal XAU count when XAU ⊂ FX)."
        ),
        "per_symbol_develop_start_server": {k: str(v) for k, v in starts.items()},
        "per_symbol_develop_end_server": {k: str(v) for k, v in ends.items()},
    }


def verify_export_run(
    export_run: dict[str, Any] | None, costs: dict[str, Any]
) -> list[str]:
    errs: list[str] = []
    if not export_run:
        errs.append("MISSING_EXPORT_RUN_JSON")
        return errs
    for k in ("run_id", "login", "server", "files", "export_finished_utc"):
        if k not in export_run:
            errs.append(f"EXPORT_RUN_MISSING_FIELD:{k}")
    cost_login = costs.get("login")
    cost_server = costs.get("server")
    if cost_login is not None and export_run.get("login") is not None:
        if int(export_run["login"]) != int(cost_login):
            errs.append(
                f"LOGIN_MISMATCH:export={export_run.get('login')} costs={cost_login}"
            )
    if cost_server and export_run.get("server") and str(export_run["server"]) != str(cost_server):
        errs.append(
            f"SERVER_MISMATCH:export={export_run.get('server')!r} costs={cost_server!r}"
        )
    for s in SYMBOLS:
        if f"history_{s}" not in (export_run.get("files") or {}):
            errs.append(f"EXPORT_RUN_MISSING_FILE_ENTRY:history_{s}")
        if f"meta_{s}" not in (export_run.get("files") or {}):
            errs.append(f"EXPORT_RUN_MISSING_FILE_ENTRY:meta_{s}")
    return errs


def write_report(
    manifests: list[SymbolManifest],
    common: dict[str, Any],
    gate: str,
    export_errs: list[str],
) -> None:
    lines = [
        "# Multi-instrument data readiness (Phase 0 — fail-closed)",
        "",
        f"**Report generated (UTC wall clock):** {datetime.now(UTC).isoformat()}",
        f"**Gate:** `{gate}`",
        f"**Bar clock contract:** `{CLOCK_CONTRACT}` (not UTC; MT5 server stamps, offset-free)",
        f"**Develop rule:** server_time `< {DEVELOP_END_SERVER}`",
        f"**Account:** verified via export_run.json vs `results/xau_research_costs.json`",
        "",
        "## Per-symbol",
        "",
        "| Symbol | Status | H1 | Develop | Server range | Eff. spread med | Point | Contract | Hard errors | Flags |",
        "|--------|--------|----|---------|--------------|-----------------|-------|----------|-------------|-------|",
    ]
    for m in manifests:
        lines.append(
            f"| {m.symbol} | {m.status} | {m.n_rows_h1} | {m.n_rows_h1_develop} | "
            f"{(m.time_min_server or '—')[:10]} → {(m.time_max_server or '—')[:10]} | "
            f"{m.spread.get('median_effective_pts', '—')} | {m.point_size} | {m.contract_size} | "
            f"{';'.join(m.hard_errors) if m.hard_errors else '—'} | "
            f"{';'.join(m.quality_flags) if m.quality_flags else '—'} |"
        )
    lines += [
        "",
        "## Costs",
        "",
        "- **Commission:** 0.0 (Standard STP)",
        "- **Spread:** `spread_raw_pts` + `spread_effective_pts` + `spread_imputed` (auditable)",
        "- **Slippage:** **UNMEASURED** (0.0 placeholder)",
        "",
        "## Export provenance errors",
        "",
        f"`{export_errs or []}`",
        "",
        "## Common develop window",
        "",
        "```json",
        json.dumps(common, indent=2),
        "```",
        "",
        "## Gate labels",
        "",
        "- `PASS_DATA_READY_WITH_IMPUTATION` — hard DQ OK; some zero-spreads imputed (auditable)",
        "- `PASS_DATA_READY` — hard DQ OK; no imputation",
        "- `FAIL_DATA` — hard error; repair export/provenance/DQ only",
        "",
        "## Explicitly not done",
        "",
        "- No signals, PF, grids, thesis freeze, holdout selection, paper, or live.",
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
    holdout = DEVELOP_END_SERVER
    if HOLDOUT_LOCK.is_file():
        # Use date component only as server-clock boundary (no tz conversion).
        hs = json.loads(HOLDOUT_LOCK.read_text()).get("holdout_start")
        if hs:
            holdout = pd.Timestamp(str(hs)[:19])

    export_run = _load_export_run(bridge)
    export_errs = verify_export_run(export_run, costs)
    print("export_run:", (export_run or {}).get("run_id"), "errs=", export_errs)

    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    manifests: list[SymbolManifest] = []
    develops: dict[str, pd.DataFrame] = {}
    for sym in SYMBOLS:
        m, dev = build_symbol(
            sym,
            bridge_dir=bridge,
            costs=costs,
            export_run=export_run,
            holdout_start=holdout,
        )
        manifests.append(m)
        path = MANIFEST_DIR / f"{sym.lower()}_h1_manifest.json"
        path.write_text(json.dumps(asdict(m), indent=2) + "\n")
        print(
            f"{sym}: status={m.status} h1={m.n_rows_h1} develop={m.n_rows_h1_develop} "
            f"hard={m.hard_errors} flags={m.quality_flags}"
        )
        if dev is not None and len(dev):
            develops[sym] = dev

    common = common_window(develops) if len(develops) == 3 else {
        "status": "FAIL",
        "reason": "not all symbols produced develop series",
        "hard_errors": ["INCOMPLETE_DEVELOP_SET"],
    }
    (MANIFEST_DIR / "common_develop_window.json").write_text(
        json.dumps(common, indent=2) + "\n"
    )

    any_hard = bool(export_errs) or any(m.status == "FAIL" for m in manifests)
    if common.get("status") == "FAIL":
        any_hard = True
    any_impute = any(
        (m.spread or {}).get("n_imputed_full", 0) for m in manifests if m.status != "FAIL"
    )

    if any_hard:
        gate = "FAIL_DATA"
    elif any_impute:
        gate = "PASS_DATA_READY_WITH_IMPUTATION"
    else:
        gate = "PASS_DATA_READY"

    write_report(manifests, common, gate, export_errs)
    print(f"Gate: {gate}")
    print(f"Report: {REPORT_PATH}")
    return 0 if gate.startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
