#!/usr/bin/env python3
"""Phase-0 multi-instrument data readiness — fail-closed (no signals / PF / grids).

Integrity rules (v6):
  * Bar clock = server_clock_as_stored (never false UTC).
  * Attest and consume the same canonical bridge_dir paths only.
  * Challenge/echo exact JSON compare (run_id, symbols, H1, holdout, account).
  * Content-addressed immutable packages; never overwrite a different package.
  * Live roots are static links through instrument_data_packages/CURRENT/...;
    only CURRENT is atomically replaced (one consumer boundary).
  * Validate staged package (lock/SHAs/counts/id) before CURRENT switch;
    post-switch verify failure rolls CURRENT back.
  * CURRENT id must be content-ID format and a direct child of PACKAGE_ROOT.
  * Package digest is read-only (never unlinks lock); lock excluded by path set.
  * Lock must declare exact SYMBOLS, PASS gate, publish_model, paths, run-id prefix.
  * Consumers pin one package via load_package_snapshot() before multi-symbol IO.
  * Publish failures write evidence beside live set (never clobber package report).
  * Research CSVs written only after hard DQ passes (no publish on FAIL).
  * build_symbol accepts out_dir (tests must not write repo artifacts).

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
PACKAGE_ROOT = ROOT / "results" / "instrument_data_packages"
CURRENT_POINTER = PACKAGE_ROOT / "CURRENT"
FAIL_REPORT_PATH = ROOT / "results" / "multi_instrument_data_readiness.FAIL.md"
PUBLISH_MODEL = "current_indirection_v6"

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


def _parse_challenge_echo(raw: Any) -> dict[str, Any] | None:
    """challenge_echo may be a JSON object or a JSON-encoded string."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _load_export_challenge(bridge_dir: Path) -> dict[str, Any] | None:
    for p in (bridge_dir / "export_challenge.json", MANIFEST_DIR / "export_challenge.json"):
        if p.is_file():
            try:
                data = json.loads(p.read_text())
            except json.JSONDecodeError:
                return None
            return data if isinstance(data, dict) else None
    return None


