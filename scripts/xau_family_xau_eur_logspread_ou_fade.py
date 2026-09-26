#!/usr/bin/env python3
"""Zero-knob XAU–EUR log-spread OU fade (both legs).

family_id: xau_eur_logspread_ou_fade_v1
β: OLS log XAU ~ log EUR on last 60 completed days (exclude today).
z vs that window. |z|>2 fade next day; exit z-cross 0 or 20 days.
Long spread = long 0.5 XAU, short EUR notional = β * XAU notional.

SAFETY: offline. No --live. Holdout not for selection.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import START_BALANCE, metrics_from_pnls  # noqa: E402

FAMILY = "xau_eur_logspread_ou_fade_v1"
LOOKBACK = 60
Z_ENTRY = 2.0
MAX_HOLD = 20
XAU_LOTS = 0.5
XAU_CS = 100.0
EUR_CS = 100000.0
XAU_PT = 0.01
EUR_PT = 0.00001
HOLDOUT = pd.Timestamp("2026-01-01")
PKG = (
    ROOT
    / "results/instrument_data_packages"
    / "4f44b452081041f39fc24f03248b8ca8-ee2a993fb5b1befd"
    / "instrument_data"
)


def _h1(name: str) -> pd.DataFrame:
    d = pd.read_csv(PKG / f"{name}_h1.csv")
    d["time"] = pd.to_datetime(d["time"])
    d["day"] = d["time"].dt.normalize()
    return d.sort_values("time")


def _daily_pack(h1: pd.DataFrame, prefix: str) -> pd.DataFrame:
    g = h1.groupby("day", sort=True)
    return pd.DataFrame(
        {
            f"{prefix}_c": g["close"].last(),
            f"{prefix}_o": g["open"].first(),
            f"{prefix}_spr": g["spread"].first(),
        }
    )


def _ols_beta(y: np.ndarray, x: np.ndarray) -> float:
    if len(y) < LOOKBACK or np.std(x) < 1e-12:
        return 0.0
    X = np.column_stack([np.ones(len(y)), x])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    return float(b[1])


def main() -> int:
    costs = json.loads((ROOT / "results" / "xau_research_costs.json").read_text())
    slip = float(costs.get("slippage_points") or 0.0)
    comm = float(costs.get("commission_per_lot") or 0.0)

    xau = _h1("xauusd")
    eur = _h1("eurusd")
    dx = _daily_pack(xau, "xau")
    de = _daily_pack(eur, "eur")
    d = dx.join(de, how="inner").dropna().sort_index()
    d = d.loc[d.index < HOLDOUT]
    lx = np.log(d["xau_c"].to_numpy(float))
    le = np.log(d["eur_c"].to_numpy(float))
    n = len(d)

    pnls: list[float] = []
    eq = [float(START_BALANCE)]
    pos = 0
    hold = 0
    beta_pos = 0.0
    xau_entry = eur_entry = 0.0
    eur_lots = 0.0
    trade_cost = 0.0

    def xau_cost(spr: float, lots: float) -> float:
        return (spr + 2.0 * slip) * XAU_PT * XAU_CS * lots + 2.0 * comm * lots

    def eur_cost(spr: float, lots: float) -> float:
        return (spr + 2.0 * slip) * EUR_PT * EUR_CS * lots

    for i in range(LOOKBACK, n - 1):
        y = lx[i - LOOKBACK : i]
        x = le[i - LOOKBACK : i]
        beta = _ols_beta(y, x)
        s_win = y - beta * x
        sd = float(np.std(s_win, ddof=1))
        if sd < 1e-12:
            continue
        s_t = lx[i] - beta * le[i]
        z = (s_t - float(np.mean(s_win))) / sd

        # next-day fill index i+1
        j = i + 1
        xo = float(d["xau_o"].iloc[j])
        eo = float(d["eur_o"].iloc[j])
        xs = float(d["xau_spr"].iloc[j])
        es = float(d["eur_spr"].iloc[j])

        if pos != 0:
            hold += 1
            exit_now = (pos > 0 and z >= 0.0) or (pos < 0 and z <= 0.0) or hold >= MAX_HOLD
            if exit_now:
                xau_pnl = pos * (xo - xau_entry) * XAU_CS * XAU_LOTS
                eur_pnl = -pos * (eo - eur_entry) * EUR_CS * eur_lots
                pnl = xau_pnl + eur_pnl - trade_cost
                pnls.append(pnl)
                eq.append(eq[-1] + pnl)
                pos = 0
                hold = 0

        if pos == 0 and abs(z) > Z_ENTRY:
            side = -1 if z > 0 else 1
            xau_notional = XAU_LOTS * XAU_CS * xo
            eur_lots = abs(beta) * xau_notional / (EUR_CS * eo) if eo > 0 else 0.0
            if eur_lots <= 0:
                continue
            pos = side
            beta_pos = beta
            xau_entry = xo
            eur_entry = eo
            hold = 0
            trade_cost = xau_cost(xs, XAU_LOTS) + eur_cost(es, eur_lots)
            _ = beta_pos

    if pos != 0:
        xo = float(d["xau_c"].iloc[-1])
        eo = float(d["eur_c"].iloc[-1])
        xau_pnl = pos * (xo - xau_entry) * XAU_CS * XAU_LOTS
        eur_pnl = -pos * (eo - eur_entry) * EUR_CS * eur_lots
        pnl = xau_pnl + eur_pnl - trade_cost
        pnls.append(pnl)
        eq.append(eq[-1] + pnl)

    m = metrics_from_pnls(pnls, np.asarray(eq, dtype=float))
    ok = (
        m.n_trades >= 40
        and m.profit_factor >= 1.2
        and m.net_profit > 0
        and m.max_drawdown_pct <= 15.0
    )
    verdict = "SOFT_PASS" if ok else "SCREEN_FAIL"
    out = {
        "family_id": FAMILY,
        "verdict": verdict,
        "promote": False,
        "live_go": False,
        "develop": {
            "n": m.n_trades,
            "wr": m.win_rate,
            "pf": m.profit_factor,
            "np": m.net_profit,
            "dd": m.max_drawdown_pct,
            "wins": m.wins,
            "losses": m.losses,
            "days": int(n),
        },
        "holdout": None,
        "notes": "XAU-EUR log-spread OU fade both legs. Always-long gold not a kill. Holdout sealed.",
    }
    dest = ROOT / "results" / f"{FAMILY}_screen.json"
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print(
        f"DEVELOP {verdict} n={m.n_trades} WR={m.win_rate:.1f}% PF={m.profit_factor:.3f} "
        f"NP={m.net_profit:.2f} DD={m.max_drawdown_pct:.2f}%"
    )
    print("wrote", dest)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
