#!/usr/bin/env python3
"""Daily rolling-β gold follow: DXY + US10Y → XAU.

Family ``exog_dxy_us10y_daily_tvbeta_xau_follow_flat_v1``.
Lock: ``results/xau_exog_beta/lock.json`` (frozen before official metrics).

Not a reopen of ``exog_london_fx_cosign_xau_follow_flat``.
Not M5. Not GARCH. Never ``backtest.py --save``. Never ``--live``.
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

from xau_research_costs import (  # noqa: E402
    load_research_costs,
    refuse_mutated_research_costs,
)

import backtest as bt  # noqa: E402

FAMILY_ID = "exog_dxy_us10y_daily_tvbeta_xau_follow_flat_v1"
LOCK_PATH = _ROOT / "results" / "xau_exog_beta" / "lock.json"
DATA_DIR = _ROOT / "results" / "xau_exog_beta" / "data"
OUT_DIR = _ROOT / "results" / "xau_exog_beta"
HOLDOUT = pd.Timestamp("2026-01-01", tz="UTC")
WINDOW = 60
WINDOW_ROBUST = 120
PRED_MIN = 0.002
OCCUPANCY = 5
SL_ATR = 1.5
ATR_N = 14
LOTS = 0.10
CONTRACT = 100.0
START_BAL = 10_000.0
PROMOTE = False
LIVE_GO = False


@dataclass(frozen=True)
class Trade:
    entry_i: int
    exit_i: int
    side: int
    entry: float
    exit: float
    reason: str
    utc_date: str
    pred: float
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


def _factor_daily(path: Path, name: str) -> pd.DataFrame:
    raw = pd.read_csv(path)
    ts = pd.to_datetime(raw["close_ts_utc"], utc=True)
    out = pd.DataFrame(
        {
            "date": ts.dt.normalize(),
            name: raw["close"].astype(float).to_numpy(),
        }
    )
    return out.dropna().drop_duplicates("date").sort_values("date")


def gold_daily(h1: pd.DataFrame) -> pd.DataFrame:
    d = h1.copy()
    d["time"] = pd.to_datetime(d["time"], utc=True)
    d["date"] = d["time"].dt.normalize()
    g = d.groupby("date", sort=True)
    out = pd.DataFrame(
        {
            "date": g["time"].min().index,
            "open": g["open"].first().to_numpy(float),
            "high": g["high"].max().to_numpy(float),
            "low": g["low"].min().to_numpy(float),
            "close": g["close"].last().to_numpy(float),
            "spread": g["spread"].last().to_numpy(float),
        }
    ).reset_index(drop=True)
    return out


def aligned_panel() -> pd.DataFrame:
    h1 = bt.load_h1()
    gold = gold_daily(h1)
    dxy = _factor_daily(DATA_DIR / "dxy_1d.csv", "dxy")
    yld = _factor_daily(DATA_DIR / "us10y_1d.csv", "us10y")
    p = gold.merge(dxy, on="date", how="inner").merge(yld, on="date", how="inner")
    p = p.sort_values("date").reset_index(drop=True)
    p["r_xau"] = np.log(p["close"] / p["close"].shift(1))
    p["r_dxy"] = np.log(p["dxy"] / p["dxy"].shift(1))
    p["r_10y"] = np.log(p["us10y"] / p["us10y"].shift(1))
    tr = pd.concat(
        [
            (p["high"] - p["low"]),
            (p["high"] - p["close"].shift(1)).abs(),
            (p["low"] - p["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    p["atr"] = tr.ewm(alpha=1 / ATR_N, adjust=False).mean()
    return p


def rolling_beta(r_y: np.ndarray, r1: np.ndarray, r2: np.ndarray, i: int, window: int) -> tuple[float, float] | None:
    """OLS r_y ~ a + b1 r1 + b2 r2 on [i-window+1, i]. Causal at i."""
    start = i - window + 1
    if start < 1 or i >= len(r_y):
        return None
    y = r_y[start : i + 1]
    x1 = r1[start : i + 1]
    x2 = r2[start : i + 1]
    if not (np.isfinite(y).all() and np.isfinite(x1).all() and np.isfinite(x2).all()):
        return None
    if y.size < window:
        return None
    x = np.column_stack([np.ones(y.size), x1, x2])
    try:
        coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    except np.linalg.LinAlgError:
        return None
    return float(coef[1]), float(coef[2])


def pred_at(p: pd.DataFrame, i: int, window: int) -> float | None:
    b = rolling_beta(
        p["r_xau"].to_numpy(float),
        p["r_dxy"].to_numpy(float),
        p["r_10y"].to_numpy(float),
        i,
        window,
    )
    if b is None:
        return None
    rd, ry = float(p["r_dxy"].iloc[i]), float(p["r_10y"].iloc[i])
    if not (np.isfinite(rd) and np.isfinite(ry)):
        return None
    return b[0] * rd + b[1] * ry


def simulate(
    p: pd.DataFrame,
    costs: dict,
    *,
    window: int = WINDOW,
    force_long: bool = False,
    pred_min: float = PRED_MIN,
) -> list[Trade]:
    n = len(p)
    open_ = p["open"].to_numpy(float)
    high = p["high"].to_numpy(float)
    low = p["low"].to_numpy(float)
    close = p["close"].to_numpy(float)
    atr = p["atr"].to_numpy(float)
    spread = np.nan_to_num(p["spread"].to_numpy(float), nan=0.0)
    dates = pd.to_datetime(p["date"], utc=True)
    point = float(costs["point_size"])
    slip = float(costs["slippage_points"])
    comm = float(costs["commission_per_lot"])
    trades: list[Trade] = []
    pos = 0
    entry = sl = 0.0
    entry_i = 0
    pred_e = 0.0
    left = 0

    def _cost(i: int) -> float:
        return (spread[i] + 2.0 * slip) * point * CONTRACT * LOTS + 2.0 * comm * LOTS

    def _close(i: int, px: float, reason: str) -> None:
        nonlocal pos
        cost = _cost(entry_i)
        pnl = (px - entry) * pos * CONTRACT * LOTS - cost
        trades.append(
            Trade(
                entry_i=entry_i,
                exit_i=i,
                side=pos,
                entry=float(entry),
                exit=float(px),
                reason=reason,
                utc_date=str(dates.iloc[entry_i].date()),
                pred=float(pred_e),
                cost=float(cost),
                pnl=float(pnl),
            )
        )
        pos = 0

    for i in range(n):
        if pos != 0:
            hit_sl = (low[i] <= sl) if pos > 0 else (high[i] >= sl)
            if hit_sl:
                _close(i, sl, "sl")
                left = 0
            else:
                left -= 1
                if left <= 0:
                    _close(i, close[i], "time")
        if pos != 0:
            continue
        if i + 1 >= n:
            continue
        pred = pred_at(p, i, window)
        if pred is None or abs(pred) < pred_min:
            continue
        side = 1 if force_long else (1 if pred > 0 else -1)
        if atr[i + 1] <= 0 or not np.isfinite(atr[i + 1]):
            continue
        pos = side
        entry_i = i + 1
        entry = float(open_[i + 1])
        sl = entry - side * SL_ATR * float(atr[i + 1])
        pred_e = float(pred)
        left = OCCUPANCY
    if pos != 0:
        _close(n - 1, float(close[-1]), "eod")
    return trades


def metrics(trades: list[Trade]) -> dict:
    pnls = [t.pnl for t in trades]
    if not pnls:
        return {
            "n": 0,
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
        "n": int(len(a)),
        "win_rate": float((a > 0).mean()),
        "profit_factor": float(pf),
        "net_profit": float(a.sum()),
        "max_dd_pct": float(dd.max() * 100.0),
        "wins": int(len(wins)),
        "losses": int(len(losses)),
    }


def split_dev_ho(trades: list[Trade]) -> tuple[list[Trade], list[Trade]]:
    dev, ho = [], []
    for t in trades:
        d = pd.Timestamp(t.utc_date).tz_localize("UTC")
        (ho if d >= HOLDOUT else dev).append(t)
    return dev, ho


def continue_ok(beta: dict, base: dict) -> bool:
    return (
        int(beta["n"]) >= 30
        and float(beta["profit_factor"]) > float(base["profit_factor"])
        and float(beta["profit_factor"]) >= 1.0
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
    beta_all = simulate(p, costs, window=WINDOW, force_long=False)
    long_all = simulate(p, costs, window=WINDOW, force_long=True)
    rob_all = simulate(p, costs, window=WINDOW_ROBUST, force_long=False)
    b_dev, b_ho = split_dev_ho(beta_all)
    l_dev, l_ho = split_dev_ho(long_all)
    r_dev, _ = split_dev_ho(rob_all)
    mb, ml, mr = metrics(b_dev), metrics(l_dev), metrics(r_dev)
    verdict = "continue" if continue_ok(mb, ml) else "kill"
    print("=== DEVELOP (utc_date < 2026-01-01) ===")
    print(f"family {FAMILY_ID}  panel_days={len(p)}  {p.date.min().date()} → {p.date.max().date()}")
    print(f"{'book':28} {'n':>4} {'WR':>6} {'PF':>7} {'NP':>10} {'DD%':>7}")
    for name, m in (
        ("beta_follow_w60", mb),
        ("always_long_same_entries", ml),
        ("robust_w120_not_pick", mr),
    ):
        print(
            f"{name:28} {m['n']:4d} {100*m['win_rate']:5.1f}% {m['profit_factor']:7.3f} "
            f"{m['net_profit']:10.1f} {m['max_dd_pct']:7.2f}"
        )
    print(f"verdict={verdict}  (score: develop PF vs always-long; n_floor=30)")
    print("costs: slip=0 UNMEASURED  lots=0.10  occupancy=5D  SL=1.5 ATR")
    payload = {
        "family_id": FAMILY_ID,
        "promote": PROMOTE,
        "live_go": LIVE_GO,
        "verdict": verdict,
        "score_window": "develop",
        "costs": costs,
        "slip_label": "UNMEASURED",
        "panel": {
            "n_days": int(len(p)),
            "start": str(p["date"].min()),
            "end": str(p["date"].max()),
        },
        "develop": {
            "beta_follow_w60": mb,
            "always_long_same_entries": ml,
            "robust_w120_not_pick": mr,
        },
    }
    if args.eval_holdout:
        payload["holdout"] = {
            "beta_follow_w60": metrics(b_ho),
            "always_long_same_entries": metrics(l_ho),
        }
        print("=== HOLDOUT (evaluate once) ===")
        for name, m in payload["holdout"].items():
            print(
                f"{name:28} {m['n']:4d} {100*m['win_rate']:5.1f}% {m['profit_factor']:7.3f} "
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
