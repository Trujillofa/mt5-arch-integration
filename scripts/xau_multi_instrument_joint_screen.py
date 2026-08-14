#!/usr/bin/env python3
"""Dedicated multi-instrument joint **develop screen** harness (v4 family).

Charter: ``results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v4.json``
Family: ``scripts/xau_family_joint_london_open_cosign_fade_flat.py``

This is the only authorized path for scoring multi-instrument joint charters.
Single-frame ``xau_family_null_maxstat`` / ``xau_sealed_family_cycle`` refuse them.

**Modes**

* Default **dry**: validate charter + print plan (no package load, no score).
* ``--frames-parquet-dir``: synthetic/non-dispositional score only. Forbidden with
  ``--write-registry`` or ``--execute-develop-screen``. Never appends the
  disposition registry.
* ``--execute-develop-screen``: dispositional develop score. Always requires
  sealed charter path under ``results/xau_charters/``, clean dispositional tree,
  exact loaded-cost match to charter, fresh out-dir, and provenance (code commit +
  costs SHA). Emits canonical ``null_maxstat.json`` for fail-closed accounting.

Null trials, sealed r1, holdout, paper, live: **not** implemented here.

SAFETY: offline only. No live orders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from xau_charter_protocol import (  # noqa: E402
    CharterError,
    assert_charter_path_for_sealed,
    assert_clean_dispositional_tree,
    build_provenance,
    ensure_fresh_run_dir,
    is_charter_runnable,
    load_charter,
    exogenous_joint_screen_refuse_message,
    multi_instrument_single_frame_refuse_message,
    sha256_file,
    validate_charter_file,
)
from xau_family_joint_london_open_cosign_fade_flat import (  # noqa: E402
    FAMILY,
    JOINT_START_EQUITY,
    SYMBOLS,
    align_joint,
    build_grid,
    joint_gate_success,
    n_passers_binary,
    simulate_joint,
    soft_pass_joint,
    soft_pass_per_symbol,
)
from xau_research_costs import RESEARCH_COSTS_PATH, load_research_costs_full  # noqa: E402

DEFAULT_CHARTER = (
    ROOT / "results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v4.json"
)
DEFAULT_OUT = ROOT / "results/xau_runs" / f"{FAMILY}_screen"

# Artifacts that must not be silently overwritten
_ARTIFACT_NAMES = ("joint_screen.json", "null_maxstat.json", "STARTED.json")


def _metrics_blob(m: Any) -> dict[str, float | int]:
    return {
        "n_trades": int(m.n_trades),
        "profit_factor": float(m.profit_factor),
        "net_profit": float(m.net_profit),
        "max_drawdown_pct": float(m.max_drawdown_pct),
        "win_rate": float(m.win_rate),
        "wins": int(m.wins),
        "losses": int(m.losses),
    }


def assert_multi_instrument_charter(charter: dict[str, Any]) -> None:
    """Fail closed: only multi_instrument_joint_v1 joint cosign family."""
    exo = exogenous_joint_screen_refuse_message(charter)
    if exo is not None:
        raise SystemExit(exo)
    refuse = multi_instrument_single_frame_refuse_message(charter)
    if refuse is None and not (charter.get("instrument") or {}).get(
        "multi_symbol_in_scope"
    ):
        raise SystemExit(
            "charter is not multi-instrument; use single-frame null_maxstat instead"
        )
    harness = charter.get("harness") or {}
    if harness.get("kind") != "multi_instrument_joint_v1":
        raise SystemExit(
            "charter harness.kind must be multi_instrument_joint_v1 "
            f"(got {harness.get('kind')!r})"
        )
    if str(charter.get("family_id") or "") != FAMILY:
        raise SystemExit(
            f"charter family_id must be {FAMILY!r} "
            f"(got {charter.get('family_id')!r})"
        )


def pin_package_id(charter: dict[str, Any]) -> str:
    pkg = (charter.get("instrument") or {}).get("data_package") or {}
    pid = str(pkg.get("package_id") or pkg.get("content_package_id") or "")
    if not pid:
        raise SystemExit("charter instrument.data_package.package_id required")
    return pid


# Sim keys used by this harness (per-symbol point_size lives in family meta — not here).
_COST_SIM_KEYS = ("spread_col", "commission_per_lot", "slippage_points")
_COST_IDENTITY_KEYS = ("account_type", "login", "server")


def _is_strict_int(v: Any) -> bool:
    """True JSON integer (bool is a subclass of int — reject it)."""
    return type(v) is int


def _is_strict_str(v: Any) -> bool:
    return type(v) is str


def _is_strict_finite_number(v: Any) -> bool:
    """Non-boolean int/float that is finite (reject NaN/Inf/bool/str)."""
    if type(v) is bool:
        return False
    if type(v) is int:
        return True
    if type(v) is float:
        return math.isfinite(v)
    return False


def _require_exact_match(key: str, charter_v: Any, loaded_v: Any, *, kind: str) -> None:
    """Fail closed on type/value mismatch for cost identity or sim keys."""
    if kind == "int":
        if not _is_strict_int(charter_v):
            raise SystemExit(
                f"charter fixed.costs.{key} must be a non-boolean integer "
                f"(got {charter_v!r} type={type(charter_v).__name__})"
            )
        if not _is_strict_int(loaded_v):
            raise SystemExit(
                f"loaded costs.{key} must be a non-boolean integer "
                f"(got {loaded_v!r} type={type(loaded_v).__name__})"
            )
        if charter_v != loaded_v:
            raise SystemExit(
                f"cost identity mismatch {key}: charter={charter_v} loaded={loaded_v}"
            )
        return
    if kind == "str":
        if not _is_strict_str(charter_v):
            raise SystemExit(
                f"charter fixed.costs.{key} must be a string "
                f"(got {charter_v!r} type={type(charter_v).__name__})"
            )
        if not _is_strict_str(loaded_v):
            raise SystemExit(
                f"loaded costs.{key} must be a string "
                f"(got {loaded_v!r} type={type(loaded_v).__name__})"
            )
        if charter_v != loaded_v:
            raise SystemExit(
                f"cost identity mismatch {key}: charter={charter_v!r} loaded={loaded_v!r}"
            )
        return
    if kind == "finite_number":
        if not _is_strict_finite_number(charter_v):
            raise SystemExit(
                f"charter fixed.costs.{key} must be a non-boolean finite number "
                f"(got {charter_v!r} type={type(charter_v).__name__})"
            )
        if not _is_strict_finite_number(loaded_v):
            raise SystemExit(
                f"loaded costs.{key} must be a non-boolean finite number "
                f"(got {loaded_v!r} type={type(loaded_v).__name__})"
            )
        if float(charter_v) != float(loaded_v):
            raise SystemExit(
                f"cost mismatch {key}: charter={charter_v} loaded={loaded_v}. "
                "Update results/xau_research_costs.json or freeze a new charter."
            )
        return
    raise SystemExit(f"internal: unknown cost kind {kind!r} for {key}")


def assert_costs_match_charter(
    charter: dict[str, Any],
    loaded: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full costs document must match charter fixed.costs on sim + identity keys.

    Strict JSON types (no NaN, no bool-as-int, no stringified login).
    Does **not** compare global ``point_size`` — execution uses per-symbol meta.

    Returns sim kwargs suitable for ``simulate_joint``:
    ``spread_col``, ``commission_per_lot``, ``slippage_points`` only.
    """
    fixed = (charter.get("fixed") or {}).get("costs") or charter.get("costs") or {}
    full = dict(loaded if loaded is not None else load_research_costs_full())

    # Identity: account_type/server strings; login non-bool int
    for k in ("account_type", "server"):
        if k not in fixed:
            raise SystemExit(f"charter fixed.costs missing identity key {k!r}")
        if k not in full:
            raise SystemExit(
                f"loaded costs missing identity key {k!r} "
                "(use full research costs document, not sim subset alone)"
            )
        _require_exact_match(k, fixed[k], full[k], kind="str")

    if "login" not in fixed:
        raise SystemExit("charter fixed.costs missing identity key 'login'")
    if "login" not in full:
        raise SystemExit(
            "loaded costs missing identity key 'login' "
            "(use full research costs document, not sim subset alone)"
        )
    _require_exact_match("login", fixed["login"], full["login"], kind="int")

    # Simulation keys: exact string spread_col; finite numbers for commission/slippage
    if "spread_col" not in fixed:
        raise SystemExit("charter fixed.costs missing spread_col")
    if "spread_col" not in full:
        raise SystemExit("loaded costs missing spread_col")
    _require_exact_match("spread_col", fixed["spread_col"], full["spread_col"], kind="str")

    for k in ("commission_per_lot", "slippage_points"):
        if k not in fixed:
            raise SystemExit(f"charter fixed.costs missing {k}")
        if k not in full:
            raise SystemExit(f"loaded costs missing {k}")
        _require_exact_match(k, fixed[k], full[k], kind="finite_number")

    # Explicitly ignore global point_size (XAU-only in research costs; FX differs).
    return {
        "spread_col": str(full["spread_col"]),
        "commission_per_lot": float(full["commission_per_lot"]),
        "slippage_points": float(full["slippage_points"]),
    }


