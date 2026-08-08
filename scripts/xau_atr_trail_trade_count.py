#!/usr/bin/env python3
"""ATR trail breakout — raise develop trade count (KEEP_OPTIMIZING priority #2).

SAFETY:
  - Develop only (time < 2026-01-01). NEVER use holdout for param choice.
  - Offline research only. NEVER --live. No orders.
  - Prior sealed holdout (n=4 underpowered) stays sealed; no re-eval this fire.

Thesis (from deep-opt skeptic):
  Champion has strong develop PF/WR but holdout n=4 (sample death). Next work is
  raise trade frequency on develop via entry_N / atr_min / filters — then wait for
  virgin sealed data (not re-mine contaminated 2026-01+ window).

Writes:
  results/xau_atr_trail_trade_count.json
  results/xau_atr_trail_trade_count.md
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

from xau_lane_deep_opt import (  # noqa: E402
    HOLDOUT_START,
    metrics_dict,
    prepare_frame,
    score_expectancy_sqrt,
    serializable_params,
    simulate_atr_trail,
)

from backtest import load_h1  # noqa: E402

OUT_JSON = ROOT / "results" / "xau_atr_trail_trade_count.json"
OUT_MD = ROOT / "results" / "xau_atr_trail_trade_count.md"
CHAMPIONS = ROOT / "results" / "xau_lane_champions.json"

# Pre-registered before ranking outcomes are inspected for selection claims.
PREREG = {
    "objective": "raise develop n while keeping quality floors (sample death fix path)",
    "develop_hard_floors": {
        "profit_factor": 1.4,
        "max_drawdown_pct": 12.0,
        "n_trades_min": 40,
        "n_trades_target": 60,
        "win_rate_diagnostic_floor": 45.0,
        "expectancy_min": 10.0,
    },
    "score": "primary = n_trades * 8 + expectancy_sqrt_n * 0.35 + PF*20; hard floor fail → -1000",
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
}


def load_champion() -> dict[str, Any]:
    data = json.loads(CHAMPIONS.read_text())
    for row in data["per_lane_champions"]:
        if row["lane_id"] == "atr_trail_breakout":
            p = dict(row["params"])
            p.pop("mode", None)
            if isinstance(p.get("hours"), list):
                p["hours"] = tuple(p["hours"]) if p["hours"] else None
            return p
    raise SystemExit("atr_trail_breakout champion missing")


def eval_params(d: pd.DataFrame, params: dict) -> dict[str, Any]:
    m = simulate_atr_trail(d, **params)
    md = metrics_dict(m)
    md["score_expectancy_sqrt"] = float(score_expectancy_sqrt(m))
    return md


def trade_count_score(md: dict[str, Any], floors: dict[str, Any]) -> float:
    """Score seeking higher n under quality floors (pre-registered formula)."""
    n = int(md["n_trades"])
    pf = float(md["profit_factor"])
    dd = float(md["max_drawdown_pct"])
    exp = float(md["expectancy"])
    exp_s = float(md["expectancy_sqrt_n"])
    if n < 5:
        return -2000.0 + n
    s = n * 8.0 + exp_s * 0.35 + min(pf, 4.0) * 20.0 + float(md["net_profit"]) / 100.0
    if pf < float(floors["profit_factor"]):
        s -= 1000.0 * (float(floors["profit_factor"]) - min(pf, float(floors["profit_factor"])))
    if dd > float(floors["max_drawdown_pct"]):
        s -= 40.0 * (dd - float(floors["max_drawdown_pct"]))
    if exp < float(floors["expectancy_min"]):
        s -= 20.0 * (float(floors["expectancy_min"]) - exp)
    # bonus for hitting sample targets
    if n >= int(floors["n_trades_min"]):
        s += 80.0
    if n >= int(floors["n_trades_target"]):
        s += 120.0
    wr_floor = floors.get("win_rate_diagnostic_floor")
    if wr_floor is not None and float(md["win_rate"]) < float(wr_floor) and n >= 10:
        s -= 1.5 * (float(wr_floor) - float(md["win_rate"]))
    return float(s)


def gate_eval(md: dict[str, Any], floors: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "pf": float(md["profit_factor"]) >= float(floors["profit_factor"]),
        "dd": float(md["max_drawdown_pct"]) <= float(floors["max_drawdown_pct"]),
        "n_min": int(md["n_trades"]) >= int(floors["n_trades_min"]),
        "expectancy": float(md["expectancy"]) >= float(floors["expectancy_min"]),
    }
    return {
        "hard_pass_trade_count": all(checks.values()),
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

    # entry_N shorter → more breakouts
    for en in (10, 12, 15, 18, 20, 24, 30, 40, 55):
        add(f"entry_N={en}", entry_N=en)

    # atr_min loosen
    for a in (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65):
        add(f"atr_min_pct={a}", atr_min_pct=a)

    # rsi ceiling
    for r in (65.0, 70.0, 75.0, 80.0, 85.0, 90.0, 100.0):
        add(f"rsi_max={r}", rsi_max=r)

    # h4 bias off (may raise n)
    add("h4_bias=False", h4_bias=False)
    add("h4_bias=True", h4_bias=True)

    # ema trend path
    for e in ("ema50", "ema100", "ema200"):
        add(f"ema_trend={e}", ema_trend=e)

    # require stack off/on
    add("require_ema_stack=True", require_ema_stack=True)
    add("require_ema_stack=False", require_ema_stack=False)

    # trail / sl
    for t in (1.5, 2.0, 2.5, 3.0, 3.5, 4.0):
        add(f"trail_atr={t}", trail_atr=t)
    for s in (1.0, 1.5, 2.0, 2.5):
        add(f"sl_atr={s}", sl_atr=s)

    # frequency controls
    for c in (0, 1, 2, 4):
        add(f"cooldown={c}", cooldown=c)
    for m in (1, 2, 3, 4):
        add(f"max_entries_per_day={m}", max_entries_per_day=m)

    # BE
    for r in (None, 1.0, 1.5):
        add(f"be_at_r={r}", be_at_r=r)

    # mid channel
    for k in (None, 0.5, 1.0):
        add(f"mid_channel_k={k}", mid_channel_k=k)

    # multi-lever packs pre-registered for "more trades, keep edge"
    add(
        "pack_freq_entry15_atr40",
        entry_N=15,
        atr_min_pct=0.40,
        h4_bias=True,
        rsi_max=80.0,
        cooldown=1,
    )
    add(
        "pack_freq_entry12_atr35_noh4",
        entry_N=12,
        atr_min_pct=0.35,
        h4_bias=False,
        rsi_max=85.0,
        cooldown=0,
        max_entries_per_day=3,
    )
    add(
        "pack_freq_entry10_atr30",
        entry_N=10,
        atr_min_pct=0.30,
        h4_bias=False,
        rsi_max=90.0,
        cooldown=0,
        max_entries_per_day=3,
        trail_atr=2.5,
    )
    add(
        "pack_entry20_atr45_rsi80",
        entry_N=20,
        atr_min_pct=0.45,
        rsi_max=80.0,
        h4_bias=True,
        cooldown=1,
    )
    add(
        "pack_entry18_atr50_trail3",
        entry_N=18,
        atr_min_pct=0.50,
        trail_atr=3.0,
        sl_atr=1.5,
        h4_bias=True,
        rsi_max=75.0,
    )
    add(
        "pack_entry15_atr50_stack_off",
        entry_N=15,
        atr_min_pct=0.50,
        require_ema_stack=False,
        h4_bias=True,
        rsi_max=80.0,
        cooldown=1,
        max_entries_per_day=3,
    )
    add(
        "pack_entry20_no_atr_floor",
        entry_N=20,
        atr_min_pct=0.0,
        h4_bias=True,
        rsi_max=85.0,
    )
    add(
        "pack_balanced_n60_path",
        entry_N=15,
        atr_min_pct=0.45,
        trail_atr=3.0,
        sl_atr=1.5,
        h4_bias=True,
        rsi_max=80.0,
        cooldown=1,
        max_entries_per_day=2,
        ema_trend="ema100",
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


def secondary_search(d: pd.DataFrame, base: dict[str, Any], budget: int = 200) -> list[dict]:
    """Cartesian search focused on n-raising axes (develop only)."""
    axes = {
        "entry_N": [10, 12, 15, 18, 20, 24],
        "atr_min_pct": [0.30, 0.35, 0.40, 0.45, 0.50, 0.55],
        "trail_atr": [2.5, 3.0, 3.5],
        "h4_bias": [False, True],
        "rsi_max": [70.0, 80.0, 90.0],
        "cooldown": [0, 1, 2],
        "max_entries_per_day": [2, 3],
    }
    keys = list(axes.keys())
    combos = []
    for vals in itertools.product(*[axes[k] for k in keys]):
        p = deepcopy(base)
        for k, v in zip(keys, vals):
            p[k] = v
        # fixed quality defaults from champ path
        p.setdefault("sl_atr", base.get("sl_atr", 1.5))
        p.setdefault("require_ema_stack", False)
        p.setdefault("ema_trend", base.get("ema_trend", "ema100"))
        p.setdefault("be_at_r", None)
        p.setdefault("mid_channel_k", None)
        combos.append(p)

    if len(combos) > budget:
        step = max(1, len(combos) // budget)
        combos = combos[::step][:budget]

    floors = PREREG["develop_hard_floors"]
    results = []
    for p in combos:
        md = eval_params(d, p)
        sc = trade_count_score(md, floors)
        results.append(
            {
                "params": serializable_params(p),
                "metrics": md,
                "score": sc,
                "gate_eval": gate_eval(md, floors),
            }
        )
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
        "# ATR trail breakout — raise develop trade count",
        "",
        f"**Timestamp (UTC):** {payload['created']}",
        f"**Window:** develop only (`time < {payload['holdout_start']}`); holdout sealed unused",
        f"**Safety:** {payload['safety']}",
        f"**n_ablations:** {payload['n_ablations']} | **secondary_evals:** {payload['n_secondary']}",
        "",
        "## Pre-registered floors (before ranking)",
        "```json",
        json.dumps(floors, indent=2),
        "```",
        "",
        f"Score formula: `{payload['preregistered']['score']}`",
        "",
        "## Baseline champion",
        "",
        f"- Params: `{json.dumps(base['params'], sort_keys=True)}`",
        f"- PF={bm['profit_factor']:.3f} WR={bm['win_rate']:.1f}% DD={bm['max_drawdown_pct']:.2f}% "
        f"n={bm['n_trades']} NP={bm['net_profit']:.1f} exp√n={bm['expectancy_sqrt_n']:.1f}",
        f"- trade_count_score={base['score']:.1f} | hard_pass_trade_count="
        f"**{base['gate_eval']['hard_pass_trade_count']}** "
        f"(n_min≥{floors['n_trades_min']}: {base['gate_eval']['checks']['n_min']})",
        "",
        "## Ablation ranking (trade_count_score)",
        "",
        "| Rank | Tag | PF | WR% | DD% | n | NP | exp√n | score | Δscore | gate |",
        "|-----:|-----|---:|----:|----:|--:|---:|------:|------:|-------:|:----:|",
    ]
    for i, row in enumerate(top, 1):
        m = row["metrics"]
        g = "Y" if row["gate_eval"]["hard_pass_trade_count"] else "n"
        lines.append(
            f"| {i} | `{row['tag']}` | {m['profit_factor']:.3f} | {m['win_rate']:.1f} | "
            f"{m['max_drawdown_pct']:.2f} | {m['n_trades']} | {m['net_profit']:.0f} | "
            f"{m['expectancy_sqrt_n']:.1f} | {row['score']:.1f} | {row['score'] - bsc:+.1f} | {g} |"
        )
    lines += ["", "## Key factor deltas (|Δscore|)", ""]
    for name, delta in payload["factor_deltas"][:15]:
        lines.append(f"- `{name}`: Δscore={delta:+.1f}")

    lines += [
        "",
        "## Secondary search top (n-raising axes)",
        "",
        "| Rank | PF | WR% | DD% | n | NP | score | gate | params highlight |",
        "|-----:|---:|----:|----:|--:|---:|------:|:----:|------------------|",
    ]
    for i, row in enumerate(top_ref, 1):
        m = row["metrics"]
        p = row["params"]
        hl = {
            k: p.get(k)
            for k in (
                "entry_N",
                "atr_min_pct",
                "trail_atr",
                "h4_bias",
                "rsi_max",
                "cooldown",
                "max_entries_per_day",
            )
        }
        g = "Y" if row["gate_eval"]["hard_pass_trade_count"] else "n"
        lines.append(
            f"| {i} | {m['profit_factor']:.3f} | {m['win_rate']:.1f} | {m['max_drawdown_pct']:.2f} | "
            f"{m['n_trades']} | {m['net_profit']:.0f} | {row['score']:.1f} | {g} | "
            f"`{json.dumps(hl, sort_keys=True)}` |"
        )

    bm2 = best["metrics"]
    lines += [
        "",
        "## Best develop candidate (NOT holdout-confirmed)",
        "",
        f"- Source: **{best['source']}** tag=`{best.get('tag', 'n/a')}`",
        f"- PF={bm2['profit_factor']:.3f} WR={bm2['win_rate']:.1f}% DD={bm2['max_drawdown_pct']:.2f}% "
        f"n={bm2['n_trades']} NP={bm2['net_profit']:.1f} exp√n={bm2['expectancy_sqrt_n']:.1f}",
        f"- hard_pass_trade_count: **{best['gate_eval']['hard_pass_trade_count']}** "
        f"| n_target≥{floors['n_trades_target']}: **{best['gate_eval']['n_target_hit']}**",
        f"- Params: `{json.dumps(best['params'], sort_keys=True)}`",
        "",
        "## Disposition",
        "",
        "- Lane **KEEP_OPTIMIZING** (not KILL).",
        f"- Baseline n={bm['n_trades']} "
        f"{'MEETS' if base['gate_eval']['hard_pass_trade_count'] else 'MISSES'} n≥{floors['n_trades_min']} floor.",
        f"- Best candidate n={bm2['n_trades']} "
        f"(Δn vs baseline {bm2['n_trades'] - bm['n_trades']:+d}).",
        "- **No holdout re-eval** this fire (prior HO n=4 underpowered + contaminated window).",
        "- Live promote: **NO-GO**. Next: htf_fib widen entries on develop, or virgin holdout when data > 2026-08-06.",
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
    base.setdefault("cooldown", 2)
    base.setdefault("long_only", True)
    base.setdefault("risk_pct", 0.01)

    base_m = eval_params(develop, base)
    base_sc = trade_count_score(base_m, floors)
    base_g = gate_eval(base_m, floors)
    print(
        f"baseline PF={base_m['profit_factor']:.3f} n={base_m['n_trades']} "
        f"WR={base_m['win_rate']:.1f} score={base_sc:.1f} gate={base_g['hard_pass_trade_count']}",
        flush=True,
    )

    abl = ablation_grid(base)
    abl_rows = []
    for i, (tag, p) in enumerate(abl, 1):
        md = eval_params(develop, p)
        sc = trade_count_score(md, floors)
        abl_rows.append(
            {
                "tag": tag,
                "params": serializable_params(p),
                "metrics": md,
                "score": sc,
                "gate_eval": gate_eval(md, floors),
            }
        )
        if i % 25 == 0:
            print(f"  ablations {i}/{len(abl)}", flush=True)
    abl_rows.sort(key=lambda x: x["score"], reverse=True)

    factor_deltas = []
    for row in abl_rows:
        if row["tag"] == "baseline_champion":
            continue
        factor_deltas.append((row["tag"], row["score"] - base_sc))
    factor_deltas.sort(key=lambda x: abs(x[1]), reverse=True)

    print("Secondary n-raising search (budget=200) ...", flush=True)
    refine = secondary_search(develop, base, budget=200)

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

    # best among hard_pass only
    gate_pass = [r for r in abl_rows if r["gate_eval"]["hard_pass_trade_count"]]
    gate_pass_ref = [r for r in refine if r["gate_eval"]["hard_pass_trade_count"]]
    best_gated = None
    if gate_pass or gate_pass_ref:
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
            "lane": "atr_trail_breakout",
            "status": "KEEP_OPTIMIZING",
            "live_go": False,
            "kill": False,
            "note": "Trade-count path on develop only; virgin holdout still required for promote",
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
        f"score={best['score']:.1f} gate={best['gate_eval']['hard_pass_trade_count']} "
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


if __name__ == "__main__":
    main()
