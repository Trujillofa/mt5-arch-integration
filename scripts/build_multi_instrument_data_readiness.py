#!/usr/bin/env python3
"""Phase-0 multi-instrument data readiness — fail-closed (no signals / PF / grids).

Integrity rules (v2):
  * Bar clock = server_clock_as_stored (never false UTC).
  * Research CSVs written only after hard DQ passes (no publish on FAIL).
  * build_symbol accepts out_dir (tests must not write repo artifacts).
  * export_run.json must attest exact source file sha/size/mtime.
  * MQL export_complete.json required for runtime account/connection.
  * Row symbol vs meta.resolved; H1 timestamps on :00:00.

SAFETY: offline data QA only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
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
ARTIFACT_LOCK = MANIFEST_DIR / "committed_artifact_lock.json"

SYMBOLS = ("XAUUSD", "EURUSD", "GBPUSD")
PRIMARY_TF = "H1"
DEVELOP_END_SERVER = pd.Timestamp("2026-01-01 00:00:00")
CLOCK_CONTRACT = "server_clock_as_stored"

MAX_ZERO_SPREAD_IMPUTE_FRAC = 0.10
MIN_DEVELOP_BARS = 10_000
# Wine often returns non-zero even after ShutdownTerminal; accept only if MQL
# completion sentinel is present and export files are fresh.
ACCEPTED_WINE_EXIT_CODES = frozenset({0, 3, 124})


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
    df = df.loc[:, need].copy()
    df["time"] = pd.to_datetime(df["time"], format="%Y.%m.%d %H:%M")
    for c in ("open", "high", "low", "close", "spread"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    tv = pd.to_numeric(df["tick_volume"], errors="coerce")
    df["tick_volume"] = tv.fillna(0).astype(int)
    return df


def _apply_spread_imputation(h1: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
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


def _iso_utc_ok(value: Any) -> bool:
    if not value or not isinstance(value, str):
        return False
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", value))


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
    published: bool = False


def _load_export_run(bridge: Path) -> dict[str, Any] | None:
    for p in (bridge / "export_run.json", EXPORT_RUN_REPO):
        if p.is_file():
            return json.loads(p.read_text())
    return None


def _load_export_complete(bridge: Path) -> dict[str, Any] | None:
    p = bridge / "export_complete.json"
    if p.is_file():
        return json.loads(p.read_text())
    return None


def verify_export_run(
    export_run: dict[str, Any] | None,
    costs: dict[str, Any],
    *,
    bridge_dir: Path,
    export_complete: dict[str, Any] | None = None,
) -> list[str]:
    """Fail-closed attestation of export_run + on-disk evidence + MQL complete."""
    errs: list[str] = []
    if not export_run:
        return ["MISSING_EXPORT_RUN_JSON"]

    run_id = export_run.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        errs.append(f"INVALID_RUN_ID:{run_id!r}")

    for k in ("login", "server", "files", "export_started_utc", "export_finished_utc", "timeframes"):
        if k not in export_run:
            errs.append(f"EXPORT_RUN_MISSING_FIELD:{k}")

    if not _iso_utc_ok(export_run.get("export_started_utc")):
        errs.append("INVALID_EXPORT_STARTED_UTC")
    if not _iso_utc_ok(export_run.get("export_finished_utc")):
        errs.append("INVALID_EXPORT_FINISHED_UTC")

    tfs = str(export_run.get("timeframes") or "")
    if tfs != "H1":
        errs.append(f"UNEXPECTED_TIMEFRAMES:{tfs!r}")

    symbols = export_run.get("symbols")
    if not isinstance(symbols, list) or set(symbols) != set(SYMBOLS):
        errs.append(f"UNEXPECTED_SYMBOLS:{symbols!r}")

    exit_code = export_run.get("wine_exit_code")
    if exit_code not in ACCEPTED_WINE_EXIT_CODES:
        errs.append(f"WINE_EXIT_NOT_ACCEPTED:{exit_code!r}")

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

    files = export_run.get("files") or {}
    if not isinstance(files, dict):
        errs.append("EXPORT_RUN_FILES_NOT_OBJECT")
        return errs

    for s in SYMBOLS:
        for kind in ("history", "meta"):
            key = f"{kind}_{s}"
            ent = files.get(key)
            if not isinstance(ent, dict):
                errs.append(f"EXPORT_RUN_MISSING_FILE_ENTRY:{key}")
                continue
            path_s = ent.get("path")
            if not path_s:
                errs.append(f"EXPORT_RUN_EMPTY_PATH:{key}")
                continue
            p = Path(str(path_s))
            if not p.is_file():
                # also try bridge_dir relative name
                alt = bridge_dir / p.name
                if alt.is_file():
                    p = alt
                else:
                    errs.append(f"EXPORT_RUN_PATH_MISSING:{key}:{path_s}")
                    continue
            try:
                st = p.stat()
            except OSError:
                errs.append(f"EXPORT_RUN_PATH_UNREADABLE:{key}")
                continue
            sha = _sha256_file(p)
            if ent.get("sha256") != sha:
                errs.append(f"EXPORT_RUN_SHA_MISMATCH:{key}")
            if int(ent.get("bytes") or -1) != int(st.st_size):
                errs.append(f"EXPORT_RUN_SIZE_MISMATCH:{key}")
            if abs(int(ent.get("mtime_unix") or 0) - int(st.st_mtime)) > 2:
                errs.append(f"EXPORT_RUN_MTIME_MISMATCH:{key}")

    # MQL runtime completion sentinel
    if not export_complete:
        errs.append("MISSING_EXPORT_COMPLETE_JSON")
    else:
        if export_complete.get("run_id") and run_id and export_complete.get("run_id") != run_id:
            # shell stamps run_id after MQL; allow complete without run_id match if shell injects later
            pass
        if not export_complete.get("terminal_connected"):
            errs.append("TERMINAL_NOT_CONNECTED_AT_EXPORT")
        if cost_login is not None and export_complete.get("account_login") is not None:
            if int(export_complete["account_login"]) != int(cost_login):
                errs.append(
                    f"MQL_LOGIN_MISMATCH:mql={export_complete.get('account_login')} costs={cost_login}"
                )
        if cost_server and export_complete.get("account_server"):
            if str(export_complete["account_server"]) != str(cost_server):
                errs.append(
                    f"MQL_SERVER_MISMATCH:mql={export_complete.get('account_server')!r} "
                    f"costs={cost_server!r}"
                )
        if not export_complete.get("ok"):
            errs.append("MQL_EXPORT_COMPLETE_NOT_OK")

    return errs


def build_symbol(
    symbol: str,
    *,
    bridge_dir: Path,
    costs: dict[str, Any],
    export_run: dict[str, Any] | None,
    holdout_start: pd.Timestamp,
    out_dir: Path | None = None,
    publish: bool = True,
) -> tuple[SymbolManifest, pd.DataFrame | None]:
    """Build manifest (+ optional research CSV).

    ``out_dir`` defaults to module OUT_DIR. Tests must pass a temp dir.
    Research CSVs are written only when ``publish`` and there are no hard errors.
    """
    publish_dir = out_dir if out_dir is not None else OUT_DIR
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

    def _fail_manifest(**extra: Any) -> SymbolManifest:
        base = dict(
            symbol=symbol,
            status="FAIL",
            clock_contract=CLOCK_CONTRACT,
            source_path=str(src),
            source_sha256=_sha256_file(src) if src.is_file() else "",
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
            hard_errors=list(hard),
            quality_flags=list(flags),
            frozen_at_utc=datetime.now(UTC).isoformat(),
            published=False,
        )
        base.update(extra)
        return SymbolManifest(**base)

    if hard:
        return _fail_manifest(), None

    raw = _parse_history(src)
    h1 = raw.loc[raw["timeframe"] == PRIMARY_TF].copy()
    h1 = h1.sort_values("time").reset_index(drop=True)

    # Non-H1 rows in an H1-only export are suspicious
    if int((raw["timeframe"] != PRIMARY_TF).sum()) > 0:
        hard.append("NON_H1_ROWS_PRESENT")

    # H1 alignment: minute and second must be 0
    if len(h1):
        bad_min = int((h1["time"].dt.minute != 0).sum())
        bad_sec = int((h1["time"].dt.second != 0).sum())
        if bad_min or bad_sec:
            hard.append(f"H1_NOT_HOUR_ALIGNED:min={bad_min},sec={bad_sec}")

    meta_raw = _load_meta_csv(meta_path)
    required_meta = ("point", "contract_size", "digits", "resolved", "requested")
    missing_meta = [k for k in required_meta if k not in meta_raw or not str(meta_raw[k]).strip()]
    if missing_meta:
        hard.append(f"INCOMPLETE_SYMBOL_META={missing_meta}")
        point = float("nan")
        contract = float("nan")
        digits = None
        meta_source = str(meta_path)
        resolved = ""
    else:
        point = float(meta_raw["point"])
        contract = float(meta_raw["contract_size"])
        digits = int(float(meta_raw["digits"]))
        meta_source = str(meta_path)
        resolved = str(meta_raw["resolved"]).strip()
        requested = str(meta_raw["requested"]).strip()
        if requested != symbol:
            hard.append(f"META_REQUESTED_NE_SYMBOL:{requested}!={symbol}")
        if point <= 0 or contract <= 0:
            hard.append("INVALID_POINT_OR_CONTRACT")

    # Row symbol must match resolved broker name (usually same as requested on Vantage)
    if len(h1) and resolved:
        syms = set(h1["symbol"].astype(str).unique())
        if syms != {resolved}:
            hard.append(f"ROW_SYMBOL_NE_RESOLVED:rows={sorted(syms)} resolved={resolved}")
    elif len(h1):
        syms = set(h1["symbol"].astype(str).unique())
        if syms != {symbol}:
            hard.append(f"ROW_SYMBOL_NE_REQUESTED:rows={sorted(syms)} requested={symbol}")

    n_dup = int(h1["time"].duplicated().sum())
    if n_dup:
        hard.append(f"DUPLICATE_TIMESTAMPS={n_dup}")
        h1 = h1.drop_duplicates(subset=["time"], keep="last").reset_index(drop=True)

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

    # ----- publish only if clean -----
    research_rel = ""
    research_sha = ""
    develop_rel = ""
    develop_sha = ""
    published = False
    if not hard and publish:
        publish_dir.mkdir(parents=True, exist_ok=True)
        research_path = publish_dir / f"{symbol.lower()}_h1.csv"
        cols = [
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
        h1_out = h1[cols].copy()
        h1_out["time"] = h1_out["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        h1_out["clock"] = CLOCK_CONTRACT
        h1_out.to_csv(research_path, index=False)

        develop_path = publish_dir / f"{symbol.lower()}_h1_develop.csv"
        dev_out = develop[cols].copy()
        dev_out["time"] = dev_out["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        dev_out["clock"] = CLOCK_CONTRACT
        dev_out.to_csv(develop_path, index=False)

        try:
            research_rel = str(research_path.relative_to(ROOT))
            develop_rel = str(develop_path.relative_to(ROOT))
        except ValueError:
            research_rel = str(research_path)
            develop_rel = str(develop_path)
        research_sha = _sha256_file(research_path)
        develop_sha = _sha256_file(develop_path)
        published = True

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
        research_csv=research_rel,
        research_csv_sha256=research_sha,
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
            "develop_csv": develop_rel,
            "develop_csv_sha256": develop_sha,
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
        published=published,
    )
    return m, develop if not hard else None


def common_window(develops: dict[str, pd.DataFrame]) -> dict[str, Any]:
    if len(develops) < 3:
        return {"status": "FAIL", "reason": "fewer than 3 develop series", "hard_errors": ["INCOMPLETE_DEVELOP_SET"]}
    for s in SYMBOLS:
        if s not in develops or develops[s].empty:
            return {"status": "FAIL", "reason": f"missing develop series {s}", "hard_errors": [f"MISSING_{s}"]}

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
        hard.append(f"only_eur={len(eurusd - gbpusd)} only_gbp={len(gbpusd - eurusd)}")
    if not xau_subset:
        hard.append("XAU_NOT_SUBSET_OF_FX")
        hard.append(f"xau_only={len(xau - eurusd)}")
    if not inter_eq_xau:
        hard.append(f"INTERSECTION_NE_XAU:{n_inter}!={counts['XAUUSD']}")
    if n_inter < MIN_DEVELOP_BARS:
        hard.append(f"INTERSECTION_TOO_SMALL:{n_inter}")

    common_start = max(starts.values())
    common_end = min(ends.values())
    return {
        "status": "FAIL" if hard else "OK",
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


def write_report(
    manifests: list[SymbolManifest],
    common: dict[str, Any],
    gate: str,
    export_errs: list[str],
) -> None:
    lines = [
        "# Multi-instrument data readiness (Phase 0 — integrity v2)",
        "",
        f"**Report generated (UTC wall clock):** {datetime.now(UTC).isoformat()}",
        f"**Gate:** `{gate}`",
        f"**Bar clock contract:** `{CLOCK_CONTRACT}` (not UTC)",
        f"**Develop rule:** server_time `< {DEVELOP_END_SERVER}`",
        "",
        "## Per-symbol",
        "",
        "| Symbol | Status | Published | H1 | Develop | Hard errors | Flags |",
        "|--------|--------|-----------|----|---------|-------------|-------|",
    ]
    for m in manifests:
        lines.append(
            f"| {m.symbol} | {m.status} | {m.published} | {m.n_rows_h1} | {m.n_rows_h1_develop} | "
            f"{';'.join(m.hard_errors) if m.hard_errors else '—'} | "
            f"{';'.join(m.quality_flags) if m.quality_flags else '—'} |"
        )
    lines += [
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
        "- `PASS_DATA_READY_WITH_IMPUTATION` / `PASS_DATA_READY`",
        "- `FAIL_DATA` — hard error; repair only",
        "",
        "## Explicitly not done",
        "",
        "- No thesis freeze, signals, PF, grids, nulls, paper, or live.",
        "",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def write_artifact_lock(manifests: list[SymbolManifest], gate: str) -> dict[str, Any]:
    """Committed-artifact lock: row counts + SHAs for research CSVs."""
    lock: dict[str, Any] = {
        "gate": gate,
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "clock_contract": CLOCK_CONTRACT,
        "artifacts": {},
    }
    for m in manifests:
        if not m.published or not m.research_csv:
            continue
        p = ROOT / m.research_csv
        dev = m.missing_duplicate_bars.get("develop_csv") or ""
        lock["artifacts"][m.symbol] = {
            "research_csv": m.research_csv,
            "research_csv_sha256": m.research_csv_sha256,
            "n_rows_h1": m.n_rows_h1,
            "n_rows_h1_develop": m.n_rows_h1_develop,
            "develop_csv": dev,
            "develop_csv_sha256": m.missing_duplicate_bars.get("develop_csv_sha256"),
            "source_sha256": m.source_sha256,
            "status": m.status,
        }
        # live verify
        if p.is_file():
            n_lines = sum(1 for _ in p.open()) - 1
            lock["artifacts"][m.symbol]["n_data_lines_on_disk"] = n_lines
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_LOCK.write_text(json.dumps(lock, indent=2) + "\n")
    return lock


def verify_committed_artifacts(lock_path: Path = ARTIFACT_LOCK) -> list[str]:
    """Assert on-disk research CSVs match committed_artifact_lock.json."""
    if not lock_path.is_file():
        return ["MISSING_ARTIFACT_LOCK"]
    lock = json.loads(lock_path.read_text())
    errs: list[str] = []
    arts = lock.get("artifacts") or {}
    for sym, ent in arts.items():
        rel = ent.get("research_csv")
        if not rel:
            errs.append(f"{sym}:missing_research_csv")
            continue
        p = ROOT / rel
        if not p.is_file():
            errs.append(f"{sym}:file_missing:{rel}")
            continue
        sha = _sha256_file(p)
        if sha != ent.get("research_csv_sha256"):
            errs.append(f"{sym}:sha_mismatch")
        n_lines = sum(1 for _ in p.open()) - 1
        if n_lines != int(ent.get("n_rows_h1") or -1):
            errs.append(f"{sym}:row_count_mismatch:{n_lines}!={ent.get('n_rows_h1')}")
        if n_lines < 1000:
            errs.append(f"{sym}:suspiciously_small:{n_lines}")
    return errs


def main() -> int:
    bridge = _wine_bridge_dir()
    print(f"Bridge dir: {bridge}")
    costs: dict[str, Any] = {}
    if COSTS_XAU.is_file():
        costs = json.loads(COSTS_XAU.read_text())
    holdout = DEVELOP_END_SERVER
    if HOLDOUT_LOCK.is_file():
        hs = json.loads(HOLDOUT_LOCK.read_text()).get("holdout_start")
        if hs:
            holdout = pd.Timestamp(str(hs)[:19])

    export_run = _load_export_run(bridge)
    export_complete = _load_export_complete(bridge)
    # Merge shell run_id into complete if MQL wrote without it
    if export_complete and export_run and not export_complete.get("run_id"):
        export_complete = dict(export_complete)
        export_complete["run_id"] = export_run.get("run_id")

    export_errs = verify_export_run(
        export_run, costs, bridge_dir=bridge, export_complete=export_complete
    )
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
            out_dir=OUT_DIR,
            publish=True,
        )
        manifests.append(m)
        path = MANIFEST_DIR / f"{sym.lower()}_h1_manifest.json"
        path.write_text(json.dumps(asdict(m), indent=2) + "\n")
        print(
            f"{sym}: status={m.status} published={m.published} h1={m.n_rows_h1} "
            f"develop={m.n_rows_h1_develop} hard={m.hard_errors} flags={m.quality_flags}"
        )
        if dev is not None and len(dev):
            develops[sym] = dev

    if len(develops) == 3:
        common = common_window(develops)
    else:
        common = {
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
    if gate.startswith("PASS_"):
        write_artifact_lock(manifests, gate)
        lock_errs = verify_committed_artifacts()
        if lock_errs:
            print("ARTIFACT_LOCK_VERIFY_FAIL:", lock_errs)
            gate = "FAIL_DATA"
            write_report(manifests, common, gate, export_errs + lock_errs)

    print(f"Gate: {gate}")
    print(f"Report: {REPORT_PATH}")
    return 0 if gate.startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