def write_started_marker(
    out_dir: Path,
    *,
    charter_path: Path,
    package_id: str,
    mode: str,
) -> Path:
    """Write STARTED marker before package load / score so interruptions are visible."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "STARTED.json"
    if path.exists():
        raise SystemExit(f"refuse overwrite existing STARTED marker: {path}")
    body = {
        "execution_state": "STARTED",
        "family_id": FAMILY,
        "mode": mode,
        "charter_path": str(charter_path),
        "package_id": package_id,
        "started_at_utc": datetime.now(UTC).isoformat(),
    }
    path.write_text(json.dumps(body, indent=2) + "\n")
    return path


def charter_null_base_seed(charter: dict[str, Any]) -> int:
    null = charter.get("null") or {}
    if null.get("base_seed") is None:
        raise SystemExit("charter null.base_seed required for screen accounting")
    return int(null["base_seed"])


def charter_n_null_planned(charter: dict[str, Any]) -> int:
    null = charter.get("null") or {}
    return int(null.get("n_trials") or null.get("min_null_trials") or 0)


def load_develop_frames_from_package(
    charter: dict[str, Any],
    *,
    package_dir: Path | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any], Path]:
    """Load develop H1 for all symbols from pinned multi-instrument package.

    Returns (frames, meta, data_path_for_provenance).
    """
    from build_multi_instrument_data_readiness import (  # noqa: WPS433
        PACKAGE_ROOT,
        load_package_snapshot,
    )

    expected_id = pin_package_id(charter)
    if package_dir is None:
        snap = load_package_snapshot(validate=True)
    else:
        snap = load_package_snapshot(package_dir, validate=True)
    if snap.package_id != expected_id:
        raise SystemExit(
            f"package_id mismatch: snapshot={snap.package_id!r} "
            f"charter={expected_id!r} (refuse cross-package score)"
        )
    holdout = (charter.get("window") or {}).get("holdout_start_server") or (
        charter.get("instrument") or {}
    ).get("data_package", {}).get("holdout_start_server")
    hs = pd.Timestamp(holdout) if holdout else None
    frames = {s: snap.read_develop(s, holdout_start=hs) for s in SYMBOLS}
    for s, df in frames.items():
        if "time" not in df.columns:
            raise SystemExit(f"{s} develop frame missing time")
        if "spread" not in df.columns:
            raise SystemExit(
                f"{s} develop frame missing spread; refuse zero-cost default"
            )
    # Provenance data path: common develop window if present, else first symbol H1
    common = snap.manifest_dir() / "common_develop_window.json"
    data_path = common if common.is_file() else snap.history_csv(SYMBOLS[0])
    meta = {
        "package_id": snap.package_id,
        "package_dir": str(snap.package_dir),
        "holdout_start": str(hs) if hs is not None else None,
        "n_rows": {s: int(len(frames[s])) for s in SYMBOLS},
        "package_root": str(PACKAGE_ROOT),
        "data_path": str(data_path),
    }
    return frames, meta, data_path


def run_joint_screen(
    frames: dict[str, pd.DataFrame],
    charter: dict[str, Any],
    *,
    costs: dict[str, Any],
    already_aligned: bool = False,
    dispositional: bool = False,
    non_dispositional_reason: str | None = None,
) -> dict[str, Any]:
    """Score sole joint config. Never runs null trials.

    ``dispositional=True`` marks a real develop-screen attempt that may later
    enter the registry. Synthetic/fixture frames must pass
    ``dispositional=False``.
    """
    assert_multi_instrument_charter(charter)
    if dispositional and non_dispositional_reason:
        raise SystemExit("internal: dispositional screen cannot carry synthetic reason")
    if not dispositional and not non_dispositional_reason:
        non_dispositional_reason = "synthetic_or_unspecified_non_dispositional"

    grid = build_grid()
    if len(grid) != 1:
        raise SystemExit(f"search_cardinality must be 1; got {len(grid)} configs")
    params = dict(grid[0])
    commission = float(costs.get("commission_per_lot") or 0.0)
    slippage = float(costs.get("slippage_points") or 0.0)
    spread_col = str(costs.get("spread_col") or "spread")

    aligned = frames if already_aligned else align_joint(frames)
    result = simulate_joint(
        aligned,
        already_aligned=True,
        commission_per_lot=commission,
        slippage_points=slippage,
        spread_col=spread_col,
        **{
            k: params[k]
            for k in params
            if k
            in (
                "coincident_hours",
                "flat_hour",
                "sl_atr",
                "tp_atr",
                "risk_pct",
                "lot_max",
                "lot_min",
                "lot_step",
            )
        },
    )

    per_soft = {s: soft_pass_per_symbol(result.per_symbol[s]) for s in SYMBOLS}
    joint_soft = soft_pass_joint(result.joint)
    gate_ok = joint_gate_success(result)
    n_pass = n_passers_binary(result)
    n_null_planned = charter_n_null_planned(charter)
    base_seed = charter_null_base_seed(charter)
    zero = n_pass == 0

    if zero:
        disposition = "SCREEN_FAIL"
        screen_status = "ZERO_PRIMARY_PASSERS"
        skipped_reason = "ZERO_PRIMARY_PASSERS"
        reason = (
            "Develop joint screen: zero soft primary passers "
            "(binary joint gate). Null trials not executed; r1 unburned."
        )
    else:
        disposition = "SCREEN_PASS_PENDING_NULL_REVIEW"
        screen_status = "PASSERS_GE_1_PENDING_NULL_REVIEW"
        skipped_reason = "SCREEN_ONLY"
        reason = (
            "Develop joint screen: primary passers=1. Null trials intentionally "
            "not run; external review required before any null/sealed run."
        )

    if not dispositional:
        reason = (
            f"NON_DISPOSITIONAL ({non_dispositional_reason}): " + reason
            + " Must not write disposition registry."
        )

    real_block = {
        "n_passers": n_pass,
        "primary_passers": n_pass,
        "n_passers_soft": n_pass,
        "n_passers_classic_status": "not_evaluated",
        "n_passers_classic": None,
        **_metrics_blob(result.joint),
        "joint_start_equity": JOINT_START_EQUITY,
        "n_signals_cosign": result.n_signals_cosign,
        "n_signals_entered": result.n_signals_entered,
        "n_signals_skipped_partial": result.n_signals_skipped_partial,
        "per_symbol": {s: _metrics_blob(result.per_symbol[s]) for s in SYMBOLS},
        "per_symbol_soft_pass": per_soft,
        "joint_soft_pass": joint_soft,
        "joint_gate_success": gate_ok,
        "n_passers_definition": "binary_joint_gate_success",
    }

    attempt_type = (
        "DETERMINISTIC_SCREEN" if dispositional else "SYNTHETIC_NON_DISPOSITIONAL"
    )

    # Canonical null_maxstat-shaped report for fail-closed parse_harness_report
    report: dict[str, Any] = {
        "method": "multi_instrument_joint_screen_v1",
        "family": FAMILY,
        "family_id": FAMILY,
        "harness": "xau_multi_instrument_joint_screen",
        "harness_kind": "multi_instrument_joint_v1",
        "dispositional": bool(dispositional),
        "non_dispositional_reason": None
        if dispositional
        else str(non_dispositional_reason),
        "screen_only": True,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "grid": params,
        "costs": {
            "commission_per_lot": commission,
            "slippage_points": slippage,
            "spread_col": spread_col,
            "costs_source": str(RESEARCH_COSTS_PATH),
        },
        "real": real_block,
        "metrics_real_grid_develop": real_block,
        "screen": {
            "zero_primary_passers": bool(zero),
            "screen_only": True,
            "rule": (
                "If real primary passers==0, SCREEN_FAIL without null trials. "
                "Synthetic/non-dispositional scores must never write the registry."
            ),
        },
        "attempt_accounting": {
            "attempt_type": attempt_type,
            "family_screen_attempt": True,
            "sealed_null_attempt": False,
            "n_null_planned": n_null_planned,
            "n_null_executed": 0,
            "null_trials_executed": 0,
            "r1_style_null_burned": False,
            "r1_burned": False,
            "screen_only": True,
            "dispositional": bool(dispositional),
        },
        "null": {
            "method": str((charter.get("null") or {}).get("method") or ""),
            "base_seed": base_seed,
            "n_trials": 0,
            "n_null_planned": n_null_planned,
            "n_null_executed": 0,
            "skipped_reason": skipped_reason,
            "trials": [],
            "p_max_pf": None,
            "p_n_passers": 1.0 if zero else None,
            "p_max_pf_status": "not_evaluated",
            "p_n_passers_status": (
                "implied_1.0_zero_real_passers" if zero else "not_evaluated_screen_only"
            ),
        },
        "verdict": {
            "disposition": disposition,
            "reason": reason,
            "promote": False,
            "live_go": False,
            "screen_status": screen_status,
            "fail_max_pf": None,
            "fail_n_passers": bool(zero),
        },
        # Convenience mirrors (not required by parser)
        "disposition": disposition,
        "screen_status": screen_status,
        "n_passers": n_pass,
        "r1_burned": False,
        "null_trials_executed": 0,
        "n_null_planned_charter": n_null_planned,
        "sealed_null_attempt": False,
        "promote": False,
        "live_go": False,
        "reason": reason,
        "per_symbol_soft_pass": per_soft,
        "joint_soft_pass": joint_soft,
        "joint_gate_success": gate_ok,
        "n_passers_definition": "binary_joint_gate_success",
    }
    return report


def ensure_fresh_artifacts(out_dir: Path) -> Path:
    """Refuse overwrite of existing screen artifacts."""
    if out_dir.exists():
        for name in _ARTIFACT_NAMES:
            p = out_dir / name
            if p.exists():
                raise SystemExit(
                    f"refuse overwrite existing screen artifact: {p}. "
                    "Choose a fresh --out-dir."
                )
        # Directory exists but empty of our artifacts — still refuse non-empty dir
        if any(out_dir.iterdir()):
            raise SystemExit(
                f"run output directory not empty (refuse overwrite): {out_dir}. "
                "Choose a fresh --out-dir."
            )
        return out_dir
    return ensure_fresh_run_dir(out_dir)


def write_screen_report(report: dict[str, Any], out_dir: Path) -> Path:
    """Write joint_screen.json and canonical null_maxstat.json (same payload).

    STARTED.json may already exist (written before score); final reports must not.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("joint_screen.json", "null_maxstat.json"):
        p = out_dir / name
        if p.exists():
            raise SystemExit(f"refuse overwrite existing screen artifact: {p}")
    path = out_dir / "joint_screen.json"
    text = json.dumps(report, indent=2, default=str) + "\n"
    path.write_text(text)
    # Canonical name for parse_harness_report_for_accounting
    (out_dir / "null_maxstat.json").write_text(text)
    return path


