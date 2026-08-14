#!/usr/bin/env python3
"""Dual SCREEN_STARTED / NULL_STARTED accounting for exogenous-predictor v1.

Implements §8 of MULTI-INSTRUMENT-EXOGENOUS-PREDICTOR-PROTOCOL-V1.md.

* SCREEN_STARTED before package load / real score — failures do **not** burn r1
* NULL_STARTED after positive screen + donor preflight — **arms** sealed-null r1;
  any incomplete attempt with only NULL_STARTED present is treated as burned
* Reserved accounting fields cannot be overridden by caller ``extra``

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
NULL_SUCCESS_NAME = "null_success.json"

# Callers may attach diagnostics via ``extra`` but must never override these.
_RESERVED_SCREEN_STARTED = frozenset(
    {
        "execution_state",
        "r1_burned",
        "r1_burn_armed",
        "sealed_null_attempt",
        "arms_r1_burn_on_failure",
        "family_id",
        "started_at_utc",
    }
)
_RESERVED_NULL_STARTED = frozenset(
    {
        "execution_state",
        "r1_burned",
        "r1_burn_armed",
        "sealed_null_attempt",
        "arms_r1_burn_on_failure",
        "family_id",
        "started_at_utc",
    }
)
_RESERVED_FAILED = frozenset(
    {
        "disposition",
        "execution_state",
        "r1_burned",
        "sealed_null_attempt",
        "n_null_executed",
        "reason",
        "finished_at_utc",
    }
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _merge_extra(base: dict[str, Any], extra: dict[str, Any] | None, reserved: frozenset[str]) -> dict[str, Any]:
    """Apply extra first, then force reserved base keys (base wins)."""
    out: dict[str, Any] = {}
    if extra:
        for k, v in extra.items():
            if k in reserved:
                continue
            out[k] = v
    out.update(base)
    return out


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
    base: dict[str, Any] = {
        "execution_state": "SCREEN_STARTED",
        "r1_burned": False,
        "r1_burn_armed": False,
        "sealed_null_attempt": False,
        "arms_r1_burn_on_failure": False,
        "family_id": family_id,
        "charter_path": charter_path,
        "package_id": package_id,
        "started_at_utc": _utc_now(),
    }
    body = _merge_extra(base, extra, _RESERVED_SCREEN_STARTED)
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
    """§8.2 step 2 — after positive screen + successful donor preflight.

    Arms the sealed-null r1 burn boundary. ``r1_burned`` stays false until a
    terminal success or FAILED_RUN_UNKNOWN is written, but
    ``r1_burn_armed=true`` / ``arms_r1_burn_on_failure=true`` mean any crash
    with only this marker present **must** be treated as burned (§8.3).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / NULL_STARTED_NAME
    if path.exists():
        raise FileExistsError(f"refuse overwrite existing NULL_STARTED: {path}")
    base: dict[str, Any] = {
        "execution_state": "NULL_STARTED",
        # Terminal burn flag is false until success/fail terminal; armed is true.
        "r1_burned": False,
        "r1_burn_armed": True,
        "sealed_null_attempt": True,
        "arms_r1_burn_on_failure": True,
        "family_id": family_id,
        "charter_path": charter_path,
        "package_id": package_id,
        "m": m,
        "n_null_planned": n_null_planned,
        "started_at_utc": _utc_now(),
    }
    body = _merge_extra(base, extra, _RESERVED_NULL_STARTED)
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
    base: dict[str, Any] = {
        "disposition": "FAILED_RUN_UNKNOWN",
        "execution_state": "UNKNOWN",
        "r1_burned": bool(r1_burned),
        "sealed_null_attempt": bool(sealed_null_attempt),
        "n_null_executed": None,
        "reason": reason,
        "family_id": family_id,
        "finished_at_utc": _utc_now(),
    }
    body = _merge_extra(base, extra, _RESERVED_FAILED)
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
    """After NULL_STARTED: burned UNKNOWN (reserved fields not overrideable)."""
    return write_failed_run_unknown(
        out_dir,
        r1_burned=True,
        sealed_null_attempt=True,
        reason=reason,
        family_id=family_id,
        extra=extra,
    )


def infer_r1_burned_from_outdir(out_dir: Path) -> bool:
    """Fail-closed accounting when a process dies after arming.

    * NULL_STARTED present and no successful null terminal → burned
    * FAILED_RUN_UNKNOWN with r1_burned true → burned
    * SCREEN_STARTED only → not burned
    """
    out_dir = Path(out_dir)
    fail = out_dir / FAILED_UNKNOWN_NAME
    if fail.is_file():
        body = load_json(fail)
        return bool(body.get("r1_burned"))
    success = out_dir / NULL_SUCCESS_NAME
    if success.is_file():
        body = load_json(success)
        return bool(body.get("r1_burned", True))
    # Marker-only crash after arming: conservative burn
    return (out_dir / NULL_STARTED_NAME).is_file()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())
