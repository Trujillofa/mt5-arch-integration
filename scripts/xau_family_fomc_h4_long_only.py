#!/usr/bin/env python3
"""Zero-knob FOMC H4 long-only.

Charter: results/xau_charters/2026-09-18_xau_fomc_h4_long_only_v1.json
Dump: results/xau_fomc_h4/xauusd_h1_2018_2025.csv (Vantage MCP; timestamps = server UTC+3).

14:00 America/New_York → UTC → +3h server. Signal = close of H4 containing
that instant; fill next H4 open; hold 8 H4 or SL 1.5 ATR. Long only.

SAFETY: offline. No --live. Holdout sealed (dump ends 2025-12-31).
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

FAMILY = "xau_fomc_h4_long_only_v1"
HOLD_BARS = 8
SL_ATR = 1.5
ATR_PERIOD = 14
RISK_PCT = 0.01
MAX_LOTS = 0.5
MIN_LOT = 0.01
POINT = 0.01
SERVER_AHEAD_UTC_H = 3
CSV = ROOT / "results/xau_fomc_h4/xauusd_h1_2018_2025.csv"
EVENTS = ROOT / "results/xau_fomc_scheduled_v1.csv"
HOLDOUT = pd.Timestamp("2026-01-01")


def resample_h4(h1: pd.DataFrame) -> pd.DataFrame:
    x = h1.copy()
    x["bucket"] = x["time"].dt.floor("4h")
    g = x.groupby("bucket", sort=True)
    out = pd.DataFrame(
        {
            "time": g["time"].first(),
            "open": g["open"].first(),
            "high": g["high"].max(),
            "low": g["low"].min(),
            "close": g["close"].last(),
            "spread": g["spread"].last(),
        }
    ).reset_index(drop=True)
    h, lo, c = out["high"].astype(float), out["low"].astype(float), out["close"].astype(float)
    prev = c.shift(1)
    tr = pd.concat([(h - lo), (h - prev).abs(), (lo - prev).abs()], axis=1).max(axis=1)
    out["atr"] = tr.ewm(alpha=1.0 / ATR_PERIOD, adjust=False).mean()
    return out


def _lots(balance: float, stop_dist: float) -> float:
    if stop_dist <= 0:
        return 0.0
    raw = (balance * RISK_PCT) / (stop_dist * CONTRACT_SIZE)
    lots = float(np.floor(raw * 100 + 1e-12) / 100.0)
    return min(max(lots, 0.0), MAX_LOTS)


def _cost(spread_pts: float, lots: float, slip: float, comm: float) -> float:
    return (spread_pts + 2.0 * slip) * POINT * CONTRACT_SIZE * lots + 2.0 * comm * lots


def main() -> int:
    costs = json.loads((ROOT / "results" / "xau_research_costs.json").read_text())
    slip = float(costs.get("slippage_points") or 0.0)
    comm = float(costs.get("commission_per_lot") or 0.0)

    h1 = pd.read_csv(CSV, parse_dates=["time"])
    med = float(h1["spread"].median())
    h1["spread"] = h1["spread"].fillna(med)
    h1 = h1.loc[h1["time"] < HOLDOUT].sort_values("time").reset_index(drop=True)
    h4 = resample_h4(h1)
    n = len(h4)
    t0 = h4["time"].to_numpy()
    t1 = t0 + np.timedelta64(4, "h")
    o = h4["open"].to_numpy(float)
    lo = h4["low"].to_numpy(float)
    c = h4["close"].to_numpy(float)
    atr = h4["atr"].to_numpy(float)
    spr = h4["spread"].to_numpy(float)

    ev = pd.read_csv(EVENTS)
    ev["statement_date"] = pd.to_datetime(ev["statement_date"])
    signal_idx: list[int] = []
    skipped = 0
    for _, row in ev.iterrows():
        et = pd.Timestamp(f"{row['statement_date'].date()} 14:00:00", tz="America/New_York")
        server = (et.tz_convert("UTC") + pd.Timedelta(hours=SERVER_AHEAD_UTC_H)).tz_localize(None)
        if server >= HOLDOUT:
            continue
        m = (t0 <= np.datetime64(server)) & (np.datetime64(server) < t1)
        hits = np.where(m)[0]
        if len(hits) == 0:
            skipped += 1
            continue
        si = int(hits[0])
        if si + 1 >= n or not np.isfinite(atr[si]) or atr[si] <= 0:
            skipped += 1
            continue
        signal_idx.append(si)

    pnls: list[float] = []
    eq = [float(START_BALANCE)]
    balance = float(START_BALANCE)
    used_fill: set[int] = set()

    for si in signal_idx:
        fi = si + 1
        if fi in used_fill or fi >= n:
            continue
        sl_dist = SL_ATR * float(atr[si])
        sl = float(o[fi]) - sl_dist
        if o[fi] <= sl:
            continue
        lots = _lots(balance, sl_dist)
        if lots < MIN_LOT:
            continue
        used_fill.add(fi)
        entry = float(o[fi])
        cost = _cost(float(spr[fi]), lots, slip, comm)
        exit_px = float(c[min(fi + HOLD_BARS - 1, n - 1)])
        reason = "time"
        last = min(fi + HOLD_BARS - 1, n - 1)
        for j in range(fi, last + 1):
            if lo[j] <= sl:
                exit_px = sl
                reason = "sl"
                break
            exit_px = float(c[j])
        pnl = (exit_px - entry) * CONTRACT_SIZE * lots - cost
        pnls.append(pnl)
        balance += pnl
        eq.append(balance)
        _ = reason

    fam = metrics_from_pnls(pnls, np.asarray(eq, dtype=float))
    # always-long 0.5 lot first open to last close
    al_entry = float(o[ATR_PERIOD + 5])
    al_exit = float(c[-1])
    al_cost = _cost(float(spr[ATR_PERIOD + 5]), MAX_LOTS, slip, comm)
    al_pnl = (al_exit - al_entry) * CONTRACT_SIZE * MAX_LOTS - al_cost
    al = metrics_from_pnls([al_pnl], np.array([START_BALANCE, START_BALANCE + al_pnl], dtype=float))

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
        "server_ahead_utc_hours": SERVER_AHEAD_UTC_H,
        "events_matched": len(signal_idx),
        "events_skipped_no_bar": skipped,
        "h1_start": str(h1["time"].iloc[0]),
        "h1_end": str(h1["time"].iloc[-1]),
        "h1_bars": int(len(h1)),
        "develop": {
            "n": fam.n_trades,
            "wr": fam.win_rate,
            "pf": fam.profit_factor,
            "np": fam.net_profit,
            "dd": fam.max_drawdown_pct,
            "wins": fam.wins,
            "losses": fam.losses,
        },
        "always_long": {"np": al.net_profit, "n": al.n_trades},
        "beat_always_long": fam.net_profit > al.net_profit,
        "holdout": None,
        "notes": "Dump timestamps treated as Vantage UTC+3. 2018-01/03 FOMC skipped (no H1).",
    }
    dest = ROOT / "results" / f"{FAMILY}_screen.json"
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print(
        f"DEVELOP {verdict} n={fam.n_trades} WR={fam.win_rate:.1f}% PF={fam.profit_factor:.3f} "
        f"NP={fam.net_profit:.2f} DD={fam.max_drawdown_pct:.2f}% | always-long NP={al.net_profit:.2f} "
        f"beat={fam.net_profit > al.net_profit} matched={len(signal_idx)} skip={skipped}"
    )
    print("wrote", dest)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