def _verify_challenge_echo(
    bridge_dir: Path,
    export_run: dict[str, Any],
    export_complete: dict[str, Any],
) -> list[str]:
    """Exact compare of export_challenge vs challenge_echo (+ export_run binding).

    Presence-only is not enough: echo must parse and match run_id, symbols,
    timeframes, holdout_start_server, and expected account fields.
    """
    errs: list[str] = []
    challenge = _load_export_challenge(bridge_dir)
    if not challenge:
        errs.append("MISSING_EXPORT_CHALLENGE_JSON")
        return errs

    echo = _parse_challenge_echo(export_complete.get("challenge_echo"))
    if echo is None:
        errs.append("CHALLENGE_ECHO_UNPARSEABLE")
        return errs

    # Required challenge fields
    required = (
        "run_id",
        "symbols",
        "timeframes",
        "holdout_start_server",
        "expect_login",
        "expect_server",
    )
    for k in required:
        if k not in challenge:
            errs.append(f"CHALLENGE_MISSING_FIELD:{k}")
        if k not in echo:
            errs.append(f"CHALLENGE_ECHO_MISSING_FIELD:{k}")

    def _norm_symbols(v: Any) -> list[str] | None:
        if not isinstance(v, list):
            return None
        return [str(x) for x in v]

    # Field-by-field exact compare
    if challenge.get("run_id") != echo.get("run_id"):
        errs.append(
            f"CHALLENGE_ECHO_RUN_ID_MISMATCH:challenge={challenge.get('run_id')!r} "
            f"echo={echo.get('run_id')!r}"
        )
    ch_syms = _norm_symbols(challenge.get("symbols"))
    echo_syms = _norm_symbols(echo.get("symbols"))
    if ch_syms is None or echo_syms is None or ch_syms != echo_syms:
        errs.append(
            f"CHALLENGE_ECHO_SYMBOLS_MISMATCH:challenge={challenge.get('symbols')!r} "
            f"echo={echo.get('symbols')!r}"
        )
    if str(challenge.get("timeframes") or "") != str(echo.get("timeframes") or ""):
        errs.append(
            f"CHALLENGE_ECHO_TIMEFRAMES_MISMATCH:challenge={challenge.get('timeframes')!r} "
            f"echo={echo.get('timeframes')!r}"
        )
    if str(challenge.get("holdout_start_server") or "") != str(
        echo.get("holdout_start_server") or ""
    ):
        errs.append(
            "CHALLENGE_ECHO_HOLDOUT_MISMATCH:"
            f"challenge={challenge.get('holdout_start_server')!r} "
            f"echo={echo.get('holdout_start_server')!r}"
        )
    try:
        ch_login = int(challenge["expect_login"]) if challenge.get("expect_login") is not None else None
        echo_login = int(echo["expect_login"]) if echo.get("expect_login") is not None else None
    except (TypeError, ValueError, KeyError):
        ch_login = echo_login = None
        errs.append("CHALLENGE_ECHO_LOGIN_UNPARSEABLE")
    if ch_login != echo_login:
        errs.append(
            f"CHALLENGE_ECHO_LOGIN_MISMATCH:challenge={challenge.get('expect_login')!r} "
            f"echo={echo.get('expect_login')!r}"
        )
    if str(challenge.get("expect_server") or "") != str(echo.get("expect_server") or ""):
        errs.append(
            f"CHALLENGE_ECHO_SERVER_MISMATCH:challenge={challenge.get('expect_server')!r} "
            f"echo={echo.get('expect_server')!r}"
        )

    # Cross-bind to export_run
    run_id = export_run.get("run_id")
    if challenge.get("run_id") != run_id:
        errs.append(
            f"CHALLENGE_RUN_ID_NE_EXPORT_RUN:challenge={challenge.get('run_id')!r} "
            f"export_run={run_id!r}"
        )
    if echo.get("run_id") != run_id:
        errs.append(
            f"CHALLENGE_ECHO_RUN_ID_NE_EXPORT_RUN:echo={echo.get('run_id')!r} "
            f"export_run={run_id!r}"
        )
    if ch_syms is not None and set(ch_syms) != set(SYMBOLS):
        errs.append(f"CHALLENGE_UNEXPECTED_SYMBOLS:{ch_syms!r}")
    if str(challenge.get("timeframes") or "") != "H1":
        errs.append(f"CHALLENGE_UNEXPECTED_TIMEFRAMES:{challenge.get('timeframes')!r}")
    if str(challenge.get("holdout_start_server") or "")[:10] != "2026-01-01":
        errs.append(
            f"CHALLENGE_HOLDOUT_UNEXPECTED:{challenge.get('holdout_start_server')!r}"
        )
    # Expected account must match export_run / costs binding surface
    if (
        export_run.get("login") is not None
        and ch_login is not None
        and int(export_run["login"]) != ch_login
    ):
        errs.append(
            f"CHALLENGE_LOGIN_NE_EXPORT_RUN:challenge={ch_login} "
            f"export_run={export_run.get('login')}"
        )
    if (
        export_run.get("server")
        and challenge.get("expect_server")
        and str(export_run["server"]) != str(challenge["expect_server"])
    ):
        errs.append(
            f"CHALLENGE_SERVER_NE_EXPORT_RUN:challenge={challenge.get('expect_server')!r} "
            f"export_run={export_run.get('server')!r}"
        )
    return errs


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

    # Wine exit codes are non-authoritative under portable ShutdownTerminal.
    # We still record them; hard-fail only when exit is non-int / missing AND
    # there is no valid MQL completion (checked below). Soft-flag weird codes.
    exit_code = export_run.get("wine_exit_code")
    wine_exit_flag: str | None = None
    if not isinstance(exit_code, int):
        wine_exit_flag = f"WINE_EXIT_NOT_INT:{exit_code!r}"
    elif exit_code not in ACCEPTED_WINE_EXIT_CODES:
        wine_exit_flag = f"WINE_EXIT_UNUSUAL:{exit_code}"

    cost_login = costs.get("login")
    cost_server = costs.get("server")
    if (
        cost_login is not None
        and export_run.get("login") is not None
        and int(export_run["login"]) != int(cost_login)
    ):
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

    # Canonical consume paths: ONLY bridge_dir/history_{S}.csv and symbol_meta_{S}.csv.
    # Attestation hashes must match these paths (ignore export_run path strings for IO).
    for s in SYMBOLS:
        for kind, fname in (
            ("history", f"history_{s}.csv"),
            ("meta", f"symbol_meta_{s}.csv"),
        ):
            key = f"{kind}_{s}"
            ent = files.get(key)
            if not isinstance(ent, dict):
                errs.append(f"EXPORT_RUN_MISSING_FILE_ENTRY:{key}")
                continue
            p = bridge_dir / fname
            if not p.is_file():
                errs.append(f"CANONICAL_PATH_MISSING:{key}:{p}")
                continue
            try:
                st = p.stat()
            except OSError:
                errs.append(f"CANONICAL_PATH_UNREADABLE:{key}")
                continue
            sha = _sha256_file(p)
            if ent.get("sha256") != sha:
                errs.append(f"EXPORT_RUN_SHA_MISMATCH:{key}:attested_ne_canonical")
            if int(ent.get("bytes") or -1) != int(st.st_size):
                errs.append(f"EXPORT_RUN_SIZE_MISMATCH:{key}")
            if abs(int(ent.get("mtime_unix") or 0) - int(st.st_mtime)) > 2:
                errs.append(f"EXPORT_RUN_MTIME_MISMATCH:{key}")
            # If export_run.path is present and names a different existing file with
            # different content, that is also a fail (split-brain attestation).
            path_s = ent.get("path")
            if path_s:
                alt = Path(str(path_s))
                if (
                    alt.is_file()
                    and alt.resolve() != p.resolve()
                    and _sha256_file(alt) != sha
                ):
                    errs.append(f"ATTESTED_PATH_DIVERGES:{key}")

    # MQL runtime completion sentinel — strict run binding + required fields
    if not export_complete:
        errs.append("MISSING_EXPORT_COMPLETE_JSON")
        if wine_exit_flag:
            errs.append(wine_exit_flag.replace("UNUSUAL", "NOT_ACCEPTED"))
    else:
        for req in (
            "ok",
            "run_id",
            "terminal_connected",
            "account_login",
            "account_server",
            "symbols",
            "challenge_echo",
        ):
            if req not in export_complete:
                errs.append(f"EXPORT_COMPLETE_MISSING_FIELD:{req}")
        if export_complete.get("run_id") != run_id:
            errs.append(
                f"RUN_ID_MISMATCH:complete={export_complete.get('run_id')!r} "
                f"export_run={run_id!r}"
            )
        # Exact challenge/echo compare (not presence-only)
        ch_errs = _verify_challenge_echo(bridge_dir, export_run, export_complete)
        errs.extend(ch_errs)
        if export_complete.get("terminal_connected") is not True:
            errs.append("TERMINAL_NOT_CONNECTED_AT_EXPORT")
        if cost_login is not None:
            if export_complete.get("account_login") is None:
                errs.append("MQL_LOGIN_MISSING")
            elif int(export_complete["account_login"]) != int(cost_login):
                errs.append(
                    f"MQL_LOGIN_MISMATCH:mql={export_complete.get('account_login')} "
                    f"costs={cost_login}"
                )
        if cost_server:
            if not export_complete.get("account_server"):
                errs.append("MQL_SERVER_MISSING")
            elif str(export_complete["account_server"]) != str(cost_server):
                errs.append(
                    f"MQL_SERVER_MISMATCH:mql={export_complete.get('account_server')!r} "
                    f"costs={cost_server!r}"
                )
        if export_complete.get("ok") is not True:
            errs.append("MQL_EXPORT_COMPLETE_NOT_OK")
        # Per-symbol ok/count vs CSV
        sym_details = export_complete.get("symbols")
        if not isinstance(sym_details, list):
            errs.append("EXPORT_COMPLETE_SYMBOLS_NOT_LIST")
        else:
            by_req = {
                str(d.get("requested")): d
                for d in sym_details
                if isinstance(d, dict)
            }
            for s in SYMBOLS:
                d = by_req.get(s)
                if not d:
                    errs.append(f"EXPORT_COMPLETE_MISSING_SYMBOL:{s}")
                    continue
                if d.get("ok") is not True:
                    errs.append(f"EXPORT_COMPLETE_SYMBOL_NOT_OK:{s}")
                hist = bridge_dir / f"history_{s}.csv"
                if hist.is_file():
                    n_csv = sum(1 for _ in hist.open()) - 1
                    bars = d.get("bars")
                    if bars is not None and int(bars) != n_csv:
                        errs.append(
                            f"EXPORT_COMPLETE_BAR_COUNT_MISMATCH:{s}:{bars}!={n_csv}"
                        )
        # Valid MQL completion ⇒ ignore unusual wine exit codes.
        # Incomplete completion ⇒ surface wine_exit_flag as hard error.
        if wine_exit_flag and any(
            e.startswith(
                (
                    "MQL_",
                    "TERMINAL_",
                    "RUN_ID",
                    "EXPORT_COMPLETE_",
                )
            )
            for e in errs
        ):
            errs.append(wine_exit_flag.replace("UNUSUAL", "NOT_ACCEPTED"))

    return errs


