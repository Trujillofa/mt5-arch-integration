#!/usr/bin/env python3
"""Zero-knob GVZCLS implied-vol sizer on the always-long XAU host.

Charter: results/xau_charters/2026-09-19_xau_gvz_voltarget_always_long_v1.json
XAU: results/xau_fomc_h4/xauusd_h1_2018_2025.csv
GVZ: results/xau_gvz/GVZCLS.csv (FRED)

SAFETY: offline. No --live. Holdout sealed. Missing GVZ → flat.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import CONTRACT_SIZE, START_BALANCE, metrics_from_pnls  # noqa: E402

FAMILY = "xau_gvz_voltarget_always_long_v1"
CHARTER = ROOT / "results/xau_charters/2026-09-19_xau_gvz_voltarget_always_long_v1.json"
CSV = ROOT / "results/xau_fomc_h4/xauusd_h1_2018_2025.csv"
GVZ = ROOT / "results/xau_gvz/GVZCLS.csv"
HOLDOUT = pd.Timestamp("2026-01-01")
TARGET_PCT = 15.0
MAX_LOTS = 0.5
MIN_LOT = 0.01
POINT = 0.01


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
            "day": g["day"].first(),
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


def load_gvz(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path)
    d = pd.DataFrame(
        {
            "gvz_date": pd.to_datetime(raw["observation_date"]),
            "gvz": pd.to_numeric(raw["GVZCLS"], errors="coerce"),
        }
    )
    d = d.loc[d["gvz_date"] < HOLDOUT].dropna(subset=["gvz"])
    d = d.loc[d["gvz"] > 0].sort_values("gvz_date").reset_index(drop=True)
    return d


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
    gvz = load_gvz(GVZ)
    joined = pd.merge_asof(
        daily.sort_values("day"),
        gvz.rename(columns={"gvz_date": "day"}),
        on="day",
        direction="backward",
        allow_exact_matches=False,
    )
    o = joined["open"].to_numpy(float)
    c = joined["close"].to_numpy(float)
    spr = joined["spread"].to_numpy(float)
    g = joined["gvz"].to_numpy(float)
    n = int(c.size)
    lots = np.zeros(n, dtype=float)
    n_flat = 0
    n_sized = 0
    first = None
    for k in range(n):
        if not np.isfinite(g[k]) or g[k] <= 0:
            n_flat += 1
            continue
        if first is None:
            first = k
        lots[k] = _floor_lots(MAX_LOTS * TARGET_PCT / float(g[k]))
        if lots[k] > 0:
            n_sized += 1
        else:
            n_flat += 1

    if first is None:
        raise SystemExit("no day with a prior GVZ observation")

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
        "gvz_start": str(gvz["gvz_date"].iloc[0].date()),
        "gvz_end": str(gvz["gvz_date"].iloc[-1].date()),
        "daily_bars": n,
        "first_sized_day": str(joined["time"].iloc[first]),
        "n_days": fam.n_trades,
        "n_sized_days": n_sized,
        "n_flat_missing_or_tiny": n_flat,
        "mean_gvz": float(np.nanmean(g[sl])),
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
        "notes": "GVZ as-of join date < D. Units = percent. Article 1.20 cuts unused. Swap unmodeled both arms.",
    }
    dest = ROOT / "results" / f"{FAMILY}_screen.json"
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print(
        f"DEVELOP {verdict} days={fam.n_trades} sized={n_sized} flat={n_flat} "
        f"NP={fam.net_profit:.2f} DD={fam.max_drawdown_pct:.2f}% Cal={cal_f:.2f} "
        f"| ctl NP={ctl.net_profit:.2f} DD={ctl.max_drawdown_pct:.2f}% Cal={cal_c:.2f} "
        f"mean_lots={float(np.mean(lots[sl])):.3f} mean_gvz={float(np.nanmean(g[sl])):.2f}"
    )
    print("wrote", dest)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
