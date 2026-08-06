#!/usr/bin/env python3
"""Donchian turtle expectancy-centric develop ablations (KEEP_OPTIMIZING priority #1).

SAFETY:
  - Develop only (time < 2026-01-01). NEVER read holdout for param choice.
  - Offline research only. NEVER --live. No orders.
  - Do not re-tune for promote claims on the contaminated 2026-01+ window.

Goals (from xau_lane_deep_opt_summary / skeptic):
  1. Pre-register expectancy-centric promote gates (WR secondary for turtles).
  2. BE / partial_tp / exit / risk ablations around frozen develop champion.
  3. Optional secondary refine on expectancy_sqrt_n (develop only).
  4. Report which structural levers move expectancy vs WR without mining holdout.

Writes:
  results/xau_donchian_expectancy_ablate.json
  results/xau_donchian_expectancy_ablate.md
"""
from __future__ import annotations

import json
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from backtest import load_h1  # noqa: E402
from xau_lane_deep_opt import (  # noqa: E402
    HOLDOUT_START,
    metrics_dict,
    prepare_frame,
    score_expectancy_sqrt,
    serializable_params,
    simulate_donchian,
)

OUT_JSON = ROOT / "results" / "xau_donchian_expectancy_ablate.json"
OUT_MD = ROOT / "results" / "xau_donchian_expectancy_ablate.md"
CHAMPIONS = ROOT / "results" / "xau_lane_champions.json"

# ---------------------------------------------------------------------------
# Pre-registered gates (turtle / expectancy thesis) — frozen BEFORE looking
# at any ablation ranking outcomes beyond baseline recompute.
# ---------------------------------------------------------------------------
PREREG_PROMOTE_GATES_DEVELOP = {
    "objective": "expectancy_sqrt_n primary; WR is diagnostic only",
    "hard_gates_develop_diagnostic": {
        "profit_factor": 1.5,
        "expectancy": 20.0,
        "expectancy_sqrt_n": 150.0,
        "max_drawdown_pct": 12.0,
        "n_trades": 40,
        "win_rate_floor_diagnostic_only": 35.0,
        "note": "WR>55 classic hard gate is MISMATCHED for turtles; not used for pass/fail here",
    },
    "future_virgin_holdout_gates": {
        "profit_factor": 1.4,
        "expectancy": 15.0,
        "expectancy_sqrt_n": 80.0,
        "max_drawdown_pct": 12.0,
        "n_trades": 20,
        "win_rate": None,
        "win_rate_note": "WR not a hard gate for turtle promote claims; report only",
        "require_virgin_bars": True,
        "forbid_retune_on_holdout": True,
    },
    "safety": "offline research only; never --live; no holdout-guided search",
}


def load_champion_params() -> dict[str, Any]:
    data = json.loads(CHAMPIONS.read_text())
    for row in data["per_lane_champions"]:
        if row["lane_id"] == "donchian_turtle":
            p = dict(row["params"])
            p.pop("mode", None)
            # normalize hours list → tuple if present
            if isinstance(p.get("hours"), list):
                p["hours"] = tuple(p["hours"]) if p["hours"] else None
            return p
    raise SystemExit("donchian_turtle champion not found in xau_lane_champions.json")


def eval_params(d: pd.DataFrame, params: dict) -> dict[str, Any]:
    m = simulate_donchian(d, **params)
    md = metrics_dict(m)
    md["score_expectancy_sqrt"] = float(score_expectancy_sqrt(m))
    return md


def passes_prereg(md: dict[str, Any], gates: dict[str, Any]) -> dict[str, Any]:
    g = gates
    checks = {
        "pf": float(md["profit_factor"]) >= float(g["profit_factor"]),
        "expectancy": float(md["expectancy"]) >= float(g["expectancy"]),
        "expectancy_sqrt_n": float(md["expectancy_sqrt_n"]) >= float(g["expectancy_sqrt_n"]),
        "dd": float(md["max_drawdown_pct"]) <= float(g["max_drawdown_pct"]),
        "n": int(md["n_trades"]) >= int(g["n_trades"]),
    }
    wr_floor = g.get("win_rate_floor_diagnostic_only")
    wr_ok = True
    if wr_floor is not None:
        wr_ok = float(md["win_rate"]) >= float(wr_floor)
    return {
        "hard_pass_expectancy": all(checks.values()),
        "checks": checks,
        "wr_diagnostic_ok": wr_ok,
        "wr_not_a_hard_gate": True,
    }