def verify_costs_file(costs: dict[str, Any] | None, path: Path = COSTS_XAU) -> list[str]:
    """Fail-closed research cost provenance."""
    errs: list[str] = []
    if not path.is_file():
        return ["MISSING_COSTS_FILE"]
    if not costs:
        return ["EMPTY_COSTS"]
    for k in (
        "broker",
        "login",
        "server",
        "account_type",
        "commission_per_lot",
        "slippage_points",
        "slippage_notes",
        "cost_label",
    ):
        if k not in costs:
            errs.append(f"COSTS_MISSING_FIELD:{k}")
    acct = str(costs.get("account_type") or "")
    if acct not in ("STANDARD_STP", "Standard STP"):
        errs.append(f"COSTS_ACCOUNT_TYPE:{costs.get('account_type')!r}")
    try:
        if float(costs.get("commission_per_lot")) != 0.0:
            errs.append(f"COSTS_COMMISSION_NE_ZERO:{costs.get('commission_per_lot')}")
    except (TypeError, ValueError):
        errs.append("COSTS_COMMISSION_INVALID")
    notes = str(costs.get("slippage_notes") or "").upper()
    if "UNMEASURED" not in notes:
        errs.append("COSTS_SLIPPAGE_NOT_MARKED_UNMEASURED")
    if costs.get("login") is None or costs.get("server") is None:
        errs.append("COSTS_LOGIN_OR_SERVER_MISSING")
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
        base = {
            "symbol": symbol,
            "status": "FAIL",
            "clock_contract": CLOCK_CONTRACT,
            "source_path": str(src),
            "source_sha256": _sha256_file(src) if src.is_file() else "",
            "research_csv": "",
            "research_csv_sha256": "",
            "timeframe": PRIMARY_TF,
            "n_rows_raw": 0,
            "n_rows_h1": 0,
            "n_rows_h1_develop": 0,
            "time_min_server": "",
            "time_max_server": "",
            "develop_time_min_server": "",
            "develop_time_max_server": "",
            "develop_rule": "server_time < holdout_start_server",
            "holdout_start_server": str(holdout_start),
            "missing_duplicate_bars": {},
            "gap_report": {},
            "spread": {},
            "point_size": float("nan"),
            "contract_size": float("nan"),
            "digits": None,
            "commission_per_lot": 0.0,
            "commission_notes": "Standard STP: commission 0; cost in spread",
            "slippage_points": 0.0,
            "slippage_notes": "UNMEASURED — left at 0; not a claim of zero slip",
            "spread_source": "MqlRates.spread via Wine Vantage export",
            "broker": str(costs.get("broker", "Vantage")),
            "account_type": str(costs.get("account_type", "STANDARD_STP")),
            "server": server,
            "login": int(login) if login is not None else None,
            "export_run_id": run_id,
            "meta_source": "",
            "meta_raw": {},
            "hard_errors": list(hard),
            "quality_flags": list(flags),
            "frozen_at_utc": datetime.now(UTC).isoformat(),
            "published": False,
        }
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
    *,
    path: Path | None = None,
) -> None:
    dest = path if path is not None else REPORT_PATH
    lines = [
        "# Multi-instrument data readiness (Phase 0 — integrity v6.1)",
        "",
        f"**Report generated (UTC wall clock):** {datetime.now(UTC).isoformat()}",
        f"**Gate:** `{gate}`",
        f"**Bar clock contract:** `{CLOCK_CONTRACT}` (not UTC)",
        f"**Develop rule:** server_time `< {DEVELOP_END_SERVER}`",
        "**Publish model:** static live roots via packages/CURRENT (v6.1 strict lock + pin)",
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
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines) + "\n")


def write_artifact_lock(
    manifests: list[SymbolManifest],
    gate: str,
    *,
    out_dir: Path,
    lock_path: Path | None = None,
    path_prefix: str = "results/instrument_data",
) -> dict[str, Any]:
    """Committed-artifact lock: full + develop row counts/SHAs for all symbols.

    Paths recorded under ``path_prefix`` (live consumer paths), while bytes/SHAs
    are taken from ``out_dir`` (package/staging content).
    """
    lock: dict[str, Any] = {
        "gate": gate,
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "clock_contract": CLOCK_CONTRACT,
        "required_symbols": list(SYMBOLS),
        "artifacts": {},
    }
    for m in manifests:
        if not m.published:
            continue
        research_name = f"{m.symbol.lower()}_h1.csv"
        develop_name = f"{m.symbol.lower()}_h1_develop.csv"
        research_path = out_dir / research_name
        develop_path = out_dir / develop_name
        if not research_path.is_file() and m.research_csv:
            research_path = ROOT / m.research_csv if not Path(m.research_csv).is_absolute() else Path(m.research_csv)
        if not develop_path.is_file():
            drel = m.missing_duplicate_bars.get("develop_csv") or ""
            if drel:
                develop_path = ROOT / drel if not Path(drel).is_absolute() else Path(drel)

        research_sha = _sha256_file(research_path) if research_path.is_file() else ""
        develop_sha = _sha256_file(develop_path) if develop_path.is_file() else ""
        n_full = sum(1 for _ in research_path.open()) - 1 if research_path.is_file() else -1
        n_dev = sum(1 for _ in develop_path.open()) - 1 if develop_path.is_file() else -1

        research_rel = f"{path_prefix}/{research_name}"
        develop_rel = f"{path_prefix}/{develop_name}"

        lock["artifacts"][m.symbol] = {
            "research_csv": research_rel,
            "research_csv_sha256": research_sha,
            "n_rows_h1": m.n_rows_h1,
            "n_rows_h1_on_disk": n_full,
            "n_rows_h1_develop": m.n_rows_h1_develop,
            "n_rows_h1_develop_on_disk": n_dev,
            "develop_csv": develop_rel,
            "develop_csv_sha256": develop_sha,
            "source_sha256": m.source_sha256,
            "status": m.status,
            "manifest_n_rows_h1": m.n_rows_h1,
            "manifest_n_rows_h1_develop": m.n_rows_h1_develop,
        }
    dest = lock_path if lock_path is not None else ARTIFACT_LOCK
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(lock, indent=2) + "\n")
    return lock


def verify_committed_artifacts(
    lock_path: Path | None = None,
    *,
    manifests: list[SymbolManifest] | None = None,
) -> list[str]:
    """Assert full + develop CSVs match lock; require exact symbol membership."""
    if lock_path is None:
        lock_path = ARTIFACT_LOCK
    if not lock_path.is_file():
        return ["MISSING_ARTIFACT_LOCK"]
    lock = json.loads(lock_path.read_text())
    errs: list[str] = []
    errs.extend(_validate_lock_schema(lock))
    arts = lock.get("artifacts") or {}
    required = set(SYMBOLS)  # never trust lock to redefine the universe

    man_by_sym = {m.symbol: m for m in (manifests or [])}

    for sym in sorted(required):
        ent = arts.get(sym)
        if not ent:
            errs.append(f"{sym}:missing_from_lock")
            continue
        # Full history
        rel = ent.get("research_csv")
        if not rel:
            errs.append(f"{sym}:missing_research_csv")
        else:
            p = ROOT / rel if not Path(rel).is_absolute() else Path(rel)
            if not p.is_file():
                errs.append(f"{sym}:full_file_missing:{rel}")
            else:
                sha = _sha256_file(p)
                if sha != ent.get("research_csv_sha256"):
                    errs.append(f"{sym}:full_sha_mismatch")
                n_lines = sum(1 for _ in p.open()) - 1
                if n_lines != int(ent.get("n_rows_h1") or -1):
                    errs.append(
                        f"{sym}:full_row_count_mismatch:{n_lines}!={ent.get('n_rows_h1')}"
                    )
                if n_lines < 1000:
                    errs.append(f"{sym}:full_suspiciously_small:{n_lines}")
        # Develop
        drel = ent.get("develop_csv")
        if not drel:
            errs.append(f"{sym}:missing_develop_csv")
        else:
            dp = ROOT / drel if not Path(drel).is_absolute() else Path(drel)
            if not dp.is_file():
                errs.append(f"{sym}:develop_file_missing:{drel}")
            else:
                dsha = _sha256_file(dp)
                if dsha != ent.get("develop_csv_sha256"):
                    errs.append(f"{sym}:develop_sha_mismatch")
                dn = sum(1 for _ in dp.open()) - 1
                if dn != int(ent.get("n_rows_h1_develop") or -1):
                    errs.append(
                        f"{sym}:develop_row_count_mismatch:{dn}!={ent.get('n_rows_h1_develop')}"
                    )
                if dn < 1000:
                    errs.append(f"{sym}:develop_suspiciously_small:{dn}")
        # Manifest consistency
        if man_by_sym:
            m = man_by_sym.get(sym)
            if m is None:
                errs.append(f"{sym}:missing_manifest_object")
            else:
                if int(m.n_rows_h1) != int(ent.get("n_rows_h1") or -1):
                    errs.append(f"{sym}:manifest_full_count_mismatch")
                if int(m.n_rows_h1_develop) != int(ent.get("n_rows_h1_develop") or -1):
                    errs.append(f"{sym}:manifest_develop_count_mismatch")
                if m.research_csv_sha256 and m.research_csv_sha256 != ent.get(
                    "research_csv_sha256"
                ):
                    errs.append(f"{sym}:manifest_full_sha_mismatch")
    return errs


