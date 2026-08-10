#!/usr/bin/env python3
"""Null / max-stat test for the XAU H1 search grid.

Question: does best-of-~1200 on real develop bars sit outside the distribution
of best-of-~1200 on return-shuffled bars (no predictive structure)?

If not, the gates measured the search, not the market — kill the bb_rsi line
rather than tune it further.

Protocol
--------
* Window: develop only (``time < holdout_start``). Holdout stays sealed.
* Costs: whatever ``strategy_params.json`` records (measured spread, etc.).
* Grid: identical to ``backtest.build_search_candidates()`` (seed 42, ~1200 +
  5 priority seeds). **No early exit** — every config is scored.
* Null: shuffle close-to-close log returns, rebuild OHLC keeping each bar's
  relative range geometry; recompute indicators; re-score the full grid.
  ``time`` / ``spread`` stay calendar-aligned (spread is a time-of-day property).
* Statistics: max PF, max search-score, n_passers, n that would early-exit
  ``search()``. p-value = fraction of null trials with stat >= real.

Does NOT overwrite strategy_params.json. Writes:
  results/xau_null_maxstat.json
  results/xau_null_maxstat.md

SAFETY: offline only — no live orders, no holdout selection.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest import (  # noqa: E402
    build_search_candidates,
    develop_only,
    holdout_start,
    indicators,
    load_h1,
    normalize_params,
    passes,
    search_score,
)
from backtest import (
    simulate as _simulate,
)

PARAMS_PATH = ROOT / "strategy_params.json"
OUT_JSON = ROOT / "results" / "xau_null_maxstat.json"
OUT_MD = ROOT / "results" / "xau_null_maxstat.md"

sys.path.insert(0, str(ROOT / "scripts"))
from xau_research_costs import load_research_costs  # noqa: E402
from xau_null_core import scramble_ohlc as scramble_ohlc  # noqa: E402
from xau_null_core import pvalue as _pvalue  # noqa: E402

# Research cost floor (Vantage RAW ECN); see results/xau_research_costs.json.
COSTS: dict[str, Any] = load_research_costs()

# Worker globals filled in each process (fork COW on Linux; re-init on spawn).
_W: dict[str, Any] = {}


def simulate(d: pd.DataFrame, **kw):
    return _simulate(d, **{**COSTS, **kw})


def serializable_params(p: dict) -> dict:
    return {k: (list(v) if isinstance(v, tuple) else v) for k, v in p.items()}


def metrics_dict(m) -> dict:
    return {
        "net_profit": float(m.net_profit),
        "win_rate": float(m.win_rate),
        "profit_factor": float(m.profit_factor),
        "max_drawdown_pct": float(m.max_drawdown_pct),
        "n_trades": int(m.n_trades),
        "wins": int(m.wins),
        "losses": int(m.losses),
    }


# scramble_ohlc imported from xau_null_core (re-exported)


def score_grid(
    d: pd.DataFrame,
    candidates: list[dict],
    *,
    progress_every: int = 0,
    label: str = "",
    min_trades: int = 20,
) -> dict[str, Any]:
    """Score every candidate (no early exit). Returns summary + top rows.

    Max-stat for the null test is gated on ``n_trades >= min_trades`` so the
    PF=99 cap on 1–2 winning trades cannot dominate best-of-grid.
    """
    n = len(candidates)
    pfs = np.empty(n, dtype=float)
    scores = np.empty(n, dtype=float)
    nets = np.empty(n, dtype=float)
    wrs = np.empty(n, dtype=float)
    dds = np.empty(n, dtype=float)
    ntr = np.empty(n, dtype=int)
    pass_mask = np.zeros(n, dtype=bool)
    early_mask = np.zeros(n, dtype=bool)

    best_i = 0
    best_score = -1e18
    best_pf_i = 0
    best_pf = -1.0
    best_min_i = -1
    best_min_score = -1e18
    best_min_pf_i = -1
    best_min_pf = -1.0

    t0 = time.time()
    for i, p in enumerate(candidates):
        m = simulate(d, **p)
        sc = search_score(m)
        pfs[i] = m.profit_factor
        scores[i] = sc
        nets[i] = m.net_profit
        wrs[i] = m.win_rate
        dds[i] = m.max_drawdown_pct
        ntr[i] = m.n_trades
        ok = passes(m)
        pass_mask[i] = ok
        early_mask[i] = bool(ok and m.profit_factor >= 1.55 and m.n_trades >= 25)
        if sc > best_score:
            best_score = sc
            best_i = i
        if m.profit_factor > best_pf or (
            m.profit_factor == best_pf and m.net_profit > nets[best_pf_i]
        ):
            best_pf = float(m.profit_factor)
            best_pf_i = i
        if m.n_trades >= min_trades:
            if sc > best_min_score:
                best_min_score = sc
                best_min_i = i
            if m.profit_factor > best_min_pf or (
                m.profit_factor == best_min_pf
                and best_min_pf_i >= 0
                and m.net_profit > nets[best_min_pf_i]
            ):
                best_min_pf = float(m.profit_factor)
                best_min_pf_i = i
        if progress_every and (i + 1) % progress_every == 0:
            print(
                f"  [{label}] {i+1}/{n} "
                f"best_PF@>={min_trades}={best_min_pf:.3f} "
                f"passers={int(pass_mask[: i + 1].sum())} "
                f"({time.time() - t0:.0f}s)",
                flush=True,
            )

    def _row(i: int) -> dict:
        return {
            "index": int(i),
            "params": serializable_params(candidates[i]),
            "profit_factor": float(pfs[i]),
            "search_score": float(scores[i]),
            "net_profit": float(nets[i]),
            "win_rate": float(wrs[i]),
            "max_drawdown_pct": float(dds[i]),
            "n_trades": int(ntr[i]),
            "passes": bool(pass_mask[i]),
            "would_early_exit_search": bool(early_mask[i]),
        }

    eligible = ntr >= min_trades
    top_idx = np.argsort(-scores)[:20]
    top_min_idx = np.argsort(-np.where(eligible, scores, -1e18))[:20]

    max_pf_min = float(pfs[eligible].max()) if eligible.any() else 0.0
    max_score_min = float(scores[eligible].max()) if eligible.any() else -1e18
    max_net_min = float(nets[eligible].max()) if eligible.any() else 0.0

    return {
        "n_configs": n,
        "min_trades_gate": min_trades,
        "elapsed_s": float(time.time() - t0),
        "best_by_score": _row(best_i),
        "best_by_pf": _row(best_pf_i),
        "best_by_score_min_trades": _row(best_min_i) if best_min_i >= 0 else None,
        "best_by_pf_min_trades": _row(best_min_pf_i) if best_min_pf_i >= 0 else None,
        "n_passers": int(pass_mask.sum()),
        "n_early_exit_eligible": int(early_mask.sum()),
        "n_with_min_trades": int(eligible.sum()),
        "pf": {
            "max_raw": float(pfs.max()) if n else 0.0,
            "max_min_trades": max_pf_min,
            "p50": float(np.median(pfs)) if n else 0.0,
            "p90": float(np.quantile(pfs, 0.90)) if n else 0.0,
            "p99": float(np.quantile(pfs, 0.99)) if n else 0.0,
            "mean": float(pfs.mean()) if n else 0.0,
        },
        "search_score": {
            "max_raw": float(scores.max()) if n else 0.0,
            "max_min_trades": max_score_min if eligible.any() else 0.0,
            "p50": float(np.median(scores)) if n else 0.0,
            "p90": float(np.quantile(scores, 0.90)) if n else 0.0,
            "p99": float(np.quantile(scores, 0.99)) if n else 0.0,
            "mean": float(scores.mean()) if n else 0.0,
        },
        "net_profit": {
            "max_raw": float(nets.max()) if n else 0.0,
            "max_min_trades": max_net_min,
            "p50": float(np.median(nets)) if n else 0.0,
            "mean": float(nets.mean()) if n else 0.0,
        },
        "top20_by_score": [_row(int(i)) for i in top_idx],
        "top20_by_score_min_trades": [
            _row(int(i)) for i in top_min_idx if eligible[int(i)]
        ],
        # decision stats (gated)
        "max_pf": max_pf_min,
        "max_score": max_score_min if eligible.any() else 0.0,
        "max_net": max_net_min,
        "max_pf_raw": float(pfs.max()) if n else 0.0,
        "max_score_raw": float(scores.max()) if n else 0.0,
    }


def _init_worker(raw_records: list, candidates: list[dict], costs: dict) -> None:
    """Spawn-safe worker init: rebuild the develop DataFrame once per process."""
    global COSTS
    COSTS = dict(costs)
    raw = pd.DataFrame.from_records(raw_records)
    raw["time"] = pd.to_datetime(raw["time"], utc=True)
    _W["raw"] = raw
    _W["candidates"] = candidates


def _null_trial(trial: int, base_seed: int) -> dict[str, Any]:
    raw = _W["raw"]
    candidates = _W["candidates"]
    rng = np.random.default_rng(base_seed + trial * 1_000_003)
    scr = scramble_ohlc(raw, rng)
    d = indicators(scr)
    summary = score_grid(d, candidates, progress_every=0, label=f"null{trial}")
    return {
        "trial": trial,
        "seed": int(base_seed + trial * 1_000_003),
        "max_pf": summary["max_pf"],
        "max_score": summary["max_score"],
        "max_net": summary["max_net"],
        "n_passers": summary["n_passers"],
        "n_early_exit_eligible": summary["n_early_exit_eligible"],
        "best_by_score": summary["best_by_score"],
        "best_by_pf": summary["best_by_pf"],
        "elapsed_s": summary["elapsed_s"],
    }


# _pvalue imported from xau_null_core as _pvalue


def write_markdown(report: dict, path: Path) -> None:
    real = report["real"]
    null = report["null"]
    verdict = report["verdict"]
    lines = [
        "# XAU null / max-stat test",
        "",
        f"**Disposition:** `{verdict['disposition']}`",
        "",
        verdict["reason"],
        "",
        "## Protocol",
        "",
        f"- Window: develop only (`time < {report['window']['holdout_start']}`), "
        f"{report['window']['bars']} H1 bars "
        f"({report['window']['start']} → {report['window']['end']})",
        f"- Grid: {report['grid']['n_configs']} configs "
        f"(max_n={report['grid']['max_n']}, seed={report['grid']['seed']}) — no early exit",
        f"- Null: {null['n_trials']} return-shuffle trials, base_seed={null['base_seed']}, "
        f"workers={null['workers']}",
        f"- Costs: `{json.dumps(report['costs'])}`",
        "",
        "## Real grid (develop, costed)",
        "",
        "Max-stat is gated on `n_trades >= 20` so the PF=99 thin-sample cap cannot dominate.",
        "",
        "| Stat | Value |",
        "|---|---|",
        f"| max PF (n≥20) | {real['max_pf']:.4f} |",
        f"| max search_score (n≥20) | {real['max_score']:.2f} |",
        f"| max net (n≥20) | ${real['max_net']:.2f} |",
        f"| max PF raw (incl. thin) | {real.get('max_pf_raw', real['max_pf']):.4f} |",
        f"| n_passers (gates) | {real['n_passers']} |",
        f"| n early-exit eligible | {real['n_early_exit_eligible']} |",
        f"| n with ≥20 trades | {real.get('n_with_min_trades', '?')} |",
        f"| PF p50 / p90 / p99 | {real['pf']['p50']:.3f} / {real['pf']['p90']:.3f} / {real['pf']['p99']:.3f} |",
        f"| elapsed | {real['elapsed_s']:.0f}s |",
        "",
        "Best by search_score among n≥20:",
        "",
        "```json",
        json.dumps(real.get("best_by_score_min_trades") or real["best_by_score"], indent=2),
        "```",
        "",
        "Shipped baseline replay (for reference):",
        "",
        "```json",
        json.dumps(report.get("baseline_replay"), indent=2),
        "```",
        "",
        "## Null distribution (best-of-grid per trial, n≥20 gated)",
        "",
        "| Stat | null max | null p50 | null p90 | p(null ≥ real) |",
        "|---|---|---|---|---|",
        f"| max PF (n≥20) | {null['max_pf']['max']:.4f} | {null['max_pf']['p50']:.4f} | "
        f"{null['max_pf']['p90']:.4f} | **{null['p_max_pf']:.3f}** |",
        f"| max score (n≥20) | {null['max_score']['max']:.2f} | {null['max_score']['p50']:.2f} | "
        f"{null['max_score']['p90']:.2f} | **{null['p_max_score']:.3f}** |",
        f"| n_passers | {null['n_passers']['max']} | {null['n_passers']['p50']:.1f} | "
        f"{null['n_passers']['p90']:.1f} | **{null['p_n_passers']:.3f}** |",
        f"| n early-exit | {null['n_early_exit']['max']} | {null['n_early_exit']['p50']:.1f} | "
        f"{null['n_early_exit']['p90']:.1f} | **{null['p_n_early_exit']:.3f}** |",
        "",
        "## Decision rule",
        "",
        "- Fail (kill line) if `p_max_pf > 0.05` **or** `p_n_passers > 0.05` — real best-of-grid",
        "  is typical of noise under the same search.",
        "- Weak if only one of the two fails; still no promote.",
        "- Pass only if both p-values ≤ 0.05 **and** real n_passers > null p90 — still not",
        "  a live go; only permission to keep researching the family (knob cut, cross-instrument).",
        "",
        f"Elapsed total: {report['elapsed_s']:.0f}s",
        "",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-null", type=int, default=40, help="null trials (default 40)")
    ap.add_argument("--max-n", type=int, default=1200, help="grid subsample size (default 1200)")
    ap.add_argument("--seed", type=int, default=42, help="grid subsample seed (match search)")
    ap.add_argument("--null-seed", type=int, default=20260808, help="base seed for null trials")
    ap.add_argument(
        "--workers",
        type=int,
        default=max(1, min(8, (os.cpu_count() or 2) - 1)),
        help="parallel null workers (default min(8, ncpu-1))",
    )
    ap.add_argument(
        "--quick",
        action="store_true",
        help="smoke: max_n=40, n_null=4 (not for disposition)",
    )
    ap.add_argument("--progress-every", type=int, default=200)
    args = ap.parse_args()

    if args.quick:
        args.max_n = 40
        args.n_null = 4
        print("QUICK smoke mode: max_n=40 n_null=4 — do not use for disposition", flush=True)

    t_all = time.time()
    cutoff = holdout_start()
    if cutoff is None:
        raise SystemExit("results/xau_holdout_lock.json missing holdout_start — refuse to run")

    raw_full = load_h1()
    raw = develop_only(raw_full, cutoff)
    print(
        f"Develop window: {len(raw)} H1 bars  {raw['time'].iloc[0]} → {raw['time'].iloc[-1]}",
        flush=True,
    )
    print(f"Costs: {COSTS}", flush=True)

    candidates = build_search_candidates(max_n=args.max_n, seed=args.seed)
    print(f"Grid: {len(candidates)} configs (max_n={args.max_n}, seed={args.seed})", flush=True)

    # --- real ---
    print("Scoring REAL grid (no early exit)...", flush=True)
    d_real = indicators(raw)
    real = score_grid(
        d_real,
        candidates,
        progress_every=args.progress_every,
        label="real",
    )

    # shipped baseline on same window + costs
    baseline_params = normalize_params(_SAVED.get("params") or {})
    base_m = simulate(d_real, **baseline_params)
    baseline_replay = {
        "params": serializable_params(baseline_params),
        **metrics_dict(base_m),
        "search_score": search_score(base_m),
        "passes": passes(base_m),
    }
    print(
        f"REAL: max_PF(n≥20)={real['max_pf']:.4f} max_score(n≥20)={real['max_score']:.1f} "
        f"passers={real['n_passers']} early={real['n_early_exit_eligible']} "
        f"baseline_PF={base_m.profit_factor:.4f} n={base_m.n_trades} "
        f"(raw max_PF={real['max_pf_raw']:.1f})",
        flush=True,
    )

    # --- nulls ---
    print(
        f"Running {args.n_null} null trials with {args.workers} workers...",
        flush=True,
    )
    # records for spawn-safe workers (fork still benefits from COW after init)
    raw_records = raw.to_dict(orient="records")
    # make timestamps JSON-serializable for from_records
    for rec in raw_records:
        t = rec["time"]
        rec["time"] = t.isoformat() if hasattr(t, "isoformat") else str(t)

    null_rows: list[dict] = []
    if args.n_null > 0:
        if args.workers <= 1:
            _init_worker(raw_records, candidates, COSTS)
            for trial in range(args.n_null):
                row = _null_trial(trial, args.null_seed)
                null_rows.append(row)
                print(
                    f"  null {trial + 1}/{args.n_null}: "
                    f"max_PF={row['max_pf']:.3f} passers={row['n_passers']} "
                    f"({row['elapsed_s']:.0f}s)",
                    flush=True,
                )
        else:
            with ProcessPoolExecutor(
                max_workers=args.workers,
                initializer=_init_worker,
                initargs=(raw_records, candidates, COSTS),
            ) as pool:
                futs = {
                    pool.submit(_null_trial, trial, args.null_seed): trial
                    for trial in range(args.n_null)
                }
                done = 0
                for fut in as_completed(futs):
                    row = fut.result()
                    null_rows.append(row)
                    done += 1
                    print(
                        f"  null done {done}/{args.n_null} (trial {row['trial']}): "
                        f"max_PF={row['max_pf']:.3f} passers={row['n_passers']} "
                        f"({row['elapsed_s']:.0f}s)",
                        flush=True,
                    )
            null_rows.sort(key=lambda r: r["trial"])

    def _dist(vals: list[float]) -> dict:
        a = np.asarray(vals, dtype=float)
        if len(a) == 0:
            return {"max": 0.0, "p50": 0.0, "p90": 0.0, "mean": 0.0}
        return {
            "max": float(a.max()),
            "p50": float(np.median(a)),
            "p90": float(np.quantile(a, 0.90)),
            "mean": float(a.mean()),
        }

    null_max_pf = [r["max_pf"] for r in null_rows]
    null_max_score = [r["max_score"] for r in null_rows]
    null_n_pass = [float(r["n_passers"]) for r in null_rows]
    null_n_early = [float(r["n_early_exit_eligible"]) for r in null_rows]

    p_max_pf = _pvalue(null_max_pf, real["max_pf"])
    p_max_score = _pvalue(null_max_score, real["max_score"])
    p_n_passers = _pvalue(null_n_pass, float(real["n_passers"]))
    p_n_early = _pvalue(null_n_early, float(real["n_early_exit_eligible"]))

    # Decision
    fail_pf = p_max_pf > 0.05
    fail_pass = p_n_passers > 0.05
    if args.quick:
        disposition = "QUICK_SMOKE_ONLY"
        reason = "Quick mode — not a real disposition. Re-run without --quick."
    elif fail_pf or fail_pass:
        disposition = "KILL_BB_RSI_LINE"
        reason = (
            f"Real best-of-grid is not distinguishable from return-shuffled nulls "
            f"(p_max_pf={p_max_pf:.3f}, p_n_passers={p_n_passers:.3f}). "
            "The gates measured the search, not the market. Do not tune further; "
            "do not promote. Cross-instrument / knob-cut only make sense after a pass."
        )
    elif real["n_passers"] <= _dist(null_n_pass).get("p90", 0):
        disposition = "WEAK_FAIL"
        reason = (
            f"p-values cleared 0.05 but real n_passers={real['n_passers']} is not above "
            f"null p90. Still not evidence of signal; keep promote=no."
        )
    else:
        disposition = "PASS_KEEP_RESEARCHING"
        reason = (
            f"Real max-stat sits outside the null (p_max_pf={p_max_pf:.3f}, "
            f"p_n_passers={p_n_passers:.3f}). Permission to continue the family "
            "(cut knobs, cross-instrument) — still not live_go / promote."
        )

    report = {
        "method": "return_shuffle_maxstat",
        "timestamp_utc": pd.Timestamp.utcnow().isoformat(),
        "window": {
            "holdout_start": str(cutoff),
            "bars": int(len(raw)),
            "start": raw["time"].iloc[0].isoformat(),
            "end": raw["time"].iloc[-1].isoformat(),
        },
        "costs": COSTS,
        "grid": {
            "max_n": args.max_n,
            "seed": args.seed,
            "n_configs": len(candidates),
        },
        "baseline_replay": baseline_replay,
        "real": real,
        "null": {
            "n_trials": args.n_null,
            "base_seed": args.null_seed,
            "workers": args.workers,
            "max_pf": _dist(null_max_pf),
            "max_score": _dist(null_max_score),
            "n_passers": _dist(null_n_pass),
            "n_early_exit": _dist(null_n_early),
            "p_max_pf": p_max_pf,
            "p_max_score": p_max_score,
            "p_n_passers": p_n_passers,
            "p_n_early_exit": p_n_early,
            "trials": null_rows,
        },
        "verdict": {
            "disposition": disposition,
            "reason": reason,
            "fail_max_pf": fail_pf,
            "fail_n_passers": fail_pass,
        },
        "elapsed_s": float(time.time() - t_all),
        "quick": bool(args.quick),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str) + "\n")
    write_markdown(report, OUT_MD)

    print(flush=True)
    print(f"Disposition: {disposition}", flush=True)
    print(reason, flush=True)
    print(f"Wrote {OUT_JSON.relative_to(ROOT)} and {OUT_MD.relative_to(ROOT)}", flush=True)
    print(f"Total elapsed: {report['elapsed_s']:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