def ablation_grid(base: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Structured one-factor and small multi-factor ablations around champion."""
    rows: list[tuple[str, dict[str, Any]]] = []

    def add(tag: str, **overrides: Any) -> None:
        p = deepcopy(base)
        p.update(overrides)
        if isinstance(p.get("hours"), list):
            p["hours"] = tuple(p["hours"]) if p["hours"] else None
        rows.append((tag, p))

    add("baseline_champion")

    # BE ablations
    for r in (0.5, 1.0, 1.5, 2.0):
        add(f"be_at_r={r}", be_at_r=r)

    # Partial TP ablations
    for r, frac in ((1.0, 0.5), (1.5, 0.5), (2.0, 0.5), (1.5, 0.33), (1.5, 0.67)):
        add(f"partial_tp_r={r}_frac={frac}", partial_tp=True, partial_tp_r=r, partial_frac=frac)

    # BE + partial combined
    add("be_1.0_plus_partial_1.5", be_at_r=1.0, partial_tp=True, partial_tp_r=1.5, partial_frac=0.5)
    add("be_1.0_plus_partial_1.0", be_at_r=1.0, partial_tp=True, partial_tp_r=1.0, partial_frac=0.5)

    # Exit channel on/off
    add("exit_channel_off", exit_on_exit_channel=False)
    add("exit_channel_off_be_1.0", exit_on_exit_channel=False, be_at_r=1.0)

    # Exit_N sweep (trail-like shorter/longer exit)
    for xn in (5, 8, 10, 12, 15, 20):
        add(f"exit_N={xn}", exit_N=xn)

    # Entry_N neighborhood
    for en in (15, 20, 24, 30, 55):
        add(f"entry_N={en}", entry_N=en)

    # atr_sl sweep
    for a in (1.0, 1.5, 2.0, 2.5, 3.0):
        add(f"atr_sl={a}", atr_sl=a)

    # Max entries / day
    for m in (1, 2, 3):
        add(f"max_entries_per_day={m}", max_entries_per_day=m)

    # H4 bias
    add("h4_bias=True", h4_bias=True)
    add("h4_bias=True_be_1.0", h4_bias=True, be_at_r=1.0)

    # Mid-channel filter
    for k in (0.5, 1.0, 1.5):
        add(f"mid_channel_k={k}", mid_channel_k=k)

    # ATR regime filter
    for a in (0.40, 0.50, 0.55):
        add(f"atr_min_pct={a}", atr_min_pct=a)

    # Session
    add("hours_london_ny", hours=tuple(range(7, 17)))
    add("hours_london_ny_late", hours=tuple(range(12, 21)))

    # Failed breakout fade
    add("failed_breakout_fade=True", failed_breakout_fade=True)

    # Cooldown
    for c in (0, 1, 2, 4):
        add(f"cooldown={c}", cooldown=c)

    # Multi-lever “risk hygiene” packs (pre-registered bundles, not holdout mined)
    add(
        "pack_be_partial_exit12",
        be_at_r=1.0,
        partial_tp=True,
        partial_tp_r=1.5,
        partial_frac=0.5,
        exit_N=12,
    )
    add(
        "pack_turtle_classic_strict",
        entry_N=20,
        exit_N=10,
        atr_sl=2.0,
        be_at_r=None,
        partial_tp=False,
        max_entries_per_day=1,
    )
    add(
        "pack_expectancy_widen_stop",
        entry_N=20,
        exit_N=10,
        atr_sl=2.5,
        be_at_r=None,
        partial_tp=False,
    )
    add(
        "pack_h4_be_max1",
        h4_bias=True,
        be_at_r=1.0,
        max_entries_per_day=1,
    )
    add(
        "pack_partial_exit8_atr2",
        partial_tp=True,
        partial_tp_r=1.5,
        partial_frac=0.5,
        exit_N=8,
        atr_sl=2.0,
    )

    # dedupe by serialized params (keep first tag)
    seen: set[str] = set()
    out: list[tuple[str, dict[str, Any]]] = []
    for tag, p in rows:
        key = json.dumps(serializable_params(p), sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        out.append((tag, p))
    return out


def secondary_refine(
    d: pd.DataFrame,
    base: dict[str, Any],
    budget: int = 120,
) -> list[dict[str, Any]]:
    """Small Cartesian refine around champion on expectancy score (develop only)."""
    axes = {
        "entry_N": [15, 20, 24, 30],
        "exit_N": [5, 8, 10, 12, 15],
        "atr_sl": [1.5, 2.0, 2.5],
        "be_at_r": [None, 1.0],
        "partial_tp": [False, True],
        "max_entries_per_day": [1, 2],
        "h4_bias": [False, True],
    }
    combos: list[dict[str, Any]] = []
    keys = list(axes.keys())
    import itertools

    for vals in itertools.product(*[axes[k] for k in keys]):
        p = deepcopy(base)
        for k, v in zip(keys, vals):
            p[k] = v
        if p.get("partial_tp"):
            p.setdefault("partial_tp_r", 1.5)
            p.setdefault("partial_frac", 0.5)
        else:
            p["partial_tp"] = False
        combos.append(p)

    # stratified subsample if over budget
    if len(combos) > budget:
        step = max(1, len(combos) // budget)
        combos = combos[::step][:budget]

    results = []
    for p in combos:
        md = eval_params(d, p)
        results.append(
            {
                "params": serializable_params(p),
                "metrics": md,
                "score": md["score_expectancy_sqrt"],
            }
        )
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def write_md(payload: dict[str, Any]) -> str:
    base = payload["baseline"]
    bm = base["metrics"]
    top_abl = payload["ablations_ranked"][:12]
    top_ref = payload["secondary_refine_top"][:8]
    pr = payload["preregistered_gates"]
    lines = [
        "# Donchian turtle — expectancy-centric develop ablations",
        "",
        f"**Timestamp (UTC):** {payload['created']}",
        f"**Window:** develop only (`time < {payload['holdout_start']}`); holdout sealed / unused",
        f"**Safety:** {payload['safety']}",
        f"**n_ablations:** {payload['n_ablations']} | **secondary_refine_evals:** {payload['n_secondary_refine']}",
        "",
        "## Pre-registered promote gates (before ranking)",
        "",
        "### Develop diagnostic (expectancy thesis)",
        "```json",
        json.dumps(pr["hard_gates_develop_diagnostic"], indent=2),
        "```",
        "",
        "### Future virgin holdout (not run this fire)",
        "```json",
        json.dumps(pr["future_virgin_holdout_gates"], indent=2),
        "```",
        "",
        "## Baseline champion (frozen from deep opt)",
        "",
        f"- Params: `{json.dumps(base['params'], sort_keys=True)}`",
        f"- PF={bm['profit_factor']:.3f} WR={bm['win_rate']:.1f}% DD={bm['max_drawdown_pct']:.2f}% "
        f"n={bm['n_trades']} NP={bm['net_profit']:.1f}",
        f"- expectancy={bm['expectancy']:.2f} exp√n={bm['expectancy_sqrt_n']:.1f} "
        f"score={bm['score_expectancy_sqrt']:.1f}",
        f"- Pre-reg develop hard_pass_expectancy: **{base['gate_eval']['hard_pass_expectancy']}**",
        "",
        "## Ablation ranking (develop score_expectancy_sqrt)",
        "",
        "| Rank | Tag | PF | WR% | DD% | n | NP | exp | exp√n | score | vs base Δscore |",
        "|-----:|-----|---:|----:|----:|--:|---:|----:|------:|------:|---------------:|",
    ]
    bsc = bm["score_expectancy_sqrt"]
    for i, row in enumerate(top_abl, 1):
        m = row["metrics"]
        lines.append(
            f"| {i} | `{row['tag']}` | {m['profit_factor']:.3f} | {m['win_rate']:.1f} | "
            f"{m['max_drawdown_pct']:.2f} | {m['n_trades']} | {m['net_profit']:.0f} | "
            f"{m['expectancy']:.1f} | {m['expectancy_sqrt_n']:.1f} | {m['score_expectancy_sqrt']:.1f} | "
            f"{m['score_expectancy_sqrt'] - bsc:+.1f} |"
        )
    lines += [
        "",
        "## Key one-factor effects (delta score vs baseline)",
        "",
    ]
    for name, delta in payload["factor_deltas"][:15]:
        lines.append(f"- `{name}`: Δscore={delta:+.1f}")

    lines += [
        "",
        "## Secondary refine top (Cartesian neighborhood, develop only)",
        "",
        "| Rank | PF | WR% | DD% | n | NP | exp√n | score | highlight params |",
        "|-----:|---:|----:|----:|--:|---:|------:|------:|------------------|",
    ]
    for i, row in enumerate(top_ref, 1):
        m = row["metrics"]
        p = row["params"]
        hl = {
            k: p.get(k)
            for k in (
                "entry_N",
                "exit_N",
                "atr_sl",
                "be_at_r",
                "partial_tp",
                "max_entries_per_day",
                "h4_bias",
            )
        }
        lines.append(
            f"| {i} | {m['profit_factor']:.3f} | {m['win_rate']:.1f} | {m['max_drawdown_pct']:.2f} | "
            f"{m['n_trades']} | {m['net_profit']:.0f} | {m['expectancy_sqrt_n']:.1f} | "
            f"{m['score_expectancy_sqrt']:.1f} | `{json.dumps(hl, sort_keys=True)}` |"
        )

    best = payload["best_develop_candidate"]
    bm2 = best["metrics"]
    lines += [
        "",
        "## Best develop candidate (ablation ∪ refine; NOT holdout-confirmed)",
        "",
        f"- Source: **{best['source']}** / tag=`{best.get('tag', 'n/a')}`",
        f"- PF={bm2['profit_factor']:.3f} WR={bm2['win_rate']:.1f}% DD={bm2['max_drawdown_pct']:.2f}% "
        f"n={bm2['n_trades']} NP={bm2['net_profit']:.1f} exp√n={bm2['expectancy_sqrt_n']:.1f}",
        f"- Pre-reg develop hard_pass_expectancy: **{best['gate_eval']['hard_pass_expectancy']}**",
        f"- Params: `{json.dumps(best['params'], sort_keys=True)}`",
        "",
        "## Disposition",
        "",
        f"- Lane remains **KEEP_OPTIMIZING** (not KILL).",
        f"- Baseline already meets pre-reg develop expectancy gates: "
        f"**{base['gate_eval']['hard_pass_expectancy']}**.",
        f"- Classic WR>55 gate still fails on turtle shapes by design — do not kill on WR.",
        f"- **No holdout re-eval this fire** (contaminated window; virgin bars not available past last peek).",
        f"- Live promote: **NO-GO**. Next: optional atr_trail trade-count work, or virgin holdout when data > last peeked end.",
        "",
        "*Offline research only; never --live.*",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    t0 = time.time()
    print("Loading H1 + indicators (develop only) ...", flush=True)
    raw = load_h1()
    d = prepare_frame(raw)
    times = pd.to_datetime(d["time"], utc=True)
    develop = d.loc[times < HOLDOUT_START].reset_index(drop=True)
    print(f"develop bars={len(develop)} holdout sealed unused", flush=True)

    base_params = load_champion_params()
    # ensure sim kwargs clean
    base_params.setdefault("cooldown", 2)
    base_params.setdefault("exit_on_exit_channel", True)
    base_params.setdefault("long_only", True)
    base_params.setdefault("risk_pct", 0.01)

    base_m = eval_params(develop, base_params)
    base_gate = passes_prereg(base_m, PREREG_PROMOTE_GATES_DEVELOP["hard_gates_develop_diagnostic"])
    print(
        f"baseline PF={base_m['profit_factor']:.3f} n={base_m['n_trades']} "
        f"WR={base_m['win_rate']:.1f} exp√n={base_m['expectancy_sqrt_n']:.1f} "
        f"gate={base_gate['hard_pass_expectancy']}",
        flush=True,
    )

    abl = ablation_grid(base_params)
    abl_rows = []
    for i, (tag, p) in enumerate(abl, 1):
        md = eval_params(develop, p)
        abl_rows.append(
            {
                "tag": tag,
                "params": serializable_params(p),
                "metrics": md,
                "gate_eval": passes_prereg(
                    md, PREREG_PROMOTE_GATES_DEVELOP["hard_gates_develop_diagnostic"]
                ),
            }
        )
        if i % 20 == 0:
            print(f"  ablations {i}/{len(abl)}", flush=True)

    abl_rows.sort(key=lambda x: x["metrics"]["score_expectancy_sqrt"], reverse=True)

    # one-factor deltas for tags that are single-override style
    bsc = base_m["score_expectancy_sqrt"]
    factor_deltas = []
    for row in abl_rows:
        tag = row["tag"]
        if tag == "baseline_champion":
            continue
        factor_deltas.append((tag, row["metrics"]["score_expectancy_sqrt"] - bsc))
    factor_deltas.sort(key=lambda x: abs(x[1]), reverse=True)

    print(f"Secondary refine (budget=120) ...", flush=True)
    refine = secondary_refine(develop, base_params, budget=120)

    # best overall
    best_abl = abl_rows[0]
    best_ref = refine[0]
    if best_ref["score"] > best_abl["metrics"]["score_expectancy_sqrt"]:
        best = {
            "source": "secondary_refine",
            "tag": "refine_top1",
            "params": best_ref["params"],
            "metrics": best_ref["metrics"],
            "gate_eval": passes_prereg(
                best_ref["metrics"],
                PREREG_PROMOTE_GATES_DEVELOP["hard_gates_develop_diagnostic"],
            ),
        }
    else:
        best = {
            "source": "ablation",
            "tag": best_abl["tag"],
            "params": best_abl["params"],
            "metrics": best_abl["metrics"],
            "gate_eval": best_abl["gate_eval"],
        }

    payload = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "safety": "offline research only; never --live; develop only; holdout unused",
        "holdout_start": str(HOLDOUT_START),
        "holdout_used": False,
        "develop_bars": int(len(develop)),
        "preregistered_gates": PREREG_PROMOTE_GATES_DEVELOP,
        "baseline": {
            "params": serializable_params(base_params),
            "metrics": base_m,
            "gate_eval": base_gate,
        },
        "n_ablations": len(abl_rows),
        "ablations_ranked": abl_rows,
        "factor_deltas": factor_deltas,
        "n_secondary_refine": len(refine),
        "secondary_refine_top": refine[:20],
        "best_develop_candidate": best,
        "seconds": round(time.time() - t0, 2),
        "disposition": {
            "lane": "donchian_turtle",
            "status": "KEEP_OPTIMIZING",
            "live_go": False,
            "kill": False,
            "note": "Expectancy gates pre-registered; ablations develop-only; no virgin holdout yet",
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str))
    OUT_MD.write_text(write_md(payload))
    print(f"Wrote {OUT_JSON}", flush=True)
    print(f"Wrote {OUT_MD}", flush=True)
    print(
        f"BEST source={best['source']} tag={best.get('tag')} "
        f"PF={best['metrics']['profit_factor']:.3f} n={best['metrics']['n_trades']} "
        f"exp√n={best['metrics']['expectancy_sqrt_n']:.1f} "
        f"gate={best['gate_eval']['hard_pass_expectancy']} ({payload['seconds']}s)",
        flush=True,
    )


if __name__ == "__main__":
    main()