PACKAGE_ID_RE = re.compile(r"^(?:[0-9a-f]{32}|norun)-[0-9a-f]{16}$")


def _required_package_rels() -> list[str]:
    """Files that must exist for a package to be publishable."""
    return (
        [f"instrument_data/{s.lower()}_h1.csv" for s in SYMBOLS]
        + [f"instrument_data/{s.lower()}_h1_develop.csv" for s in SYMBOLS]
        + [f"instrument_data_manifests/{s.lower()}_h1_manifest.json" for s in SYMBOLS]
        + [
            "instrument_data_manifests/common_develop_window.json",
            "instrument_data_manifests/committed_artifact_lock.json",
            "multi_instrument_data_readiness.md",
        ]
    )


def _optional_package_rels() -> list[str]:
    return [
        "instrument_data_manifests/export_run.json",
        "instrument_data_manifests/export_complete.json",
        "instrument_data_manifests/export_challenge.json",
    ]


# Lock is stamped after content-id freeze; never part of content digest.
_DIGEST_EXCLUDE_RELS = frozenset(
    {
        "instrument_data_manifests/committed_artifact_lock.json",
    }
)


def _package_member_relpaths(package_dir: Path) -> list[str]:
    """Stable ordered relative paths of files that constitute package content."""
    rels: list[str] = []
    for rel in _required_package_rels() + _optional_package_rels():
        if (package_dir / rel).is_file():
            rels.append(rel)
    return sorted(rels)


def _package_digest_member_relpaths(package_dir: Path) -> list[str]:
    """Members hashed for content-addressed package ID (excludes lock; read-only)."""
    return [r for r in _package_member_relpaths(package_dir) if r not in _DIGEST_EXCLUDE_RELS]


def _package_content_digest(package_dir: Path) -> str:
    """SHA-256 over sorted (relpath, file_sha) pairs — immutable content identity.

    Read-only: never mutates package files. Lock is excluded so stamp fields
    (package_id, frozen_at) do not require unlink/recompute cycles.
    """
    h = hashlib.sha256()
    members = _package_digest_member_relpaths(package_dir)
    if not members:
        raise FileNotFoundError(f"empty package digest set: {package_dir}")
    for rel in members:
        p = package_dir / rel
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(_sha256_file(p).encode("ascii"))
        h.update(b"\0")
    return h.hexdigest()


def content_package_id(package_dir: Path, run_id: str | None) -> str:
    """Immutable content/build-derived package ID.

    Format: ``{run_id_or_norun}-{content_sha16}``. Same bytes ⇒ same ID; different
    bytes never share an ID, so rebuilds cannot clobber a prior package.
    """
    digest16 = _package_content_digest(package_dir)[:16]
    rid = run_id if run_id and re.fullmatch(r"[0-9a-f]{32}", run_id) else "norun"
    return f"{rid}-{digest16}"


def validate_package_id(package_id: str) -> str:
    """Require content-ID format; reject path separators / escapes."""
    if not isinstance(package_id, str) or not package_id:
        raise ValueError(f"invalid package_id: {package_id!r}")
    if any(sep in package_id for sep in ("/", "\\", "\0")) or ".." in package_id:
        raise ValueError(f"PACKAGE_ID_PATH_ESCAPE:{package_id!r}")
    if not PACKAGE_ID_RE.fullmatch(package_id):
        raise ValueError(f"invalid package_id format: {package_id!r}")
    return package_id


PASS_GATE_PREFIX = "PASS_DATA_READY"
EXPECTED_PATH_PREFIX = "results/instrument_data"


def _validate_lock_schema(lock: dict[str, Any]) -> list[str]:
    """Fail-closed lock fields: exact symbol universe, gate, publish model, paths."""
    errs: list[str] = []
    req = lock.get("required_symbols")
    if not isinstance(req, list) or set(req) != set(SYMBOLS) or len(req) != len(SYMBOLS):
        errs.append(
            f"LOCK_REQUIRED_SYMBOLS:have={req!r} need={list(SYMBOLS)}"
        )
    arts = lock.get("artifacts")
    if not isinstance(arts, dict):
        errs.append("LOCK_ARTIFACTS_NOT_OBJECT")
        arts = {}
    if set(arts.keys()) != set(SYMBOLS):
        errs.append(
            f"LOCK_ARTIFACT_KEYS:have={sorted(arts.keys())} need={sorted(SYMBOLS)}"
        )
    gate = str(lock.get("gate") or "")
    if not gate.startswith(PASS_GATE_PREFIX):
        errs.append(f"LOCK_GATE_NOT_PASS:gate={gate!r}")
    pm = lock.get("publish_model")
    if pm != PUBLISH_MODEL:
        errs.append(f"LOCK_PUBLISH_MODEL:have={pm!r} need={PUBLISH_MODEL!r}")
    run_id = lock.get("export_run_id")
    package_id = lock.get("package_id")
    if package_id is not None:
        try:
            validate_package_id(str(package_id))
        except ValueError as e:
            errs.append(f"LOCK_PACKAGE_ID_INVALID:{e}")
        else:
            if isinstance(run_id, str) and re.fullmatch(r"[0-9a-f]{32}", run_id):
                prefix = str(package_id).split("-", 1)[0]
                if prefix != run_id:
                    errs.append(
                        f"LOCK_RUN_ID_PREFIX_MISMATCH:package_id={package_id!r} "
                        f"export_run_id={run_id!r}"
                    )
            elif run_id is not None and not (
                isinstance(run_id, str) and re.fullmatch(r"[0-9a-f]{32}", run_id)
            ):
                errs.append(f"LOCK_EXPORT_RUN_ID_INVALID:{run_id!r}")
    elif run_id is not None:
        errs.append("LOCK_MISSING_PACKAGE_ID_WITH_RUN_ID")

    for sym in SYMBOLS:
        ent = arts.get(sym)
        if not isinstance(ent, dict):
            continue
        want_full = f"{EXPECTED_PATH_PREFIX}/{sym.lower()}_h1.csv"
        want_dev = f"{EXPECTED_PATH_PREFIX}/{sym.lower()}_h1_develop.csv"
        if ent.get("research_csv") != want_full:
            errs.append(
                f"{sym}:LOCK_PATH_FULL:have={ent.get('research_csv')!r} need={want_full!r}"
            )
        if ent.get("develop_csv") != want_dev:
            errs.append(
                f"{sym}:LOCK_PATH_DEVELOP:have={ent.get('develop_csv')!r} need={want_dev!r}"
            )
    return errs