def append_disposition_registry(
    charter_path: Path,
    report: dict[str, Any],
    *,
    screen_artifact: str,
) -> None:
    """Append disposition registry row — dispositional develop screens only."""
    if not report.get("dispositional"):
        raise SystemExit(
            "REFUSE_REGISTRY_WRITE: report is non-dispositional "
            f"({report.get('non_dispositional_reason')!r}); "
            "synthetic scores must not close the real charter"
        )
    if report.get("attempt_accounting", {}).get("attempt_type") != "DETERMINISTIC_SCREEN":
        raise SystemExit(
            "REFUSE_REGISTRY_WRITE: attempt_type must be DETERMINISTIC_SCREEN"
        )
    from xau_charter_protocol import DISPOSITION_REGISTRY, charter_file_sha256

    row = {
        "attempt_type": "DETERMINISTIC_SCREEN",
        "charter_path": str(
            charter_path.as_posix().replace(str(ROOT) + "/", "")
            if str(charter_path).startswith(str(ROOT))
            else charter_path
        ),
        "charter_sha256": charter_file_sha256(charter_path),
        "disposition": report["verdict"]["disposition"],
        "family_id": FAMILY,
        "family_screen_attempt": True,
        "live_go": False,
        "metrics_real_grid_develop": report["real"],
        "n_null_executed": 0,
        "n_null_planned": int(report["null"]["n_null_planned"]),
        "n_null_planned_charter": int(report["null"]["n_null_planned"]),
        "null_trials_executed": 0,
        "p_max_pf_status": "not_evaluated",
        "p_n_passers_implied": 1.0 if int(report["real"]["n_passers"]) == 0 else None,
        "promote": False,
        "r1_burned": False,
        "reason": report["verdict"]["reason"],
        "recorded_at_utc": report["recorded_at_utc"],
        "screen_artifact": screen_artifact,
        "screen_only": True,
        "screen_status": report["verdict"]["screen_status"],
        "sealed_null_attempt": False,
    }
    DISPOSITION_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    with DISPOSITION_REGISTRY.open("a") as f:
        f.write(json.dumps(row, separators=(", ", ": ")) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--charter",
        type=Path,
        default=DEFAULT_CHARTER,
        help="immutable multi-instrument joint charter JSON",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT,
        help="fresh directory for joint_screen.json / null_maxstat.json",
    )
    ap.add_argument(
        "--execute-develop-screen",
        action="store_true",
        help=(
            "Dispositional: load pinned package develop frames and score. "
            "Requires sealed charter path + clean tree + cost match."
        ),
    )
    ap.add_argument(
        "--package-dir",
        type=Path,
        default=None,
        help="optional package dir (default: CURRENT via load_package_snapshot)",
    )
    ap.add_argument(
        "--frames-parquet-dir",
        type=Path,
        default=None,
        help=(
            "NON-DISPOSITIONAL synthetic frames only "
            "({XAUUSD,EURUSD,GBPUSD}.parquet). Forbidden with "
            "--write-registry or --execute-develop-screen."
        ),
    )
    ap.add_argument(
        "--write-registry",
        action="store_true",
        help=(
            "append disposition registry after dispositional develop screen only "
            "(forbidden for synthetic)"
        ),
    )
    args = ap.parse_args(argv)

    # --- mutually exclusive / fail-closed flag combinations ---
    if args.frames_parquet_dir is not None and args.execute_develop_screen:
        raise SystemExit(
            "REFUSE: --frames-parquet-dir is synthetic/non-dispositional and "
            "cannot combine with --execute-develop-screen"
        )
    if args.frames_parquet_dir is not None and args.write_registry:
        raise SystemExit(
            "REFUSE: --frames-parquet-dir is synthetic/non-dispositional and "
            "cannot combine with --write-registry (would close the real charter)"
        )
    if args.write_registry and not args.execute_develop_screen:
        raise SystemExit(
            "REFUSE: --write-registry requires --execute-develop-screen "
            "(dispositional develop screen only)"
        )

    charter_path = args.charter.resolve()
    if not charter_path.is_file():
        raise SystemExit(f"charter not found: {charter_path}")

    verrs = validate_charter_file(charter_path)
    if verrs:
        raise SystemExit("charter validation failed:\n- " + "\n- ".join(verrs))

    charter = load_charter(charter_path)
    assert_multi_instrument_charter(charter)
    pkg_id = pin_package_id(charter)
    sha = hashlib.sha256(charter_path.read_bytes()).hexdigest()

    print(
        f"joint screen harness: family={FAMILY} charter_sha={sha[:12]}… "
        f"package_id={pkg_id}",
        flush=True,
    )

    # --- dry plan ---
    if not args.execute_develop_screen and args.frames_parquet_dir is None:
        print(
            "DRY PLAN (develop screen not executed):\n"
            f"  charter={charter_path}\n"
            f"  package_id={pkg_id}\n"
            f"  out_dir={args.out_dir}\n"
            "  null_trials=never\n"
            "  dispositional path requires --execute-develop-screen "
            "(sealed charter + clean tree + cost match).\n"
            "  Synthetic offline (non-dispositional): --frames-parquet-dir DIR\n"
            "Re-run with --execute-develop-screen only after explicit authorization.",
            flush=True,
        )
        return 0

    # Freshness BEFORE any package load / score (fail-closed order).
    try:
        out_dir = ensure_fresh_artifacts(args.out_dir.resolve())
    except CharterError as e:
        raise SystemExit(str(e)) from e

    # --- synthetic non-dispositional ---
    if args.frames_parquet_dir is not None:
        write_started_marker(
            out_dir,
            charter_path=charter_path,
            package_id=pkg_id,
            mode="synthetic_non_dispositional",
        )
        frames: dict[str, pd.DataFrame] = {}
        for s in SYMBOLS:
            p = args.frames_parquet_dir / f"{s}.parquet"
            if not p.is_file():
                raise SystemExit(f"missing frame parquet: {p}")
            frames[s] = pd.read_parquet(p)
        costs = assert_costs_match_charter(charter)
        report = run_joint_screen(
            frames,
            charter,
            costs=costs,
            already_aligned=False,
            dispositional=False,
            non_dispositional_reason="frames_parquet_dir_synthetic",
        )
        report["charter_path"] = str(charter_path)
        report["charter_sha256"] = sha
        report["package_id"] = pkg_id
        report["data"] = {
            "source": "frames_parquet_dir",
            "dir": str(args.frames_parquet_dir),
            "dispositional": False,
        }
        out = write_screen_report(report, out_dir)
        print(
            f"NON_DISPOSITIONAL synthetic screen written: {out}\n"
            f"  disposition={report['verdict']['disposition']} "
            f"(must not write registry)\n"
            f"  n_passers={report['real']['n_passers']}",
            flush=True,
        )
        return 0

    # --- dispositional develop screen ---
    ok_run, why = is_charter_runnable(charter_path)
    if not ok_run:
        raise SystemExit(f"charter not runnable: {why}")
    try:
        assert_charter_path_for_sealed(charter_path)
        assert_clean_dispositional_tree()
    except CharterError as e:
        raise SystemExit(str(e)) from e

    costs = assert_costs_match_charter(charter)
    # STARTED before package load so interrupted attempts remain visible
    write_started_marker(
        out_dir,
        charter_path=charter_path,
        package_id=pkg_id,
        mode="execute_develop_screen",
    )
    frames, data_meta, data_path = load_develop_frames_from_package(
        charter, package_dir=args.package_dir
    )
    report = run_joint_screen(
        frames,
        charter,
        costs=costs,
        already_aligned=False,
        dispositional=True,
    )
    report["charter_path"] = str(charter_path)
    report["charter_sha256"] = sha
    report["package_id"] = pkg_id
    report["data"] = data_meta

    base_seed = charter_null_base_seed(charter)
    provenance = build_provenance(
        charter_path=charter_path,
        costs_path=RESEARCH_COSTS_PATH,
        data_path=data_path,
        null_seed=base_seed,
        n_null=0,
        out_dir=out_dir,
        require_clean_tree=True,
        extra={
            "family": FAMILY,
            "package_id": pkg_id,
            "attempt_type": "DETERMINISTIC_SCREEN",
            "screen_only": True,
            "n_null_planned": charter_n_null_planned(charter),
            "n_null_executed": 0,
            "costs_sha256": sha256_file(RESEARCH_COSTS_PATH),
        },
    )
    report["provenance"] = provenance

    out = write_screen_report(report, out_dir)
    print(
        f"DISPOSITIONAL develop screen written: {out}\n"
        f"  disposition={report['verdict']['disposition']} "
        f"screen_status={report['verdict']['screen_status']} "
        f"n_passers={report['real']['n_passers']} "
        f"joint_n_trades={report['real']['n_trades']}\n"
        f"  code_commit={provenance.get('code_commit')} "
        f"costs_sha256={(provenance.get('costs_sha256') or '')[:12]}…",
        flush=True,
    )

    if args.write_registry:
        rel = (
            str(out.relative_to(ROOT))
            if out.is_relative_to(ROOT)
            else str(out)
        )
        append_disposition_registry(charter_path, report, screen_artifact=rel)
        print("disposition registry: appended", flush=True)

    # Fail-closed accounting: exit 0 for both SCREEN_FAIL and pending-null pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
