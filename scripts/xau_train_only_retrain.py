#!/usr/bin/env python3
"""Train-only grid search for XAU H1 bb_rsi; evaluate once on frozen OOS.

Does NOT overwrite strategy_params.json. Writes:
  results/xau_train_only_retrain.json
  results/xau_candidate_params.json (only if OOS gates pass and n_trades>=15)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest import (  # noqa: E402
    START_BALANCE,
    indicators,
    load_h1,
    passes,
    simulate as _simulate,
)

PARAMS_PATH = ROOT / "strategy_params.json"

# Charge the same costs the shipped baseline was fitted with; a frictionless
# comparison against a costed baseline is not a comparison.
_SAVED = json.loads(PARAMS_PATH.read_text())
COSTS = _SAVED.get("costs", {})


def simulate(d, **kw):  # noqa: F811  (cost-aware wrapper over backtest.simulate)
    return _simulate(d, **{**COSTS, **kw})

OUT_PATH = ROOT / "results" / "xau_train_only_retrain.json"
CANDIDATE_PATH = ROOT / "results" / "xau_candidate_params.json"


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


def is_better(m, best_m, best_passes: bool) -> bool:
    """Prefer passers by net_profit; else best PF among PF>1.0; else best PF."""
    m_ok = passes(m)
    if m_ok and not best_passes:
        return True
    if m_ok and best_passes:
        return m.net_profit > best_m.net_profit
    if not m_ok and best_passes:
        return False
    # neither passes
    m_pf_ok = m.profit_factor > 1.0 and m.n_trades > 0
    best_pf_ok = best_m.profit_factor > 1.0 and best_m.n_trades > 0
    if m_pf_ok and not best_pf_ok:
        return True
    if m_pf_ok and best_pf_ok:
        if m.profit_factor > best_m.profit_factor:
            return True
        if abs(m.profit_factor - best_m.profit_factor) < 1e-9 and m.net_profit > best_m.net_profit:
            return True
        return False
    if not m_pf_ok and best_pf_ok:
        return False
    # both PF<=1: still pick higher PF, then net_profit
    if m.profit_factor > best_m.profit_factor:
        return True
    if abs(m.profit_factor - best_m.profit_factor) < 1e-9 and m.net_profit > best_m.net_profit:
        return True
    return False


def build_grid() -> list[dict]:
    grid: list[dict] = []
    for rsi_buy in (25, 30, 35):
        for rsi_sell in (50, 55, 60):
            for sl_atr, tp_atr in ((1.0, 1.5), (1.5, 2.0), (1.2, 2.5)):
                for require_uptrend in (True, False):
                    for bb_col in ("bb_lo", "bb_lo15"):
                        for cooldown in (1, 2, 3):
                            grid.append(
                                dict(
                                    mode="bb_rsi",
                                    rsi_buy=float(rsi_buy),
                                    rsi_sell=float(rsi_sell),
                                    sl_atr=float(sl_atr),
                                    tp_atr=float(tp_atr),
                                    bb_col=bb_col,
                                    trend_col="ema200",
                                    use_macd_filter=False,
                                    hours=None,
                                    long_only=True,
                                    risk_pct=0.01,
                                    cooldown=int(cooldown),
                                    require_uptrend=bool(require_uptrend),
                                )
                            )
    return grid


def main() -> int:
    t0 = time.perf_counter()
    raw = load_h1()
    d = indicators(raw)
    times = pd.to_datetime(d["time"], utc=True)
    t_start = times.iloc[0]
    t_end = times.iloc[-1]
    split_ts = t_start + 0.7 * (t_end - t_start)

    train = d.loc[times < split_ts].reset_index(drop=True)
    oos = d.loc[times >= split_ts].reset_index(drop=True)
    print(
        f"bars={len(d)} train={len(train)} oos={len(oos)} "
        f"split={split_ts} range={t_start} → {t_end}"
    )

    grid = build_grid()
    search_size = len(grid)
    print(f"grid size={search_size}")

    best_p = grid[0]
    best_m = simulate(train, **best_p)
    best_ok = passes(best_m)
    n_pass = 1 if best_ok else 0

    for i, p in enumerate(grid):
        if i == 0:
            continue
        m = simulate(train, **p)
        ok = passes(m)
        if ok:
            n_pass += 1
        if is_better(m, best_m, best_ok):
            best_p, best_m, best_ok = p, m, ok
        if (i + 1) % 50 == 0:
            print(
                f"... {i+1}/{search_size} passers={n_pass} "
                f"best_PF={best_m.profit_factor:.3f} NP={best_m.net_profit:.1f} "
                f"n={best_m.n_trades} gates={best_ok}"
            )

    search_s = time.perf_counter() - t0
    print(f"--- train winner (search {search_s:.1f}s, passers={n_pass}) ---")
    print(
        f"PF={best_m.profit_factor:.4f} WR={best_m.win_rate:.2f} "
        f"DD={best_m.max_drawdown_pct:.2f} n={best_m.n_trades} NP={best_m.net_profit:.2f}"
    )
    print(f"params={best_p}")

    # Frozen OOS eval once — no re-search
    oos_m = simulate(oos, **best_p)
    oos_gates_pass = passes(oos_m)
    print("--- OOS (frozen) ---")
    print(
        f"PF={oos_m.profit_factor:.4f} WR={oos_m.win_rate:.2f} "
        f"DD={oos_m.max_drawdown_pct:.2f} n={oos_m.n_trades} NP={oos_m.net_profit:.2f} "
        f"gates={oos_gates_pass}"
    )

    # Baseline: current strategy_params.json
    baseline_raw = normalize_params(json.loads(PARAMS_PATH.read_text())["params"])
    # require_uptrend may be absent; simulate defaults True
    baseline_train = simulate(train, **baseline_raw)
    baseline_oos = simulate(oos, **baseline_raw)
    print("--- baseline train/OOS ---")
    print(f"train: {metrics_dict(baseline_train)}")
    print(f"oos:   {metrics_dict(baseline_oos)}")

    out = {
        "best_params": {
            k: (list(v) if isinstance(v, tuple) else v) for k, v in best_p.items()
        },
        "train_metrics": metrics_dict(best_m),
        "oos_metrics": metrics_dict(oos_m),
        "baseline_train": metrics_dict(baseline_train),
        "baseline_oos": metrics_dict(baseline_oos),
        "oos_gates_pass": oos_gates_pass,
        "search_size": search_size,
        "split": str(split_ts),
        "train_gates_pass": best_ok,
        "n_passers_train": n_pass,
        "search_seconds": search_s,
        "baseline_params": {
            k: (list(v) if isinstance(v, tuple) else v) for k, v in baseline_raw.items()
        },
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2) + "\n")
    print(f"Wrote {OUT_PATH}")

    # Candidate only if OOS gates pass and enough trades — do NOT touch strategy_params.json
    if oos_gates_pass and oos_m.n_trades >= 15:
        cand = {
            "metrics": {
                "net_profit": oos_m.net_profit,
                "win_rate": oos_m.win_rate,
                "profit_factor": oos_m.profit_factor,
                "max_drawdown_pct": oos_m.max_drawdown_pct,
                "n_trades": oos_m.n_trades,
            },
            "params": {
                k: (list(v) if isinstance(v, tuple) else v) for k, v in best_p.items()
            },
            "timeframe": "H1",
            "start_balance": START_BALANCE,
            "source": "train_only_retrain",
            "train_metrics": metrics_dict(best_m),
            "oos_metrics": metrics_dict(oos_m),
        }
        CANDIDATE_PATH.write_text(json.dumps(cand, indent=2) + "\n")
        print(f"Wrote candidate {CANDIDATE_PATH}")
    else:
        print(
            f"No candidate write (oos_gates_pass={oos_gates_pass}, "
            f"n_trades={oos_m.n_trades}; need gates + n>=15)"
        )

    print(
        f"SUMMARY train PF={best_m.profit_factor:.3f} WR={best_m.win_rate:.1f} "
        f"DD={best_m.max_drawdown_pct:.2f} n={best_m.n_trades} | "
        f"OOS PF={oos_m.profit_factor:.3f} WR={oos_m.win_rate:.1f} "
        f"DD={oos_m.max_drawdown_pct:.2f} n={oos_m.n_trades} gates={oos_gates_pass}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