def seal_package_identity(
    package_dir: Path,
    run_id: str | None,
    *,
    gate: str,
    manifests: list[SymbolManifest],
) -> tuple[str, dict[str, Any]]:
    """Write lock stamped with content id (digest excludes lock; no unlink)."""
    stage_man = package_dir / "instrument_data_manifests"
    stage_data = package_dir / "instrument_data"
    lock_path = stage_man / "committed_artifact_lock.json"
    # Content id is independent of lock bytes — compute first, then write lock once.
    package_id = content_package_id(package_dir, run_id)
    lock = write_artifact_lock(
        manifests,
        gate,
        out_dir=stage_data,
        lock_path=lock_path,
        path_prefix="results/instrument_data",
    )
    lock["package_id"] = package_id
    lock["publish_model"] = PUBLISH_MODEL
    lock["export_run_id"] = run_id
    lock["required_symbols"] = list(SYMBOLS)
    lock_path.write_text(json.dumps(lock, indent=2) + "\n")
    # Stability check is read-only (lock still excluded from digest)
    pid2 = content_package_id(package_dir, run_id)
    if pid2 != package_id:
        raise RuntimeError(f"package_id unstable: {package_id} vs {pid2}")
    return package_id, lock


def _live_package_file_map(package_dir: Path) -> list[tuple[Path, Path]]:
    """Map package members to live consumer paths (via OUT_DIR/MANIFEST_DIR/REPORT)."""
    pairs: list[tuple[Path, Path]] = []
    for rel in _package_member_relpaths(package_dir):
        src = package_dir / rel
        if rel.startswith("instrument_data_manifests/"):
            pairs.append((src, MANIFEST_DIR / Path(rel).name))
        elif rel.startswith("instrument_data/"):
            pairs.append((src, OUT_DIR / Path(rel).name))
        elif rel == "multi_instrument_data_readiness.md":
            pairs.append((src, REPORT_PATH))
    return pairs


def _read_current_package_id() -> str | None:
    """Return validated CURRENT package id, or None if unset.

    Symlink CURRENT -> <package_id> preferred. Plain-text CURRENT accepted only
    if it is a single content-ID token (no path separators).
    """
    if not (CURRENT_POINTER.exists() or CURRENT_POINTER.is_symlink()):
        return None
    raw: str | None = None
    if CURRENT_POINTER.is_symlink():
        target = Path(str(CURRENT_POINTER.readlink()))
        # Only single-component relative names (no path escape)
        if target.is_absolute() or len(target.parts) != 1:
            raise RuntimeError(
                f"CURRENT_SYMLINK_ESCAPE: target={target!s} "
                "(must be single relative package id under PACKAGE_ROOT)"
            )
        raw = target.parts[0]
    elif CURRENT_POINTER.is_file():
        raw = CURRENT_POINTER.read_text().strip()
        if not raw:
            return None
        if any(sep in raw for sep in ("/", "\\", "\0")) or ".." in raw or "\n" in raw:
            raise RuntimeError(f"CURRENT_TEXT_ESCAPE:{raw!r}")
    else:
        return None
    try:
        return validate_package_id(raw)
    except ValueError as e:
        raise RuntimeError(f"CURRENT_INVALID_ID:{e}") from e


def resolve_current_package_dir() -> Path | None:
    """Resolve CURRENT to an existing direct child of PACKAGE_ROOT, or None.

    Raises RuntimeError on dangling/escaped CURRENT (refuse live mutation).
    """
    pid = _read_current_package_id()
    if not pid:
        return None
    pkg_root = PACKAGE_ROOT.resolve()
    pkg = (PACKAGE_ROOT / pid).resolve()
    if pkg.parent != pkg_root:
        raise RuntimeError(
            f"CURRENT_PATH_ESCAPE: pointer={pid!r} resolved={pkg} "
            f"not a direct child of {pkg_root}"
        )
    if not pkg.is_dir():
        raise RuntimeError(
            f"CURRENT_PACKAGE_MISSING: pointer={pid!r} path={pkg} "
            "(abort before live mutation; repair CURRENT or restore package)"
        )
    return pkg


def _write_current_package_id(package_id: str) -> None:
    """Atomically point CURRENT at package_id (relative single-component symlink)."""
    package_id = validate_package_id(package_id)
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    target_dir = PACKAGE_ROOT / package_id
    if not target_dir.is_dir():
        raise FileNotFoundError(f"cannot point CURRENT at missing package {package_id}")
    # Confirm final path is direct child before flip
    if target_dir.resolve().parent != PACKAGE_ROOT.resolve():
        raise RuntimeError(f"CURRENT_PATH_ESCAPE on write: {package_id}")
    tmp = CURRENT_POINTER.with_name(".CURRENT.new")
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    tmp.symlink_to(package_id, target_is_directory=True)
    tmp.replace(CURRENT_POINTER)


def _atomic_symlink_replace(link: Path, target: Path, *, target_is_directory: bool) -> None:
    """Replace ``link`` with a symlink to ``target`` via tmp+rename (atomic)."""
    import shutil

    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        rel = os.path.relpath(target, start=link.parent)
    except ValueError:
        rel = str(target)

    if link.exists() and not link.is_symlink():
        displaced = link.with_name(f".{link.name}.displaced_{os.getpid()}")
        if displaced.exists() or displaced.is_symlink():
            if displaced.is_dir() and not displaced.is_symlink():
                shutil.rmtree(displaced)
            else:
                displaced.unlink()
        link.rename(displaced)

    tmp = link.with_name(f".{link.name}.new")
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    tmp.symlink_to(rel, target_is_directory=target_is_directory)
    tmp.replace(link)


def _static_live_root_specs() -> list[tuple[Path, str, bool]]:
    """(live_path, relative target through CURRENT, is_directory).

    Live roots are static; only CURRENT moves. Relative targets are from
    live_path.parent (results/).
    """
    return [
        (OUT_DIR, "instrument_data_packages/CURRENT/instrument_data", True),
        (
            MANIFEST_DIR,
            "instrument_data_packages/CURRENT/instrument_data_manifests",
            True,
        ),
        (
            REPORT_PATH,
            "instrument_data_packages/CURRENT/multi_instrument_data_readiness.md",
            False,
        ),
    ]


def ensure_static_live_roots_through_current() -> None:
    """Ensure live consumer paths are static symlinks via packages/CURRENT/...

    Idempotent. Does not flip CURRENT. Safe when CURRENT is missing (links are
    dangling until CURRENT is set).
    """
    import shutil

    for live, rel_target, is_dir in _static_live_root_specs():
        desired = Path(rel_target)
        if live.is_symlink():
            try:
                if Path(str(live.readlink())) == desired:
                    continue
            except OSError:
                pass
        live.parent.mkdir(parents=True, exist_ok=True)
        if live.exists() and not live.is_symlink():
            displaced = live.with_name(f".{live.name}.displaced_{os.getpid()}")
            if displaced.exists() or displaced.is_symlink():
                if displaced.is_dir() and not displaced.is_symlink():
                    shutil.rmtree(displaced)
                else:
                    displaced.unlink()
            live.rename(displaced)
        tmp = live.with_name(f".{live.name}.new")
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()
        tmp.symlink_to(rel_target, target_is_directory=is_dir)
        tmp.replace(live)


def install_package_to_live(package_dir: Path) -> None:
    """Publish package_dir by ensuring static live roots + flipping CURRENT only.

    The sole atomic consumer boundary is CURRENT. Live roots always go through
    instrument_data_packages/CURRENT/... so a crash mid-install cannot leave
    data/manifests/report pointing at different packages.
    """
    if not package_dir.is_dir():
        raise FileNotFoundError(f"package missing: {package_dir}")
    package_id = package_dir.name
    validate_package_id(package_id)
    if package_dir.resolve().parent != PACKAGE_ROOT.resolve():
        raise RuntimeError(
            f"package not under PACKAGE_ROOT: {package_dir} parent={package_dir.parent}"
        )
    for rel in _required_package_rels():
        if not (package_dir / rel).is_file():
            raise FileNotFoundError(f"package incomplete: {rel}")

    ensure_static_live_roots_through_current()
    _write_current_package_id(package_id)


