#!/usr/bin/env python3
"""Zero-knob AUDJPY carry long-hold.

Charter: results/xau_charters/2026-09-19_audjpy_carry_long_hold_v1.json
Swap: screen-time SymbolInfo. If unreadable, fail-closed (swap<=0 → SCREEN_FAIL).

SAFETY: offline. No --live. Holdout sealed.
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

FAMILY = "audjpy_carry_long_hold_v1"
CHARTER = ROOT / "results/xau_charters/2026-09-19_audjpy_carry_long_hold_v1.json"
CSV = ROOT / "results/audjpy_carry/audjpy_h1_2018_2025.csv"
SWAP_SIDECAR = ROOT / "results/audjpy_carry/swap_long_usd_per_lot_night.json"
HOLDOUT = pd.Timestamp("2026-01-01")
LOTS = 0.10
POINT = 0.001
# Vantage symbols.json USDJPY tick_value (JPY profit → USD). Same profit ccy as AUDJPY.
TICK_VALUE = 0.64240104


def resample_daily(h1: pd.DataFrame) -> pd.DataFrame:
    x = h1.copy()
    x["day"] = x["time"].dt.normalize()
    g = x.groupby("day", sort=True)
    return pd.DataFrame(
        {
            "time": g["time"].first(),
            "day": g["day"].first(),
            "open": g["open"].first(),
            "close": g["close"].last(),
            "high": g["high"].max(),
            "low": g["low"].min(),
            "spread": g["spread"].last(),
        }
    ).reset_index(drop=True)


def _load_swap() -> float | None:
    if not SWAP_SIDECAR.is_file():
        return None
    raw = json.loads(SWAP_SIDECAR.read_text())
    v = raw.get("swap_long_usd_per_lot_night")
    if v is None:
        return None
    return float(v)


def _nights(days: pd.Series) -> tuple[int, int]:
    """Weekday rollovers; Wednesday counts as 3. No invented weekend days."""
    n_wed = 0
    n_other = 0
    for i in range(len(days) - 1):
        a = days.iloc[i]
        b = days.iloc[i + 1]
        # one rollover if next calendar trading day follows
        if (b - a).days <= 0:
            continue
        # count the weekday of date a as the night we hold into the next bar
        wd = int(a.dayofweek)  # Mon=0 ... Wed=2
        if wd == 2:
            n_wed += 1
        elif wd < 5:
            n_other += 1
    return n_wed, n_other


def main() -> int:
    charter = json.loads(CHARTER.read_text())
    if charter.get("family_id") != FAMILY:
        raise SystemExit("charter family_id mismatch")

    h1 = pd.read_csv(CSV, parse_dates=["time"])
    h1 = h1.loc[h1["time"] < HOLDOUT].sort_values("time")
    med = float(h1["spread"].median())
    h1["spread"] = h1["spread"].fillna(med)
    d = resample_daily(h1)
    o0 = float(d["open"].iloc[0])
    cN = float(d["close"].iloc[-1])
    spr0 = float(d["spread"].iloc[0])
    sprN = float(d["spread"].iloc[-1])
    price_pnl = (cN - o0) / POINT * TICK_VALUE * LOTS
    spread_cost = (spr0 + sprN) * TICK_VALUE * LOTS * 0.5
    # one-way each end ≈ 0.5 * (spread pts * tick_value * lots) * 2 ends = (spr0+sprN)/2 * tv * lots * 2
    # = (spr0+sprN)*tv*lots*0.5  ... use full RT at each end: spr * tv * lots
    spread_cost = (spr0 + sprN) * TICK_VALUE * LOTS

    swap = _load_swap()
    swap_reason = "sidecar"
    if swap is None:
        swap = 0.0
        swap_reason = "symbolinfo_unreadable_bridge_stale_fail_closed"

    n_wed, n_other = _nights(d["day"])
    swap_nights_eff = 3 * n_wed + n_other
    swap_pnl = swap * LOTS * swap_nights_eff

    np_swap = price_pnl - spread_cost + swap_pnl
    np_noswap = price_pnl - spread_cost
    # path DD from daily marks (price only; swap accrued linearly)
    px = d["close"].to_numpy(float)
    daily_jpy = np.diff(np.concatenate([[o0], px]))
    daily_usd = daily_jpy / POINT * TICK_VALUE * LOTS
    # allocate swap across weekdays equally for equity path
    extra = np.zeros(len(daily_usd))
    if swap_nights_eff > 0 and swap != 0:
        extra[:] = swap_pnl / len(daily_usd)
    eq_path = np.concatenate([[START_BALANCE], START_BALANCE + np.cumsum(daily_usd + extra)])
    # charge spread at start
    eq_path[1:] -= spr0 * TICK_VALUE * LOTS
    eq_path[-1] -= sprN * TICK_VALUE * LOTS
    m = metrics_from_pnls([np_swap], eq_path)
    ok = swap > 0 and np_swap > 0 and m.max_drawdown_pct <= 15.0 and np_swap > np_noswap
    verdict = "SOFT_PASS" if ok else "SCREEN_FAIL"
    out = {
        "family_id": FAMILY,
        "verdict": verdict,
        "promote": False,
        "live_go": False,
        "swap_usd_per_lot_night": swap,
        "swap_source": swap_reason,
        "swap_nights_wed": n_wed,
        "swap_nights_other": n_other,
        "swap_nights_effective": swap_nights_eff,
        "price_pnl": price_pnl,
        "spread_cost": spread_cost,
        "swap_pnl": swap_pnl,
        "develop": {"np": np_swap, "dd": m.max_drawdown_pct},
        "no_swap_arm": {"np": np_noswap},
        "gates": {
            "swap_gt_0": swap > 0,
            "net_profit_gt_0": np_swap > 0,
            "dd_le_15": m.max_drawdown_pct <= 15.0,
            "np_gt_no_swap": np_swap > np_noswap,
        },
        "holdout": None,
        "notes": "Fail-closed if SymbolInfo swap unread. tick_value from Vantage USDJPY snapshot.",
    }
    dest = ROOT / "results" / f"{FAMILY}_screen.json"
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print(
        f"DEVELOP {verdict} NP={np_swap:.2f} DD={m.max_drawdown_pct:.2f}% "
        f"no_swap={np_noswap:.2f} swap={swap} src={swap_reason}"
    )
    print("wrote", dest)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
