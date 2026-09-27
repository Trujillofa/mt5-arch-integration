#!/usr/bin/env python3
"""Zero-knob daily rolling-β EUR+GBP → XAU long-or-flat (never short).

Charter family_id: exog_eur_gbp_tvbeta_xau_long_or_flat_v1
Roadmap sequel to failed *fixed* London FX cosign — not DXY β, not H4 pullback.

β from OLS on last 60 *completed* daily log returns (XAU ~ EUR + GBP),
excluding day T. pred_T = b_e*r_eur_T + b_g*r_gbp_T. If pred_T > 0, long XAU
on day T+1 (first H1 open → last H1 close). Else flat. Never short.

Control: always-long 0.5 lot same dates/costs.
Holdout never for selection.

SAFETY: offline. No --live.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import CONTRACT_SIZE, START_BALANCE, Metrics, metrics_from_pnls  # noqa: E402

FAMILY = "exog_eur_gbp_tvbeta_xau_long_or_flat_v1"
LOOKBACK = 60
LOTS = 0.5
POINT = 0.01
HOLDOUT = pd.Timestamp("2026-01-01")
PKG = (
    ROOT
    / "results/instrument_data_packages"
    / "4f44b452081041f39fc24f03248b8ca8-ee2a993fb5b1befd"
    / "instrument_data"
)


def _daily(path: Path, symbol: str) -> pd.Series:
    d = pd.read_csv(path)
    d["time"] = pd.to_datetime(d["time"])
    d["day"] = d["time"].dt.strftime("%Y-%m-%d")
    return d.groupby("day", sort=True)["close"].last().rename(symbol)


def _h1(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path)
    d["time"] = pd.to_datetime(d["time"])
    d["day"] = d["time"].dt.strftime("%Y-%m-%d")
    return d.sort_values("time")


def _ols_beta(y: np.ndarray, x1: np.ndarray, x2: np.ndarray) -> tuple[float, float]:
    n = len(y)
    if n < LOOKBACK:
        return 0.0, 0.0
    X = np.column_stack([np.ones(n), x1, x2])
    try:
        b, *_ = np.linalg.lstsq(X, y, rcond=None)
    except np.linalg.LinAlgError:
        return 0.0, 0.0
    return float(b[1]), float(b[2])


def _rt_cost(spread_pts: float, lots: float, slip: float, comm: float) -> float:
    return (spread_pts + 2.0 * slip) * POINT * CONTRACT_SIZE * lots + 2.0 * comm * lots


def simulate_window(
    days: list[str],
    rx: np.ndarray,
    re: np.ndarray,
    rg: np.ndarray,
    xau_h1: pd.DataFrame,
    *,
    slip: float,
    comm: float,
) -> tuple[Metrics, Metrics]:
    """Returns (family, always_long) metrics on this day list."""
    n = len(days)
    pnls: list[float] = []
    eq = [float(START_BALANCE)]
    al_entry = None
    al_exit = None
    al_cost = 0.0

    for i in range(LOOKBACK, n - 1):
        be, bg = _ols_beta(rx[i - LOOKBACK : i], re[i - LOOKBACK : i], rg[i - LOOKBACK : i])
        pred = be * re[i] + bg * rg[i]
        day_trade = days[i + 1]
        bars = xau_h1.loc[xau_h1["day"] == day_trade]
        if bars.empty:
            continue
        o = float(bars["open"].iloc[0])
        c = float(bars["close"].iloc[-1])
        spr = float(bars["spread"].iloc[0]) if "spread" in bars.columns else 0.0
        if al_entry is None:
            al_entry = o
            al_cost = _rt_cost(spr, LOTS, slip, comm)
        al_exit = c
        if pred > 0.0:
            cost = _rt_cost(spr, LOTS, slip, comm)
            pnl = (c - o) * CONTRACT_SIZE * LOTS - cost
            pnls.append(pnl)
            eq.append(eq[-1] + pnl)

    fam = metrics_from_pnls(pnls, np.asarray(eq, dtype=float))
    if al_entry is None or al_exit is None:
        al = Metrics(0, 0, 0, 0, 0, 0, 0)
    else:
        ap = (al_exit - al_entry) * CONTRACT_SIZE * LOTS - al_cost
        al = metrics_from_pnls([ap], np.array([START_BALANCE, START_BALANCE + ap], dtype=float))
    return fam, al


def main() -> int:
    costs = json.loads((ROOT / "results" / "xau_research_costs.json").read_text())
    slip = float(costs.get("slippage_points") or 0.0)
    comm = float(costs.get("commission_per_lot") or 0.0)

    xau_h1 = _h1(PKG / "xauusd_h1.csv")
    xau_d = _daily(PKG / "xauusd_h1.csv", "xau")
    eur_d = _daily(PKG / "eurusd_h1.csv", "eur")
    gbp_d = _daily(PKG / "gbpusd_h1.csv", "gbp")
    daily = pd.concat([xau_d, eur_d, gbp_d], axis=1, join="inner").dropna().sort_index()
    rx = np.log(daily["xau"]).diff().to_numpy()
    re = np.log(daily["eur"]).diff().to_numpy()
    rg = np.log(daily["gbp"]).diff().to_numpy()
    days = list(daily.index)
    # drop first nan return
    rx, re, rg, days = rx[1:], re[1:], rg[1:], days[1:]

    ts = pd.to_datetime(days)
    dev_mask = ts < HOLDOUT
    idx = np.where(dev_mask)[0]
    fam, al = simulate_window(
        [days[i] for i in idx],
        rx[idx],
        re[idx],
        rg[idx],
        xau_h1,
        slip=slip,
        comm=comm,
    )
    ok = (
        fam.n_trades >= 40
        and fam.profit_factor >= 1.2
        and fam.net_profit > 0
        and fam.max_drawdown_pct <= 15.0
        and fam.net_profit > al.net_profit
    )
    verdict = "SOFT_PASS" if ok else "SCREEN_FAIL"
    out = {
        "family_id": FAMILY,
        "verdict": verdict,
        "promote": False,
        "live_go": False,
        "lookback": LOOKBACK,
        "develop": {
            "n": fam.n_trades,
            "wr": fam.win_rate,
            "pf": fam.profit_factor,
            "np": fam.net_profit,
            "dd": fam.max_drawdown_pct,
        },
        "always_long": {"np": al.net_profit, "n": al.n_trades},
        "beat_always_long": fam.net_profit > al.net_profit,
        "holdout": None,
        "notes": "EUR+GBP rolling OLS 60d → long XAU next day iff pred>0; never short. Holdout sealed.",
    }
    dest = ROOT / "results" / f"{FAMILY}_screen.json"
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print(
        f"DEVELOP {verdict} n={fam.n_trades} WR={fam.win_rate:.1f}% PF={fam.profit_factor:.3f} "
        f"NP={fam.net_profit:.2f} DD={fam.max_drawdown_pct:.2f}% | always-long NP={al.net_profit:.2f} "
        f"beat={fam.net_profit > al.net_profit}"
    )
    print("wrote", dest)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
