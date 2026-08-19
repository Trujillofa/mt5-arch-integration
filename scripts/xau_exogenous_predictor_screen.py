#!/usr/bin/env python3
"""Dedicated develop-screen runner for multi_instrument_exogenous_predictor_v1.

Phase E: one explicit ``--run`` against the pinned multi-instrument develop
package. Does not execute the sealed null.

SAFETY
- Holdout is refused (server_time < holdout_start only).
- Real package load happens only under ``--run`` (dispositional path).
- Synthetic callers pass ``frames=`` and ``dispositional=False`` (tests).
- No MT5 / Wine / orders.
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
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import xau_exogenous_predictor_accounting as acct  # noqa: E402
import xau_family_exog_london_fx_cosign_xau_follow_flat as fam  # noqa: E402
from xau_charter_protocol import gates_from_charter  # noqa: E402
from xau_exogenous_predictor_core import HARNESS_KIND, ProtocolError  # noqa: E402

DEFAULT_CHARTER = fam.DEFAULT_CHARTER_PATH
FAMILY_ID = fam.FAMILY_ID
SYMBOLS = fam.SYMBOLS


class ScreenError(RuntimeError):
    """Fail-closed screen-runner contract violation."""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def charter_holdout_start(charter: dict[str, Any]) -> pd.Timestamp:
    win = charter.get("window") or {}
    raw = win.get("holdout_start_server") or win.get("holdout_start")
    if not raw:
        pkg = (charter.get("instrument") or {}).get("data_package") or {}
        raw = pkg.get("holdout_start_server")
    if not raw:
        raise ScreenError("charter window.holdout_start_server required")
    ts = pd.Timestamp(raw)
    if getattr(ts, "tzinfo", None) is not None or getattr(ts, "tz", None) is not None:
        raise ScreenError("holdout_start must be timezone-naive server_clock_as_stored")
    return ts


def pin_package_id(charter: dict[str, Any]) -> str:
    pkg = (charter.get("instrument") or {}).get("data_package") or {}
    pid = str(pkg.get("package_id") or pkg.get("content_package_id") or "")
    if not pid:
        raise ScreenError("charter instrument.data_package.package_id required")
    return pid


def default_artifact_dir(*, run_date: str | None = None) -> Path:
    day = run_date or datetime.now(UTC).date().isoformat()
    return ROOT / "results" / "xau_runs" / f"{day}_{FAMILY_ID}_screen_r1"


def assert_frames_strictly_before_holdout(
    frames: dict[str, pd.DataFrame],
    holdout_start: pd.Timestamp,
) -> None:
    """Refuse any bar at/after holdout_start (develop window only)."""
    for sym, df in frames.items():
        if "time" not in df.columns:
            raise ScreenError(f"{sym}: frame missing time column")
        t = pd.to_datetime(df["time"])
        if getattr(t.dtype, "tz", None) is not None:
            raise ScreenError(
                f"{sym}: time must be timezone-naive server_clock_as_stored"
            )
        if len(t) == 0:
            raise ScreenError(f"{sym}: empty develop frame")
        if bool((t >= holdout_start).any()):
            raise ScreenError(
                f"HOLDOUT_OVERLAP: {sym} contains bars at/after holdout_start="
                f"{holdout_start} — refuse develop screen"
            )
        if t.max() >= holdout_start:
            raise ScreenError(
                f"HOLDOUT_OVERLAP: {sym} max(time)={t.max()} >= holdout_start="
                f"{holdout_start}"
            )


def load_develop_frames_from_package(
    charter: dict[str, Any],
    *,
    package_dir: Path | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Load develop H1 via existing snapshot loader; refuse holdout overlap."""
    from build_multi_instrument_data_readiness import (  # noqa: WPS433
        load_package_snapshot,
    )

    expected_id = pin_package_id(charter)
    snap = (
        load_package_snapshot(validate=True)
        if package_dir is None
        else load_package_snapshot(package_dir, validate=True)
    )
    if snap.package_id != expected_id:
        raise ScreenError(
            f"package_id mismatch: snapshot={snap.package_id!r} "
            f"charter={expected_id!r}"
        )
    holdout = charter_holdout_start(charter)
    frames = {
        s: snap.read_develop(s, holdout_start=holdout) for s in SYMBOLS
    }
    for s, df in frames.items():
        if "spread" not in df.columns:
            raise ScreenError(
                f"{s}: develop frame missing spread; refuse zero-cost default"
            )
    assert_frames_strictly_before_holdout(frames, holdout)

    # Package file sha map from charter pin (published) + live content id
    pkg_block = (charter.get("instrument") or {}).get("data_package") or {}
    sha_map = dict(pkg_block.get("sha256") or {})
    meta = {
        "package_id": snap.package_id,
        "content_package_id": pkg_block.get("content_package_id"),
        "package_dir": str(snap.package_dir),
        "holdout_start_server": str(holdout),
        "n_rows": {s: int(len(frames[s])) for s in SYMBOLS},
        "charter_file_sha256_map": sha_map,
    }
    return frames, meta


