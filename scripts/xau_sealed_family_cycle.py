#!/usr/bin/env python3
"""Sealed family research cycle (protocol v2.1).

1. Validate frozen charter (immutable path).
2. Enforce family_id / null / costs equality with CLI.
3. Run synthetic fixtures (blocking — family smoke must pass).
4. One-shot: develop grid + null on real develop window.
5. Append program-level attempt ledger.
6. Refuse overwrite of run directory.

Usage::

  python3 scripts/xau_sealed_family_cycle.py \\
    --charter results/xau_charters/2026-08-10_server_hour_window_flat_v1.json \\
    --family server_hour_window_flat \\
    --run-id r1

SAFETY: offline only. No --live.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from xau_charter_protocol import (  # noqa: E402
    DEFAULT_NULL_BASE_SEED,
    CharterError,
    append_attempt,
    assert_charter_path_for_sealed,
    assert_clean_dispositional_tree,
    build_provenance,
    count_attempts,
    ensure_fresh_run_dir,
    is_charter_runnable,
    load_charter,
    multi_instrument_single_frame_refuse_message,
    null_spec_from_charter,
    run_output_dir,
    validate_charter_file,
)
from xau_research_costs import RESEARCH_COSTS_PATH, load_research_costs  # noqa: E402

from backtest import CSV_PATH  # noqa: E402

# Sealed full-null dispositions that may appear on an OK path (not SCREEN_FAIL).
_KNOWN_SEALED_NULL_DISPOSITIONS = frozenset(
    {
        "PASS_KEEP_RESEARCHING",
        "WEAK_FAIL",
    }
)


def _strict_int(v: Any) -> int | None:
    """Accept only true integers (int, not bool). No strings, floats, or coercion."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    return None


def _field_strict_int(block: dict[str, Any], key: str) -> tuple[int | None, str | None]:
    """Return (value, error_reason). Present-but-invalid is an error, not absence."""
    if key not in block:
        return None, f"missing_field:{key}"
    n = _strict_int(block[key])
    if n is None:
        return None, f"invalid_type:{key}"
    return n, None


def _unknown_accounting(
    *,
    n_null_planned: int,
    exit_code: int | None,
    report_status: str,
    reported_disposition: str | None = None,
    report: dict[str, Any] | None = None,
    null_seed: Any = None,
) -> dict[str, Any]:
    """Fail-closed UNKNOWN template for all non-OK accounting paths."""
    out: dict[str, Any] = {
        "n_null_planned": int(n_null_planned),
        "exit_code": exit_code,
        "disposition": "FAILED_RUN_UNKNOWN",
        "reported_disposition": reported_disposition,
        "execution_state": "UNKNOWN",
        "n_null_executed": None,
        "null_trials_executed": None,
        "attempt_type": "FAILED_RUN_UNKNOWN",
        "family_screen_attempt": True,
        "sealed_null_attempt": True,
        "r1_burned": True,
        "report_status": report_status,
    }
    if null_seed is not None:
        out["null_seed"] = null_seed
    if report is not None:
        out["report"] = report
    return out


def _is_known_sealed_null_disposition(disposition: str) -> bool:
    if disposition in _KNOWN_SEALED_NULL_DISPOSITIONS:
        return True
    return disposition.startswith("KILL_")


def _require_equal_counts(
    values: list[int], *, label: str
) -> tuple[int | None, str | None]:
    if not values:
        return None, f"missing_counts:{label}"
    first = values[0]
    for v in values[1:]:
        if v != first:
            return None, f"count_conflict:{label}"
    return first, None


def _null_trials_identity_ok(null_block: dict[str, Any], planned: int) -> str | None:
    """Require null.trials length==planned with explicit trial ids == range(planned).

    No positional fallback: every row must contain a present strict-int ``trial``.
    IDs must equal ``set(range(planned))`` exactly (unique and in-range).
    """
    if "trials" not in null_block:
        return "missing_or_invalid_null.trials"
    trials = null_block.get("trials")
    if not isinstance(trials, list):
        return "missing_or_invalid_null.trials"
    if len(trials) != planned:
        return "null.trials_length_mismatch"
    ids: list[int] = []
    for row in trials:
        if not isinstance(row, dict):
            return "null.trials_row_not_object"
        if "trial" not in row:
            return "null.trials_missing_trial_id"
        n = _strict_int(row["trial"])
        if n is None:
            return "null.trials_invalid_trial_id"
        ids.append(n)
    if set(ids) != set(range(planned)):
        return "null.trials_id_set_mismatch"
    return None