def verify_live_matches_package(package_dir: Path) -> list[str]:
    """Assert live paths resolve through CURRENT into package_dir with matching bytes."""
    errs: list[str] = []
    try:
        pkg_res = package_dir.resolve()
    except OSError as e:
        return [f"PACKAGE_UNRESOLVABLE:{e}"]

    # CURRENT must point at this package
    try:
        cur = resolve_current_package_dir()
    except RuntimeError as e:
        return [f"CURRENT_RESOLVE_FAIL:{e}"]
    if cur is None:
        errs.append("CURRENT_UNSET")
    elif cur.resolve() != pkg_res:
        errs.append(f"CURRENT_NOT_PACKAGE:current={cur.name} want={package_dir.name}")

    for live, rel_target, _is_dir in _static_live_root_specs():
        if not live.is_symlink():
            errs.append(f"LIVE_NOT_SYMLINK:{live.name}")
            continue
        try:
            if Path(str(live.readlink())) != Path(rel_target):
                errs.append(
                    f"LIVE_NOT_THROUGH_CURRENT:{live.name}:"
                    f"got={live.readlink()!s} want={rel_target}"
                )
        except OSError as e:
            errs.append(f"LIVE_SYMLINK_BROKEN:{live.name}:{e}")

    for src, dst in _live_package_file_map(package_dir):
        if not src.is_file():
            continue
        if not dst.exists() and not dst.is_symlink():
            errs.append(f"LIVE_MISSING:{dst.name}")
            continue
        try:
            if not dst.is_file():
                errs.append(f"LIVE_NOT_FILE:{dst.name}")
                continue
            if _sha256_file(src) != _sha256_file(dst):
                errs.append(f"LIVE_SHA_MISMATCH:{dst.name}")
            dres = dst.resolve()
            if pkg_res not in dres.parents and dres.parent != pkg_res:
                errs.append(f"LIVE_NOT_UNDER_PACKAGE:{dst.name}")
        except OSError as e:
            errs.append(f"LIVE_READ_FAIL:{dst.name}:{e}")
    return errs


def verify_package_artifacts(
    package_dir: Path,
    *,
    manifests: list[SymbolManifest] | None = None,
    expected_package_id: str | None = None,
) -> list[str]:
    """Validate lock/counts/SHAs/package_id against files *inside* package_dir.

    Read-only: never mutates package files (lock is never unlinked).
    Does not depend on live CURRENT. Used before promotion.
    """
    errs: list[str] = []
    for rel in _required_package_rels():
        if not (package_dir / rel).is_file():
            errs.append(f"PACKAGE_MISSING:{rel}")
    lock_path = package_dir / "instrument_data_manifests" / "committed_artifact_lock.json"
    if not lock_path.is_file():
        errs.append("PACKAGE_MISSING_LOCK")
        return errs
    try:
        lock = json.loads(lock_path.read_text())
    except json.JSONDecodeError as e:
        return [f"PACKAGE_LOCK_JSON:{e}"]

    errs.extend(_validate_lock_schema(lock))

    if expected_package_id is not None:
        if lock.get("package_id") != expected_package_id:
            errs.append(
                f"LOCK_PACKAGE_ID_MISMATCH:lock={lock.get('package_id')!r} "
                f"expected={expected_package_id!r}"
            )
        if package_dir.name != expected_package_id:
            errs.append(
                f"DIR_PACKAGE_ID_MISMATCH:dir={package_dir.name!r} "
                f"expected={expected_package_id!r}"
            )
        try:
            validate_package_id(expected_package_id)
        except ValueError as e:
            errs.append(f"PACKAGE_ID_INVALID:{e}")

    # Content id: read-only recompute (lock excluded by digest member set)
    run_for_id = (
        lock.get("export_run_id")
        if isinstance(lock.get("export_run_id"), str)
        else None
    )
    recomputed = content_package_id(package_dir, run_for_id)
    want_id = expected_package_id or lock.get("package_id")
    if want_id and recomputed != want_id:
        errs.append(
            f"CONTENT_ID_MISMATCH:recomputed={recomputed} expected={want_id}"
        )

    arts = lock.get("artifacts") if isinstance(lock.get("artifacts"), dict) else {}
    required = set(SYMBOLS)
    man_by_sym = {m.symbol: m for m in (manifests or [])}
    data_dir = package_dir / "instrument_data"

    for sym in sorted(required):
        ent = arts.get(sym)
        if not isinstance(ent, dict):
            errs.append(f"{sym}:missing_from_lock")
            continue
        research_name = f"{sym.lower()}_h1.csv"
        develop_name = f"{sym.lower()}_h1_develop.csv"
        rp = data_dir / research_name
        dp = data_dir / develop_name
        if not rp.is_file():
            errs.append(f"{sym}:full_file_missing:{research_name}")
        else:
            sha = _sha256_file(rp)
            if sha != ent.get("research_csv_sha256"):
                errs.append(f"{sym}:full_sha_mismatch")
            n_lines = sum(1 for _ in rp.open()) - 1
            if n_lines != int(ent.get("n_rows_h1") or -1):
                errs.append(
                    f"{sym}:full_row_count_mismatch:{n_lines}!={ent.get('n_rows_h1')}"
                )
            if n_lines < 1000 and int(ent.get("n_rows_h1") or 0) >= 1000:
                errs.append(f"{sym}:full_suspiciously_small:{n_lines}")
        if not dp.is_file():
            errs.append(f"{sym}:develop_file_missing:{develop_name}")
        else:
            dsha = _sha256_file(dp)
            if dsha != ent.get("develop_csv_sha256"):
                errs.append(f"{sym}:develop_sha_mismatch")
            dn = sum(1 for _ in dp.open()) - 1
            if dn != int(ent.get("n_rows_h1_develop") or -1):
                errs.append(
                    f"{sym}:develop_row_count_mismatch:{dn}!={ent.get('n_rows_h1_develop')}"
                )
            if dn < 1000 and int(ent.get("n_rows_h1_develop") or 0) >= 1000:
                errs.append(f"{sym}:develop_suspiciously_small:{dn}")
        if man_by_sym:
            m = man_by_sym.get(sym)
            if m is None:
                errs.append(f"{sym}:missing_manifest_object")
            else:
                if int(m.n_rows_h1) != int(ent.get("n_rows_h1") or -1):
                    errs.append(f"{sym}:manifest_full_count_mismatch")
                if int(m.n_rows_h1_develop) != int(ent.get("n_rows_h1_develop") or -1):
                    errs.append(f"{sym}:manifest_develop_count_mismatch")
                if m.research_csv_sha256 and m.research_csv_sha256 != ent.get(
                    "research_csv_sha256"
                ):
                    errs.append(f"{sym}:manifest_full_sha_mismatch")
    return errs


def recover_live_from_current() -> str | None:
    """Startup recovery: ensure static roots through CURRENT; return package id."""
    pkg = resolve_current_package_dir()
    ensure_static_live_roots_through_current()
    if pkg is None:
        return None
    return pkg.name