def verify_gates_carry_stratified(charter: dict[str, Any]) -> dict[str, Any]:
    resolved = gates_from_charter(charter)
    sr = resolved.get("stratified_required")
    if not isinstance(sr, dict) or not sr:
        raise ScreenError(
            "gates_from_charter must carry stratified_required "
            "(Phase B enforcement / PR #25)"
        )
    return resolved


def write_screen_artifact(
    out_dir: Path,
    *,
    charter: dict[str, Any],
    charter_path: Path,
    report: dict[str, Any],
    dry_plan: dict[str, Any],
    package_meta: dict[str, Any] | None,
    gates_resolved: dict[str, Any],
    dispositional: bool,
) -> dict[str, Path]:
    """Write report + provenance. SCREEN_STARTED already written when dispositional."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    charter_sha = _sha256_file(charter_path)
    (out_dir / "charter.sha256").write_text(charter_sha + "\n")
    written["charter.sha256"] = out_dir / "charter.sha256"

    plan_path = out_dir / "dry_plan.json"
    plan_path.write_text(json.dumps(dry_plan, indent=2, sort_keys=True) + "\n")
    written["dry_plan.json"] = plan_path

    gates_path = out_dir / "gates_resolved.json"
    gates_path.write_text(json.dumps(gates_resolved, indent=2, sort_keys=True) + "\n")
    written["gates_resolved.json"] = gates_path

    if package_meta is not None:
        pkg_path = out_dir / "package_meta.json"
        pkg_path.write_text(json.dumps(package_meta, indent=2, sort_keys=True) + "\n")
        written["package_meta.json"] = pkg_path

    body = {
        "family_id": FAMILY_ID,
        "charter_path": str(charter_path),
        "charter_sha256": charter_sha,
        "charter_version": charter.get("charter_version"),
        "dispositional": bool(dispositional),
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "report": report,
        "package": package_meta,
    }
    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    written["report.json"] = report_path
    return written


def run_screen(
    *,
    charter_path: Path | None = None,
    frames: dict[str, pd.DataFrame] | None = None,
    out_dir: Path | None = None,
    package_dir: Path | None = None,
    dispositional: bool = False,
    allow_existing_out_dir: bool = False,
) -> dict[str, Any]:
    """Execute family screen into ``out_dir``.

    dispositional=True: real develop package path; writes SCREEN_STARTED.
    dispositional=False: synthetic frames required; no package load.
    """
    cpath = Path(charter_path) if charter_path is not None else DEFAULT_CHARTER
    charter = fam.load_charter(cpath)
    if charter.get("family_id") != FAMILY_ID:
        raise ScreenError(
            f"REFUSE_WRONG_FAMILY: {charter.get('family_id')!r} != {FAMILY_ID!r}"
        )
    harness = (charter.get("harness") or {}).get("kind")
    if harness != HARNESS_KIND:
        raise ScreenError(
            f"REFUSE_WRONG_HARNESS: harness.kind={harness!r} != {HARNESS_KIND!r}"
        )

    gates_resolved = verify_gates_carry_stratified(charter)
    dry = fam.dry_plan(cpath)
    out = Path(out_dir) if out_dir is not None else default_artifact_dir()

    if out.exists() and any(out.iterdir()) and not allow_existing_out_dir:
        raise ScreenError(f"refuse overwrite existing screen artifact dir: {out}")

    package_meta: dict[str, Any] | None = None
    if dispositional:
        if frames is not None:
            raise ScreenError(
                "dispositional screen must load the package itself "
                "(do not pass frames=)"
            )
        # SCREEN_STARTED before package load (protocol §8.1)
        out.mkdir(parents=True, exist_ok=True)
        acct.write_screen_started(
            out,
            family_id=FAMILY_ID,
            charter_path=str(cpath),
            package_id=pin_package_id(charter),
        )
        frames, package_meta = load_develop_frames_from_package(
            charter, package_dir=package_dir
        )
    else:
        if frames is None:
            raise ScreenError("synthetic screen requires frames=")
        holdout = charter_holdout_start(charter)
        assert_frames_strictly_before_holdout(frames, holdout)
        out.mkdir(parents=True, exist_ok=True)

    result = fam.run_family(frames, charter=charter)
    if result.stratified is None:
        raise ScreenError("stratified evaluation absent after run_family")
    report = fam.report_dict(result)
    # Fail closed: disposition / null_armed must match stratified resolution
    if "disposition" not in report or "null_armed" not in report:
        raise ScreenError("report_dict missing disposition/null_armed")
    if "strata" not in report or "pooled" not in report:
        raise ScreenError("report_dict missing pooled/strata metrics")

    written = write_screen_artifact(
        out,
        charter=charter,
        charter_path=cpath,
        report=report,
        dry_plan=dry,
        package_meta=package_meta,
        gates_resolved=gates_resolved,
        dispositional=dispositional,
    )
    return {
        "out_dir": str(out),
        "report": report,
        "written": {k: str(v) for k, v in written.items()},
        "dispositional": dispositional,
        "charter_sha256": _sha256_file(cpath),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--charter",
        default=str(DEFAULT_CHARTER),
        help="path to frozen exogenous charter (default: v4)",
    )
    ap.add_argument(
        "--out-dir",
        default=None,
        help="artifact directory (default: results/xau_runs/<date>_…_screen_r1)",
    )
    ap.add_argument(
        "--package-dir",
        default=None,
        help="optional explicit package dir (default: CURRENT snapshot)",
    )
    ap.add_argument(
        "--run",
        action="store_true",
        help="REQUIRED to load the develop package and write the r1 screen artifact",
    )
    ap.add_argument(
        "--dry-plan",
        action="store_true",
        help="print dry plan only (default when --run is absent)",
    )
    args = ap.parse_args(argv)

    cpath = Path(args.charter)
    charter = fam.load_charter(cpath)
    harness = (charter.get("harness") or {}).get("kind")
    if harness != HARNESS_KIND:
        raise SystemExit(
            f"REFUSE_WRONG_HARNESS: harness.kind={harness!r} != {HARNESS_KIND!r}"
        )

    if not args.run:
        plan = fam.dry_plan(cpath)
        plan["note"] = "dry only — pass --run to execute develop screen (burns screen r1 accounting marker)"
        plan["default_out_dir"] = str(default_artifact_dir())
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    out = Path(args.out_dir) if args.out_dir else default_artifact_dir()
    pkg = Path(args.package_dir) if args.package_dir else None
    result = run_screen(
        charter_path=cpath,
        out_dir=out,
        package_dir=pkg,
        dispositional=True,
    )
    print(json.dumps(
        {
            "out_dir": result["out_dir"],
            "disposition": result["report"]["disposition"],
            "null_armed": result["report"]["null_armed"],
            "r1_burned": result["report"]["r1_burned"],
            "soft_passers": result["report"]["soft_passers"],
            "pooled": result["report"]["pooled"],
            "strata": result["report"]["strata"],
            "charter_sha256": result["charter_sha256"],
        },
        indent=2,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ScreenError, ProtocolError, fam.ProtocolError, FileExistsError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(2) from e