def _screen_trials_empty_ok(null_block: dict[str, Any]) -> str | None:
    """Screen proof requires null.trials present and exactly []."""
    if "trials" not in null_block:
        return "screen_null.trials_missing"
    trials = null_block.get("trials")
    if not isinstance(trials, list):
        return "screen_null.trials_not_list"
    if trials != []:
        return "screen_null.trials_not_empty"
    return None


def _verify_reported_null_seed(
    null_block: dict[str, Any] | None,
    expected_null_seed: int | None,
) -> tuple[int | None, str | None]:
    """Require report null.base_seed exact int match to charter expected seed.

    Returns (verified_seed, error_code). On success error is None and seed is int.
    Missing / wrong type / mismatch → FAILED_RUN_UNKNOWN on OK paths.
    """
    if expected_null_seed is None:
        return None, "missing_expected_null_seed"
    if type(expected_null_seed) is not int or expected_null_seed < 0:
        return None, "invalid_expected_null_seed"
    if null_block is None:
        return None, "missing_null_block"
    if "base_seed" not in null_block:
        return None, "missing_null.base_seed"
    raw = null_block.get("base_seed")
    # Reject bool (subclass of int), float, str, None, negatives.
    if type(raw) is not int or raw < 0:
        return None, "invalid_null.base_seed"
    if raw != expected_null_seed:
        return None, "null.base_seed_mismatch"
    return raw, None


