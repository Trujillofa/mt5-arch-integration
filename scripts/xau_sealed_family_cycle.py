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
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from xau_charter_protocol import (  # noqa: E402
    CharterError,
    append_attempt,
    assert_charter_path_for_sealed,
    assert_clean_dispositional_tree,
    build_provenance,
    count_attempts,
    ensure_fresh_run_dir,
    load_charter,
    null_spec_from_charter,
    run_output_dir,
    validate_charter,
)
from xau_research_costs import RESEARCH_COSTS_PATH, load_research_costs  # noqa: E402

from backtest import CSV_PATH  # noqa: E402


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
    entry_h = rule.get("entry_hour") or (rule.get("entry_hours_server") or [None])[0]
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
    from xau_charter_protocol import is_charter_runnable

    ok_run, why = is_charter_runnable(charter_path)
    if not ok_run:
        raise SystemExit(f"charter not runnable: {why}")

    errs = validate_charter(charter)
    if errs:
        raise SystemExit("charter validation failed:\n- " + "\n- ".join(errs))

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
    n_null = int(ns["n_trials"])
    null_method = str(ns["method"])

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
    ]

    print("Sealed real grid + null (single command):", " ".join(cmd), flush=True)
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = time.time() - t0

    result_json = out_dir / "null_maxstat.json"
    disposition = "FAILED_RUN"
    if result_json.is_file():
        report = json.loads(result_json.read_text())
        disposition = str(report.get("verdict", {}).get("disposition") or "UNKNOWN")
        prov = build_provenance(
            charter_path=charter_path,
            costs_path=RESEARCH_COSTS_PATH,
            data_path=CSV_PATH,
            null_seed=int(report.get("null", {}).get("base_seed") or 0),
            n_null=n_null,
            out_dir=out_dir,
            require_clean_tree=True,
            extra={
                "disposition": disposition,
                "null_method": null_method,
                "family_id": family_id,
                "sealed_cycle_elapsed_s": elapsed,
                "fixture": fixture,
            },
        )
        (out_dir / "provenance.json").write_text(json.dumps(prov, indent=2) + "\n")

    append_attempt(
        {
            "family_id": family_id,
            "charter_path": str(charter_path),
            "run_id": args.run_id,
            "output_dir": str(out_dir),
            "disposition": disposition,
            "null_method": null_method,
            "n_null": n_null,
            "exit_code": proc.returncode,
            "elapsed_s": elapsed,
            "attempt_index": n_attempts + 1,
        }
    )
    print(f"Disposition: {disposition} (exit={proc.returncode})", flush=True)
    print("Attempt ledger: results/xau_family_attempts.jsonl", flush=True)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
