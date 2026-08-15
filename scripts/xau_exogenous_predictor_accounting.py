#!/usr/bin/env python3
"""Dual SCREEN_STARTED / NULL_STARTED accounting for exogenous-predictor v1.

Implements §8 of MULTI-INSTRUMENT-EXOGENOUS-PREDICTOR-PROTOCOL-V1.md.

* SCREEN_STARTED before package load / real score — failures do **not** burn r1
* NULL_STARTED after positive screen + donor preflight — **consumes** sealed-null r1
  immediately (``r1_burned=true`` on the marker); existence of NULL_STARTED is
  authoritative for burn inference even if a contradictory terminal appears
* At most **one** terminal report per out-dir (cross-filename exclusivity)
* Null success requires NULL_STARTED, matching family_id, and
  ``n_null_executed == n_null_planned``
* Reserved accounting fields cannot be overridden by caller ``extra``

SAFETY: offline research only. No registry write helpers for real charters here
(Phase C / dispositional harness). Synthetic tests use these pure I/O helpers.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCREEN_STARTED_NAME = "SCREEN_STARTED.json"
NULL_STARTED_NAME = "NULL_STARTED.json"
FAILED_UNKNOWN_NAME = "FAILED_RUN_UNKNOWN.json"
NULL_SUCCESS_NAME = "null_success.json"
TRIALS_EVIDENCE_NAME = "null_trials_evidence.json"

# One terminal report only (protocol §8.3: single terminal disposition).
_TERMINAL_NAMES = frozenset({FAILED_UNKNOWN_NAME, NULL_SUCCESS_NAME})
MIN_NULL_TRIALS_SUCCESS = 999

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
        "n_null_planned",
        "m",
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
        "n_null_executed",
        "n_null_planned",
        "family_id",
        "finished_at_utc",
    }
)


class AccountingError(RuntimeError):
    """Hard fail-closed accounting contract violation."""


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


def _existing_terminals(out_dir: Path) -> list[str]:
    return sorted(name for name in _TERMINAL_NAMES if (out_dir / name).is_file())


def _refuse_if_terminal_exists(out_dir: Path) -> None:
    existing = _existing_terminals(out_dir)
    if existing:
        raise FileExistsError(
            f"refuse second terminal report in {out_dir}: already have {existing} "
            "(protocol: one terminal report)"
        )


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
    # Monotonic: no markers after a terminal disposition already exists.
    _refuse_if_terminal_exists(out_dir)
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
    m: int,
    n_null_planned: int,
    charter_path: str | None = None,
    package_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """§8.2 step 2 — after positive screen + successful donor preflight.

    Writing NULL_STARTED **consumes** the sealed-null r1 attempt:
    ``r1_burned=true`` on the marker itself. Existence of this file is
    authoritative for burn inference (§8.3).

    ``m`` (event count) and ``n_null_planned`` are **mandatory** and become
    the sole authority for success-terminal T=M / N checks.

    Refuses if any terminal already exists (no reverse ordering).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _refuse_if_terminal_exists(out_dir)
    if isinstance(m, bool) or not isinstance(m, int) or m < 1:
        raise AccountingError("m must be a non-bool int >= 1 (armed event count)")
    if isinstance(n_null_planned, bool) or not isinstance(n_null_planned, int):
        raise AccountingError("n_null_planned must be a non-bool int")
    if n_null_planned < MIN_NULL_TRIALS_SUCCESS:
        raise AccountingError(
            f"n_null_planned={n_null_planned} < {MIN_NULL_TRIALS_SUCCESS}"
        )
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
    """Terminal FAILED_RUN_UNKNOWN (write-once, exclusive); r1_burned per §8."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _refuse_if_terminal_exists(out_dir)
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


def _trial_attr(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _require_finite_number(name: str, raw: Any) -> float:
    try:
        v = float(raw)
    except (TypeError, ValueError) as e:
        raise AccountingError(f"{name} not numeric: {raw!r}") from e
    if not math.isfinite(v):
        raise AccountingError(f"{name} must be finite (got {raw!r})")
    return v


def _validate_assignment_geometry(
    assignment: list[int],
    *,
    m: int,
    h: int,
    trial_j: int,
) -> None:
    """Unique donors, length M, pairwise non-segment-overlapping H-windows."""
    if len(assignment) != m:
        raise AccountingError(
            f"trials[{trial_j}].assignment length {len(assignment)} != m={m}"
        )
    if len(assignment) != len(set(assignment)):
        raise AccountingError(
            f"trials[{trial_j}].assignment has duplicate donor ids: {assignment}"
        )
    for a in range(m):
        for b in range(a + 1, m):
            i, j = assignment[a], assignment[b]
            # segment overlap: not (i+h-1 < j or j+h-1 < i)
            if not (i + h - 1 < j or j + h - 1 < i):
                raise AccountingError(
                    f"trials[{trial_j}].assignment donors {i} and {j} "
                    f"segment-overlap under H={h}"
                )


def validate_null_trial_evidence(
    trials: Any,
    *,
    planned: int,
    m: int,
    h: int = 3,
) -> list[dict[str, Any]]:
    """Fail-closed validation of actual trial results (not a bare id list).

    Accepts ``NullTrialResult`` objects or dict rows with keys:
    trial_id, assignment, trades (or n_trades + trade_pnls), metrics optional.

    ``m`` is the armed event count from NULL_STARTED — authoritative; callers
    cannot override it.
    """
    if isinstance(m, bool) or not isinstance(m, int) or m < 1:
        raise AccountingError(f"m must be non-bool int >= 1 (got {m!r})")
    if not isinstance(trials, (list, tuple)):
        raise AccountingError("trials must be a list/tuple of trial results")
    if len(trials) != planned:
        raise AccountingError(
            f"len(trials)={len(trials)} must equal n_null_planned={planned}"
        )
    evidence: list[dict[str, Any]] = []
    for j, tr in enumerate(trials):
        tid = _trial_attr(tr, "trial_id")
        if isinstance(tid, bool) or not isinstance(tid, int) or tid != j:
            raise AccountingError(
                f"trials[{j}].trial_id must equal {j} (got {tid!r})"
            )
        assignment_raw = _trial_attr(tr, "assignment")
        if not isinstance(assignment_raw, (list, tuple)) or not assignment_raw:
            raise AccountingError(f"trials[{j}].assignment required non-empty list")
        if any(
            isinstance(x, bool) or not isinstance(x, int) for x in assignment_raw
        ):
            raise AccountingError(f"trials[{j}].assignment must be non-bool ints")
        assignment = [int(x) for x in assignment_raw]
        _validate_assignment_geometry(assignment, m=m, h=h, trial_j=j)
        trades = _trial_attr(tr, "trades")
        trade_pnls = _trial_attr(tr, "trade_pnls")
        metrics = _trial_attr(tr, "metrics") or {}
        pnls: list[float] = []
        if trades is not None:
            if not isinstance(trades, (list, tuple)):
                raise AccountingError(f"trials[{j}].trades must be a list")
            for t in trades:
                if isinstance(t, dict):
                    raw_pnl = t.get("pnl")
                elif isinstance(t, (int, float)) and not isinstance(t, bool):
                    raw_pnl = t
                else:
                    raw_pnl = getattr(t, "pnl", None)
                pnls.append(_require_finite_number(f"trials[{j}].pnl", raw_pnl))
        elif isinstance(trade_pnls, (list, tuple)):
            for k, pnl in enumerate(trade_pnls):
                pnls.append(
                    _require_finite_number(f"trials[{j}].trade_pnls[{k}]", pnl)
                )
        else:
            raise AccountingError(
                f"trials[{j}] must include trades or trade_pnls evidence"
            )
        n_trades = len(pnls)
        if n_trades != m:
            raise AccountingError(f"trials[{j}]: T={n_trades} != m={m} (armed M)")
        if n_trades != len(assignment):
            raise AccountingError(
                f"trials[{j}]: T={n_trades} != len(assignment)={len(assignment)}"
            )
        m_metric = metrics.get("n_trades") if isinstance(metrics, dict) else None
        if m_metric is not None and int(m_metric) != n_trades:
            raise AccountingError(
                f"trials[{j}]: metrics.n_trades={m_metric} != len(trades)={n_trades}"
            )
        if isinstance(metrics, dict):
            for mk in ("net_profit", "profit_factor", "max_drawdown_pct"):
                if mk in metrics:
                    _require_finite_number(
                        f"trials[{j}].metrics.{mk}", metrics[mk]
                    )
        evidence.append(
            {
                "trial_id": tid,
                "assignment": assignment,
                "n_trades": n_trades,
                "trade_pnls": pnls,
                "net_profit": float(sum(pnls)),
            }
        )
    if [e["trial_id"] for e in evidence] != list(range(planned)):
        raise AccountingError("trial_id sequence must be exactly range(N)")
    return evidence


def write_null_success(
    out_dir: Path,
    *,
    family_id: str,
    trials: list[Any] | tuple[Any, ...],
    h: int = 3,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Successful sealed null terminal (write-once, exclusive).

    Requires:
    * NULL_STARTED present with mandatory m and n_null_planned
    * family_id matches
    * n_null_planned = N ≥ 999
    * ``m`` from NULL_STARTED is authoritative (no caller override)
    * ``trials`` has real trade evidence, T=m, finite pnls, valid assignments
    * persists ``null_trials_evidence.json`` with allow_nan=False
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _refuse_if_terminal_exists(out_dir)
    started_path = out_dir / NULL_STARTED_NAME
    if not started_path.is_file():
        raise AccountingError(
            "null_success requires NULL_STARTED.json (null never armed)"
        )
    started = load_json(started_path)
    if started.get("family_id") != family_id:
        raise AccountingError(
            f"null_success family_id={family_id!r} does not match "
            f"NULL_STARTED.family_id={started.get('family_id')!r}"
        )
    planned = started.get("n_null_planned")
    if isinstance(planned, bool) or not isinstance(planned, int):
        raise AccountingError(
            "NULL_STARTED.n_null_planned must be a non-bool int for success terminal"
        )
    if planned < MIN_NULL_TRIALS_SUCCESS:
        raise AccountingError(
            f"NULL_STARTED.n_null_planned={planned} < {MIN_NULL_TRIALS_SUCCESS} "
            "(exogenous N floor; refuse certifying under-planned null)"
        )
    m_started = started.get("m")
    if isinstance(m_started, bool) or not isinstance(m_started, int) or m_started < 1:
        raise AccountingError(
            "NULL_STARTED.m must be a non-bool int >= 1 (armed event count)"
        )
    evidence = validate_null_trial_evidence(
        trials, planned=planned, m=m_started, h=h
    )
    # Persist auditable evidence before success terminal (write-once, no NaN/Inf).
    ev_path = out_dir / TRIALS_EVIDENCE_NAME
    if ev_path.exists():
        raise FileExistsError(f"refuse overwrite existing trials evidence: {ev_path}")
    try:
        ev_path.write_text(
            json.dumps(evidence, indent=2, allow_nan=False) + "\n"
        )
    except (ValueError, OverflowError) as e:
        raise AccountingError(
            f"trials evidence not JSON-serializable without NaN/Inf: {e}"
        ) from e

    path = out_dir / NULL_SUCCESS_NAME
    base: dict[str, Any] = {
        "disposition": "NULL_COMPLETE",
        "execution_state": "SUCCESS",
        "r1_burned": True,
        "sealed_null_attempt": True,
        "n_null_executed": planned,
        "n_null_planned": planned,
        "m": m_started,
        "trials_evidence": TRIALS_EVIDENCE_NAME,
        "trial_ids_ok": True,
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
    """After NULL_STARTED: burned UNKNOWN (write-once exclusive; reserved locked)."""
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