@dataclass(frozen=True)
class PackageSnapshot:
    """Pinned multi-instrument package view for one research operation.

    Resolve CURRENT once, then read every symbol from ``package_dir`` only.
    Do not re-resolve CURRENT between symbol loads (avoids cross-flip reads).
    """

    package_id: str
    package_dir: Path

    def data_dir(self) -> Path:
        return self.package_dir / "instrument_data"

    def manifest_dir(self) -> Path:
        return self.package_dir / "instrument_data_manifests"

    def history_csv(self, symbol: str) -> Path:
        if symbol not in SYMBOLS:
            raise ValueError(f"unknown symbol {symbol!r}; need one of {SYMBOLS}")
        return self.data_dir() / f"{symbol.lower()}_h1.csv"

    def develop_csv(self, symbol: str) -> Path:
        if symbol not in SYMBOLS:
            raise ValueError(f"unknown symbol {symbol!r}; need one of {SYMBOLS}")
        return self.data_dir() / f"{symbol.lower()}_h1_develop.csv"

    def lock_path(self) -> Path:
        return self.manifest_dir() / "committed_artifact_lock.json"

    def read_history(self, symbol: str) -> pd.DataFrame:
        path = self.history_csv(symbol)
        if not path.is_file():
            raise FileNotFoundError(f"missing history in pinned package: {path}")
        return pd.read_csv(path)

    def read_develop(self, symbol: str) -> pd.DataFrame:
        path = self.develop_csv(symbol)
        if not path.is_file():
            raise FileNotFoundError(f"missing develop in pinned package: {path}")
        return pd.read_csv(path)

    def read_all_histories(self) -> dict[str, pd.DataFrame]:
        """Load all SYMBOLS from this pinned package (single directory)."""
        return {s: self.read_history(s) for s in SYMBOLS}

    def read_all_develop(self) -> dict[str, pd.DataFrame]:
        return {s: self.read_develop(s) for s in SYMBOLS}


def load_package_snapshot(
    package_dir: Path | None = None,
    *,
    validate: bool = True,
) -> PackageSnapshot:
    """Resolve and pin one package directory for multi-symbol research IO.

    If ``package_dir`` is None, resolves CURRENT once. Subsequent reads must use
    the returned snapshot paths — never re-open live roots per symbol mid-operation.
    """
    if package_dir is None:
        pkg = resolve_current_package_dir()
        if pkg is None:
            raise RuntimeError("NO_CURRENT_PACKAGE: cannot load snapshot")
    else:
        pkg = package_dir
        if not pkg.is_dir():
            raise FileNotFoundError(f"package_dir missing: {pkg}")
        # If under PACKAGE_ROOT, enforce direct-child safety
        try:
            if pkg.resolve().parent == PACKAGE_ROOT.resolve():
                validate_package_id(pkg.name)
        except ValueError as e:
            raise RuntimeError(f"INVALID_PACKAGE_DIR:{e}") from e

    package_id = pkg.name
    if validate:
        errs = verify_package_artifacts(pkg, expected_package_id=package_id)
        if errs:
            raise RuntimeError(f"SNAPSHOT_VALIDATE_FAIL:{errs}")
    return PackageSnapshot(package_id=package_id, package_dir=pkg.resolve())


