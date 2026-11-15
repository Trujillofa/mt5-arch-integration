#!/usr/bin/env python3
"""Zero-knob EUR–GBP log-spread OU fade (both FX legs). Off-gold.

Charter: results/xau_charters/2026-09-19_eur_gbp_logspread_ou_fade_v1.json
Phase 0 EUR∩GBP H1. Expanding β min 252, |z|>2, exit 0 or 5d.

SAFETY: offline. No --live. Holdout sealed (time < 2026-01-01).
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

FAMILY = "eur_gbp_logspread_ou_fade_v1"
CHARTER = ROOT / "results/xau_charters/2026-09-19_eur_gbp_logspread_ou_fade_v1.json"
PKG = (
    ROOT
    / "results/instrument_data_packages"
    / "4f44b452081041f39fc24f03248b8ca8-ee2a993fb5b1befd"
    / "instrument_data"
)
HOLDOUT = pd.Timestamp("2026-01-01")
MIN_OBS = 252
Z_ENTRY = 2.0
MAX_HOLD = 5
EUR_LOTS = 0.10
CS = 100000.0
PT = 0.00001


def _daily(name: str, prefix: str) -> pd.DataFrame:
    d = pd.read_csv(PKG / f"{name}_h1.csv", parse_dates=["time"])
    d = d.loc[d["time"] < HOLDOUT].sort_values("time")
    d["day"] = d["time"].dt.normalize()
    g = d.groupby("day", sort=True)
    return pd.DataFrame(
        {
            f"{prefix}_c": g["close"].last(),
            f"{prefix}_o": g["open"].first(),
            f"{prefix}_spr": g["spread"].last(),
        }
    )


def _ols(y: np.ndarray, x: np.ndarray) -> tuple[float, float]:
    X = np.column_stack([np.ones(len(y)), x])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    return float(b[0]), float(b[1])


def _rt(spr: float, lots: float) -> float:
    return float(spr) * PT * CS * lots


def main() -> int:
    charter = json.loads(CHARTER.read_text())
    if charter.get("family_id") != FAMILY:
        raise SystemExit("charter family_id mismatch")

    de = _daily("eurusd", "eur")
    dg = _daily("gbpusd", "gbp")
    d = de.join(dg, how="inner").dropna().sort_index()
    le = np.log(d["eur_c"].to_numpy(float))
    lg = np.log(d["gbp_c"].to_numpy(float))
    n = len(d)

    pnls: list[float] = []
    eq = [float(START_BALANCE)]
    pos = 0
    hold = 0
    eur_entry = gbp_entry = 0.0
    gbp_lots = 0.0
    trade_cost = 0.0

    for i in range(MIN_OBS, n - 1):
        y = le[:i]
        x = lg[:i]
        if np.std(x) < 1e-12:
            continue
        a, beta = _ols(y, x)
        resid = y - (a + beta * x)
        sd = float(np.std(resid, ddof=1))
        if sd < 1e-12:
            continue
        z = (le[i] - (a + beta * lg[i])) / sd
        j = i + 1
        eo = float(d["eur_o"].iloc[j])
        go = float(d["gbp_o"].iloc[j])
        es = float(d["eur_spr"].iloc[j])
        gs = float(d["gbp_spr"].iloc[j])

        if pos != 0:
            hold += 1
            exit_now = (pos > 0 and z >= 0.0) or (pos < 0 and z <= 0.0) or hold >= MAX_HOLD
            if exit_now:
                eur_pnl = pos * (eo - eur_entry) * CS * EUR_LOTS
                gbp_pnl = -pos * (go - gbp_entry) * CS * gbp_lots
                pnl = eur_pnl + gbp_pnl - trade_cost
                pnls.append(pnl)
                eq.append(eq[-1] + pnl)
                pos = 0
                hold = 0

        if pos == 0 and abs(z) > Z_ENTRY:
            side = -1 if z > 0 else 1
            eur_notional = EUR_LOTS * CS * eo
            gbp_lots = abs(beta) * eur_notional / (CS * go) if go > 0 else 0.0
            if gbp_lots <= 0:
                continue
            pos = side
            eur_entry = eo
            gbp_entry = go
            hold = 0
            trade_cost = _rt(es, EUR_LOTS) + _rt(gs, gbp_lots)

    if pos != 0:
        eo = float(d["eur_c"].iloc[-1])
        go = float(d["gbp_c"].iloc[-1])
        eur_pnl = pos * (eo - eur_entry) * CS * EUR_LOTS
        gbp_pnl = -pos * (go - gbp_entry) * CS * gbp_lots
        pnl = eur_pnl + gbp_pnl - trade_cost
        pnls.append(pnl)
        eq.append(eq[-1] + pnl)

    m = metrics_from_pnls(pnls, np.asarray(eq, dtype=float))
    al = (float(d["eur_c"].iloc[-1]) - float(d["eur_o"].iloc[MIN_OBS])) * CS * EUR_LOTS
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
        "first_day": str(d.index.min()),
        "last_day": str(d.index.max()),
        "develop": {
            "n": m.n_trades,
            "wr": m.win_rate,
            "pf": m.profit_factor,
            "np": m.net_profit,
            "dd": m.max_drawdown_pct,
            "wins": m.wins,
            "losses": m.losses,
        },
        "always_long_eur_report_only": {"np": al, "lots": EUR_LOTS},
        "holdout": None,
        "notes": "Off-gold. Expanding β min 252. 2026 unused.",
    }
    dest = ROOT / "results" / f"{FAMILY}_screen.json"
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print(
        f"DEVELOP {verdict} n={m.n_trades} WR={m.win_rate:.1f}% PF={m.profit_factor:.3f} "
        f"NP={m.net_profit:.2f} DD={m.max_drawdown_pct:.2f}% | AL-EUR report NP={al:.2f}"
    )
    print("wrote", dest)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
