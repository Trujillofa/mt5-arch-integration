#!/usr/bin/env python3
"""HTF Fib XAU — widen entries post-fix (KEEP_OPTIMIZING priority #3).

SAFETY:
  - Develop only (time < 2026-01-01). NEVER use holdout for param choice.
  - Offline research only. NEVER --live. No orders.
  - Fib pivot stamp is causal via htf_fib_core (active = c+right). No retune on sealed HO.

Thesis (deep-opt skeptic):
  Post-fix champion: develop n=17 PF 3.58; holdout n=14 underpowered.
  Need n≥20 path on develop via careful widen of fib zone / cooldown / RSI /
  pivot geometry before any future virgin sealed look.

Writes:
  results/xau_htf_fib_widen_entries.json
  results/xau_htf_fib_widen_entries.md
"""
from __future__ import annotations

import itertools
import json
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

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
    score_fib,
    serializable_params,
    simulate_htf_fib_enhanced,
)

OUT_JSON = ROOT / "results" / "xau_htf_fib_widen_entries.json"
OUT_MD = ROOT / "results" / "xau_htf_fib_widen_entries.md"
CHAMPIONS = ROOT / "results" / "xau_lane_champions.json"

PREREG = {
    "objective": "raise develop n toward ≥20–30 while PF/DD floors hold (post-fix sparse sample)",
    "develop_hard_floors": {
        "profit_factor": 1.3,
        "max_drawdown_pct": 10.0,
        "n_trades_min": 20,
        "n_trades_target": 30,
        "win_rate_diagnostic_floor": 50.0,
        "expectancy_min": 15.0,
    },
    "score": "score_fib + 12*n if n>=15; hard floor fail heavily penalized",
    "future_virgin_holdout": {
        "require_virgin_bars_after": "2026-08-06 (last peeked data end)",
        "gates": {
            "profit_factor": 1.5,
            "win_rate": 55.0,
            "max_drawdown_pct": 10.0,
            "n_trades": 20,
        },
        "forbid_retune_on_holdout": True,
    },
    "safety": "offline research only; never --live; holdout unused this fire",
    "note": "fib confirmation fixed; residual H4 left-label bucket caveat remains",
}


def load_champion() -> dict[str, Any]:
    data = json.loads(CHAMPIONS.read_text())
    for row in data["per_lane_champions"]:
        if row["lane_id"] == "htf_fib_xau":
            p = dict(row["params"])
            p.pop("mode", None)
            if isinstance(p.get("hours"), list):
                p["hours"] = tuple(p["hours"]) if p["hours"] else None
            return p
    raise SystemExit("htf_fib_xau champion missing")


def eval_params(d: pd.DataFrame, params: dict) -> dict[str, Any]:
    m = simulate_htf_fib_enhanced(d, **params)
    md = metrics_dict(m)
    md["score_fib"] = float(score_fib(m))
    return md


def n_path_score(md: dict[str, Any], floors: dict[str, Any]) -> float:
    from backtest import Metrics

    # rebuild Metrics-like scoring via score_fib fields already in md
    n = int(md["n_trades"])
    pf = float(md["profit_factor"])
    dd = float(md["max_drawdown_pct"])
    exp = float(md["expectancy"])
    s = float(md["score_fib"]) + float(n) * 12.0 + min(pf, 4.0) * 15.0
    if n >= int(floors["n_trades_min"]):
        s += 100.0
    if n >= int(floors["n_trades_target"]):
        s += 150.0
    if pf < float(floors["profit_factor"]):
        s -= 800.0 * (float(floors["profit_factor"]) - min(pf, float(floors["profit_factor"])))
    if dd > float(floors["max_drawdown_pct"]):
        s -= 50.0 * (dd - float(floors["max_drawdown_pct"]))
    if exp < float(floors["expectancy_min"]) and n >= 5:
        s -= 15.0 * (float(floors["expectancy_min"]) - exp)
    wr_f = floors.get("win_rate_diagnostic_floor")
    if wr_f is not None and n >= 8 and float(md["win_rate"]) < float(wr_f):
        s -= 2.0 * (float(wr_f) - float(md["win_rate"]))
    if n < 10:
        s -= 100.0
    return float(s)


