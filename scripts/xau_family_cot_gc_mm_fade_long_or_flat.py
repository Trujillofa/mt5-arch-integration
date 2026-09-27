#!/usr/bin/env python3
"""Zero-knob COMEX GC managed-money z fade → XAU long-or-flat.

Charter: results/xau_charters/2026-09-19_xau_cot_gc_mm_fade_long_or_flat_v1.json
XAU: results/xau_fomc_h4/xauusd_h1_2018_2025.csv
COT: results/xau_cot/cftc_disagg_fut_gold_comex_2016_2025.csv

SAFETY: offline. No --live. Holdout sealed. Never trade as-of Tuesday.
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

FAMILY = "xau_cot_gc_mm_fade_long_or_flat_v1"
CHARTER = ROOT / "results/xau_charters/2026-09-19_xau_cot_gc_mm_fade_long_or_flat_v1.json"
CSV = ROOT / "results/xau_fomc_h4/xauusd_h1_2018_2025.csv"
COT = ROOT / "results/xau_cot/cftc_disagg_fut_gold_comex_2016_2025.csv"
HOLDOUT = pd.Timestamp("2026-01-01")
DEV_START = pd.Timestamp("2018-04-02")
LOTS = 0.5
POINT = 0.01
MIN_WEEKS = 52
Z_ENTER = -2.0
Z_FLAT = -0.5


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


def _one_way(spread_pts: float, abs_dlots: float, slip: float, comm: float) -> float:
    if abs_dlots <= 0:
        return 0.0
    return (spread_pts + 2.0 * slip) * POINT * CONTRACT_SIZE * abs_dlots * 0.5 + comm * abs_dlots


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


def first_friday_after(as_of: pd.Timestamp) -> pd.Timestamp:
    """First Friday strictly after as-of (never same-day Friday)."""
    d = (4 - int(as_of.dayofweek)) % 7
    if d == 0:
        d = 7
    return as_of + pd.Timedelta(days=d)


def load_cot(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, parse_dates=["as_of"])
    m = raw["market"].astype(str).str.upper()
    d = raw.loc[
        m.str.contains("GOLD") & m.str.contains("COMMODITY EXCHANGE") & ~m.str.contains("MICRO")
    ].copy()
    d = d.sort_values("as_of").drop_duplicates("as_of")
    oi = pd.to_numeric(d["open_interest_all"], errors="coerce")
    lng = pd.to_numeric(d["mm_long_all"], errors="coerce")
    sht = pd.to_numeric(d["mm_short_all"], errors="coerce")
    d["mm_net_pct_oi"] = (lng - sht) / oi * 100.0
    d = d.loc[oi > 0].dropna(subset=["mm_net_pct_oi", "as_of"])
    return d.reset_index(drop=True)


def expanding_z(net: np.ndarray) -> np.ndarray:
    """z_i vs mean/std of prints strictly before i. NaN if <52 or std=0."""
    z = np.full(net.size, np.nan)
    for i in range(net.size):
        if i < MIN_WEEKS:
            continue
        hist = net[:i]
        sd = float(hist.std(ddof=1))
        if sd <= 0.0 or not np.isfinite(sd):
            continue
        z[i] = (float(net[i]) - float(hist.mean())) / sd
    return z


def round_trips(
    o: np.ndarray, c: np.ndarray, spr: np.ndarray, lots: np.ndarray, slip: float, comm: float
) -> list[float]:
    """PnL per 0→long→0 cycle. Open trade flattened at last close."""
    pnls: list[float] = []
    n = int(o.size)
    i = 0
    while i < n:
        if lots[i] <= 0:
            i += 1
            continue
        entry = float(o[i])
        cost = _one_way(float(spr[i]), float(lots[i]), slip, comm)
        j = i
        while j + 1 < n and lots[j + 1] > 0:
            j += 1
        if j + 1 < n:
            exit_px = float(o[j + 1])
            cost += _one_way(float(spr[j + 1]), float(lots[j]), slip, comm)
        else:
            exit_px = float(c[j])
            cost += _one_way(float(spr[j]), float(lots[j]), slip, comm)
        pnls.append((exit_px - entry) * CONTRACT_SIZE * float(lots[i]) - cost)
        i = j + 1
    return pnls


def main() -> int:
    charter = json.loads(CHARTER.read_text())
    if charter.get("family_id") != FAMILY:
        raise SystemExit("charter family_id mismatch")
    if CSV.resolve().name == "xauusd_data.csv":
        raise SystemExit("refusing xauusd_data.csv (2021-only bull)")
    if not COT.is_file():
        raise SystemExit("BLOCKED_ON_DATA: missing COT csv")

    costs = json.loads((ROOT / "results" / "xau_research_costs.json").read_text())
    slip = float(costs.get("slippage_points") or 0.0)
    comm = float(costs.get("commission_per_lot") or 0.0)

    cot = load_cot(COT)
    net = cot["mm_net_pct_oi"].to_numpy(float)
    z = expanding_z(net)
    intended = 0.0
    fridays: list[pd.Timestamp] = []
    targets: list[float] = []
    zs: list[float] = []
    n_skip_warmup = 0
    n_skip_std = 0
    n_enter = 0
    n_flat_sig = 0
    n_hold = 0
    for i, row in cot.iterrows():
        zi = z[i]
        if not np.isfinite(zi):
            if i < MIN_WEEKS:
                n_skip_warmup += 1
            else:
                n_skip_std += 1
            continue
        prev = intended
        if zi < Z_ENTER:
            intended = LOTS
            n_enter += 1
        elif zi > Z_FLAT:
            intended = 0.0
            n_flat_sig += 1
        else:
            n_hold += 1
        fridays.append(first_friday_after(pd.Timestamp(row["as_of"])))
        targets.append(intended)
        zs.append(float(zi))
        _ = prev

    h1 = pd.read_csv(CSV, parse_dates=["time"])
    h1 = h1.loc[(h1["time"] >= DEV_START) & (h1["time"] < HOLDOUT)].sort_values("time")
    med = float(h1["spread"].median())
    h1["spread"] = h1["spread"].fillna(med)
    daily = resample_daily(h1)
    days = daily["day"].to_numpy()
    n = len(daily)
    lots = np.zeros(n, dtype=float)
    cur = 0.0
    k = 0
    n_sig = len(fridays)
    for i in range(n):
        while k < n_sig and days[i] > np.datetime64(fridays[k]):
            cur = targets[k]
            k += 1
        lots[i] = cur

    o = daily["open"].to_numpy(float)
    c = daily["close"].to_numpy(float)
    spr = daily["spread"].to_numpy(float)
    fam_daily, fam_eq = _path(o, c, spr, lots, slip, comm)
    ctl_lots = np.full(n, LOTS, dtype=float)
    ctl_daily, ctl_eq = _path(o, c, spr, ctl_lots, slip, comm)
    rt = round_trips(o, c, spr, lots, slip, comm)
    fam = metrics_from_pnls(rt, fam_eq)
    # NP/DD from daily path (honest equity); n/PF/WR from round trips
    fam_np = float(np.sum(fam_daily))
    ctl_np = float(np.sum(ctl_daily))
    peak = np.maximum.accumulate(fam_eq)
    dd = float(np.where(peak > 0, (peak - fam_eq) / peak, 0.0).max() * 100)
    ctl_peak = np.maximum.accumulate(ctl_eq)
    ctl_dd = float(np.where(ctl_peak > 0, (ctl_peak - ctl_eq) / ctl_peak, 0.0).max() * 100)

    ok = (
        fam.n_trades >= 40
        and fam.profit_factor >= 1.2
        and fam_np > 0.0
        and dd <= 15.0
        and fam_np > ctl_np
    )
    verdict = "SOFT_PASS" if ok else "SCREEN_FAIL"
    n_long_days = int((lots > 0).sum())
    out = {
        "family_id": FAMILY,
        "verdict": verdict,
        "promote": False,
        "live_go": False,
        "h1_start": str(h1["time"].iloc[0]),
        "h1_end": str(h1["time"].iloc[-1]),
        "cot_as_of_min": str(cot["as_of"].iloc[0].date()),
        "cot_as_of_max": str(cot["as_of"].iloc[-1].date()),
        "cot_rows": int(len(cot)),
        "n_signals_valid_z": n_sig,
        "n_skip_warmup": n_skip_warmup,
        "n_skip_std0": n_skip_std,
        "n_z_enter": n_enter,
        "n_z_flatten": n_flat_sig,
        "n_z_hold": n_hold,
        "n_long_days": n_long_days,
        "n_flat_days": n - n_long_days,
        "develop": {
            "n": fam.n_trades,
            "wr": fam.win_rate,
            "pf": fam.profit_factor,
            "np": fam_np,
            "dd": dd,
            "wins": fam.wins,
            "losses": fam.losses,
        },
        "always_long": {"np": ctl_np, "dd": ctl_dd, "n_days": n, "lots": LOTS},
        "gates": {
            "n_trades_min_40": fam.n_trades >= 40,
            "profit_factor_min_1_2": fam.profit_factor >= 1.2,
            "net_profit_gt_0": fam_np > 0.0,
            "dd_le_15": dd <= 15.0,
            "must_beat_always_long_net": fam_np > ctl_np,
        },
        "holdout": None,
        "notes": (
            "Disaggregated Futures-Only GOLD - COMMODITY EXCHANGE INC. "
            "Signal first Friday strictly after as-of; fill next daily open. "
            "Expanding z min 52w, ddof=1. Round-trip n/PF; daily-path NP/DD. "
            "Swap unmodeled both arms."
        ),
    }
    dest = ROOT / "results" / f"{FAMILY}_screen.json"
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print(
        f"DEVELOP {verdict} n={fam.n_trades} WR={fam.win_rate:.1f}% PF={fam.profit_factor:.3f} "
        f"NP={fam_np:.2f} DD={dd:.2f}% | always-long NP={ctl_np:.2f} DD={ctl_dd:.2f}% "
        f"beat={fam_np > ctl_np} long_days={n_long_days}/{n} "
        f"z_enter={n_enter} z_flat={n_flat_sig} hold={n_hold}"
    )
    print("wrote", dest)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
