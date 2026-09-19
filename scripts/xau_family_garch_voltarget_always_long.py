#!/usr/bin/env python3
"""Zero-knob GARCH(1,1) vol-target on the always-long XAU host.

Charter: results/xau_charters/2026-09-19_xau_garch_voltarget_always_long_v1.json
Dump: results/xau_fomc_h4/xauusd_h1_2018_2025.csv

SAFETY: offline. No --live. Holdout sealed. Fail-closed (flat) if MLE fails.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import CONTRACT_SIZE, START_BALANCE, metrics_from_pnls  # noqa: E402

FAMILY = "xau_garch_voltarget_always_long_v1"
CHARTER = ROOT / "results/xau_charters/2026-09-19_xau_garch_voltarget_always_long_v1.json"
CSV = ROOT / "results/xau_fomc_h4/xauusd_h1_2018_2025.csv"
HOLDOUT = pd.Timestamp("2026-01-01")
MIN_OBS = 252
TARGET_ANN = 0.15
MAX_LOTS = 0.5
MIN_LOT = 0.01
POINT = 0.01
ANN = np.sqrt(252.0)


def _sigmoid(x: float) -> float:
    return float(1.0 / (1.0 + np.exp(-np.clip(x, -60.0, 60.0))))


def _unpack(z: np.ndarray) -> tuple[float, float, float]:
    omega = float(np.exp(np.clip(z[0], -30.0, 5.0)))
    alpha = 0.998 * _sigmoid(float(z[1]))
    beta = (0.998 - alpha) * _sigmoid(float(z[2]))
    return omega, alpha, beta


def _filter_var(r: np.ndarray, omega: float, alpha: float, beta: float) -> np.ndarray:
    n = int(r.size)
    sig2 = np.empty(n, dtype=float)
    sig2[0] = max(float(np.mean(r * r)), 1e-12)
    for t in range(1, n):
        v = omega + alpha * r[t - 1] * r[t - 1] + beta * sig2[t - 1]
        sig2[t] = v if v > 1e-12 else 1e-12
    return sig2


def _nll(z: np.ndarray, r: np.ndarray) -> float:
    omega, alpha, beta = _unpack(z)
    sig2 = _filter_var(r, omega, alpha, beta)
    return float(0.5 * np.sum(np.log(sig2) + (r * r) / sig2))


def _fit_garch(
    r: np.ndarray, z0: np.ndarray
) -> tuple[np.ndarray | None, tuple[float, float, float] | None]:
    if r.size < MIN_OBS or not np.isfinite(r).all():
        return None, None

    def obj(z: np.ndarray) -> float:
        v = _nll(z, r)
        return v if np.isfinite(v) else 1e12

    out = minimize(obj, z0, method="L-BFGS-B", options={"maxiter": 80})
    if not out.success and out.nit < 5:
        return None, None
    z = np.asarray(out.x, dtype=float)
    if not np.isfinite(z).all():
        return None, None
    params = _unpack(z)
    if not all(np.isfinite(p) for p in params):
        return None, None
    return z, params


def _one_way(spread_pts: float, abs_dlots: float, slip: float, comm: float) -> float:
    if abs_dlots <= 0:
        return 0.0
    return (spread_pts + 2.0 * slip) * POINT * CONTRACT_SIZE * abs_dlots * 0.5 + comm * abs_dlots


def _floor_lots(raw: float) -> float:
    if not np.isfinite(raw) or raw <= 0:
        return 0.0
    lots = float(np.floor(min(raw, MAX_LOTS) * 100.0 + 1e-12) / 100.0)
    if lots < MIN_LOT:
        return 0.0
    return lots


def resample_daily(h1: pd.DataFrame) -> pd.DataFrame:
    x = h1.copy()
    x["day"] = x["time"].dt.normalize()
    g = x.groupby("day", sort=True)
    return pd.DataFrame(
        {
            "time": g["time"].first(),
            "open": g["open"].first(),
            "high": g["high"].max(),
            "low": g["low"].min(),
            "close": g["close"].last(),
            "spread": g["spread"].last(),
        }
    ).reset_index(drop=True)


def _path(
    o: np.ndarray,
    c: np.ndarray,
    spr: np.ndarray,
    lots: np.ndarray,
    slip: float,
    comm: float,
) -> tuple[list[float], np.ndarray]:
    n = int(o.size)
    pnls: list[float] = []
    eq = [float(START_BALANCE)]
    prev = 0.0
    for i in range(n):
        gap = (float(o[i]) - float(c[i - 1])) * CONTRACT_SIZE * prev if i else 0.0
        cost = _one_way(float(spr[i]), abs(float(lots[i]) - prev), slip, comm)
        body = (float(c[i]) - float(o[i])) * CONTRACT_SIZE * float(lots[i])
        pnl = gap + body - cost
        pnls.append(pnl)
        eq.append(eq[-1] + pnl)
        prev = float(lots[i])
    if prev > 0:
        flat = _one_way(float(spr[-1]), prev, slip, comm)
        pnls[-1] -= flat
        eq[-1] -= flat
    return pnls, np.asarray(eq, dtype=float)


def main() -> int:
    charter = json.loads(CHARTER.read_text())
    if charter.get("family_id") != FAMILY:
        raise SystemExit("charter family_id mismatch")
    costs = json.loads((ROOT / "results" / "xau_research_costs.json").read_text())
    slip = float(costs.get("slippage_points") or 0.0)
    comm = float(costs.get("commission_per_lot") or 0.0)

    if CSV.resolve().name == "xauusd_data.csv":
        raise SystemExit("refusing xauusd_data.csv (2021-only bull)")

    h1 = pd.read_csv(CSV, parse_dates=["time"])
    h1 = h1.loc[h1["time"] < HOLDOUT].sort_values("time").reset_index(drop=True)
    med = float(h1["spread"].median())
    h1["spread"] = h1["spread"].fillna(med)
    daily = resample_daily(h1)
    o = daily["open"].to_numpy(float)
    c = daily["close"].to_numpy(float)
    spr = daily["spread"].to_numpy(float)
    n = int(c.size)
    r_all = np.empty(n, dtype=float)
    r_all[0] = np.nan
    r_all[1:] = np.log(c[1:] / c[:-1])

    lots = np.zeros(n, dtype=float)
    z = np.array([np.log(1e-6), -2.94, 2.2], dtype=float)  # ~α 0.05, β 0.90
    n_fail = 0
    n_sized = 0
    first = None
    for k in range(n):
        r = r_all[1:k]
        if r.size < MIN_OBS:
            continue
        if first is None:
            first = k
        fitted, params = _fit_garch(r, z)
        if fitted is None or params is None:
            n_fail += 1
            lots[k] = 0.0
            continue
        z = fitted
        omega, alpha, beta = params
        sig2 = _filter_var(r, omega, alpha, beta)
        sigma2_d = omega + alpha * r[-1] * r[-1] + beta * sig2[-1]
        if not np.isfinite(sigma2_d) or sigma2_d <= 0:
            n_fail += 1
            lots[k] = 0.0
            continue
        sigma_ann = float(np.sqrt(sigma2_d) * ANN)
        lots[k] = _floor_lots(MAX_LOTS * TARGET_ANN / sigma_ann)
        if lots[k] > 0:
            n_sized += 1

    if first is None:
        raise SystemExit("warmup never cleared 252 daily returns")

    sl = slice(first, n)
    fam_pnls, fam_eq = _path(o[sl], c[sl], spr[sl], lots[sl], slip, comm)
    ctl_lots = np.full(n - first, MAX_LOTS, dtype=float)
    ctl_pnls, ctl_eq = _path(o[sl], c[sl], spr[sl], ctl_lots, slip, comm)
    fam = metrics_from_pnls(fam_pnls, fam_eq)
    ctl = metrics_from_pnls(ctl_pnls, ctl_eq)
    cal_f = fam.net_profit / max(fam.max_drawdown_pct, 1e-9)
    cal_c = ctl.net_profit / max(ctl.max_drawdown_pct, 1e-9)
    ok = fam.net_profit > 0.0 and fam.max_drawdown_pct < ctl.max_drawdown_pct and cal_f > cal_c
    verdict = "SOFT_PASS" if ok else "SCREEN_FAIL"
    out = {
        "family_id": FAMILY,
        "verdict": verdict,
        "promote": False,
        "live_go": False,
        "h1_start": str(h1["time"].iloc[0]),
        "h1_end": str(h1["time"].iloc[-1]),
        "daily_bars": n,
        "first_sized_day": str(daily["time"].iloc[first]),
        "n_days": fam.n_trades,
        "n_sized_days": n_sized,
        "n_mle_fail": n_fail,
        "develop": {
            "np": fam.net_profit,
            "dd": fam.max_drawdown_pct,
            "calmar": cal_f,
            "wr": fam.win_rate,
            "pf": fam.profit_factor,
            "mean_lots": float(np.mean(lots[sl])),
        },
        "constant_lot": {
            "np": ctl.net_profit,
            "dd": ctl.max_drawdown_pct,
            "calmar": cal_c,
            "lots": MAX_LOTS,
        },
        "gates": {
            "net_profit_gt_0": fam.net_profit > 0.0,
            "dd_lt_control": fam.max_drawdown_pct < ctl.max_drawdown_pct,
            "calmar_gt_control": cal_f > cal_c,
        },
        "holdout": None,
        "notes": "Expanding GARCH(1,1) MLE; fail-closed flat on MLE failure. Swap unmodeled both arms.",
    }
    dest = ROOT / "results" / f"{FAMILY}_screen.json"
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print(
        f"DEVELOP {verdict} days={fam.n_trades} sized={n_sized} fail={n_fail} "
        f"NP={fam.net_profit:.2f} DD={fam.max_drawdown_pct:.2f}% Cal={cal_f:.2f} "
        f"| ctl NP={ctl.net_profit:.2f} DD={ctl.max_drawdown_pct:.2f}% Cal={cal_c:.2f} "
        f"mean_lots={float(np.mean(lots[sl])):.3f}"
    )
    print("wrote", dest)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
