#!/usr/bin/env python3
"""Walk-forward (expanding train / sequential OOS) for XAU H1 bb_rsi.

Per fold: small grid on TRAIN only; evaluate winner on that fold's OOS only.
Also runs fixed strategy_params.json across the same OOS folds (no retrain).

Does NOT overwrite strategy_params.json. Writes:
  results/xau_walkforward.json

SAFETY: offline only — no live orders, no fitting on test folds.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest import (  # noqa: E402
    START_BALANCE,
    indicators,
    load_h1,
    passes,
)
from backtest import (
    simulate as _simulate,
)

PARAMS_PATH = ROOT / "strategy_params.json"

# Charge the same costs the shipped baseline was fitted with; a frictionless
# comparison against a costed baseline is not a comparison.
_SAVED = json.loads(PARAMS_PATH.read_text())
COSTS = _SAVED.get("costs", {})


def simulate(d, **kw):  # noqa: F811  (cost-aware wrapper over backtest.simulate)
    return _simulate(d, **{**COSTS, **kw})

OUT_PATH = ROOT / "results" / "xau_walkforward.json"

# OOS region & fold count (equal bar chunks over 2025–end if data allows)
OOS_REGION_START = pd.Timestamp("2025-01-01", tz="UTC")
N_FOLDS = 4
MIN_TRAIN_BARS = 500  # need enough history before first OOS


def metrics_dict(m) -> dict:
    return {
        "net_profit": m.net_profit,
        "win_rate": m.win_rate,
        "profit_factor": m.profit_factor,
        "max_drawdown_pct": m.max_drawdown_pct,
        "n_trades": m.n_trades,
        "wins": m.wins,
        "losses": m.losses,
    }


def normalize_params(raw: dict) -> dict:
    p = dict(raw)
    if isinstance(p.get("hours"), list):
        p["hours"] = tuple(p["hours"]) if p["hours"] else None
    return p


def serializable_params(p: dict) -> dict:
    return {k: (list(v) if isinstance(v, tuple) else v) for k, v in p.items()}


def is_better(m, best_m, best_passes: bool) -> bool:
    """Prefer passers by net_profit; else best among non-passers by net_profit."""
    m_ok = passes(m)
    if m_ok and not best_passes:
        return True
    if m_ok and best_passes:
        return m.net_profit > best_m.net_profit
    if not m_ok and best_passes:
        return False
    # neither passes: pick higher net_profit (then PF, then more trades)
    if m.net_profit > best_m.net_profit:
        return True
    if abs(m.net_profit - best_m.net_profit) < 1e-9:
        if m.profit_factor > best_m.profit_factor:
            return True
        if abs(m.profit_factor - best_m.profit_factor) < 1e-9 and m.n_trades > best_m.n_trades:
            return True
    return False


def build_small_grid(base: dict) -> list[dict]:
    """Subset of retrain grid: rsi_buy × sl/tp × require_uptrend; rest from base/fixed."""
    grid: list[dict] = []
    fixed = {
        "mode": "bb_rsi",
        "rsi_sell": float(base.get("rsi_sell", 50.0)),
        "bb_col": base.get("bb_col", "bb_lo"),
        "trend_col": base.get("trend_col", "ema200"),
        "use_macd_filter": bool(base.get("use_macd_filter", False)),
        "hours": base.get("hours"),
        "long_only": bool(base.get("long_only", True)),
        "risk_pct": float(base.get("risk_pct", 0.01)),
        "cooldown": int(base.get("cooldown", 2)),
    }
    if isinstance(fixed["hours"], list):
        fixed["hours"] = tuple(fixed["hours"]) if fixed["hours"] else None

    for rsi_buy in (25, 30, 35):
        for sl_atr, tp_atr in ((1.0, 1.5), (1.5, 2.0)):
            for require_uptrend in (True, False):
                grid.append(
                    {
                        **fixed,
                        "rsi_buy": float(rsi_buy),
                        "sl_atr": float(sl_atr),
                        "tp_atr": float(tp_atr),
                        "require_uptrend": bool(require_uptrend),
                    }
                )
    return grid


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

    # equal bar chunks
    chunks = np.array_split(oos_idx, N_FOLDS)
    folds: list[dict] = []
    for k, chunk in enumerate(chunks):
        if len(chunk) == 0:
            continue
        i0, i1 = int(chunk[0]), int(chunk[-1])  # inclusive end index in d
        train = d.iloc[:i0].reset_index(drop=True)
        oos = d.iloc[i0 : i1 + 1].reset_index(drop=True)
        if len(train) < MIN_TRAIN_BARS:
            raise RuntimeError(
                f"Fold {k}: train bars {len(train)} < MIN_TRAIN_BARS={MIN_TRAIN_BARS}"
            )
        folds.append(
            {
                "fold": k + 1,
                "train_end_idx": i0,  # exclusive
                "oos_start_idx": i0,
                "oos_end_idx": i1,
                "train": train,
                "oos": oos,
            }
        )
    return folds


def pick_best_on_train(train: pd.DataFrame, grid: list[dict]) -> tuple[dict, object, bool, int]:
    best_p = grid[0]
    best_m = simulate(train, **best_p)
    best_ok = passes(best_m)
    n_pass = 1 if best_ok else 0
    for p in grid[1:]:
        m = simulate(train, **p)
        ok = passes(m)
        if ok:
            n_pass += 1
        if is_better(m, best_m, best_ok):
            best_p, best_m, best_ok = p, m, ok
    return best_p, best_m, best_ok, n_pass


def main() -> int:
    t0 = time.perf_counter()
    raw = load_h1()
    d = indicators(raw)
    times = pd.to_datetime(d["time"], utc=True)
    t_start = times.iloc[0]
    t_end = times.iloc[-1]

    baseline_raw = normalize_params(json.loads(PARAMS_PATH.read_text())["params"])
    # simulate defaults require_uptrend=True if absent
    if "require_uptrend" not in baseline_raw:
        baseline_raw = {**baseline_raw, "require_uptrend": True}

    grid = build_small_grid(baseline_raw)
    folds = build_folds(d, times)

    print(
        f"bars={len(d)} range={t_start} → {t_end} | "
        f"folds={len(folds)} grid={len(grid)} OOS_from={OOS_REGION_START}"
    )

    fold_results: list[dict] = []
    for f in folds:
        k = f["fold"]
        train, oos = f["train"], f["oos"]
        print(
            f"\n=== Fold {k}/{len(folds)} train={bar_range(train)} oos={bar_range(oos)} ==="
        )

        best_p, best_train_m, train_ok, n_pass = pick_best_on_train(train, grid)
        oos_m = simulate(oos, **best_p)
        oos_ok = passes(oos_m)

        base_oos_m = simulate(oos, **baseline_raw)
        base_oos_ok = passes(base_oos_m)

        rec = {
            "fold": k,
            "train_range": bar_range(train),
            "oos_range": bar_range(oos),
            "chosen_params": serializable_params(best_p),
            "train_metrics": metrics_dict(best_train_m),
            "train_gates_pass": train_ok,
            "n_passers_train": n_pass,
            "oos_metrics": metrics_dict(oos_m),
            "oos_gates_pass": oos_ok,
            "baseline_oos_metrics": metrics_dict(base_oos_m),
            "baseline_oos_gates_pass": base_oos_ok,
        }
        fold_results.append(rec)
        print(
            f"  WF train: PF={best_train_m.profit_factor:.3f} NP={best_train_m.net_profit:.1f} "
            f"n={best_train_m.n_trades} gates={train_ok} passers={n_pass}"
        )
        print(
            f"  WF OOS:   PF={oos_m.profit_factor:.3f} NP={oos_m.net_profit:.1f} "
            f"WR={oos_m.win_rate:.1f} DD={oos_m.max_drawdown_pct:.2f} "
            f"n={oos_m.n_trades} gates={oos_ok}"
        )
        print(
            f"  Base OOS: PF={base_oos_m.profit_factor:.3f} NP={base_oos_m.net_profit:.1f} "
            f"n={base_oos_m.n_trades} gates={base_oos_ok}"
        )
        print(f"  params={best_p}")

    # Aggregate WF OOS
    oos_nps = [r["oos_metrics"]["net_profit"] for r in fold_results]
    oos_trades = [r["oos_metrics"]["n_trades"] for r in fold_results]
    oos_wrs = [r["oos_metrics"]["win_rate"] for r in fold_results]
    oos_pfs = [r["oos_metrics"]["profit_factor"] for r in fold_results]
    oos_dds = [r["oos_metrics"]["max_drawdown_pct"] for r in fold_results]
    oos_pass = [bool(r["oos_gates_pass"]) for r in fold_results]
    total_trades = int(sum(oos_trades))
    total_np = float(sum(oos_nps))

    # Weighted mean WR (by trades); mean PF of folds with trades
    wr_num = sum(
        r["oos_metrics"]["win_rate"] * r["oos_metrics"]["n_trades"] for r in fold_results
    )
    mean_wr = float(wr_num / total_trades) if total_trades else 0.0
    pfs_with_trades = [
        r["oos_metrics"]["profit_factor"]
        for r in fold_results
        if r["oos_metrics"]["n_trades"] > 0
    ]
    mean_pf = float(np.mean(pfs_with_trades)) if pfs_with_trades else 0.0
    # Combined PF-ish: total gross W / total gross L reconstructed is hard without
    # per-trade; use sum(NP) and trade-weighted mean PF as report stats.
    fold_pass_rate = float(sum(oos_pass) / len(oos_pass)) if oos_pass else 0.0
    min_oos_dd = float(min(oos_dds)) if oos_dds else 0.0
    max_oos_dd = float(max(oos_dds)) if oos_dds else 0.0

    # Baseline aggregate
    b_nps = [r["baseline_oos_metrics"]["net_profit"] for r in fold_results]
    b_trades = [r["baseline_oos_metrics"]["n_trades"] for r in fold_results]
    b_wrs = [r["baseline_oos_metrics"]["win_rate"] for r in fold_results]
    b_pfs = [
        r["baseline_oos_metrics"]["profit_factor"]
        for r in fold_results
        if r["baseline_oos_metrics"]["n_trades"] > 0
    ]
    b_dds = [r["baseline_oos_metrics"]["max_drawdown_pct"] for r in fold_results]
    b_pass = [bool(r["baseline_oos_gates_pass"]) for r in fold_results]
    b_total_trades = int(sum(b_trades))
    b_total_np = float(sum(b_nps))
    b_wr_num = sum(
        r["baseline_oos_metrics"]["win_rate"] * r["baseline_oos_metrics"]["n_trades"]
        for r in fold_results
    )
    b_mean_wr = float(b_wr_num / b_total_trades) if b_total_trades else 0.0
    b_mean_pf = float(np.mean(b_pfs)) if b_pfs else 0.0
    b_fold_pass_rate = float(sum(b_pass) / len(b_pass)) if b_pass else 0.0

    elapsed = time.perf_counter() - t0
    aggregate = {
        "n_folds": len(fold_results),
        "sum_net_profit": total_np,
        "total_trades": total_trades,
        "mean_win_rate": mean_wr,
        "mean_profit_factor": mean_pf,
        "fold_pass_rate": fold_pass_rate,
        "folds_pass": oos_pass,
        "min_oos_drawdown_pct": min_oos_dd,
        "max_oos_drawdown_pct": max_oos_dd,
        "per_fold_net_profit": oos_nps,
        "per_fold_trades": oos_trades,
        "per_fold_profit_factor": oos_pfs,
        "per_fold_win_rate": oos_wrs,
    }
    baseline_aggregate = {
        "sum_net_profit": b_total_np,
        "total_trades": b_total_trades,
        "mean_win_rate": b_mean_wr,
        "mean_profit_factor": b_mean_pf,
        "fold_pass_rate": b_fold_pass_rate,
        "folds_pass": b_pass,
        "min_oos_drawdown_pct": float(min(b_dds)) if b_dds else 0.0,
        "max_oos_drawdown_pct": float(max(b_dds)) if b_dds else 0.0,
        "per_fold_net_profit": b_nps,
        "per_fold_trades": b_trades,
    }

    out = {
        "method": "expanding_train_equal_bar_oos",
        "n_folds": len(fold_results),
        "oos_region_start": str(OOS_REGION_START),
        "data_range": {"start": str(t_start), "end": str(t_end), "n_bars": int(len(d))},
        "grid_size": len(grid),
        "grid_axes": {
            "rsi_buy": [25, 30, 35],
            "sl_tp": [[1.0, 1.5], [1.5, 2.0]],
            "require_uptrend": [True, False],
        },
        "selection": "passes then net_profit on train only",
        "baseline_params": serializable_params(baseline_raw),
        "start_balance": START_BALANCE,
        "folds": fold_results,
        "aggregate_oos": aggregate,
        "baseline_aggregate_oos": baseline_aggregate,
        "vs_baseline": {
            "delta_sum_net_profit": total_np - b_total_np,
            "delta_total_trades": total_trades - b_total_trades,
            "delta_mean_pf": mean_pf - b_mean_pf,
            "delta_fold_pass_rate": fold_pass_rate - b_fold_pass_rate,
            "wf_better_on_np": total_np > b_total_np,
        },
        "search_seconds": elapsed,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2) + "\n")
    print(f"\nWrote {OUT_PATH} in {elapsed:.1f}s")
    print(
        f"SUMMARY WF OOS: NP={total_np:.2f} trades={total_trades} "
        f"meanPF={mean_pf:.3f} meanWR={mean_wr:.1f} "
        f"pass_rate={fold_pass_rate:.0%} minDD={min_oos_dd:.2f}"
    )
    print(
        f"SUMMARY BASE OOS: NP={b_total_np:.2f} trades={b_total_trades} "
        f"meanPF={b_mean_pf:.3f} meanWR={b_mean_wr:.1f} "
        f"pass_rate={b_fold_pass_rate:.0%}"
    )
    print(
        f"VS BASE: dNP={total_np - b_total_np:.2f} "
        f"dPF={mean_pf - b_mean_pf:.3f} "
        f"dPass={fold_pass_rate - b_fold_pass_rate:.0%}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
