#!/usr/bin/env python3
"""Zero-knob XAU–XAG log-spread OU fade (both legs).

Charter: results/xau_charters/2026-09-19_xau_xag_logspread_ou_fade_v1.json
β: expanding OLS log XAU ~ 1+log XAG on days strictly before signal close.
z vs that window. |z|>2 fade next open; exit z-cross 0 or 5 days.

SAFETY: offline. No --live. Holdout sealed. Refuse gold-only.
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

FAMILY = "xau_xag_logspread_ou_fade_v1"
CHARTER = ROOT / "results/xau_charters/2026-09-19_xau_xag_logspread_ou_fade_v1.json"
XAU_CSV = ROOT / "results/xau_fomc_h4/xauusd_h1_2018_2025.csv"
XAG_CSV = ROOT / "results/xau_xag/xagusd_h1_2018_2025.csv"
HOLDOUT = pd.Timestamp("2026-01-01")
MIN_OBS = 252
Z_ENTRY = 2.0
MAX_HOLD = 5
XAU_LOTS = 0.5
XAU_CS = 100.0
XAG_CS = 5000.0
XAU_PT = 0.01
XAG_PT = 0.001


def _h1(path: Path, prefix: str) -> pd.DataFrame:
    d = pd.read_csv(path, parse_dates=["time"])
    d = d.loc[d["time"] < HOLDOUT].sort_values("time")
    med = float(d["spread"].median())
    d["spread"] = d["spread"].fillna(med)
    d["day"] = d["time"].dt.normalize()
    g = d.groupby("day", sort=True)
    return pd.DataFrame(
        {
            f"{prefix}_c": g["close"].last(),
            f"{prefix}_o": g["open"].first(),
            f"{prefix}_spr": g["spread"].last(),
        }
    )


def _ols_beta(y: np.ndarray, x: np.ndarray) -> tuple[float, float]:
    X = np.column_stack([np.ones(len(y)), x])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    return float(b[0]), float(b[1])


def main() -> int:
    charter = json.loads(CHARTER.read_text())
    if charter.get("family_id") != FAMILY:
        raise SystemExit("charter family_id mismatch")
    if not XAG_CSV.is_file():
        raise SystemExit("BLOCKED_ON_DATA: missing XAG H1")
    costs = json.loads((ROOT / "results" / "xau_research_costs.json").read_text())
    slip = float(costs.get("slippage_points") or 0.0)
    comm = float(costs.get("commission_per_lot") or 0.0)

    dx = _h1(XAU_CSV, "xau")
    dg = _h1(XAG_CSV, "xag")
    d = dx.join(dg, how="inner").dropna().sort_index()
    d = d.loc[d.index < HOLDOUT]
    lx = np.log(d["xau_c"].to_numpy(float))
    lg = np.log(d["xag_c"].to_numpy(float))
    n = len(d)

    def xau_cost(spr: float, lots: float) -> float:
        return (spr + 2.0 * slip) * XAU_PT * XAU_CS * lots + 2.0 * comm * lots

    def xag_cost(spr: float, lots: float) -> float:
        return (spr + 2.0 * slip) * XAG_PT * XAG_CS * lots + 2.0 * comm * lots

    pnls: list[float] = []
    eq = [float(START_BALANCE)]
    pos = 0
    hold = 0
    xau_entry = xag_entry = 0.0
    xag_lots = 0.0
    trade_cost = 0.0

    for i in range(MIN_OBS, n - 1):
        y = lx[:i]
        x = lg[:i]
        if np.std(x) < 1e-12:
            continue
        a, beta = _ols_beta(y, x)
        resid = y - (a + beta * x)
        sd = float(np.std(resid, ddof=1))
        if sd < 1e-12:
            continue
        z = (lx[i] - (a + beta * lg[i])) / sd
        j = i + 1
        xo = float(d["xau_o"].iloc[j])
        go = float(d["xag_o"].iloc[j])
        xs = float(d["xau_spr"].iloc[j])
        gs = float(d["xag_spr"].iloc[j])

        if pos != 0:
            hold += 1
            exit_now = (pos > 0 and z >= 0.0) or (pos < 0 and z <= 0.0) or hold >= MAX_HOLD
            if exit_now:
                xau_pnl = pos * (xo - xau_entry) * XAU_CS * XAU_LOTS
                xag_pnl = -pos * (go - xag_entry) * XAG_CS * xag_lots
                pnl = xau_pnl + xag_pnl - trade_cost
                pnls.append(pnl)
                eq.append(eq[-1] + pnl)
                pos = 0
                hold = 0

        if pos == 0 and abs(z) > Z_ENTRY:
            side = -1 if z > 0 else 1
            xau_notional = XAU_LOTS * XAU_CS * xo
            xag_lots = abs(beta) * xau_notional / (XAG_CS * go) if go > 0 else 0.0
            if xag_lots <= 0:
                continue
            pos = side
            xau_entry = xo
            xag_entry = go
            hold = 0
            trade_cost = xau_cost(xs, XAU_LOTS) + xag_cost(gs, xag_lots)

    if pos != 0:
        xo = float(d["xau_c"].iloc[-1])
        go = float(d["xag_c"].iloc[-1])
        xau_pnl = pos * (xo - xau_entry) * XAU_CS * XAU_LOTS
        xag_pnl = -pos * (go - xag_entry) * XAG_CS * xag_lots
        pnl = xau_pnl + xag_pnl - trade_cost
        pnls.append(pnl)
        eq.append(eq[-1] + pnl)

    m = metrics_from_pnls(pnls, np.asarray(eq, dtype=float))
    # report-only always-long 0.5 XAU on the joined window
    al_entry = float(d["xau_o"].iloc[MIN_OBS])
    al_exit = float(d["xau_c"].iloc[-1])
    al_np = (al_exit - al_entry) * XAU_CS * XAU_LOTS
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
        "join_days": int(n),
        "xag_start": str(d.index.min()),
        "xag_end": str(d.index.max()),
        "develop": {
            "n": m.n_trades,
            "wr": m.win_rate,
            "pf": m.profit_factor,
            "np": m.net_profit,
            "dd": m.max_drawdown_pct,
            "wins": m.wins,
            "losses": m.losses,
        },
        "always_long_xau_report_only": {"np": al_np, "lots": XAU_LOTS},
        "holdout": None,
        "notes": "Expanding β min 252, |z|>2, hold 5d. Always-long XAU not a kill gate.",
    }
    dest = ROOT / "results" / f"{FAMILY}_screen.json"
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print(
        f"DEVELOP {verdict} n={m.n_trades} WR={m.win_rate:.1f}% PF={m.profit_factor:.3f} "
        f"NP={m.net_profit:.2f} DD={m.max_drawdown_pct:.2f}% | AL-XAU report NP={al_np:.2f}"
    )
    print("wrote", dest)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