def gate_eval(md: dict[str, Any], floors: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "pf": float(md["profit_factor"]) >= float(floors["profit_factor"]),
        "dd": float(md["max_drawdown_pct"]) <= float(floors["max_drawdown_pct"]),
        "n_min": int(md["n_trades"]) >= int(floors["n_trades_min"]),
        "expectancy": float(md["expectancy"]) >= float(floors["expectancy_min"]),
    }
    return {
        "hard_pass_n_path": all(checks.values()),
        "n_target_hit": int(md["n_trades"]) >= int(floors["n_trades_target"]),
        "checks": checks,
        "wr_diagnostic_ok": float(md["win_rate"])
        >= float(floors.get("win_rate_diagnostic_floor", 0)),
    }


def ablation_grid(base: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []

    def add(tag: str, **ov: Any) -> None:
        p = deepcopy(base)
        p.update(ov)
        if isinstance(p.get("hours"), list):
            p["hours"] = tuple(p["hours"]) if p["hours"] else None
        rows.append((tag, p))

    add("baseline_champion")

    # Widen fib zone (entry band)
    zones = [
        (0.5, 0.786),
        (0.5, 0.886),
        (0.382, 0.786),
        (0.382, 0.886),
        (0.618, 0.886),
        (0.5, 0.618),  # tighter mid
        (0.618, 0.786),  # champ
        (0.705, 0.786),
        (0.5, 1.0),
    ]
    for lo, hi in zones:
        add(f"fib={lo}-{hi}", fib_lo=lo, fib_hi=hi)

    # Pivot geometry (more pivots / faster confirm)
    for L, R in ((3, 3), (3, 5), (5, 3), (5, 5), (8, 3), (8, 5), (2, 2), (4, 3)):
        add(f"pivot_L{L}_R{R}", pivot_left=L, pivot_right=R)

    # Cooldown lower → more entries
    for c in (0, 1, 2, 3, 5):
        add(f"cooldown={c}", cooldown=c)

    # RSI long max widen
    for r in (30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0):
        add(f"rsi_long_max={r}", rsi_long_max=r)

    # RSI MA filter on/off
    add("use_rsi_ma_filter=True", use_rsi_ma_filter=True)
    add("use_rsi_ma_filter=False", use_rsi_ma_filter=False)

    # Bias filters
    add("require_ema200_bias=True", require_ema200_bias=True)
    add("require_ema200_bias=False", require_ema200_bias=False)
    add("h4_bias=True", h4_bias=True)
    add("h4_bias=False", h4_bias=False)

    # SL/TP
    for s in (1.0, 1.2, 1.5, 2.0, 2.5):
        add(f"sl_atr={s}", sl_atr=s)
    for t in (2.0, 2.5, 3.0, 3.5, 4.0):
        add(f"tp_atr={t}", tp_atr=t)

    # max entries
    for m in (1, 2, 3, 4):
        add(f"max_entries_per_day={m}", max_entries_per_day=m)

    # BE
    for b in (None, 1.0, 1.5):
        add(f"be_at_r={b}", be_at_r=b)

    # flat_only
    add("flat_only=False", flat_only=False)

    # Pre-registered widen packs
    add(
        "pack_wide_050_886_cd0",
        fib_lo=0.5,
        fib_hi=0.886,
        cooldown=0,
        rsi_long_max=45.0,
        max_entries_per_day=3,
    )
    add(
        "pack_wide_0382_786_rsi50",
        fib_lo=0.382,
        fib_hi=0.786,
        cooldown=0,
        rsi_long_max=50.0,
        pivot_left=3,
        pivot_right=3,
        max_entries_per_day=3,
    )
    add(
        "pack_n20_path_050_786",
        fib_lo=0.5,
        fib_hi=0.786,
        cooldown=0,
        rsi_long_max=45.0,
        pivot_left=5,
        pivot_right=3,
        sl_atr=1.2,
        tp_atr=3.0,
        max_entries_per_day=3,
    )
    add(
        "pack_fast_pivot_2_2_wide",
        pivot_left=2,
        pivot_right=2,
        fib_lo=0.5,
        fib_hi=0.886,
        cooldown=0,
        rsi_long_max=50.0,
        max_entries_per_day=3,
    )
    add(
        "pack_golden_plus_cd0",
        fib_lo=0.618,
        fib_hi=0.786,
        cooldown=0,
        rsi_long_max=45.0,
        max_entries_per_day=3,
        use_rsi_ma_filter=False,
    )
    add(
        "pack_balanced_n_quality",
        fib_lo=0.5,
        fib_hi=0.786,
        pivot_left=5,
        pivot_right=3,
        cooldown=1,
        rsi_long_max=40.0,
        sl_atr=1.5,
        tp_atr=3.0,
        max_entries_per_day=2,
    )
    add(
        "pack_very_wide_050_100",
        fib_lo=0.5,
        fib_hi=1.0,
        cooldown=0,
        rsi_long_max=55.0,
        max_entries_per_day=4,
        pivot_left=3,
        pivot_right=3,
    )

    seen: set[str] = set()
    out: list[tuple[str, dict[str, Any]]] = []
    for tag, p in rows:
        key = json.dumps(serializable_params(p), sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        out.append((tag, p))
    return out


def secondary_search(d: pd.DataFrame, base: dict[str, Any], budget: int = 150) -> list[dict]:
    axes = {
        "fib_lo": [0.382, 0.5, 0.618],
        "fib_hi": [0.786, 0.886, 1.0],
        "pivot_left": [3, 5, 8],
        "pivot_right": [2, 3, 5],
        "cooldown": [0, 1, 2],
        "rsi_long_max": [35.0, 40.0, 45.0, 50.0],
        "max_entries_per_day": [2, 3],
        "sl_atr": [1.2, 1.5],
        "tp_atr": [2.5, 3.0],
    }
    keys = list(axes.keys())
    combos = []
    for vals in itertools.product(*[axes[k] for k in keys]):
        p = deepcopy(base)
        for k, v in zip(keys, vals):
            p[k] = v
        if float(p["fib_lo"]) >= float(p["fib_hi"]):
            continue
        p.setdefault("use_rsi_ma_filter", False)
        p.setdefault("require_ema200_bias", False)
        p.setdefault("h4_bias", False)
        p.setdefault("flat_only", True)
        p.setdefault("be_at_r", None)
        combos.append(p)

    if len(combos) > budget:
        step = max(1, len(combos) // budget)
        combos = combos[::step][:budget]

    floors = PREREG["develop_hard_floors"]
    results = []
    for i, p in enumerate(combos, 1):
        md = eval_params(d, p)
        sc = n_path_score(md, floors)
        results.append(
            {
                "params": serializable_params(p),
                "metrics": md,
                "score": sc,
                "gate_eval": gate_eval(md, floors),
            }
        )
        if i % 40 == 0:
            print(f"  secondary {i}/{len(combos)}", flush=True)
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def write_md(payload: dict[str, Any]) -> str:
    floors = payload["preregistered"]["develop_hard_floors"]
    base = payload["baseline"]
    bm = base["metrics"]
    top = payload["ablations_ranked"][:12]
    top_ref = payload["secondary_top"][:8]
    best = payload["best_develop_candidate"]
    bsc = base["score"]
    lines = [
        "# HTF Fib XAU — widen entries post-fix (develop only)",
        "",
        f"**Timestamp (UTC):** {payload['created']}",
        f"**Window:** develop only (`time < {payload['holdout_start']}`); holdout sealed unused",
        f"**Safety:** {payload['safety']}",
        f"**n_ablations:** {payload['n_ablations']} | **secondary_evals:** {payload['n_secondary']}",
        "",
        "## Pre-registered floors",
        "```json",
        json.dumps(floors, indent=2),
        "```",
        "",
        "## Baseline champion (post-fix deep-opt freeze)",
        "",
        f"- Params: `{json.dumps(base['params'], sort_keys=True)}`",
        f"- PF={bm['profit_factor']:.3f} WR={bm['win_rate']:.1f}% DD={bm['max_drawdown_pct']:.2f}% "
        f"n={bm['n_trades']} NP={bm['net_profit']:.1f} exp√n={bm['expectancy_sqrt_n']:.1f}",
        f"- n_path_score={base['score']:.1f} | hard_pass_n_path="
        f"**{base['gate_eval']['hard_pass_n_path']}** "
        f"(n≥{floors['n_trades_min']}: {base['gate_eval']['checks']['n_min']})",
        "",
        "## Ablation ranking",
        "",
        "| Rank | Tag | PF | WR% | DD% | n | NP | exp√n | score | Δscore | gate |",
        "|-----:|-----|---:|----:|----:|--:|---:|------:|------:|-------:|:----:|",
    ]
    for i, row in enumerate(top, 1):
        m = row["metrics"]
        g = "Y" if row["gate_eval"]["hard_pass_n_path"] else "n"
        lines.append(
            f"| {i} | `{row['tag']}` | {m['profit_factor']:.3f} | {m['win_rate']:.1f} | "
            f"{m['max_drawdown_pct']:.2f} | {m['n_trades']} | {m['net_profit']:.0f} | "
            f"{m['expectancy_sqrt_n']:.1f} | {row['score']:.1f} | {row['score'] - bsc:+.1f} | {g} |"
        )
    lines += ["", "## Key factor deltas", ""]
    for name, delta in payload["factor_deltas"][:15]:
        lines.append(f"- `{name}`: Δscore={delta:+.1f}")

    lines += [
        "",
        "## Secondary search top",
        "",
        "| Rank | PF | WR% | DD% | n | NP | score | gate | highlight |",
        "|-----:|---:|----:|----:|--:|---:|------:|:----:|-----------|",
    ]
    for i, row in enumerate(top_ref, 1):
        m = row["metrics"]
        p = row["params"]
        hl = {
            k: p.get(k)
            for k in (
                "fib_lo",
                "fib_hi",
                "pivot_left",
                "pivot_right",
                "cooldown",
                "rsi_long_max",
                "max_entries_per_day",
            )
        }
        g = "Y" if row["gate_eval"]["hard_pass_n_path"] else "n"
        lines.append(
            f"| {i} | {m['profit_factor']:.3f} | {m['win_rate']:.1f} | {m['max_drawdown_pct']:.2f} | "
            f"{m['n_trades']} | {m['net_profit']:.0f} | {row['score']:.1f} | {g} | "
            f"`{json.dumps(hl, sort_keys=True)}` |"
        )

    bm2 = best["metrics"]
    bg = payload.get("best_gate_pass_candidate")
    lines += [
        "",
        "## Best develop candidate (NOT holdout-confirmed)",
        "",
        f"- Source: **{best['source']}** tag=`{best.get('tag', 'n/a')}`",
        f"- PF={bm2['profit_factor']:.3f} WR={bm2['win_rate']:.1f}% DD={bm2['max_drawdown_pct']:.2f}% "
        f"n={bm2['n_trades']} NP={bm2['net_profit']:.1f}",
        f"- hard_pass_n_path: **{best['gate_eval']['hard_pass_n_path']}** "
        f"| n_target≥{floors['n_trades_target']}: **{best['gate_eval']['n_target_hit']}**",
        f"- Params: `{json.dumps(best['params'], sort_keys=True)}`",
        "",
    ]
    if bg:
        m3 = bg["metrics"]
        lines += [
            "## Best gate-pass candidate",
            "",
            f"- Source: **{bg['source']}** tag=`{bg.get('tag', 'n/a')}`",
            f"- PF={m3['profit_factor']:.3f} WR={m3['win_rate']:.1f}% DD={m3['max_drawdown_pct']:.2f}% "
            f"n={m3['n_trades']} NP={m3['net_profit']:.1f}",
            f"- Params: `{json.dumps(bg['params'], sort_keys=True)}`",
            "",
        ]
    lines += [
        "## Disposition",
        "",
        f"- Lane **KEEP_OPTIMIZING** (not KILL).",
        f"- Baseline n={bm['n_trades']} "
        f"{'MEETS' if base['gate_eval']['hard_pass_n_path'] else 'MISSES'} n≥{floors['n_trades_min']}.",
        f"- Best n={bm2['n_trades']} (Δn {bm2['n_trades'] - bm['n_trades']:+d} vs baseline).",
        "- **No holdout re-eval** this fire (prior HO n=14 underpowered + contaminated window).",
        "- Live promote: **NO-GO**. After this fire, develop work on KEEP_OPTIMIZING lanes is largely done; next is virgin holdout when bars exist after 2026-08-06, or optional deeper refine without holdout peeks.",
        "",
        "*Offline research only; never --live.*",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    t0 = time.time()
    floors = PREREG["develop_hard_floors"]
    print("Loading H1 + indicators (develop only) ...", flush=True)
    raw = load_h1()
    d = prepare_frame(raw)
    times = pd.to_datetime(d["time"], utc=True)
    develop = d.loc[times < HOLDOUT_START].reset_index(drop=True)
    print(f"develop bars={len(develop)} holdout sealed unused", flush=True)

    base = load_champion()
    base.setdefault("flat_only", True)
    base.setdefault("long_only", True)
    base.setdefault("risk_pct", 0.01)
    base.setdefault("rsi_short_min", 60.0)

    base_m = eval_params(develop, base)
    base_sc = n_path_score(base_m, floors)
    base_g = gate_eval(base_m, floors)
    print(
        f"baseline PF={base_m['profit_factor']:.3f} n={base_m['n_trades']} "
        f"WR={base_m['win_rate']:.1f} score={base_sc:.1f} gate={base_g['hard_pass_n_path']}",
        flush=True,
    )

    abl = ablation_grid(base)
    abl_rows = []
    for i, (tag, p) in enumerate(abl, 1):
        md = eval_params(develop, p)
        sc = n_path_score(md, floors)
        abl_rows.append(
            {
                "tag": tag,
                "params": serializable_params(p),
                "metrics": md,
                "score": sc,
                "gate_eval": gate_eval(md, floors),
            }
        )
        if i % 20 == 0:
            print(f"  ablations {i}/{len(abl)}", flush=True)
    abl_rows.sort(key=lambda x: x["score"], reverse=True)

    factor_deltas = []
    for row in abl_rows:
        if row["tag"] == "baseline_champion":
            continue
        factor_deltas.append((row["tag"], row["score"] - base_sc))
    factor_deltas.sort(key=lambda x: abs(x[1]), reverse=True)

    print("Secondary widen search (budget=150) ...", flush=True)
    refine = secondary_search(develop, base, budget=150)

    best_abl = abl_rows[0]
    best_ref = refine[0]
    if best_ref["score"] > best_abl["score"]:
        best = {
            "source": "secondary_search",
            "tag": "refine_top1",
            "params": best_ref["params"],
            "metrics": best_ref["metrics"],
            "score": best_ref["score"],
            "gate_eval": best_ref["gate_eval"],
        }
    else:
        best = {
            "source": "ablation",
            "tag": best_abl["tag"],
            "params": best_abl["params"],
            "metrics": best_abl["metrics"],
            "score": best_abl["score"],
            "gate_eval": best_abl["gate_eval"],
        }

    gate_pass = [r for r in abl_rows if r["gate_eval"]["hard_pass_n_path"]]
    gate_pass_ref = [r for r in refine if r["gate_eval"]["hard_pass_n_path"]]
    best_gated = None
    cands = []
    for r in gate_pass:
        cands.append(
            {
                "source": "ablation",
                "tag": r["tag"],
                "params": r["params"],
                "metrics": r["metrics"],
                "score": r["score"],
                "gate_eval": r["gate_eval"],
            }
        )
    for r in gate_pass_ref:
        cands.append(
            {
                "source": "secondary_search",
                "tag": "refine_gate_pass",
                "params": r["params"],
                "metrics": r["metrics"],
                "score": r["score"],
                "gate_eval": r["gate_eval"],
            }
        )
    if cands:
        cands.sort(key=lambda x: x["score"], reverse=True)
        best_gated = cands[0]

    payload = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "safety": "offline research only; never --live; develop only; holdout unused",
        "holdout_start": str(HOLDOUT_START),
        "holdout_used": False,
        "develop_bars": int(len(develop)),
        "preregistered": PREREG,
        "baseline": {
            "params": serializable_params(base),
            "metrics": base_m,
            "score": base_sc,
            "gate_eval": base_g,
        },
        "n_ablations": len(abl_rows),
        "ablations_ranked": abl_rows,
        "factor_deltas": factor_deltas,
        "n_secondary": len(refine),
        "secondary_top": refine[:25],
        "best_develop_candidate": best,
        "best_gate_pass_candidate": best_gated,
        "n_gate_pass_ablation": len(gate_pass),
        "n_gate_pass_secondary": len(gate_pass_ref),
        "seconds": round(time.time() - t0, 2),
        "disposition": {
            "lane": "htf_fib_xau",
            "status": "KEEP_OPTIMIZING",
            "live_go": False,
            "kill": False,
            "note": "Widen path on develop only; virgin holdout required for promote",
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
        f"score={best['score']:.1f} gate={best['gate_eval']['hard_pass_n_path']} "
        f"({payload['seconds']}s)",
        flush=True,
    )
    if best_gated:
        print(
            f"BEST_GATED source={best_gated['source']} tag={best_gated.get('tag')} "
            f"PF={best_gated['metrics']['profit_factor']:.3f} n={best_gated['metrics']['n_trades']} "
            f"score={best_gated['score']:.1f}",
            flush=True,
        )
    else:
        print("BEST_GATED none under pre-reg floors", flush=True)


if __name__ == "__main__":
    main()