def parse_harness_report_for_accounting(
    *,
    result_json: Path,
    n_null_planned: int,
    exit_code: int | None,
    expected_null_seed: int | None = None,
) -> dict[str, Any]:
    """Derive attempt accounting from harness report + process exit (fail-closed).

    Only two OK paths exist, both requiring complete typed proof:

    1. DETERMINISTIC_SCREEN with full proof fields → r1_burned=false.
    2. Full sealed-null success (n_exec == charter planned > 0, trials list) →
       r1_burned=true.

    Both OK paths require ``expected_null_seed`` and an exact integer match to
    report ``null.base_seed``. Missing / mismatch / invalid seed →
    FAILED_RUN_UNKNOWN (never invent seed 0).

    Invalid-present count fields never fall back to another block. Everything
    else → disposition FAILED_RUN_UNKNOWN, r1_burned=true, n_null_executed=None.
    """
    charter_planned = int(n_null_planned)
    base_exit = int(exit_code) if exit_code is not None else None
    exit_for_unknown = base_exit if base_exit is not None else -1

    if not result_json.is_file():
        return _unknown_accounting(
            n_null_planned=charter_planned,
            exit_code=exit_for_unknown,
            report_status="missing",
        )
    try:
        report = json.loads(result_json.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return _unknown_accounting(
            n_null_planned=charter_planned,
            exit_code=exit_for_unknown,
            report_status=f"malformed:{type(e).__name__}",
        )
    if not isinstance(report, dict):
        return _unknown_accounting(
            n_null_planned=charter_planned,
            exit_code=exit_for_unknown,
            report_status="malformed:not_object",
        )

    verdict = report.get("verdict") if isinstance(report.get("verdict"), dict) else None
    null_block = report.get("null") if isinstance(report.get("null"), dict) else None
    acct = (
        report.get("attempt_accounting")
        if isinstance(report.get("attempt_accounting"), dict)
        else None
    )
    screen = report.get("screen") if isinstance(report.get("screen"), dict) else None
    real = report.get("real") if isinstance(report.get("real"), dict) else None

    reported_disposition: str | None = None
    if verdict is not None and verdict.get("disposition") is not None:
        reported_disposition = str(verdict.get("disposition"))

    # Raw report seed (may be invalid); never coerce for provenance invention.
    null_seed_raw = null_block.get("base_seed") if null_block is not None else None

    def _fail(reason: str) -> dict[str, Any]:
        return _unknown_accounting(
            n_null_planned=charter_planned,
            exit_code=exit_for_unknown,
            report_status=reason,
            reported_disposition=reported_disposition,
            report=report,
            null_seed=null_seed_raw,
        )

    def _require_ok_blocks() -> str | None:
        if verdict is None:
            return "missing_verdict"
        if null_block is None:
            return "missing_null_block"
        if acct is None:
            return "missing_attempt_accounting"
        return None

    def _load_paired_counts(
        *, expected_exec: int | None, expected_planned: int
    ) -> tuple[int | None, int | None, str | None]:
        """Load required counts from both blocks; all must agree.

        Returns (n_exec, n_plan, error).
        """
        assert null_block is not None and acct is not None
        fields: list[tuple[dict[str, Any], str, str]] = [
            (null_block, "n_null_planned", "null.n_null_planned"),
            (null_block, "n_null_executed", "null.n_null_executed"),
            (null_block, "n_trials", "null.n_trials"),
            (acct, "n_null_planned", "attempt_accounting.n_null_planned"),
            (acct, "n_null_executed", "attempt_accounting.n_null_executed"),
            (acct, "null_trials_executed", "attempt_accounting.null_trials_executed"),
        ]
        got: dict[str, int] = {}
        for block, key, label in fields:
            n, err = _field_strict_int(block, key)
            if err is not None:
                # rewrite generic missing/invalid with labeled key
                if err.startswith("missing_field:"):
                    return None, None, f"missing_field:{label}"
                return None, None, f"invalid_type:{label}"
            assert n is not None
            got[label] = n

        plan_vals = [
            got["null.n_null_planned"],
            got["attempt_accounting.n_null_planned"],
        ]
        exec_vals = [
            got["null.n_null_executed"],
            got["null.n_trials"],
            got["attempt_accounting.n_null_executed"],
            got["attempt_accounting.null_trials_executed"],
        ]
        n_plan, err = _require_equal_counts(plan_vals, label="n_null_planned")
        if err:
            return None, None, err
        n_exec, err = _require_equal_counts(exec_vals, label="n_null_executed")
        if err:
            return None, None, err
        assert n_plan is not None and n_exec is not None
        if n_plan != expected_planned:
            return None, None, "plan_mismatch"
        if expected_exec is not None and n_exec != expected_exec:
            return None, None, "exec_count_mismatch"
        return n_exec, n_plan, None

    # ------------------------------------------------------------------
    # Path 1: Deterministic screen OK (ONLY path with r1_burned=false)
    # ------------------------------------------------------------------
    if base_exit == 0 and reported_disposition == "SCREEN_FAIL":
        block_err = _require_ok_blocks()
        if block_err:
            return _fail(block_err)
        assert verdict is not None and null_block is not None and acct is not None
        if screen is None:
            return _fail("missing_screen_block")
        if real is None:
            return _fail("missing_real_block")
        if acct.get("attempt_type") != "DETERMINISTIC_SCREEN":
            return _fail("attempt_type_not_deterministic_screen")
        if str(verdict.get("screen_status") or "") != "ZERO_PRIMARY_PASSERS":
            return _fail("screen_status_not_zero_primary")
        if str(null_block.get("skipped_reason") or "") != "ZERO_PRIMARY_PASSERS":
            return _fail("skipped_reason_not_zero_primary")
        if screen.get("zero_primary_passers") is not True:
            return _fail("screen.zero_primary_passers_not_true")
        real_n, real_err = _field_strict_int(real, "n_passers")
        if real_err:
            return _fail(f"real.{real_err}")
        if real_n != 0:
            return _fail("real.n_passers_not_zero")
        if acct.get("family_screen_attempt") is not True:
            return _fail("family_screen_attempt_not_true")
        if acct.get("sealed_null_attempt") is not False:
            return _fail("sealed_null_attempt_not_false")

        n_exec, _n_plan, cerr = _load_paired_counts(
            expected_exec=0, expected_planned=charter_planned
        )
        if cerr:
            return _fail(cerr)
        assert n_exec == 0

        trials_err = _screen_trials_empty_ok(null_block)
        if trials_err:
            return _fail(trials_err)

        verified_seed, seed_err = _verify_reported_null_seed(
            null_block, expected_null_seed
        )
        if seed_err:
            return _fail(seed_err)
        assert verified_seed is not None

        return {
            "n_null_planned": charter_planned,
            "exit_code": base_exit,
            "disposition": "SCREEN_FAIL",
            "reported_disposition": reported_disposition,
            "execution_state": "OK",
            "n_null_executed": 0,
            "null_trials_executed": 0,
            "attempt_type": "DETERMINISTIC_SCREEN",
            "family_screen_attempt": True,
            "sealed_null_attempt": False,
            "r1_burned": False,
            "report_status": "ok",
            "null_seed": verified_seed,
            "report": report,
        }

    # ------------------------------------------------------------------
    # Path 2: Full-null success OK
    # ------------------------------------------------------------------
    if base_exit == 0:
        block_err = _require_ok_blocks()
        if block_err:
            return _fail(block_err)
        assert verdict is not None and null_block is not None and acct is not None
        if reported_disposition is None or not _is_known_sealed_null_disposition(
            reported_disposition
        ):
            return _fail("unknown_or_invalid_disposition")
        if acct.get("attempt_type") != "SEALED_NULL":
            return _fail("attempt_type_not_sealed_null")
        if acct.get("family_screen_attempt") is not True:
            return _fail("family_screen_attempt_not_true")
        if acct.get("sealed_null_attempt") is not True:
            return _fail("sealed_null_attempt_not_true")

        n_exec, _n_plan, cerr = _load_paired_counts(
            expected_exec=charter_planned, expected_planned=charter_planned
        )
        if cerr:
            return _fail(cerr)
        assert n_exec is not None
        if n_exec <= 0:
            return _fail("n_null_executed_not_positive")
        if n_exec != charter_planned:
            return _fail("partial_or_plan_mismatch")

        trials_err = _null_trials_identity_ok(null_block, charter_planned)
        if trials_err:
            return _fail(trials_err)

        verified_seed, seed_err = _verify_reported_null_seed(
            null_block, expected_null_seed
        )
        if seed_err:
            return _fail(seed_err)
        assert verified_seed is not None

        return {
            "n_null_planned": charter_planned,
            "exit_code": base_exit,
            "disposition": reported_disposition,
            "reported_disposition": reported_disposition,
            "execution_state": "OK",
            "n_null_executed": n_exec,
            "null_trials_executed": n_exec,
            "attempt_type": "SEALED_NULL",
            "family_screen_attempt": True,
            "sealed_null_attempt": True,
            "r1_burned": True,
            "report_status": "ok",
            "null_seed": verified_seed,
            "report": report,
        }

    # Nonzero exit / no exit / incomplete → UNKNOWN
    reason = "incomplete_or_nonzero_exit"
    if base_exit is None:
        reason = "no_exit_code"
    elif base_exit != 0:
        reason = "incomplete_or_nonzero_exit"
    return _fail(reason)


def _assert_family_matches_charter(family_cli: str, charter: dict[str, Any]) -> str:
    fid = str(charter.get("family_id") or "").strip()
    if not fid:
        raise SystemExit("charter missing family_id")
    # normalize CLI: allow xau_family_<id> or bare id
    cli = family_cli.strip().replace("-", "_")
    if cli.startswith("xau_family_"):
        cli = cli[len("xau_family_") :]
    if cli != fid:
        raise SystemExit(
            f"charter/runtime family mismatch: --family={family_cli!r} "
            f"vs charter.family_id={fid!r}"
        )
    return fid


def _assert_costs_match_charter(charter: dict[str, Any]) -> dict[str, Any]:
    """Loaded research costs must match charter fixed.costs on sim keys."""
    fixed = (charter.get("fixed") or {}).get("costs") or charter.get("costs") or {}
    loaded = load_research_costs()
    for k in ("spread_col", "point_size", "commission_per_lot", "slippage_points"):
        if k not in fixed:
            continue
        if k not in loaded:
            raise SystemExit(f"loaded costs missing {k}")
        a, b = fixed[k], loaded[k]
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if abs(float(a) - float(b)) > 1e-12:
                raise SystemExit(
                    f"cost mismatch {k}: charter={a} loaded={b}. "
                    "Update results/xau_research_costs.json or freeze a new charter."
                )
        elif a != b:
            raise SystemExit(f"cost mismatch {k}: charter={a!r} loaded={b!r}")
    return loaded


def _run_synthetic_fixture(family: str, charter: dict[str, Any]) -> dict[str, Any]:
    """Blocking fixture: null invariants + family.simulate must succeed."""
    import importlib

    import numpy as np
    import pandas as pd
    from xau_null_core import apply_null_method, null_invariants_ok

    rng = np.random.default_rng(0)
    # 4 full days × 23 bars (hours 1..23) to mimic develop day length
    rows = []
    price = 2000.0
    for day in range(4):
        for hour in range(1, 24):
            ret = float(rng.normal(0, 0.002))
            price = price * float(np.exp(ret))
            ts = pd.Timestamp(f"2024-01-{2 + day:02d} {hour:02d}:00:00", tz="UTC")
            rows.append(
                {
                    "time": ts,
                    "open": price,
                    "high": price * 1.0005,
                    "low": price * 0.9995,
                    "close": price,
                    "spread": 18.0,
                    "timeframe": "H1",
                }
            )
    raw = pd.DataFrame(rows)

    ns = null_spec_from_charter(charter)
    method = str(ns["method"])
    rule = charter.get("rule") or {}
    # Session-shaped entry hour: fixed hour, or first of entry_hours_server /
    # entry_allowed_hours_server (early_server_range_break_flat uses the latter).
    entry_h = rule.get("entry_hour")
    if entry_h is None:
        for key in ("entry_hours_server", "entry_allowed_hours_server"):
            seq = rule.get(key) or []
            if seq:
                entry_h = seq[0]
                break
    flat_h = rule.get("flat_hour") or rule.get("flat_hour_server")
    if flat_h is None:
        active = rule.get("session_active_hours_server") or []
        flat_h = active[-1] if active else None

    scr = apply_null_method(raw, rng, method=method, block_days=int(ns.get("block_days") or 1))
    inv = null_invariants_ok(
        raw,
        scr,
        method=method,
        entry_hour=int(entry_h) if entry_h is not None else None,
        flat_hour=int(flat_h) if flat_h is not None else None,
    )
    required = [k for k, v in inv.items() if k != "protocol_session_valid"]
    bad = {k: inv[k] for k in required if not inv.get(k)}
    if bad:
        raise SystemExit(f"synthetic null invariant fail method={method}: {bad} full={inv}")

    # family smoke — must not be skipped
    mod_name = f"xau_family_{family}" if not family.startswith("xau_family_") else family
    try:
        mod = importlib.import_module(mod_name)
    except ModuleNotFoundError:
        mod = importlib.import_module(family)
    if not hasattr(mod, "simulate") or not hasattr(mod, "prepare"):
        raise SystemExit(f"family {family!r} missing prepare/simulate")
    d = mod.prepare(raw)
    params: dict[str, Any] = {}
    if hasattr(mod, "build_grid"):
        g = mod.build_grid()
        if g:
            params = dict(g[0])
    elif hasattr(mod, "grid"):
        g = mod.grid(max_n=1, seed=0)
        if g:
            params = dict(g[0])
    costs = load_research_costs()
    m = mod.simulate(d, **{**costs, **params})
    _ = m.n_trades

    return {"null_invariants": inv, "family_smoke": "ok", "null_method": method}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--charter", required=True, help="immutable charter JSON")
    ap.add_argument("--family", required=True, help="must equal charter.family_id")
    ap.add_argument("--run-id", default="r1")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument(
        "--dry-fixture-only",
        action="store_true",
        help="only synthetic fixtures + charter validate (no real data null)",
    )
    args = ap.parse_args(argv)

    charter_path = Path(args.charter)
    charter = load_charter(charter_path)

    ok_run, why = is_charter_runnable(charter_path)
    if not ok_run:
        raise SystemExit(f"charter not runnable: {why}")

    errs = validate_charter_file(charter_path)
    if errs:
        raise SystemExit("charter validation failed:\n- " + "\n- ".join(errs))

    # Fail closed before fixtures/ledger/null: multi-instrument joint charters must
    # not use this sealed wrapper (it hardcodes single-frame null_maxstat).
    _refuse = multi_instrument_single_frame_refuse_message(charter)
    if _refuse:
        raise SystemExit(_refuse)

    # Dispositional path: sealed path under charters/ + HEAD blob + clean tree
    if not args.dry_fixture_only:
        try:
            assert_charter_path_for_sealed(charter_path)
            assert_clean_dispositional_tree()
        except CharterError as e:
            raise SystemExit(str(e)) from e

    family_id = _assert_family_matches_charter(args.family, charter)
    _assert_costs_match_charter(charter)

    n_attempts = count_attempts(family_id)
    print(f"Program attempts for {family_id!r} so far: {n_attempts}", flush=True)

    print("Synthetic fixture smoke (blocking)...", flush=True)
    fixture = _run_synthetic_fixture(family_id, charter)
    print(f"  fixture: {fixture}", flush=True)

    if args.dry_fixture_only:
        print("dry-fixture-only: stop before real grid/null", flush=True)
        return 0

    out_dir = run_output_dir(family_id, run_id=args.run_id)
    try:
        ensure_fresh_run_dir(out_dir)
    except CharterError as e:
        raise SystemExit(str(e)) from e

    ns = null_spec_from_charter(charter)
    n_null_planned = int(ns["n_trials"])
    null_method = str(ns["method"])
    # Explicit seed from charter (or house default). Never leave seed to harness
    # default alone under sealed path — pins against seed shopping.
    sealed_null_seed = (
        int(ns["base_seed"]) if ns.get("base_seed") is not None else int(DEFAULT_NULL_BASE_SEED)
    )

    # Single sealed invocation — no CLI null overrides (charter is sole source).
    cmd = [
        sys.executable,
        str(SCRIPTS / "xau_family_null_maxstat.py"),
        "--family",
        family_id,
        "--charter",
        str(charter_path),
        "--out-dir",
        str(out_dir),
        "--workers",
        str(args.workers),
        "--strict-charter",
        "--null-seed",
        str(sealed_null_seed),
    ]

    # Finding B: pre-launch STARTED ledger row so interruption cannot erase the attempt.
    attempt_id = uuid.uuid4().hex
    attempt_index = n_attempts + 1
    append_attempt(
        {
            "attempt_id": attempt_id,
            "family_id": family_id,
            "charter_path": str(charter_path),
            "run_id": args.run_id,
            "output_dir": str(out_dir),
            "null_method": null_method,
            "n_null_planned": n_null_planned,
            "n_null_executed": None,
            "execution_state": "STARTED",
            "disposition": "FAILED_RUN_UNKNOWN",
            "attempt_type": "STARTED",
            "family_screen_attempt": True,
            "sealed_null_attempt": True,
            "r1_burned": True,
            "report_status": "started",
            "attempt_index": attempt_index,
        }
    )

    print("Sealed real grid + null (single command):", " ".join(cmd), flush=True)
    t0 = time.time()
    proc_returncode: int | None = None
    elapsed: float | None = None
    acct: dict[str, Any] | None = None
    result_json = out_dir / "null_maxstat.json"
    # Deferred re-raise after accounting/provenance so UNKNOWN runs still get
    # n_null=None provenance (never planned-as-executed) and a terminal ledger.
    deferred_exc: BaseException | None = None

    try:
        try:
            proc = subprocess.run(cmd, cwd=str(ROOT))
            proc_returncode = int(proc.returncode)
        except KeyboardInterrupt as e:
            proc_returncode = None
            deferred_exc = e
        except OSError as e:
            proc_returncode = None
            deferred_exc = e
        finally:
            elapsed = time.time() - t0
            # Parse when we have an exit code; on interrupt/launch error still parse
            # report if present, else hard UNKNOWN with no_exit_code.
            if proc_returncode is not None:
                acct = parse_harness_report_for_accounting(
                    result_json=result_json,
                    n_null_planned=n_null_planned,
                    exit_code=proc_returncode,
                    expected_null_seed=sealed_null_seed,
                )
            else:
                # Interrupt / launch error: parse report if any, else hard UNKNOWN
                if result_json.is_file():
                    acct = parse_harness_report_for_accounting(
                        result_json=result_json,
                        n_null_planned=n_null_planned,
                        exit_code=-1,  # nonzero → UNKNOWN path
                        expected_null_seed=sealed_null_seed,
                    )
                    # force UNKNOWN if parse somehow returned OK (should not)
                    if acct.get("execution_state") != "UNKNOWN":
                        acct = _unknown_accounting(
                            n_null_planned=n_null_planned,
                            exit_code=None,
                            report_status="interrupted_or_launch_error",
                            reported_disposition=acct.get("reported_disposition"),
                            report=acct.get("report"),
                            null_seed=acct.get("null_seed"),
                        )
                else:
                    acct = _unknown_accounting(
                        n_null_planned=n_null_planned,
                        exit_code=None,
                        report_status="interrupted_or_launch_error",
                    )

        # Provenance best-effort (including interrupt/OSError UNKNOWN paths).
        # Ledger terminal write must not depend on provenance success.
        assert acct is not None
        disposition = str(acct["disposition"])
        n_null_executed = acct["n_null_executed"]
        attempt_type = str(acct["attempt_type"])
        family_screen_attempt = bool(acct["family_screen_attempt"])
        sealed_null_attempt = bool(acct["sealed_null_attempt"])
        r1_burned = bool(acct["r1_burned"])
        execution_state = str(acct["execution_state"])

        try:
            # Provenance null_seed: verified non-negative int when present.
            # Never invent 0 when reported seed is missing/invalid.
            reported_seed = acct.get("null_seed")
            null_seed_i: int | None
            if type(reported_seed) is int and reported_seed >= 0:
                null_seed_i = reported_seed
            else:
                null_seed_i = None
            # Top-level provenance.n_null is executed count only. When unknown
            # (FAILED_RUN_UNKNOWN), pass None — never substitute planned.
            prov_n_null: int | None = (
                None if n_null_executed is None else int(n_null_executed)
            )
            prov = build_provenance(
                charter_path=charter_path,
                costs_path=RESEARCH_COSTS_PATH,
                data_path=CSV_PATH,
                null_seed=null_seed_i,
                n_null=prov_n_null,
                out_dir=out_dir,
                require_clean_tree=True,
                extra={
                    "disposition": disposition,
                    "null_method": null_method,
                    "family_id": family_id,
                    "sealed_cycle_elapsed_s": elapsed,
                    "fixture": fixture,
                    "n_null_planned": int(acct.get("n_null_planned") or n_null_planned),
                    "n_null_executed": n_null_executed,
                    "null_trials_executed": n_null_executed,
                    "null_seed_expected": sealed_null_seed,
                    "attempt_type": attempt_type,
                    "family_screen_attempt": family_screen_attempt,
                    "sealed_null_attempt": sealed_null_attempt,
                    "r1_burned": r1_burned,
                    "execution_state": execution_state,
                    "report_status": acct.get("report_status"),
                    "attempt_id": attempt_id,
                },
            )
            (out_dir / "provenance.json").write_text(json.dumps(prov, indent=2) + "\n")
        except Exception as e:
            # Prefer provenance error if both deferred interrupt and prov fail;
            # outer finally still writes terminal ledger before re-raise.
            if deferred_exc is None:
                deferred_exc = e
            else:
                # Keep original interrupt/OSError; chain provenance failure.
                e.__cause__ = deferred_exc
                deferred_exc = e
    finally:
        # Terminal append_attempt always includes same attempt_id as STARTED.
        if acct is None:
            acct = _unknown_accounting(
                n_null_planned=n_null_planned,
                exit_code=proc_returncode,
                report_status="interrupted_or_launch_error",
            )
        ledger_record = {
            "attempt_id": attempt_id,
            "family_id": family_id,
            "charter_path": str(charter_path),
            "run_id": args.run_id,
            "output_dir": str(out_dir),
            "disposition": str(acct["disposition"]),
            "null_method": null_method,
            "n_null_planned": int(acct.get("n_null_planned") or n_null_planned),
            "n_null_executed": acct.get("n_null_executed"),
            "null_trials_executed": acct.get("n_null_executed"),
            "attempt_type": str(acct["attempt_type"]),
            "family_screen_attempt": bool(acct["family_screen_attempt"]),
            "sealed_null_attempt": bool(acct["sealed_null_attempt"]),
            "r1_burned": bool(acct["r1_burned"]),
            "execution_state": str(acct["execution_state"]),
            "report_status": acct.get("report_status"),
            "reported_disposition": acct.get("reported_disposition"),
            "exit_code": proc_returncode,
            "elapsed_s": elapsed,
            "attempt_index": attempt_index,
        }
        append_attempt(ledger_record)

    if deferred_exc is not None:
        raise deferred_exc

    print(
        f"Disposition: {acct['disposition']} execution_state={acct['execution_state']} "
        f"(exit={proc_returncode})",
        flush=True,
    )
    print("Attempt ledger: results/xau_family_attempts.jsonl", flush=True)
    return int(proc_returncode) if proc_returncode is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
