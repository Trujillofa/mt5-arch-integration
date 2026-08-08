#!/usr/bin/env python3
"""Null / max-stat test for the XAU Donchian turtle search grid.

Question: does best-of-~1200 Donchian configs on real develop bars sit outside
the distribution of best-of-grid on return-shuffled bars (no predictive
structure)?

If not, the gates measured the search, not the market — kill the Donchian line
rather than retune champions.

Protocol
--------
* Window: develop only (``time < holdout_start`` / 2026-01-01). Holdout sealed.
* Costs: ``strategy_params.json`` costs block → ``simulate_donchian`` kwargs.
* Data: ``load_h1`` + ``prepare_frame`` (donch channels, atr_pctile, day_id, …).
* Grid: ``grid_donchian()`` from ``xau_lane_deep_opt``; if huge, deterministic
  subsample ``max_n=1200`` seed=42. Always prepend frozen catalog Donchian
  entries (``baseline_donchian_turtle``, refined if present). No early exit.
* Null: same ``scramble_ohlc`` return-shuffle as ``xau_null_maxstat``; re-run
  ``prepare_frame`` each trial; re-score full grid. Default n_null=40, workers≤8.
* Gates: report classic ``passes`` and turtle ``soft_pass_expectancy``; primary
  decision stats are max_pf (n≥20 gated) and n_passers_soft.
* Decision: KILL_DONCHIAN_LINE if p_max_pf>0.05 OR p_n_passers>0.05;
  else PASS_KEEP_FROZEN (still promote=no / live_go=false).

Writes:
  results/xau_donchian_null_maxstat.json
  results/xau_donchian_null_maxstat.md

SAFETY: offline only — no live orders, no holdout selection, no champion retune.
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
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from xau_frozen_multi_year_eval import (  # noqa: E402
    soft_pass_expectancy,
)
from xau_lane_deep_opt import (  # noqa: E402
    grid_donchian,
    metrics_dict,
    prepare_frame,
    serializable_params,
)
from xau_lane_deep_opt import (
    simulate_donchian as _simulate_donchian,
)
from xau_null_core import scramble_ohlc  # noqa: E402

from backtest import (  # noqa: E402
    develop_only,
    holdout_start,
    load_h1,
    passes,
)

PARAMS_PATH = ROOT / "strategy_params.json"
CATALOG_PATH = ROOT / "results" / "xau_frozen_champions_catalog.json"
OUT_JSON = ROOT / "results" / "xau_donchian_null_maxstat.json"
OUT_MD = ROOT / "results" / "xau_donchian_null_maxstat.md"

from xau_research_costs import load_research_costs  # noqa: E402

# Research cost floor (Vantage RAW ECN); see results/xau_research_costs.json.
COSTS: dict[str, Any] = load_research_costs()

# Worker globals (fork COW on Linux; re-init on spawn).
_W: dict[str, Any] = {}

# Soft gate needs n≥40; max_pf gate stays n≥20 (thin PF=99 cannot dominate).
MIN_TRADES_MAX_PF = 20
MIN_TRADES_SOFT = 40


def simulate_donchian(d: pd.DataFrame, **kw):
    return _simulate_donchian(d, **{**COSTS, **kw})


def normalize_params(params: dict[str, Any]) -> dict[str, Any]:
    """Catalog / grid params → kwargs for simulate_donchian."""
    p = dict(params)
    p.pop("mode", None)
    hours = p.get("hours")
    if isinstance(hours, list):
        p["hours"] = tuple(hours) if hours else None
    elif hours is not None and not isinstance(hours, tuple):
        p["hours"] = None
    return p


def param_key(p: dict) -> str:
    return json.dumps(serializable_params(p), sort_keys=True, default=str)


def load_frozen_donchian_params() -> list[dict[str, Any]]:
    """Prepend baseline_donchian_turtle + refined Donchian entries if present."""
    if not CATALOG_PATH.is_file():
        return []
    cat = json.loads(CATALOG_PATH.read_text())
    entries = cat.get("entries") or []
    frozen: list[dict[str, Any]] = []
    # Prefer explicit baseline first, then any other donchian_turtle lane.
    ordered: list[dict] = []
    rest: list[dict] = []
    for e in entries:
        lane = str(e.get("lane") or e.get("family") or "")
        eid = str(e.get("id") or "")
        if lane != "donchian_turtle" and "donch" not in eid.lower():
            continue
        if eid == "baseline_donchian_turtle" or eid.startswith("baseline_donch"):
            ordered.append(e)
        else:
            rest.append(e)
    for e in ordered + rest:
        params = e.get("params") or {}
        if not isinstance(params, dict):
            continue
        frozen.append(normalize_params(params))
    return frozen


def build_donchian_candidates(*, max_n: int = 1200, seed: int = 42) -> list[dict]:
    """grid_donchian subsample + frozen catalog Donchian entries prepended."""
    grid, _axes = grid_donchian()
    grid = [normalize_params(p) for p in grid]
    if len(grid) > max_n:
        rng = np.random.default_rng(seed)
        idx = np.sort(rng.choice(len(grid), size=max_n, replace=False))
        grid = [grid[int(i)] for i in idx]

    frozen = load_frozen_donchian_params()
    out: list[dict] = []
    seen: set[str] = set()
    for p in frozen + grid:
        k = param_key(p)
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out


def classic_pass(m) -> bool:
    return bool(passes(m))


def soft_pass_m(m) -> bool:
    md = metrics_dict(m)
    return bool(soft_pass_expectancy(md))


def score_grid(
    d: pd.DataFrame,
    candidates: list[dict],
    *,
    progress_every: int = 0,
    label: str = "",
    min_trades: int = MIN_TRADES_MAX_PF,
) -> dict[str, Any]:
    """Score every Donchian candidate (no early exit). Returns summary + top rows.

    Max-stat for the null test is gated on ``n_trades >= min_trades`` so the
    PF=99 cap on 1–2 winning trades cannot dominate best-of-grid.
    """
    n = len(candidates)
    pfs = np.empty(n, dtype=float)
    nets = np.empty(n, dtype=float)
    wrs = np.empty(n, dtype=float)
    dds = np.empty(n, dtype=float)
    ntr = np.empty(n, dtype=int)
    exps = np.empty(n, dtype=float)
    classic_mask = np.zeros(n, dtype=bool)
    soft_mask = np.zeros(n, dtype=bool)

    best_pf_i = 0
    best_pf = -1.0
    best_min_pf_i = -1
    best_min_pf = -1.0
    best_soft_i = -1
    best_soft_exp = -1e18

    t0 = time.time()
    for i, p in enumerate(candidates):
        m = simulate_donchian(d, **p)
        md = metrics_dict(m)
        pfs[i] = m.profit_factor
        nets[i] = m.net_profit
        wrs[i] = m.win_rate
        dds[i] = m.max_drawdown_pct
        ntr[i] = m.n_trades
        exps[i] = float(md["expectancy"])
        classic_mask[i] = classic_pass(m)
        soft_mask[i] = soft_pass_expectancy(md)

        if m.profit_factor > best_pf or (
            m.profit_factor == best_pf and m.net_profit > nets[best_pf_i]
        ):
            best_pf = float(m.profit_factor)
            best_pf_i = i
        if m.n_trades >= min_trades:
            if m.profit_factor > best_min_pf or (
                m.profit_factor == best_min_pf
                and best_min_pf_i >= 0
                and m.net_profit > nets[best_min_pf_i]
            ):
                best_min_pf = float(m.profit_factor)
                best_min_pf_i = i
        if soft_mask[i] and (
            exps[i] > best_soft_exp
            or (exps[i] == best_soft_exp and m.profit_factor > pfs[max(best_soft_i, 0)])
        ):
            best_soft_exp = exps[i]
            best_soft_i = i

        if progress_every and (i + 1) % progress_every == 0:
            print(
                f"  [{label}] {i + 1}/{n} "
                f"best_PF@>={min_trades}={best_min_pf:.3f} "
                f"classic={int(classic_mask[: i + 1].sum())} "
                f"soft={int(soft_mask[: i + 1].sum())} "
                f"({time.time() - t0:.0f}s)",
                flush=True,
            )

    def _row(i: int) -> dict:
        return {
            "index": int(i),
            "params": serializable_params(candidates[i]),
            "profit_factor": float(pfs[i]),
            "net_profit": float(nets[i]),
            "win_rate": float(wrs[i]),
            "max_drawdown_pct": float(dds[i]),
            "n_trades": int(ntr[i]),
            "expectancy": float(exps[i]),
            "passes_classic": bool(classic_mask[i]),
            "passes_soft": bool(soft_mask[i]),
        }

    eligible = ntr >= min_trades
    max_pf_min = float(pfs[eligible].max()) if eligible.any() else 0.0
    max_net_min = float(nets[eligible].max()) if eligible.any() else 0.0

    # Top by PF among n≥min_trades
    top_min_idx = np.argsort(-np.where(eligible, pfs, -1e18))[:20]
    top_soft_idx = np.argsort(-np.where(soft_mask, exps, -1e18))[:20]

    return {
        "n_configs": n,
        "min_trades_gate": min_trades,
        "min_trades_soft": MIN_TRADES_SOFT,
        "elapsed_s": float(time.time() - t0),
        "best_by_pf": _row(best_pf_i),
        "best_by_pf_min_trades": _row(best_min_pf_i) if best_min_pf_i >= 0 else None,
        "best_soft_passer": _row(best_soft_i) if best_soft_i >= 0 else None,
        "n_passers_classic": int(classic_mask.sum()),
        "n_passers_soft": int(soft_mask.sum()),
        # Alias used as primary decision n_passers
        "n_passers": int(soft_mask.sum()),
        "n_with_min_trades": int(eligible.sum()),
        "pf": {
            "max_raw": float(pfs.max()) if n else 0.0,
            "max_min_trades": max_pf_min,
            "p50": float(np.median(pfs)) if n else 0.0,
            "p90": float(np.quantile(pfs, 0.90)) if n else 0.0,
            "p99": float(np.quantile(pfs, 0.99)) if n else 0.0,
            "mean": float(pfs.mean()) if n else 0.0,
        },
        "net_profit": {
            "max_raw": float(nets.max()) if n else 0.0,
            "max_min_trades": max_net_min,
            "p50": float(np.median(nets)) if n else 0.0,
            "mean": float(nets.mean()) if n else 0.0,
        },
        "top20_by_pf_min_trades": [
            _row(int(i)) for i in top_min_idx if eligible[int(i)]
        ],
        "top20_soft_passers": [
            _row(int(i)) for i in top_soft_idx if soft_mask[int(i)]
        ],
        # decision stats (gated)
        "max_pf": max_pf_min,
        "max_net": max_net_min,
        "max_pf_raw": float(pfs.max()) if n else 0.0,
    }


def _init_worker(raw_records: list, candidates: list[dict], costs: dict) -> None:
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
    d = prepare_frame(scr)
    summary = score_grid(d, candidates, progress_every=0, label=f"null{trial}")
    return {
        "trial": trial,
        "seed": int(base_seed + trial * 1_000_003),
        "max_pf": summary["max_pf"],
        "max_net": summary["max_net"],
        "n_passers": summary["n_passers"],
        "n_passers_soft": summary["n_passers_soft"],
        "n_passers_classic": summary["n_passers_classic"],
        "best_by_pf": summary["best_by_pf"],
        "best_by_pf_min_trades": summary["best_by_pf_min_trades"],
        "elapsed_s": summary["elapsed_s"],
    }


def _pvalue(null_vals: list[float], real: float) -> float:
    """One-sided: P(null >= real). Add-one smoothing so p never hits 0."""
    if not null_vals:
        return 1.0
    hits = sum(1 for v in null_vals if v >= real)
    return (hits + 1) / (len(null_vals) + 1)


def write_markdown(report: dict, path: Path) -> None:
    real = report["real"]
    null = report["null"]
    verdict = report["verdict"]
    lines = [
        "# XAU Donchian null / max-stat test",
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
        f"(max_n={report['grid']['max_n']}, seed={report['grid']['seed']}, "
        f"frozen_prepended={report['grid']['n_frozen_prepended']}) — no early exit",
        f"- Null: {null['n_trials']} return-shuffle trials, base_seed={null['base_seed']}, "
        f"workers={null['workers']}",
        f"- Costs: `{json.dumps(report['costs'])}`",
        "- Soft gates (turtle): PF≥1.5, n≥40, DD≤12, expectancy≥20",
        "- Classic gates: n≥20, PF>1.5, WR>55, DD<10",
        "",
        "## Real grid (develop, costed)",
        "",
        "Max-stat is gated on `n_trades >= 20` so the PF=99 thin-sample cap cannot dominate.",
        "Primary n_passers = soft (turtle expectancy gates).",
        "",
        "| Stat | Value |",
        "|---|---|",
        f"| max PF (n≥20) | {real['max_pf']:.4f} |",
        f"| max net (n≥20) | ${real['max_net']:.2f} |",
        f"| max PF raw (incl. thin) | {real.get('max_pf_raw', real['max_pf']):.4f} |",
        f"| n_passers_soft (primary) | {real['n_passers_soft']} |",
        f"| n_passers_classic | {real['n_passers_classic']} |",
        f"| n with ≥20 trades | {real.get('n_with_min_trades', '?')} |",
        f"| PF p50 / p90 / p99 | {real['pf']['p50']:.3f} / {real['pf']['p90']:.3f} / {real['pf']['p99']:.3f} |",
        f"| elapsed | {real['elapsed_s']:.0f}s |",
        "",
        "Best by PF among n≥20:",
        "",
        "```json",
        json.dumps(real.get("best_by_pf_min_trades") or real["best_by_pf"], indent=2),
        "```",
        "",
        "Frozen catalog baselines on same window:",
        "",
        "```json",
        json.dumps(report.get("frozen_replay"), indent=2),
        "```",
        "",
        "## Null distribution (best-of-grid per trial, n≥20 gated PF / soft passers)",
        "",
        "| Stat | null max | null p50 | null p90 | p(null ≥ real) |",
        "|---|---|---|---|---|",
        f"| max PF (n≥20) | {null['max_pf']['max']:.4f} | {null['max_pf']['p50']:.4f} | "
        f"{null['max_pf']['p90']:.4f} | **{null['p_max_pf']:.3f}** |",
        f"| n_passers_soft | {null['n_passers']['max']} | {null['n_passers']['p50']:.1f} | "
        f"{null['n_passers']['p90']:.1f} | **{null['p_n_passers']:.3f}** |",
        f"| n_passers_classic | {null['n_passers_classic']['max']} | "
        f"{null['n_passers_classic']['p50']:.1f} | {null['n_passers_classic']['p90']:.1f} | "
        f"**{null['p_n_passers_classic']:.3f}** |",
        "",
        "## Decision rule",
        "",
        "- Fail (`KILL_DONCHIAN_LINE`) if `p_max_pf > 0.05` **or** `p_n_passers > 0.05` —",
        "  real best-of-grid is typical of noise under the same search.",
        "- Pass (`PASS_KEEP_FROZEN`) only if both p-values ≤ 0.05 — still **not** live_go;",
        "  only permission to keep the frozen Donchian entries (promote=no).",
        "- Do not retune champions from this script.",
        "",
        f"Elapsed total: {report['elapsed_s']:.0f}s",
        "",
        f"promote=no | live_go=false | quick={report.get('quick', False)}",
        "",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-null", type=int, default=40, help="null trials (default 40)")
    ap.add_argument("--max-n", type=int, default=1200, help="grid subsample size (default 1200)")
    ap.add_argument("--seed", type=int, default=42, help="grid subsample seed")
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

    args.workers = max(1, min(8, int(args.workers)))

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

    frozen = load_frozen_donchian_params()
    candidates = build_donchian_candidates(max_n=args.max_n, seed=args.seed)
    print(
        f"Grid: {len(candidates)} configs (max_n={args.max_n}, seed={args.seed}, "
        f"frozen_prepended={len(frozen)})",
        flush=True,
    )

    # --- real ---
    print("Scoring REAL Donchian grid (no early exit)...", flush=True)
    d_real = prepare_frame(raw)
    real = score_grid(
        d_real,
        candidates,
        progress_every=args.progress_every,
        label="real",
    )

    # Frozen catalog replay on same window + costs
    frozen_replay: list[dict] = []
    for i, p in enumerate(frozen):
        m = simulate_donchian(d_real, **p)
        md = metrics_dict(m)
        frozen_replay.append(
            {
                "index": i,
                "params": serializable_params(p),
                **md,
                "passes_classic": classic_pass(m),
                "passes_soft": soft_pass_expectancy(md),
            }
        )
    print(
        f"REAL: max_PF(n≥20)={real['max_pf']:.4f} "
        f"soft_passers={real['n_passers_soft']} classic_passers={real['n_passers_classic']} "
        f"(raw max_PF={real['max_pf_raw']:.1f})",
        flush=True,
    )

    # --- nulls ---
    print(
        f"Running {args.n_null} null trials with {args.workers} workers...",
        flush=True,
    )
    raw_records = raw.to_dict(orient="records")
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
                    f"max_PF={row['max_pf']:.3f} soft={row['n_passers_soft']} "
                    f"classic={row['n_passers_classic']} ({row['elapsed_s']:.0f}s)",
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
                        f"max_PF={row['max_pf']:.3f} soft={row['n_passers_soft']} "
                        f"classic={row['n_passers_classic']} ({row['elapsed_s']:.0f}s)",
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
    null_n_soft = [float(r["n_passers_soft"]) for r in null_rows]
    null_n_classic = [float(r["n_passers_classic"]) for r in null_rows]

    p_max_pf = _pvalue(null_max_pf, real["max_pf"])
    p_n_passers = _pvalue(null_n_soft, float(real["n_passers_soft"]))
    p_n_classic = _pvalue(null_n_classic, float(real["n_passers_classic"]))

    fail_pf = p_max_pf > 0.05
    fail_pass = p_n_passers > 0.05
    if args.quick:
        disposition = "QUICK_SMOKE_ONLY"
        reason = "Quick mode — not a real disposition. Re-run without --quick."
    elif fail_pf or fail_pass:
        disposition = "KILL_DONCHIAN_LINE"
        reason = (
            f"Real best-of-Donchian-grid is not distinguishable from return-shuffled nulls "
            f"(p_max_pf={p_max_pf:.3f}, p_n_passers={p_n_passers:.3f}). "
            "The gates measured the search, not the market. Do not retune champions; "
            "do not promote. promote=no / live_go=false."
        )
    else:
        disposition = "PASS_KEEP_FROZEN"
        reason = (
            f"Real max-stat sits outside the null (p_max_pf={p_max_pf:.3f}, "
            f"p_n_passers={p_n_passers:.3f}). Keep frozen Donchian entries only — "
            "still promote=no / live_go=false. Do not retune."
        )

    report = {
        "method": "return_shuffle_maxstat_donchian",
        "lane": "donchian_turtle",
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
            "n_frozen_prepended": len(frozen),
            "source": "grid_donchian + frozen catalog prepend",
        },
        "gates": {
            "classic": "n>=20, PF>1.5, WR>55, DD<10",
            "soft_pass_expectancy": "PF>=1.5, n>=40, DD<=12, expectancy>=20",
            "primary_n_passers": "soft_pass_expectancy",
            "max_pf_min_trades": MIN_TRADES_MAX_PF,
        },
        "frozen_replay": frozen_replay,
        "real": real,
        "null": {
            "n_trials": args.n_null,
            "base_seed": args.null_seed,
            "workers": args.workers,
            "max_pf": _dist(null_max_pf),
            "n_passers": _dist(null_n_soft),
            "n_passers_classic": _dist(null_n_classic),
            "p_max_pf": p_max_pf,
            "p_n_passers": p_n_passers,
            "p_n_passers_classic": p_n_classic,
            "trials": null_rows,
        },
        "verdict": {
            "disposition": disposition,
            "reason": reason,
            "fail_max_pf": fail_pf,
            "fail_n_passers": fail_pass,
            "promote": False,
            "live_go": False,
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
