#!/usr/bin/env python3
"""Sealed family research cycle (protocol v2).

1. Validate frozen charter (immutable path).
2. Run synthetic fixture smoke (no real market data).
3. One-shot: develop grid + null on real develop window (no intermediate edits).
4. Append program-level attempt ledger.
5. Refuse overwrite of run directory.

Does **not** peek at real-grid results mid-run for retuning — single process.

Usage::

  python3 scripts/xau_sealed_family_cycle.py \\
    --charter results/xau_charters/2026-08-10_tod_london_ny_flat_v1.json \\
    --family tod_london_ny_flat \\
    --run-id r1

SAFETY: offline only. No --live. Do not attach to PR #1 scope without review.
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
    build_provenance,
    count_attempts,
    ensure_fresh_run_dir,
    load_charter,
    null_spec_from_charter,
    run_output_dir,
    validate_charter,
)
from xau_research_costs import RESEARCH_COSTS_PATH  # noqa: E402
from backtest import CSV_PATH  # noqa: E402


def _run_synthetic_fixture(family: str) -> dict[str, Any]:
    """Import family and run a tiny synthetic bar path if provided."""
    # Prefer family module hook; else shared fixture check on null_core.
    from xau_null_core import apply_null_method, null_invariants_ok
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(0)
    n = 48
    # 2 days of H1-ish bars
    times = pd.date_range("2024-01-02", periods=n, freq="h", tz="UTC")
    close = 2000.0 + np.cumsum(rng.normal(0, 0.5, size=n))
    raw = pd.DataFrame(
        {
            "time": times,
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "spread": np.full(n, 18.0),
            "timeframe": "H1",
        }
    )
    for method in ("global_return_shuffle", "day_block_shuffle", "circular_day_shift"):
        scr = apply_null_method(raw, rng, method=method, block_days=1)
        inv = null_invariants_ok(raw, scr, method=method)
        if not all(inv.values()):
            raise SystemExit(f"synthetic null invariant fail method={method}: {inv}")

    # optional family.simulate smoke
    try:
        import importlib

        mod_name = f"xau_family_{family}" if not family.startswith("xau_family_") else family
        try:
            mod = importlib.import_module(mod_name)
        except ModuleNotFoundError:
            mod = importlib.import_module(family)
        if hasattr(mod, "simulate") and hasattr(mod, "prepare"):
            d = mod.prepare(raw)
            # one empty/default param dict
            params = {}
            if hasattr(mod, "build_grid"):
                g = mod.build_grid()
                if g:
                    params = dict(g[0])
            elif hasattr(mod, "grid"):
                g = mod.grid(max_n=1, seed=0)
                if g:
                    params = dict(g[0])
            m = mod.simulate(d, **params)
            _ = m
    except Exception as e:
        # fixture still passes null invariants; family smoke is best-effort
        return {"null_invariants": "ok", "family_smoke": f"skip:{type(e).__name__}:{e}"}

    return {"null_invariants": "ok", "family_smoke": "ok"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--charter", required=True, help="immutable charter JSON")
    ap.add_argument("--family", required=True, help="family module / builtin name")
    ap.add_argument("--run-id", default="r1")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument(
        "--dry-fixture-only",
        action="store_true",
        help="only synthetic fixtures + charter validate (no real data null)",
    )
    ap.add_argument(
        "--allow-low-n-null",
        action="store_true",
        help="pass through to null harness (smoke only)",
    )
    args = ap.parse_args(argv)

    charter_path = Path(args.charter)
    charter = load_charter(charter_path)
    errs = validate_charter(charter)
    if errs and not args.dry_fixture_only:
        # allow dry fixture on incomplete drafts
        raise SystemExit("charter validation failed:\n- " + "\n- ".join(errs))
    if errs:
        print("WARNING charter validation:", errs, flush=True)

    family_id = str(charter.get("family_id") or args.family)
    n_attempts = count_attempts(family_id)
    print(f"Program attempts for {family_id!r} so far: {n_attempts}", flush=True)

    print("Synthetic fixture smoke...", flush=True)
    fixture = _run_synthetic_fixture(args.family)
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

    # Single sealed invocation — no intermediate file edits by this script.
    cmd = [
        sys.executable,
        str(SCRIPTS / "xau_family_null_maxstat.py"),
        "--family",
        args.family,
        "--charter",
        str(charter_path),
        "--out-dir",
        str(out_dir),
        "--n-null",
        str(n_null),
        "--null-method",
        null_method,
        "--workers",
        str(args.workers),
    ]
    if args.allow_low_n_null:
        cmd.append("--allow-low-n-null")

    print("Sealed real grid + null (single command):", " ".join(cmd), flush=True)
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = time.time() - t0

    result_json = out_dir / "null_maxstat.json"
    disposition = "FAILED_RUN"
    if result_json.is_file():
        report = json.loads(result_json.read_text())
        disposition = str(report.get("verdict", {}).get("disposition") or "UNKNOWN")
        # write provenance alongside
        prov = build_provenance(
            charter_path=charter_path,
            costs_path=RESEARCH_COSTS_PATH,
            data_path=CSV_PATH,
            null_seed=int(report.get("null", {}).get("base_seed") or 0),
            n_null=n_null,
            out_dir=out_dir,
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
    print(f"Attempt ledger: results/xau_family_attempts.jsonl", flush=True)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
