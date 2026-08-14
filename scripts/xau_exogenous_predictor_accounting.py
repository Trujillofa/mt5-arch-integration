#!/usr/bin/env python3
"""Dual SCREEN_STARTED / NULL_STARTED accounting for exogenous-predictor v1.

Implements §8 of MULTI-INSTRUMENT-EXOGENOUS-PREDICTOR-PROTOCOL-V1.md.

* SCREEN_STARTED before package load / real score — failures do **not** burn r1
* NULL_STARTED after positive screen + donor preflight — **consumes** sealed-null r1
  immediately (``r1_burned=true`` on the marker); existence of NULL_STARTED is
  authoritative for burn inference even if a contradictory terminal appears
* Terminal reports are **write-once** (refuse overwrite)
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
_RESERVED_SUCCESS = frozenset(
    {
        "disposition",
        "execution_state",
        "r1_burned",
        "sealed_null_attempt",
        "finished_at_utc",
    }
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _merge_extra(
    base: dict[str, Any], extra: dict[str, Any] | None, reserved: frozenset[str]
) -> dict[str, Any]:
    """Apply extra first, then force reserved base keys (base wins)."""
    out: dict[str, Any] = {}
    if extra:
        for k, v in extra.items():
            if k in reserved:
                continue
            out[k] = v
    out.update(base)
    return out


def _write_once(path: Path, body: dict[str, Any]) -> Path:
    if path.exists():
        raise FileExistsError(f"refuse overwrite existing terminal/marker: {path}")
    path.write_text(json.dumps(body, indent=2) + "\n")
    return path


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
    return _write_once(path, body)


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

    Writing NULL_STARTED **consumes** the sealed-null r1 attempt:
    ``r1_burned=true`` on the marker itself. Existence of this file is
    authoritative for burn inference (§8.3).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / NULL_STARTED_NAME
    base: dict[str, Any] = {
        "execution_state": "NULL_STARTED",
        "r1_burned": True,
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
    return _write_once(path, body)


def write_failed_run_unknown(
    out_dir: Path,
    *,
    r1_burned: bool,
    sealed_null_attempt: bool,
    reason: str,
    family_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Terminal FAILED_RUN_UNKNOWN (write-once); r1_burned per §8.1 vs §8.3."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / FAILED_UNKNOWN_NAME
    # If null was armed, force burned regardless of caller args.
    if (out_dir / NULL_STARTED_NAME).is_file():
        r1_burned = True
        sealed_null_attempt = True
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
    return _write_once(path, body)


def write_null_success(
    out_dir: Path,
    *,
    family_id: str | None = None,
    n_null_executed: int | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Successful sealed null terminal (write-once); r1 remains burned."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / NULL_SUCCESS_NAME
    base: dict[str, Any] = {
        "disposition": "NULL_COMPLETE",
        "execution_state": "SUCCESS",
        "r1_burned": True,
        "sealed_null_attempt": True,
        "n_null_executed": n_null_executed,
        "family_id": family_id,
        "finished_at_utc": _utc_now(),
    }
    body = _merge_extra(base, extra, _RESERVED_SUCCESS)
    return _write_once(path, body)


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
    """After NULL_STARTED: burned UNKNOWN (write-once; reserved fields locked)."""
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

    **NULL_STARTED is authoritative:** if present, always burned — even when a
    contradictory terminal claims ``r1_burned=false`` (should not be writable
    after arming; defense in depth).
    """
    out_dir = Path(out_dir)
    if (out_dir / NULL_STARTED_NAME).is_file():
        return True
    fail = out_dir / FAILED_UNKNOWN_NAME
    if fail.is_file():
        body = load_json(fail)
        return bool(body.get("r1_burned"))
    success = out_dir / NULL_SUCCESS_NAME
    if success.is_file():
        body = load_json(success)
        return bool(body.get("r1_burned", True))
    return False


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())
