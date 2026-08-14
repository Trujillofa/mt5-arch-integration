#!/usr/bin/env python3
"""Dual SCREEN_STARTED / NULL_STARTED accounting for exogenous-predictor v1.

Implements §8 of MULTI-INSTRUMENT-EXOGENOUS-PREDICTOR-PROTOCOL-V1.md.

* SCREEN_STARTED before package load / real score — failures do **not** burn r1
* NULL_STARTED after positive screen + donor preflight — failures **burn** r1

SAFETY: offline research only. No registry write helpers for real charters here
(Phase C / dispositional harness). Synthetic tests use these pure I/O helpers.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCREEN_STARTED_NAME = "SCREEN_STARTED.json"
NULL_STARTED_NAME = "NULL_STARTED.json"
FAILED_UNKNOWN_NAME = "FAILED_RUN_UNKNOWN.json"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def write_screen_started(
    out_dir: Path,
    *,
    family_id: str,
    charter_path: str | None = None,
    package_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """§8.1 step 3 — write before package load / real score."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / SCREEN_STARTED_NAME
    if path.exists():
        raise FileExistsError(f"refuse overwrite existing SCREEN_STARTED: {path}")
    body: dict[str, Any] = {
        "execution_state": "SCREEN_STARTED",
        "r1_burned": False,
        "sealed_null_attempt": False,
        "family_id": family_id,
        "charter_path": charter_path,
        "package_id": package_id,
        "started_at_utc": _utc_now(),
    }
    if extra:
        body.update(extra)
    path.write_text(json.dumps(body, indent=2) + "\n")
    return path


def write_null_started(
    out_dir: Path,
    *,
    family_id: str,
    charter_path: str | None = None,
    package_id: str | None = None,
    m: int | None = None,
    n_null_planned: int | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """§8.2 step 2 — after positive screen + successful donor preflight."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / NULL_STARTED_NAME
    if path.exists():
        raise FileExistsError(f"refuse overwrite existing NULL_STARTED: {path}")
    body: dict[str, Any] = {
        "execution_state": "NULL_STARTED",
        "r1_burned": False,  # terminal success/fail sets final burn
        "sealed_null_attempt": True,
        "arms_r1_burn_on_failure": True,
        "family_id": family_id,
        "charter_path": charter_path,
        "package_id": package_id,
        "m": m,
        "n_null_planned": n_null_planned,
        "started_at_utc": _utc_now(),
    }
    if extra:
        body.update(extra)
    path.write_text(json.dumps(body, indent=2) + "\n")
    return path


def write_failed_run_unknown(
    out_dir: Path,
    *,
    r1_burned: bool,
    sealed_null_attempt: bool,
    reason: str,
    family_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Terminal FAILED_RUN_UNKNOWN; r1_burned per §8.1 vs §8.3."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / FAILED_UNKNOWN_NAME
    body: dict[str, Any] = {
        "disposition": "FAILED_RUN_UNKNOWN",
        "execution_state": "UNKNOWN",
        "r1_burned": bool(r1_burned),
        "sealed_null_attempt": bool(sealed_null_attempt),
        "n_null_executed": None,
        "reason": reason,
        "family_id": family_id,
        "finished_at_utc": _utc_now(),
    }
    if extra:
        body.update(extra)
    path.write_text(json.dumps(body, indent=2) + "\n")
    return path


def screen_phase_failure_report(
    out_dir: Path,
    *,
    reason: str,
    family_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """After SCREEN_STARTED, before NULL_STARTED: visible, r1_burned=false."""
    return write_failed_run_unknown(
        out_dir,
        r1_burned=False,
        sealed_null_attempt=False,
        reason=reason,
        family_id=family_id,
        extra=extra,
    )


def null_phase_failure_report(
    out_dir: Path,
    *,
    reason: str,
    family_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """After NULL_STARTED: burned UNKNOWN."""
    return write_failed_run_unknown(
        out_dir,
        r1_burned=True,
        sealed_null_attempt=True,
        reason=reason,
        family_id=family_id,
        extra=extra,
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())
