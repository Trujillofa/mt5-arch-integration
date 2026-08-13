#!/usr/bin/env python3
"""Dedicated multi-instrument joint **develop screen** harness (v4 family).

Charter: ``results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v4.json``
Family: ``scripts/xau_family_joint_london_open_cosign_fade_flat.py``

This is the only authorized path for scoring multi-instrument joint charters.
Single-frame ``xau_family_null_maxstat`` / ``xau_sealed_family_cycle`` refuse them.

Default CLI mode is **dry**: validates charter + prints plan without loading package
or scoring develop. Develop screen requires explicit ``--execute-develop-screen``.

Null trials, sealed r1, holdout, paper, live: **not** implemented here.

SAFETY: offline only. No live orders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
    assert_charter_path_for_sealed,
    is_charter_runnable,
    load_charter,
    multi_instrument_single_frame_refuse_message,
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
from xau_research_costs import RESEARCH_COSTS_PATH, load_research_costs  # noqa: E402

DEFAULT_CHARTER = (
    ROOT / "results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v4.json"
)
DEFAULT_OUT = ROOT / "results/xau_runs" / f"{FAMILY}_screen"


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


def load_develop_frames_from_package(
    charter: dict[str, Any],
    *,
    package_dir: Path | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Load develop H1 for all symbols from pinned multi-instrument package.

    Does not score — caller must run ``run_joint_screen``. Prefer not to call
    until develop screen is explicitly authorized.
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
    frames = {
        s: snap.read_develop(s, holdout_start=hs) for s in SYMBOLS
    }
    # Normalize column names expected by family prepare_symbol
    for s, df in frames.items():
        if "time" not in df.columns:
            raise SystemExit(f"{s} develop frame missing time")
        # Ensure spread present
        if "spread" not in df.columns:
            raise SystemExit(
                f"{s} develop frame missing spread; refuse zero-cost default"
            )
    meta = {
        "package_id": snap.package_id,
        "package_dir": str(snap.package_dir),
        "holdout_start": str(hs) if hs is not None else None,
        "n_rows": {s: int(len(frames[s])) for s in SYMBOLS},
        "package_root": str(PACKAGE_ROOT),
    }
    return frames, meta


def run_joint_screen(
    frames: dict[str, pd.DataFrame],
    charter: dict[str, Any],
    *,
    costs: dict[str, Any] | None = None,
    already_aligned: bool = False,
) -> dict[str, Any]:
    """Score sole joint config on provided frames (synthetic or develop).

    Never runs null trials. Returns a screen report dict.
    """
    assert_multi_instrument_charter(charter)
    grid = build_grid()
    if len(grid) != 1:
        raise SystemExit(f"search_cardinality must be 1; got {len(grid)} configs")
    params = dict(grid[0])
    cost_kw = dict(costs or load_research_costs())
    # point_size is per-symbol in family meta; do not pass XAU point_size globally
    commission = float(cost_kw.get("commission_per_lot") or 0.0)
    slippage = float(cost_kw.get("slippage_points") or 0.0)
    spread_col = str(cost_kw.get("spread_col") or "spread")

    aligned = frames if already_aligned else align_joint(frames)

    result = simulate_joint(
        aligned,
        already_aligned=True,
        commission_per_lot=commission,
        slippage_points=slippage,
        spread_col=spread_col,
        **{k: params[k] for k in params if k in (
            "coincident_hours",
            "flat_hour",
            "sl_atr",
            "tp_atr",
            "risk_pct",
            "lot_max",
            "lot_min",
            "lot_step",
        )},
    )

    per_soft = {s: soft_pass_per_symbol(result.per_symbol[s]) for s in SYMBOLS}
    joint_soft = soft_pass_joint(result.joint)
    gate_ok = joint_gate_success(result)
    n_pass = n_passers_binary(result)
    zero = n_pass == 0

    if zero:
        disposition = "SCREEN_FAIL"
        screen_status = "ZERO_PRIMARY_PASSERS"
        reason = (
            "Develop joint screen: zero soft primary passers "
            "(binary joint gate). Null trials not executed; r1 unburned."
        )
    else:
        disposition = "SCREEN_PASS_PENDING_NULL_REVIEW"
        screen_status = "SCREEN_ONLY"
        reason = (
            "Develop joint screen: primary passers=1. Null trials intentionally "
            "not run; external review required before any null/sealed run."
        )

    report: dict[str, Any] = {
        "family_id": FAMILY,
        "harness": "xau_multi_instrument_joint_screen",
        "harness_kind": "multi_instrument_joint_v1",
        "screen_only": True,
        "null_trials_executed": 0,
        "n_null_planned_charter": int((charter.get("null") or {}).get("n_trials") or 0),
        "sealed_null_attempt": False,
        "r1_burned": False,
        "disposition": disposition,
        "screen_status": screen_status,
        "promote": False,
        "live_go": False,
        "n_passers": n_pass,
        "n_passers_definition": "binary_joint_gate_success",
        "per_symbol_soft_pass": per_soft,
        "joint_soft_pass": joint_soft,
        "joint_gate_success": gate_ok,
        "metrics_real_grid_develop": {
            "primary_passers": n_pass,
            "n_passers_soft": n_pass,
            "n_passers_classic": 0,  # classic not used for primary
            **_metrics_blob(result.joint),
            "joint_start_equity": JOINT_START_EQUITY,
            "n_signals_cosign": result.n_signals_cosign,
            "n_signals_entered": result.n_signals_entered,
            "n_signals_skipped_partial": result.n_signals_skipped_partial,
            "per_symbol": {s: _metrics_blob(result.per_symbol[s]) for s in SYMBOLS},
        },
        "grid": params,
        "costs": {
            "commission_per_lot": commission,
            "slippage_points": slippage,
            "spread_col": spread_col,
            "costs_source": str(RESEARCH_COSTS_PATH),
        },
        "reason": reason,
        "recorded_at_utc": datetime.now(UTC).isoformat(),
    }
    return report


def write_screen_report(report: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "joint_screen.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    # Mirror null_maxstat naming for disposition tools that look for this file
    (out_dir / "null_maxstat.json").write_text(
        json.dumps(
            {
                "screen_only": True,
                "family_id": report["family_id"],
                "real": report["metrics_real_grid_develop"],
                "n_null_executed": 0,
                "disposition": report["disposition"],
                "screen_status": report["screen_status"],
                "joint_screen": report,
            },
            indent=2,
        )
        + "\n"
    )
    return path


def append_disposition_if_requested(
    charter_path: Path,
    charter: dict[str, Any],
    report: dict[str, Any],
    *,
    screen_artifact: str,
) -> None:
    """Append disposition registry row (only when caller opts in)."""
    from xau_charter_protocol import DISPOSITION_REGISTRY, charter_file_sha256

    row = {
        "attempt_type": "DETERMINISTIC_SCREEN",
        "charter_path": str(charter_path.as_posix().replace(str(ROOT) + "/", "")),
        "charter_sha256": charter_file_sha256(charter_path),
        "disposition": report["disposition"],
        "family_id": FAMILY,
        "family_screen_attempt": True,
        "live_go": False,
        "metrics_real_grid_develop": report["metrics_real_grid_develop"],
        "n_null_executed": 0,
        "n_null_planned": int(report.get("n_null_planned_charter") or 0),
        "n_null_planned_charter": int(report.get("n_null_planned_charter") or 0),
        "null_trials_executed": 0,
        "p_max_pf_status": "not_evaluated",
        "p_n_passers_implied": 1.0 if report["n_passers"] == 0 else None,
        "promote": False,
        "r1_burned": False,
        "reason": report["reason"],
        "recorded_at_utc": report["recorded_at_utc"],
        "screen_artifact": screen_artifact,
        "screen_only": True,
        "screen_status": report["screen_status"],
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
        help="directory for joint_screen.json / null_maxstat.json",
    )
    ap.add_argument(
        "--execute-develop-screen",
        action="store_true",
        help=(
            "Load pinned package develop frames and score. "
            "Requires explicit authorization; default is dry plan only."
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
            "offline synthetic/fixture frames: directory with "
            "{XAUUSD,EURUSD,GBPUSD}.parquet (skips package load)"
        ),
    )
    ap.add_argument(
        "--write-registry",
        action="store_true",
        help="append disposition row after a successful screen evaluation",
    )
    ap.add_argument(
        "--strict-charter-path",
        action="store_true",
        help="require sealed charter path under results/xau_charters/",
    )
    args = ap.parse_args(argv)

    charter_path = args.charter.resolve()
    if not charter_path.is_file():
        raise SystemExit(f"charter not found: {charter_path}")

    verrs = validate_charter_file(charter_path)
    if verrs:
        raise SystemExit("charter validation failed:\n- " + "\n- ".join(verrs))
    ok_run, why = is_charter_runnable(charter_path)
    if not ok_run:
        raise SystemExit(f"charter not runnable: {why}")
    if args.strict_charter_path:
        try:
            assert_charter_path_for_sealed(charter_path)
        except Exception as e:
            raise SystemExit(str(e)) from e

    charter = load_charter(charter_path)
    assert_multi_instrument_charter(charter)
    pkg_id = pin_package_id(charter)
    sha = hashlib.sha256(charter_path.read_bytes()).hexdigest()

    print(
        f"joint screen harness: family={FAMILY} charter_sha={sha[:12]}… "
        f"package_id={pkg_id}",
        flush=True,
    )

    if not args.execute_develop_screen and args.frames_parquet_dir is None:
        print(
            "DRY PLAN (develop screen not executed):\n"
            f"  charter={charter_path}\n"
            f"  package_id={pkg_id}\n"
            f"  out_dir={args.out_dir}\n"
            "  null_trials=never\n"
            "Re-run with --execute-develop-screen only after explicit authorization.\n"
            "Synthetic offline score: --frames-parquet-dir DIR",
            flush=True,
        )
        return 0

    if args.frames_parquet_dir is not None:
        frames = {}
        for s in SYMBOLS:
            p = args.frames_parquet_dir / f"{s}.parquet"
            if not p.is_file():
                raise SystemExit(f"missing frame parquet: {p}")
            frames[s] = pd.read_parquet(p)
        data_meta = {"source": "frames_parquet_dir", "dir": str(args.frames_parquet_dir)}
    else:
        # Authorized develop path only
        frames, data_meta = load_develop_frames_from_package(
            charter, package_dir=args.package_dir
        )

    costs = load_research_costs()
    report = run_joint_screen(frames, charter, costs=costs, already_aligned=False)
    report["charter_path"] = str(charter_path)
    report["charter_sha256"] = sha
    report["data"] = data_meta
    report["package_id"] = pkg_id

    out = write_screen_report(report, args.out_dir)
    print(
        f"screen written: {out}\n"
        f"  disposition={report['disposition']} "
        f"screen_status={report['screen_status']} "
        f"n_passers={report['n_passers']} "
        f"joint_n_trades={report['metrics_real_grid_develop']['n_trades']}",
        flush=True,
    )

    if args.write_registry:
        append_disposition_if_requested(
            charter_path,
            charter,
            report,
            screen_artifact=str(out.relative_to(ROOT))
            if out.is_relative_to(ROOT)
            else str(out),
        )
        print("disposition registry: appended", flush=True)

    return 0 if report["disposition"] != "SCREEN_FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
