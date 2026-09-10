#!/usr/bin/env python3
"""DFII10 falling-regime: long gold or flat.

Family ``exog_dfii10_regime_long_or_flat_v1``.
Lock: ``results/xau_exog_regime/lock.json`` (frozen before official metrics).

Never short as the primary rule. Does not reopen daily β-sign books.
Never ``backtest.py --save``. Never ``--live``.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from xau_exog_beta import gold_daily  # noqa: E402
from xau_exog_beta_realyield import asof_on  # noqa: E402
from xau_research_costs import load_research_costs, refuse_mutated_research_costs  # noqa: E402

import backtest as bt  # noqa: E402

FAMILY_ID = "exog_dfii10_regime_long_or_flat_v1"
LOCK_PATH = _ROOT / "results" / "xau_exog_regime" / "lock.json"
FRED_DIR = _ROOT / "results" / "xau_exog_beta" / "data" / "fred"
OUT_DIR = _ROOT / "results" / "xau_exog_regime"
HOLDOUT = pd.Timestamp("2026-01-01", tz="UTC")
LOOKBACK = 20
LOTS = 0.10
CONTRACT = 100.0
START_BAL = 10_000.0
PROMOTE = False
LIVE_GO = False
PCT_LOOKBACK = 252
PCT_Q = 0.40


@dataclass(frozen=True)
class Trade:
    entry_i: int
    exit_i: int
    side: int
    entry: float
    exit: float
    utc_date: str
    exit_date: str
    reason: str
    on_days: int
    cost: float
    pnl: float


def load_lock() -> dict:
    if not LOCK_PATH.is_file():
        raise SystemExit(f"missing lock {LOCK_PATH}")
    lock = json.loads(LOCK_PATH.read_text())
    if lock.get("family_id") != FAMILY_ID:
        raise SystemExit("family_id mismatch")
    if not lock.get("frozen_before_metrics"):
        raise SystemExit("lock must be frozen_before_metrics")
    if lock.get("promote") is True or lock.get("live_go") is True:
        raise SystemExit("promote/live_go must stay false")
    return lock



def _fred_dfii10() -> pd.DataFrame:
    raw = pd.read_csv(FRED_DIR / "DFII10.csv", parse_dates=["date"])
    return (
        pd.DataFrame(
            {
                "date": pd.to_datetime(raw["date"], utc=True).dt.normalize(),
                "value": raw["value"].astype(float),
            }
        )
        .dropna()
        .drop_duplicates("date")
        .sort_values("date")
        .reset_index(drop=True)
    )


def aligned_panel() -> pd.DataFrame:
    gold = gold_daily(bt.load_h1())
    real = _fred_dfii10()
    p = gold.copy()
    p["dfii10"] = asof_on(p["date"], real, "dfii10")
    return p


def regime_falling(dfii: np.ndarray, lookback: int = LOOKBACK) -> np.ndarray:
    """True = long. Uses only values at/before i (as-of series already causal)."""
    n = len(dfii)
    out = np.zeros(n, dtype=bool)
    for i in range(lookback, n):
        a, b = dfii[i], dfii[i - lookback]
        if np.isfinite(a) and np.isfinite(b):
            out[i] = bool(a < b)
    return out


def regime_below_pct(dfii: np.ndarray, lookback: int = PCT_LOOKBACK, q: float = PCT_Q) -> np.ndarray:
    n = len(dfii)
    out = np.zeros(n, dtype=bool)
    for i in range(1, n):
        start = max(0, i - lookback)
        past = dfii[start:i]  # prior days only, not i
        past = past[np.isfinite(past)]
        if past.size < 40:
            continue
        if np.isfinite(dfii[i]) and dfii[i] < float(np.quantile(past, q)):
            out[i] = True
    return out


def _rt_cost(spread_pts: float, costs: dict) -> float:
    return (
        (float(spread_pts) + 2.0 * float(costs["slippage_points"]))
        * float(costs["point_size"])
        * CONTRACT
        * LOTS
        + 2.0 * float(costs["commission_per_lot"]) * LOTS
    )


def simulate_regime(p: pd.DataFrame, on: np.ndarray, costs: dict) -> list[Trade]:
    """Enter/exit at next daily open after regime[i] is knowable. Long only."""
    n = len(p)
    open_ = p["open"].to_numpy(float)
    close = p["close"].to_numpy(float)
    spread = np.nan_to_num(p["spread"].to_numpy(float), nan=0.0)
    dates = pd.to_datetime(p["date"], utc=True)
    trades: list[Trade] = []
    pos = False
    entry_i = 0
    entry = 0.0
    on_days = 0

    def _close(i: int, px: float, reason: str) -> None:
        nonlocal pos
        cost = _rt_cost(spread[entry_i], costs)
        pnl = (px - entry) * CONTRACT * LOTS - cost
        trades.append(
            Trade(
                entry_i=entry_i,
                exit_i=i,
                side=1,
                entry=float(entry),
                exit=float(px),
                utc_date=str(dates.iloc[entry_i].date()),
                exit_date=str(dates.iloc[i].date()),
                reason=reason,
                on_days=on_days,
                cost=float(cost),
                pnl=float(pnl),
            )
        )
        pos = False

    for i in range(n - 1):
        want = bool(on[i])
        if (not pos) and want:
            entry_i = i + 1
            entry = float(open_[entry_i])
            pos = True
            on_days = 1
            continue
        if pos:
            on_days += 1
            if not want:
                _close(i + 1, float(open_[i + 1]), "regime_off")
    if pos:
        _close(n - 1, float(close[-1]), "eod")
    return trades


def simulate_always_long(p: pd.DataFrame, costs: dict, first_i: int) -> list[Trade]:
    """One continuous long from first eligible next-open through last bar."""
    n = len(p)
    if first_i + 1 >= n:
        return []
    open_ = p["open"].to_numpy(float)
    close = p["close"].to_numpy(float)
    spread = np.nan_to_num(p["spread"].to_numpy(float), nan=0.0)
    dates = pd.to_datetime(p["date"], utc=True)
    entry_i = first_i + 1
    entry = float(open_[entry_i])
    exit_i = n - 1
    cost = _rt_cost(spread[entry_i], costs)
    pnl = (float(close[exit_i]) - entry) * CONTRACT * LOTS - cost
    return [
        Trade(
            entry_i=entry_i,
            exit_i=exit_i,
            side=1,
            entry=entry,
            exit=float(close[exit_i]),
            utc_date=str(dates.iloc[entry_i].date()),
            exit_date=str(dates.iloc[exit_i].date()),
            reason="always_long",
            on_days=exit_i - entry_i + 1,
            cost=float(cost),
            pnl=float(pnl),
        )
    ]


def metrics(trades: list[Trade], *, on_days: int | None = None) -> dict:
    pnls = [t.pnl for t in trades]
    if not pnls:
        return {
            "n_trades": 0,
            "regime_on_days": int(on_days or 0),
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "net_profit": 0.0,
            "max_dd_pct": 0.0,
        }
    a = np.asarray(pnls, dtype=float)
    wins = a[a > 0]
    losses = a[a <= 0]
    gw = float(wins.sum()) if len(wins) else 0.0
    gl = float(-losses.sum()) if len(losses) else 0.0
    pf = (gw / gl) if gl > 1e-12 else (99.0 if gw > 0 else 0.0)
    eq = START_BAL + np.cumsum(a)
    peak = np.maximum.accumulate(eq)
    dd = np.where(peak > 0, (peak - eq) / peak, 0.0)
    return {
        "n_trades": int(len(a)),
        "regime_on_days": int(on_days if on_days is not None else sum(t.on_days for t in trades)),
        "win_rate": float((a > 0).mean()),
        "profit_factor": float(pf),
        "net_profit": float(a.sum()),
        "max_dd_pct": float(dd.max() * 100.0),
        "wins": int(len(wins)),
        "losses": int(len(losses)),
    }


def continue_ok(reg: dict, base: dict) -> bool:
    return (
        int(reg.get("regime_on_days") or 0) >= 30
        and float(reg["profit_factor"]) >= 1.0
        and float(reg["net_profit"]) > float(base["net_profit"])
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--eval-holdout", action="store_true")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args()
    load_lock()
    costs = load_research_costs()
    refuse_mutated_research_costs(costs)
    p = aligned_panel()
    dfii = p["dfii10"].to_numpy(float)
    on_pri = regime_falling(dfii, LOOKBACK)
    on_rob = regime_below_pct(dfii)
    first_i = LOOKBACK
    dates = pd.to_datetime(p["date"], utc=True)

    def _clip(trades: list[Trade], *, holdout: bool) -> list[Trade]:
        out = []
        for t in trades:
            d = pd.Timestamp(t.utc_date).tz_localize("UTC")
            if holdout and d >= HOLDOUT or (not holdout) and d < HOLDOUT:
                out.append(t)
        return out

    # Always-long per window: flatten at last bar of that window, not across holdout.
    def _always(end_mask) -> list[Trade]:
        idx = np.where(end_mask)[0]
        if len(idx) == 0:
            return []
        sub = p.iloc[: idx[-1] + 1].reset_index(drop=True)
        # first eligible in this slice
        return simulate_always_long(sub, costs, first_i)

    dev_mask = dates < HOLDOUT
    ho_mask = dates >= HOLDOUT

    reg_all = simulate_regime(p, on_pri, costs)
    rob_all = simulate_regime(p, on_rob, costs)
    r_dev, r_ho = _clip(reg_all, holdout=False), _clip(reg_all, holdout=True)
    rob_dev, _ = _clip(rob_all, holdout=False), None
    al_dev = _always(dev_mask.to_numpy())
    # holdout always-long starts at first holdout bar that has lookback in full series
    ho_idx = np.where(ho_mask.to_numpy())[0]
    al_ho: list[Trade] = []
    if len(ho_idx):
        # enter at first holdout open, exit last holdout close
        sub = p.iloc[: ho_idx[-1] + 1].reset_index(drop=True)
        start = max(int(ho_idx[0]) - 1, first_i)
        al_ho = simulate_always_long(sub.iloc[start:].reset_index(drop=True), costs, 0)

    md = metrics(r_dev)
    ml = metrics(al_dev)
    mr = metrics(rob_dev)
    verdict = "continue" if continue_ok(md, ml) else "kill"

    print("=== DEVELOP (utc_date < 2026-01-01) ===")
    print(f"family {FAMILY_ID}  panel={len(p)}  {p.date.min().date()} → {p.date.max().date()}")
    print(f"{'book':28} {'n':>4} {'on_d':>5} {'WR':>6} {'PF':>7} {'NP':>10} {'DD%':>7}")
    for name, m in (
        ("regime_falling_20d", md),
        ("always_long_continuous", ml),
        ("robust_pct40_not_pick", mr),
    ):
        print(
            f"{name:28} {m['n_trades']:4d} {m['regime_on_days']:5d} "
            f"{100 * m['win_rate']:5.1f}% {m['profit_factor']:7.3f} "
            f"{m['net_profit']:10.1f} {m['max_dd_pct']:7.2f}"
        )
    print(f"verdict={verdict}  n_floor=regime_on_days>=30; PF>=1 and net>always_long")
    print("costs: slip=0 UNMEASURED  lots=0.10  long_or_flat  no short")

    payload = {
        "family_id": FAMILY_ID,
        "promote": PROMOTE,
        "live_go": LIVE_GO,
        "verdict": verdict,
        "score_window": "develop",
        "costs": costs,
        "slip_label": "UNMEASURED",
        "develop": {
            "regime_falling_20d": md,
            "always_long_continuous": ml,
            "robust_pct40_not_pick": mr,
        },
    }
    if args.eval_holdout:
        payload["holdout"] = {
            "regime_falling_20d": metrics(r_ho),
            "always_long_continuous": metrics(al_ho),
        }
        print("=== HOLDOUT (evaluate once) ===")
        for name, m in payload["holdout"].items():
            print(
                f"{name:28} {m['n_trades']:4d} {m['regime_on_days']:5d} "
                f"{100 * m['win_rate']:5.1f}% {m['profit_factor']:7.3f} "
                f"{m['net_profit']:10.1f} {m['max_dd_pct']:7.2f}"
            )
    else:
        print("holdout: not printed (pass --eval-holdout)")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "develop.json").write_text(json.dumps(payload, indent=2) + "\n")
    if args.eval_holdout:
        (args.out_dir / "holdout.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {args.out_dir / 'develop.json'}")


if __name__ == "__main__":
    main()
