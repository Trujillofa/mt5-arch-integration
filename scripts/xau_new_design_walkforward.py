#!/usr/bin/env python3
"""Walk-forward validation for XAU new-design shortlist.

Expanding train + 4 equal-bar OOS folds from 2025-01-01 (same spirit as
xau_walkforward.py). For each shortlist design (max 5):

  A) Fixed params from shortlist across folds (no re-fit)
  B) Optional light re-fit on train per fold (small neighbor grid)

Writes:
  results/xau_new_design_walkforward.json
  results/xau_new_design_candidates.json

SAFETY: offline research only — no --live, never place orders.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from backtest import START_BALANCE, load_h1, passes  # noqa: E402
from xau_new_design_search import (  # noqa: E402
    extend_indicators,
    is_better,
    metrics_dict,
    serializable_params,
    simulate_design,
)

SHORTLIST_PATH = ROOT / "results" / "xau_new_design_search.json"
OUT_PATH = ROOT / "results" / "xau_new_design_walkforward.json"
CANDIDATES_PATH = ROOT / "results" / "xau_new_design_candidates.json"

OOS_REGION_START = pd.Timestamp("2025-01-01", tz="UTC")
N_FOLDS = 4
MIN_TRAIN_BARS = 500
MAX_DESIGNS = 5
# Light re-fit budget: enable; mark clearly in output
ENABLE_REFIT = True


def normalize_params(raw: dict) -> dict:
    p = dict(raw)
    if isinstance(p.get("hours"), list):
        p["hours"] = tuple(p["hours"]) if p["hours"] else None
    # cooldown must be int for cool counter
    if "cooldown" in p and p["cooldown"] is not None:
        p["cooldown"] = int(p["cooldown"])
    return p


def bar_range(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"start": None, "end": None, "n_bars": 0}
    return {
        "start": str(pd.to_datetime(df["time"].iloc[0], utc=True)),
        "end": str(pd.to_datetime(df["time"].iloc[-1], utc=True)),
        "n_bars": int(len(df)),
    }


def build_folds(d: pd.DataFrame, times: pd.Series) -> list[dict]:
    """Expanding train / sequential equal-bar OOS folds over 2025→end."""
    oos_mask = times >= OOS_REGION_START
    oos_idx = np.flatnonzero(oos_mask.to_numpy())
    if len(oos_idx) < N_FOLDS * 50:
        raise RuntimeError(
            f"Not enough OOS bars from {OOS_REGION_START}: {len(oos_idx)} bars"
        )

    chunks = np.array_split(oos_idx, N_FOLDS)
    folds: list[dict] = []
    for k, chunk in enumerate(chunks):
        if len(chunk) == 0:
            continue
        i0, i1 = int(chunk[0]), int(chunk[-1])
        train = d.iloc[:i0].reset_index(drop=True)
        oos = d.iloc[i0 : i1 + 1].reset_index(drop=True)
        if len(train) < MIN_TRAIN_BARS:
            raise RuntimeError(
                f"Fold {k}: train bars {len(train)} < MIN_TRAIN_BARS={MIN_TRAIN_BARS}"
            )
        folds.append(
            {
                "fold": k + 1,
                "train_end_idx": i0,
                "oos_start_idx": i0,
                "oos_end_idx": i1,
                "train": train,
                "oos": oos,
            }
        )
    return folds


def soft_pass(m) -> bool:
    """Hard passes() when n>=20; softer fold gate when n<20."""
    if m.n_trades >= 20:
        return bool(passes(m))
    if m.n_trades <= 0:
        return False
    return (
        m.profit_factor > 1.2
        and m.win_rate > 50.0
        and m.max_drawdown_pct < 12.0
    )


def _uniq_floats(vals: list[float], nd: int = 4) -> list[float]:
    seen: set[float] = set()
    out: list[float] = []
    for v in vals:
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            continue
        x = round(float(v), nd)
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def neighbor_grid(base: dict) -> list[dict]:
    """Small neighborhood around shortlist params (mode-specific)."""
    mode = base.get("mode", "")
    shared_keys = (
        "risk_pct",
        "max_lots",
        "long_only",
        "hours",
        "mode",
    )
    fixed = {k: base[k] for k in shared_keys if k in base}
    grid: list[dict] = []

    def add(overrides: dict) -> None:
        p = {**base, **fixed, **overrides}
        p = normalize_params(p)
        grid.append(p)

    # always include exact base
    add({})

    if mode == "vol_gate_bb":
        atr0 = float(base.get("atr_max_pct", 0.5))
        rsi0 = float(base.get("rsi_buy", 30))
        sl0 = float(base.get("sl_atr", 1.5))
        tp0 = float(base.get("tp_atr", 2.0))
        cd0 = int(base.get("cooldown", 2))
        for atr_max in _uniq_floats([atr0, atr0 - 0.05, atr0 + 0.05, atr0 - 0.1]):
            for rsi_buy in _uniq_floats([rsi0, rsi0 - 5, rsi0 + 5]):
                for sl_atr, tp_atr in (
                    (sl0, tp0),
                    (max(1.0, sl0 - 0.3), tp0),
                    (sl0, tp0 + 0.5),
                ):
                    for cooldown in sorted({cd0, max(1, cd0 - 1), cd0 + 1}):
                        for exit_spike in (True, False):
                            add(
                                {
                                    "atr_max_pct": atr_max,
                                    "rsi_buy": rsi_buy,
                                    "sl_atr": float(sl_atr),
                                    "tp_atr": float(tp_atr),
                                    "cooldown": int(cooldown),
                                    "exit_on_vol_spike": bool(exit_spike),
                                }
                            )
        # cap size
        grid = _dedupe_params(grid)[:24]

    elif mode == "atr_breakout":
        amin = float(base.get("atr_min_pct", 0.55))
        sl0 = float(base.get("sl_atr", 2.0))
        tp0 = float(base.get("tp_atr", 4.0))
        dn0 = int(base.get("donch_n", 20))
        cd0 = int(base.get("cooldown", 3))
        rmax = float(base.get("rsi_max", 75))
        for atr_min in _uniq_floats([amin, amin - 0.05, amin + 0.05]):
            for donch_n in sorted({dn0, 20, 24, 30}):
                for sl_atr, tp_atr in (
                    (sl0, tp0),
                    (sl0 - 0.2, tp0),
                    (sl0, tp0 - 0.5),
                    (sl0 + 0.2, tp0 + 0.5),
                ):
                    for cooldown in sorted({cd0, max(1, cd0 - 1)}):
                        for rsi_max in _uniq_floats([rmax, rmax - 5, rmax + 5]):
                            add(
                                {
                                    "atr_min_pct": atr_min,
                                    "donch_n": int(donch_n),
                                    "sl_atr": float(sl_atr),
                                    "tp_atr": float(tp_atr),
                                    "cooldown": int(cooldown),
                                    "rsi_max": rsi_max,
                                }
                            )
        grid = _dedupe_params(grid)[:24]

    elif mode == "ema_pullback":
        sl0 = float(base.get("sl_atr", 2.0))
        tp0 = float(base.get("tp_atr", 3.0))
        rlo = float(base.get("rsi_lo", 40))
        rhi = float(base.get("rsi_hi", 55))
        buf = float(base.get("atr_buffer", 0.5))
        ahi = float(base.get("atr_pctile_hi", 0.75))
        cd0 = int(base.get("cooldown", 2))
        for atr_buffer in _uniq_floats([buf, max(0.0, buf - 0.25), buf + 0.25]):
            for atr_pctile_hi in _uniq_floats([ahi, ahi - 0.1, min(1.0, ahi + 0.1)]):
                for rsi_lo, rsi_hi in (
                    (rlo, rhi),
                    (rlo - 5, rhi),
                    (rlo, rhi + 5),
                    (rlo - 5, rhi + 5),
                ):
                    for sl_atr, tp_atr in (
                        (sl0, tp0),
                        (sl0 - 0.25, tp0),
                        (sl0, tp0 + 0.5),
                    ):
                        for cooldown in sorted({cd0, max(1, cd0 - 1)}):
                            add(
                                {
                                    "atr_buffer": atr_buffer,
                                    "atr_pctile_hi": atr_pctile_hi,
                                    "rsi_lo": float(rsi_lo),
                                    "rsi_hi": float(rsi_hi),
                                    "sl_atr": float(sl_atr),
                                    "tp_atr": float(tp_atr),
                                    "cooldown": int(cooldown),
                                }
                            )
        grid = _dedupe_params(grid)[:24]

    elif mode == "dual_regime":
        sw = float(base.get("switch_pct", 0.6))
        sl_bo = float(base.get("sl_atr_bo", 1.8))
        tp_bo = float(base.get("tp_atr_bo", 4.0))
        sl_mr = float(base.get("sl_atr_mr", 1.5))
        tp_mr = float(base.get("tp_atr_mr", 2.5))
        rb = float(base.get("rsi_buy", 30))
        dn0 = int(base.get("donch_n", 20))
        cd0 = int(base.get("cooldown", 2))
        for switch_pct in _uniq_floats([sw, sw - 0.05, sw + 0.05]):
            for donch_n in sorted({dn0, 20, 24}):
                for sl_atr_bo, tp_atr_bo in (
                    (sl_bo, tp_bo),
                    (sl_bo - 0.2, tp_bo),
                    (sl_bo, tp_bo - 0.5),
                ):
                    for sl_atr_mr, tp_atr_mr in (
                        (sl_mr, tp_mr),
                        (sl_mr, tp_mr + 0.5),
                    ):
                        for rsi_buy in _uniq_floats([rb, rb - 5, rb + 5]):
                            for cooldown in sorted({cd0, max(1, cd0 - 1)}):
                                add(
                                    {
                                        "switch_pct": switch_pct,
                                        "donch_n": int(donch_n),
                                        "sl_atr_bo": float(sl_atr_bo),
                                        "tp_atr_bo": float(tp_atr_bo),
                                        "sl_atr_mr": float(sl_atr_mr),
                                        "tp_atr_mr": float(tp_atr_mr),
                                        "rsi_buy": rsi_buy,
                                        "cooldown": int(cooldown),
                                    }
                                )
        grid = _dedupe_params(grid)[:24]
    else:
        # generic: vary sl/tp/cooldown only
        sl0 = float(base.get("sl_atr", 1.5))
        tp0 = float(base.get("tp_atr", 2.5))
        cd0 = int(base.get("cooldown", 2))
        for sl_atr in _uniq_floats([sl0, sl0 - 0.3, sl0 + 0.3]):
            for tp_atr in _uniq_floats([tp0, tp0 - 0.5, tp0 + 0.5]):
                for cooldown in sorted({cd0, max(1, cd0 - 1), cd0 + 1}):
                    add({"sl_atr": sl_atr, "tp_atr": tp_atr, "cooldown": int(cooldown)})
        grid = _dedupe_params(grid)[:18]

    return grid if grid else [normalize_params(base)]


def _param_key(p: dict) -> str:
    return json.dumps(serializable_params(p), sort_keys=True, default=str)


def _dedupe_params(grid: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for p in grid:
        k = _param_key(p)
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def pick_best_on_train(train: pd.DataFrame, grid: list[dict]) -> tuple[dict, Any, bool, int]:
    best_p = grid[0]
    best_m = simulate_design(train, **best_p)
    best_ok = passes(best_m)
    n_pass = 1 if best_ok else 0
    for p in grid[1:]:
        m = simulate_design(train, **p)
        ok = passes(m)
        if ok:
            n_pass += 1
        if is_better(m, best_m, best_ok):
            best_p, best_m, best_ok = p, m, ok
    return best_p, best_m, best_ok, n_pass


def aggregate_folds(fold_recs: list[dict], metrics_key: str, pass_key: str) -> dict:
    nps = [r[metrics_key]["net_profit"] for r in fold_recs]
    trades = [r[metrics_key]["n_trades"] for r in fold_recs]
    wrs = [r[metrics_key]["win_rate"] for r in fold_recs]
    pfs = [r[metrics_key]["profit_factor"] for r in fold_recs]
    dds = [r[metrics_key]["max_drawdown_pct"] for r in fold_recs]
    soft = [bool(r[pass_key]) for r in fold_recs]
    hard = [bool(r.get(pass_key.replace("soft", "hard"), False)) for r in fold_recs]
    # hard key may be separate
    hard_key = pass_key.replace("soft_pass", "hard_pass")
    if hard_key in fold_recs[0]:
        hard = [bool(r[hard_key]) for r in fold_recs]
    total_trades = int(sum(trades))
    total_np = float(sum(nps))
    wr_num = sum(
        r[metrics_key]["win_rate"] * r[metrics_key]["n_trades"] for r in fold_recs
    )
    mean_wr = float(wr_num / total_trades) if total_trades else 0.0
    pfs_with = [
        r[metrics_key]["profit_factor"]
        for r in fold_recs
        if r[metrics_key]["n_trades"] > 0
    ]
    mean_pf = float(np.mean(pfs_with)) if pfs_with else 0.0
    soft_rate = float(sum(soft) / len(soft)) if soft else 0.0
    hard_rate = float(sum(hard) / len(hard)) if hard else 0.0
    return {
        "n_folds": len(fold_recs),
        "sum_net_profit": total_np,
        "total_trades": total_trades,
        "mean_win_rate": mean_wr,
        "mean_profit_factor": mean_pf,
        "fold_pass_rate": soft_rate,  # soft-aware (primary)
        "fold_hard_pass_rate": hard_rate,
        "folds_soft_pass": soft,
        "folds_hard_pass": hard,
        "min_oos_drawdown_pct": float(min(dds)) if dds else 0.0,
        "max_oos_drawdown_pct": float(max(dds)) if dds else 0.0,
        "per_fold_net_profit": nps,
        "per_fold_trades": trades,
        "per_fold_profit_factor": pfs,
        "per_fold_win_rate": wrs,
    }


def run_design(
    design: dict,
    folds: list[dict],
    *,
    enable_refit: bool,
) -> dict:
    design_id = design["id"]
    base = normalize_params(design["params"])
    train_gates = bool(design.get("train_gates", False))
    shortlist_oos = design.get("oos") or {}
    shortlist_train = design.get("train") or {}

    fixed_folds: list[dict] = []
    refit_folds: list[dict] = []

    for f in folds:
        k = f["fold"]
        train, oos = f["train"], f["oos"]
        tr_rng, oos_rng = bar_range(train), bar_range(oos)

        # A) Fixed params
        train_m = simulate_design(train, **base)
        oos_m = simulate_design(oos, **base)
        hard_ok = bool(passes(oos_m))
        soft_ok = soft_pass(oos_m)
        fixed_rec = {
            "fold": k,
            "train_range": tr_rng,
            "oos_range": oos_rng,
            "params": serializable_params(base),
            "train_metrics": metrics_dict(train_m),
            "train_gates_pass": bool(passes(train_m)),
            "oos_metrics": metrics_dict(oos_m),
            "oos_hard_pass": hard_ok,
            "oos_soft_pass": soft_ok,
        }
        fixed_folds.append(fixed_rec)
        print(
            f"  [{design_id}] fold{k} FIXED OOS: "
            f"PF={oos_m.profit_factor:.3f} NP={oos_m.net_profit:.1f} "
            f"WR={oos_m.win_rate:.1f} DD={oos_m.max_drawdown_pct:.2f} "
            f"n={oos_m.n_trades} soft={soft_ok} hard={hard_ok}"
        )

        # B) Light re-fit (optional)
        if enable_refit:
            grid = neighbor_grid(base)
            best_p, best_train_m, train_ok, n_pass = pick_best_on_train(train, grid)
            refit_oos_m = simulate_design(oos, **best_p)
            r_hard = bool(passes(refit_oos_m))
            r_soft = soft_pass(refit_oos_m)
            refit_rec = {
                "fold": k,
                "train_range": tr_rng,
                "oos_range": oos_rng,
                "chosen_params": serializable_params(best_p),
                "grid_size": len(grid),
                "n_passers_train": n_pass,
                "train_metrics": metrics_dict(best_train_m),
                "train_gates_pass": train_ok,
                "oos_metrics": metrics_dict(refit_oos_m),
                "oos_hard_pass": r_hard,
                "oos_soft_pass": r_soft,
                "params_changed": _param_key(best_p) != _param_key(base),
            }
            refit_folds.append(refit_rec)
            print(
                f"  [{design_id}] fold{k} REFIT OOS: "
                f"PF={refit_oos_m.profit_factor:.3f} NP={refit_oos_m.net_profit:.1f} "
                f"WR={refit_oos_m.win_rate:.1f} n={refit_oos_m.n_trades} "
                f"soft={r_soft} train_passers={n_pass} changed={refit_rec['params_changed']}"
            )

    fixed_agg = aggregate_folds(fixed_folds, "oos_metrics", "oos_soft_pass")
    # attach hard from fixed_folds
    fixed_agg["folds_hard_pass"] = [bool(r["oos_hard_pass"]) for r in fixed_folds]
    fixed_agg["fold_hard_pass_rate"] = float(
        sum(fixed_agg["folds_hard_pass"]) / len(fixed_folds)
    )

    out: dict[str, Any] = {
        "id": design_id,
        "tag": design.get("tag"),
        "train_gates": train_gates,
        "shortlist_train": shortlist_train,
        "shortlist_oos": shortlist_oos,
        "params": serializable_params(base),
        "fixed": {
            "method": "fixed_shortlist_params_no_refit",
            "folds": fixed_folds,
            "aggregate_oos": fixed_agg,
        },
    }

    if enable_refit and refit_folds:
        refit_agg = aggregate_folds(refit_folds, "oos_metrics", "oos_soft_pass")
        refit_agg["folds_hard_pass"] = [bool(r["oos_hard_pass"]) for r in refit_folds]
        refit_agg["fold_hard_pass_rate"] = float(
            sum(refit_agg["folds_hard_pass"]) / len(refit_folds)
        )
        out["refit"] = {
            "method": "light_neighbor_grid_refit_per_fold",
            "note": "OPTIONAL light re-fit on train only; OOS evaluated once per fold",
            "folds": refit_folds,
            "aggregate_oos": refit_agg,
        }
    else:
        out["refit"] = {
            "method": "light_neighbor_grid_refit_per_fold",
            "enabled": False,
            "note": "skipped",
        }

    return out


def qualifies_candidate(design_result: dict) -> tuple[bool, str]:
    """train gates AND oos PF>1.2 AND oos n>=8 AND (wf soft_pass_rate>=0.5 OR fixed sum NP>0 with mean PF>1.2)."""
    train_ok = bool(design_result.get("train_gates"))
    if not train_ok:
        return False, "train_gates=false"

    # Prefer original shortlist OOS for PF/n gate; fall back to fixed WF aggregate
    short_oos = design_result.get("shortlist_oos") or {}
    fixed_agg = design_result.get("fixed", {}).get("aggregate_oos") or {}

    oos_pf = short_oos.get("profit_factor")
    oos_n = short_oos.get("n_trades")
    if oos_pf is None or oos_n is None:
        oos_pf = fixed_agg.get("mean_profit_factor", 0.0)
        oos_n = fixed_agg.get("total_trades", 0)

    if not (float(oos_pf) > 1.2 and int(oos_n) >= 8):
        # Also accept if fixed WF aggregate itself clears the bar
        wf_pf = float(fixed_agg.get("mean_profit_factor", 0.0))
        wf_n = int(fixed_agg.get("total_trades", 0))
        if not (wf_pf > 1.2 and wf_n >= 8):
            return (
                False,
                f"oos PF/n fail (shortlist PF={oos_pf} n={oos_n}; "
                f"wf meanPF={wf_pf} n={wf_n})",
            )
        # shortlist failed but WF aggregate passes → continue with WF numbers
        oos_pf, oos_n = wf_pf, wf_n

    soft_rate = float(fixed_agg.get("fold_pass_rate", 0.0))
    sum_np = float(fixed_agg.get("sum_net_profit", 0.0))
    mean_pf = float(fixed_agg.get("mean_profit_factor", 0.0))

    if soft_rate >= 0.5:
        return True, f"soft_pass_rate={soft_rate:.2f}>=0.5"
    if sum_np > 0 and mean_pf > 1.2:
        return True, f"fixed sum_np={sum_np:.2f}>0 and mean_pf={mean_pf:.3f}>1.2"
    return (
        False,
        f"wf soft_pass_rate={soft_rate:.2f}<0.5 and "
        f"not (sum_np={sum_np:.2f}>0 & mean_pf={mean_pf:.3f}>1.2)",
    )


def main() -> int:
    t0 = time.perf_counter()
    shortlist_doc = json.loads(SHORTLIST_PATH.read_text())
    shortlist = list(shortlist_doc.get("shortlist") or [])[:MAX_DESIGNS]
    if not shortlist:
        raise RuntimeError(f"No shortlist designs in {SHORTLIST_PATH}")

    raw = load_h1()
    d = extend_indicators(raw)
    times = pd.to_datetime(d["time"], utc=True)
    t_start, t_end = times.iloc[0], times.iloc[-1]
    folds = build_folds(d, times)

    print(
        f"bars={len(d)} range={t_start} → {t_end} | "
        f"folds={len(folds)} designs={len(shortlist)} "
        f"OOS_from={OOS_REGION_START} refit={ENABLE_REFIT}"
    )
    for f in folds:
        print(
            f"  fold{f['fold']}: train={bar_range(f['train'])} oos={bar_range(f['oos'])}"
        )

    design_results: list[dict] = []
    for design in shortlist:
        print(f"\n=== Design {design['id']} train_gates={design.get('train_gates')} ===")
        rec = run_design(design, folds, enable_refit=ENABLE_REFIT)
        design_results.append(rec)
        fa = rec["fixed"]["aggregate_oos"]
        print(
            f"  FIXED AGG: NP={fa['sum_net_profit']:.2f} trades={fa['total_trades']} "
            f"meanPF={fa['mean_profit_factor']:.3f} meanWR={fa['mean_win_rate']:.1f} "
            f"soft_pass_rate={fa['fold_pass_rate']:.0%}"
        )
        if "aggregate_oos" in rec.get("refit", {}):
            ra = rec["refit"]["aggregate_oos"]
            print(
                f"  REFIT AGG: NP={ra['sum_net_profit']:.2f} trades={ra['total_trades']} "
                f"meanPF={ra['mean_profit_factor']:.3f} "
                f"soft_pass_rate={ra['fold_pass_rate']:.0%}"
            )

    # Candidates
    candidates: list[dict] = []
    reject_reasons: list[dict] = []
    for rec in design_results:
        ok, reason = qualifies_candidate(rec)
        entry = {
            "id": rec["id"],
            "tag": rec.get("tag"),
            "train_gates": rec["train_gates"],
            "params": rec["params"],
            "shortlist_oos": rec.get("shortlist_oos"),
            "fixed_aggregate_oos": rec["fixed"]["aggregate_oos"],
            "qualify_reason": reason,
        }
        if "aggregate_oos" in rec.get("refit", {}):
            entry["refit_aggregate_oos"] = rec["refit"]["aggregate_oos"]
        if ok:
            candidates.append(entry)
        else:
            reject_reasons.append({"id": rec["id"], "reason": reason})

    elapsed = time.perf_counter() - t0
    out = {
        "method": "expanding_train_equal_bar_oos",
        "n_folds": len(folds),
        "oos_region_start": str(OOS_REGION_START),
        "data_range": {
            "start": str(t_start),
            "end": str(t_end),
            "n_bars": int(len(d)),
        },
        "start_balance": START_BALANCE,
        "shortlist_source": str(SHORTLIST_PATH.relative_to(ROOT)),
        "n_designs": len(design_results),
        "soft_pass_rule": {
            "n_ge_20": "passes() → PF>1.5 WR>55 DD<10 n>=20",
            "n_lt_20": "PF>1.2 WR>50 DD<12 (soft_pass)",
        },
        "refit_enabled": ENABLE_REFIT,
        "refit_note": (
            "OPTIONAL light neighbor-grid re-fit on train per fold; "
            "fixed-param path is primary"
        ),
        "fold_meta": [
            {
                "fold": f["fold"],
                "train_range": bar_range(f["train"]),
                "oos_range": bar_range(f["oos"]),
            }
            for f in folds
        ],
        "designs": design_results,
        "search_seconds": elapsed,
        "safety": "offline research only; never --live; never place orders",
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2) + "\n")
    print(f"\nWrote {OUT_PATH} in {elapsed:.1f}s")

    if candidates:
        cand_doc = {
            "n_candidates": len(candidates),
            "criteria": (
                "train_gates AND (shortlist oos PF>1.2 & n>=8 OR fixed WF meanPF>1.2 & n>=8) "
                "AND (wf soft_pass_rate>=0.5 OR fixed sum_NP>0 with mean_PF>1.2)"
            ),
            "candidates": candidates,
            "rejected": reject_reasons,
            "source_wf": str(OUT_PATH.relative_to(ROOT)),
        }
    else:
        cand_doc = {
            "n_candidates": 0,
            "candidates": [],
            "reason": (
                "No design met train_gates + oos PF/n + "
                "(wf soft_pass_rate>=0.5 OR fixed sum_NP>0 with mean_PF>1.2)"
            ),
            "rejected": reject_reasons,
            "criteria": (
                "train_gates AND (shortlist oos PF>1.2 & n>=8 OR fixed WF meanPF>1.2 & n>=8) "
                "AND (wf soft_pass_rate>=0.5 OR fixed sum_NP>0 with mean_PF>1.2)"
            ),
            "source_wf": str(OUT_PATH.relative_to(ROOT)),
        }
    CANDIDATES_PATH.write_text(json.dumps(cand_doc, indent=2) + "\n")
    print(f"Wrote {CANDIDATES_PATH} n_candidates={cand_doc['n_candidates']}")

    # Summary line
    for rec in design_results:
        fa = rec["fixed"]["aggregate_oos"]
        ok, reason = qualifies_candidate(rec)
        print(
            f"SUMMARY {rec['id']}: fixed NP={fa['sum_net_profit']:.1f} "
            f"n={fa['total_trades']} meanPF={fa['mean_profit_factor']:.3f} "
            f"soft_rate={fa['fold_pass_rate']:.0%} candidate={ok} ({reason})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