def write_package_sha_manifest(package_dir: Path, dest: Path | None = None) -> Path:
    """Write read-only SHA inventory for a package (artifact mechanism without bulk git)."""
    package_id = package_dir.name
    files: dict[str, dict[str, Any]] = {}
    for rel in _package_member_relpaths(package_dir):
        fp = package_dir / rel
        st = fp.stat()
        files[rel] = {
            "sha256": _sha256_file(fp),
            "bytes": int(st.st_size),
        }
    body = {
        "package_id": package_id,
        "publish_model": PUBLISH_MODEL,
        "required_symbols": list(SYMBOLS),
        "files": files,
        "content_package_id": content_package_id(
            package_dir,
            package_id.split("-", 1)[0]
            if PACKAGE_ID_RE.fullmatch(package_id)
            else None,
        ),
    }
    out = dest if dest is not None else (PACKAGE_ROOT / f"{package_id}.sha256.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(body, indent=2) + "\n")
    return out


def finalize_package_dir(package_dir: Path, package_id: str) -> Path:
    """Place package at PACKAGE_ROOT/package_id without destroying different content."""
    import shutil

    package_id = validate_package_id(package_id)
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    final_pkg = PACKAGE_ROOT / package_id
    stage_digest = _package_content_digest(package_dir)

    if final_pkg.resolve() == package_dir.resolve():
        return final_pkg

    if final_pkg.exists():
        if not final_pkg.is_dir():
            raise RuntimeError(f"PACKAGE_ID_OCCUPIED_BY_NON_DIR:{final_pkg}")
        existing = _package_content_digest(final_pkg)
        if existing != stage_digest:
            raise RuntimeError(
                f"PACKAGE_ID_COLLISION: id={package_id} exists with different content "
                f"(existing={existing[:16]} staged={stage_digest[:16]}). "
                "Refusing to overwrite immutable package."
            )
        if package_dir.exists() and package_dir.resolve() != final_pkg.resolve():
            shutil.rmtree(package_dir, ignore_errors=True)
        return final_pkg

    shutil.move(str(package_dir), str(final_pkg))
    return final_pkg


def publish_versioned_package(
    package_dir: Path,
    package_id: str,
    *,
    manifests: list[SymbolManifest] | None = None,
    prevalidated: bool = False,
) -> Path:
    """Promote package to CURRENT via single atomic pointer flip.

    Safety rules (v6):
    1. Resolve previous CURRENT *before* mutation; dangling/escape aborts.
    2. Never overwrite an existing different package (immutable IDs).
    3. Validate staged package lock/SHAs/counts/id *before* CURRENT switch.
    4. Live roots are static links through CURRENT/...; only CURRENT is replaced.
    5. Post-switch verify failure rolls CURRENT back to previous package.
    """
    package_id = validate_package_id(package_id)
    prev_pkg = resolve_current_package_dir()

    final_pkg = finalize_package_dir(package_dir, package_id)

    if not prevalidated:
        pre_errs = verify_package_artifacts(
            final_pkg, manifests=manifests, expected_package_id=package_id
        )
        if pre_errs:
            raise RuntimeError(f"PRE_SWITCH_VALIDATE_FAIL:{pre_errs}")

    # Idempotent: already CURRENT and live matches
    cur = _read_current_package_id()
    if cur == package_id:
        ensure_static_live_roots_through_current()
        live_errs = verify_live_matches_package(final_pkg)
        if not live_errs:
            return final_pkg
        # Repair static roots / CURRENT only
        ensure_static_live_roots_through_current()
        _write_current_package_id(package_id)
        live_errs = verify_live_matches_package(final_pkg)
        if live_errs:
            raise RuntimeError(f"LIVE_REPAIR_FAILED:{live_errs}")
        return final_pkg

    try:
        ensure_static_live_roots_through_current()
        _write_current_package_id(package_id)
        live_errs = verify_live_matches_package(final_pkg)
        if live_errs:
            raise RuntimeError(f"LIVE_VERIFY_FAIL:{live_errs}")
    except Exception:
        if prev_pkg is not None:
            try:
                ensure_static_live_roots_through_current()
                _write_current_package_id(prev_pkg.name)
            except Exception as rb_err:
                raise RuntimeError(
                    f"publish failed and rollback failed: {rb_err}"
                ) from rb_err
        raise
    return final_pkg


def write_fail_evidence(
    manifests: list[SymbolManifest],
    common: dict[str, Any],
    gate: str,
    export_errs: list[str],
) -> Path:
    """Write FAIL evidence beside the live set — never into the CURRENT package."""
    write_report(manifests, common, gate, export_errs, path=FAIL_REPORT_PATH)
    return FAIL_REPORT_PATH


def _atomic_publish_staging(staging: Path, final: Path) -> None:
    """Legacy per-CSV helper — prefer publish_versioned_package."""
    final.mkdir(parents=True, exist_ok=True)
    for name in (
        [f"{s.lower()}_h1.csv" for s in SYMBOLS]
        + [f"{s.lower()}_h1_develop.csv" for s in SYMBOLS]
    ):
        src = staging / name
        if not src.is_file():
            raise FileNotFoundError(f"staging missing {name}")
        dst = final / name
        tmp = final / f".{name}.tmp"
        tmp.write_bytes(src.read_bytes())
        tmp.replace(dst)


def main() -> int:
    import shutil
    import tempfile

    bridge = _wine_bridge_dir()
    print(f"Bridge dir: {bridge}")

    if not COSTS_XAU.is_file():
        print("Gate: FAIL_DATA (missing costs file)")
        write_fail_evidence([], {"status": "FAIL"}, "FAIL_DATA", ["MISSING_COSTS_FILE"])
        return 1
    costs = json.loads(COSTS_XAU.read_text())
    cost_errs = verify_costs_file(costs)
    if cost_errs:
        print("COSTS_FAIL:", cost_errs)
        write_fail_evidence([], {"status": "FAIL"}, "FAIL_DATA", cost_errs)
        return 1

    holdout = DEVELOP_END_SERVER
    if HOLDOUT_LOCK.is_file():
        hs = json.loads(HOLDOUT_LOCK.read_text()).get("holdout_start")
        if hs:
            holdout = pd.Timestamp(str(hs)[:19])

    export_run = _load_export_run(bridge)
    export_complete = _load_export_complete(bridge)

    export_errs = verify_export_run(
        export_run, costs, bridge_dir=bridge, export_complete=export_complete
    )
    print("export_run:", (export_run or {}).get("run_id"), "errs=", export_errs)

    run_id: str | None = None
    if export_run and isinstance(export_run.get("run_id"), str):
        run_id = str(export_run["run_id"])

    try:
        prev_pkg = resolve_current_package_dir()
    except RuntimeError as e:
        print("CURRENT_PREFLIGHT_FAIL:", e)
        write_fail_evidence([], {"status": "FAIL"}, "FAIL_DATA", [str(e)])
        return 1
    if prev_pkg:
        print(f"Previous package (rollback source): {prev_pkg.name}")

    # Ensure live roots use CURRENT indirection (migration from per-package links)
    ensure_static_live_roots_through_current()

    staging_root = Path(tempfile.mkdtemp(prefix="instr_pkg_", dir=str(ROOT / "results")))
    package_stage = staging_root / "staging_pkg"
    stage_data = package_stage / "instrument_data"
    stage_man = package_stage / "instrument_data_manifests"
    stage_data.mkdir(parents=True, exist_ok=True)
    stage_man.mkdir(parents=True, exist_ok=True)

    manifests: list[SymbolManifest] = []
    develops: dict[str, pd.DataFrame] = {}
    publish_stage = not bool(export_errs)

    for sym in SYMBOLS:
        m, dev = build_symbol(
            sym,
            bridge_dir=bridge,
            costs=costs,
            export_run=export_run,
            holdout_start=holdout,
            out_dir=stage_data,
            publish=publish_stage,
        )
        manifests.append(m)
        (stage_man / f"{sym.lower()}_h1_manifest.json").write_text(
            json.dumps(asdict(m), indent=2) + "\n"
        )
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
    (stage_man / "common_develop_window.json").write_text(
        json.dumps(common, indent=2) + "\n"
    )

    for name in ("export_run.json", "export_complete.json", "export_challenge.json"):
        for src in (bridge / name, MANIFEST_DIR / name):
            if src.is_file():
                (stage_man / name).write_text(src.read_text())
                break

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

    report_stage = package_stage / "multi_instrument_data_readiness.md"
    write_report(manifests, common, gate, export_errs, path=report_stage)

    package_id = "unbuilt"

    if gate.startswith("PASS_"):
        for m in manifests:
            if m.published:
                m.research_csv = f"results/instrument_data/{m.symbol.lower()}_h1.csv"
                m.missing_duplicate_bars["develop_csv"] = (
                    f"results/instrument_data/{m.symbol.lower()}_h1_develop.csv"
                )
                sp = stage_data / f"{m.symbol.lower()}_h1.csv"
                dp = stage_data / f"{m.symbol.lower()}_h1_develop.csv"
                m.research_csv_sha256 = _sha256_file(sp)
                m.missing_duplicate_bars["develop_csv_sha256"] = _sha256_file(dp)
                (stage_man / f"{m.symbol.lower()}_h1_manifest.json").write_text(
                    json.dumps(asdict(m), indent=2) + "\n"
                )

        write_report(manifests, common, gate, export_errs, path=report_stage)
        package_id, _lock = seal_package_identity(
            package_stage, run_id, gate=gate, manifests=manifests
        )
        print(f"Package id (content-addressed): {package_id}")

        # Pre-switch validation on staging (before finalize moves it)
        # Finalize first so package sits under PACKAGE_ROOT, then validate, then flip.
        try:
            final_pkg = finalize_package_dir(package_stage, package_id)
            pre_errs = verify_package_artifacts(
                final_pkg, manifests=manifests, expected_package_id=package_id
            )
            if pre_errs:
                raise RuntimeError(f"PRE_SWITCH_VALIDATE_FAIL:{pre_errs}")
            publish_versioned_package(
                final_pkg, package_id, manifests=manifests, prevalidated=True
            )
        except Exception as e:
            print("PACKAGE_PUBLISH_FAIL:", e)
            gate = "FAIL_DATA"
            fail_path = write_fail_evidence(
                manifests,
                common,
                gate,
                export_errs + [f"PACKAGE_PUBLISH_FAIL:{e}"],
            )
            shutil.rmtree(staging_root, ignore_errors=True)
            print(f"Gate: {gate}")
            print(f"Fail evidence: {fail_path}")
            return 1

        # Post-switch safety net: if still failing, roll back CURRENT
        lock_errs = verify_committed_artifacts(manifests=manifests)
        if lock_errs:
            print("ARTIFACT_LOCK_VERIFY_FAIL:", lock_errs)
            if prev_pkg is not None:
                try:
                    _write_current_package_id(prev_pkg.name)
                    print(f"Rolled CURRENT back to {prev_pkg.name}")
                except Exception as rb:
                    print("ROLLBACK_AFTER_POST_VERIFY_FAIL:", rb)
            gate = "FAIL_DATA"
            write_fail_evidence(manifests, common, gate, export_errs + lock_errs)
            shutil.rmtree(staging_root, ignore_errors=True)
            print(f"Gate: {gate}")
            return 1
    else:
        print("Skipping publish — gate not PASS (package staging discarded)")
        write_fail_evidence(manifests, common, gate, export_errs)

    shutil.rmtree(staging_root, ignore_errors=True)
    print(f"Gate: {gate}")
    print(f"Report: {REPORT_PATH}")
    if gate.startswith("PASS_"):
        print(f"Package: {PACKAGE_ROOT / package_id} CURRENT={package_id}")
    return 0 if gate.startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
