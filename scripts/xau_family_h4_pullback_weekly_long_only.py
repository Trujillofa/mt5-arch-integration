#!/usr/bin/env python3
"""Zero-knob H4 pivot-low reclaim, weekly EMA20 permission, long only.

Charter: results/xau_charters/2026-09-17_xau_h4_pullback_weekly_long_only_v1.json
Pivots: scripts/htf_fib_core.confirmed_pivots (center+right only).

SAFETY: offline. No --live. Holdout never for selection.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from htf_fib_core import confirmed_pivots  # noqa: E402

from backtest import CONTRACT_SIZE, START_BALANCE, Metrics, metrics_from_pnls  # noqa: E402

FAMILY = "xau_h4_pullback_weekly_long_only_v1"
kill_label = "KILL_XAU_H4_PULLBACK_WEEKLY_LONG_ONLY"
use_soft_primary = True

LEFT = 5
RIGHT = 5
WEEKLY_EMA = 20
ATR_PERIOD = 14
SL_ATR_FRAC = 0.25
RISK_PCT = 0.01
MAX_LOTS = 0.5
MIN_LOT = 0.01
WARMUP = 80
POINT = 0.01
HOLDOUT = pd.Timestamp("2026-01-01T00:00:00+00:00")


def load_h1(csv_path: Path) -> pd.DataFrame:
    raw = pd.read_csv(csv_path)
    d = raw.loc[raw["timeframe"] == "H1"].copy()
    d["time"] = pd.to_datetime(d["time"], utc=True)
    return d.sort_values("time").reset_index(drop=True)


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
            "tick_volume": g["tick_volume"].sum(),
        }
    ).reset_index(drop=True)
    h = out["high"].astype(float)
    lo = out["low"].astype(float)
    c = out["close"].astype(float)
    prev = c.shift(1)
    tr = pd.concat([(h - lo), (h - prev).abs(), (lo - prev).abs()], axis=1).max(axis=1)
    out["atr"] = tr.ewm(alpha=1.0 / ATR_PERIOD, adjust=False).mean()
    out["week"] = out["time"].dt.to_period("W-SUN")
    return out


def attach_weekly_permission(h4: pd.DataFrame) -> pd.DataFrame:
    d = h4.copy()
    weekly = d.groupby("week", sort=True)["close"].last()
    ema = weekly.ewm(span=WEEKLY_EMA, adjust=False).mean()
    perm_by_week: dict[Any, bool] = {}
    kill_by_week: dict[Any, bool] = {}
    weeks = list(weekly.index)
    for i, w in enumerate(weeks):
        if i == 0:
            perm_by_week[w] = False
        else:
            prev = weeks[i - 1]
            perm_by_week[w] = bool(weekly.loc[prev] > ema.loc[prev])
        kill_by_week[w] = bool(weekly.loc[w] < ema.loc[w])
    d["permission"] = d["week"].map(perm_by_week).astype(bool)
    last = d.groupby("week", sort=True).tail(1).index
    d["week_end"] = False
    d.loc[last, "week_end"] = True
    d["weekly_kill"] = False
    d.loc[last, "weekly_kill"] = d.loc[last, "week"].map(kill_by_week).astype(bool)
    return d


def prepare(raw: pd.DataFrame) -> pd.DataFrame:
    h1 = raw.loc[raw["timeframe"] == "H1"].copy() if "timeframe" in raw.columns else raw.copy()
    h1["time"] = pd.to_datetime(h1["time"], utc=True)
    h1 = h1.sort_values("time").reset_index(drop=True)
    return attach_weekly_permission(resample_h4(h1))


def build_grid() -> list[dict]:
    return [{"left": LEFT, "right": RIGHT, "weekly_ema": WEEKLY_EMA, "sl_atr_frac": SL_ATR_FRAC}]


def grid(*, max_n: int = 1200, seed: int = 42) -> list[dict]:
    _ = max_n, seed
    return build_grid()


def _round_lots(raw_lots: float) -> float:
    lots = float(np.floor(raw_lots * 100 + 1e-12) / 100.0)
    return min(max(lots, 0.0), MAX_LOTS)


def _rt_cost(
    spread_pts: float, lots: float, slippage_points: float, commission_per_lot: float
) -> float:
    return (
        float(spread_pts) + 2.0 * float(slippage_points)
    ) * POINT * CONTRACT_SIZE * lots + 2.0 * float(commission_per_lot) * lots


def simulate(
    d: pd.DataFrame,
    *,
    spread_col: str | None = "spread",
    point_size: float = POINT,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    trade_log: list[dict[str, Any]] | None = None,
    **_extra: Any,
) -> Metrics:
    _ = point_size
    n = len(d)
    if n < WARMUP + 2:
        return Metrics(0, 0, 0, 0, 0, 0, 0)

    open_ = d["open"].to_numpy(float)
    high = d["high"].to_numpy(float)
    low = d["low"].to_numpy(float)
    close = d["close"].to_numpy(float)
    atr = d["atr"].to_numpy(float)
    perm = d["permission"].to_numpy(bool)
    week_kill = d["weekly_kill"].to_numpy(bool)
    if spread_col and spread_col in d.columns:
        spread_pts = np.nan_to_num(d[spread_col].to_numpy(float), nan=0.0)
    else:
        spread_pts = np.zeros(n)

    events = confirmed_pivots(high, low, LEFT, RIGHT)
    lows = [(a, p) for a, p, t in events if t < 0]
    # latest confirmed pivot low at or before i
    latest_a = np.full(n, -1, dtype=int)
    latest_p = np.full(n, np.nan)
    j = 0
    cur_a, cur_p = -1, np.nan
    for i in range(n):
        while j < len(lows) and lows[j][0] <= i:
            cur_a, cur_p = lows[j]
            j += 1
        latest_a[i] = cur_a
        latest_p[i] = cur_p

    consumed: set[int] = set()
    pos = False
    pending_entry = False
    pending_exit = False
    swing = sl = entry = cost = lots = entry_stop_dist = 0.0
    pivot_id = -1
    balance = float(START_BALANCE)
    peak = balance
    equity = np.full(n, balance)
    pnls: list[float] = []

    def book(exit_px: float, reason: str, bar: int) -> None:
        nonlocal pos, pending_exit, pending_entry, balance, peak
        pnl = (exit_px - entry) * CONTRACT_SIZE * lots - cost
        pnls.append(pnl)
        balance += pnl
        peak = max(peak, balance)
        if trade_log is not None:
            trade_log.append(
                {
                    "exit_bar": bar,
                    "entry": entry,
                    "exit": exit_px,
                    "lots": lots,
                    "pnl": pnl,
                    "reason": reason,
                    "swing": swing,
                }
            )
        pos = False
        pending_exit = False
        pending_entry = False

    for i in range(WARMUP, n):
        if pending_exit and not pos:
            pending_exit = False
        if pending_exit and pos:
            book(open_[i], "flatten_open", i)

        if pending_entry and not pos:
            pending_entry = False
            if open_[i] <= sl:
                consumed.add(pivot_id)
            else:
                risk_cash = balance * RISK_PCT
                stop_dist = entry_stop_dist
                raw = risk_cash / (stop_dist * CONTRACT_SIZE) if stop_dist > 0 else 0.0
                lots = _round_lots(raw)
                if lots < MIN_LOT or stop_dist * CONTRACT_SIZE * MIN_LOT > risk_cash:
                    consumed.add(pivot_id)
                else:
                    entry = float(open_[i])
                    cost = _rt_cost(spread_pts[i], lots, slippage_points, commission_per_lot)
                    pos = True
                    consumed.add(pivot_id)

        if pos:
            if low[i] <= sl:
                book(sl, "sl", i)
            else:
                if close[i] < swing:
                    pending_exit = True
                if bool(week_kill[i]):
                    pending_exit = True

        if (not pos) and (not pending_entry) and bool(perm[i]):
            pid = int(latest_a[i])
            pv = float(latest_p[i])
            if pid >= 0 and pid not in consumed and np.isfinite(pv) and close[i] > pv:
                atr_i = float(atr[i])
                if atr_i > 0:
                    sl_px = pv - SL_ATR_FRAC * atr_i
                    dist = close[i] - sl_px
                    if sl_px < pv and dist > 0:
                        pending_entry = True
                        pivot_id = pid
                        swing = pv
                        sl = sl_px
                        entry_stop_dist = float(pv - sl_px)

        equity[i] = balance
        if pos:
            equity[i] = balance + (close[i] - entry) * CONTRACT_SIZE * lots - cost

    if pos:
        book(float(close[-1]), "eod", n - 1)
        equity[-1] = balance

    return metrics_from_pnls(pnls, equity)


def always_long_metrics(
    d: pd.DataFrame,
    *,
    slippage_points: float = 0.0,
    commission_per_lot: float = 0.0,
) -> Metrics:
    """Single 0.5-lot long from first post-warmup open to last close."""
    n = len(d)
    if n < WARMUP + 2:
        return Metrics(0, 0, 0, 0, 0, 0, 0)
    lots = MAX_LOTS
    entry = float(d["open"].iloc[WARMUP])
    exit_px = float(d["close"].iloc[-1])
    spr = float(d["spread"].iloc[WARMUP]) if "spread" in d.columns else 0.0
    cost = _rt_cost(spr, lots, slippage_points, commission_per_lot)
    pnl = (exit_px - entry) * CONTRACT_SIZE * lots - cost
    eq = np.array([START_BALANCE, START_BALANCE + pnl], dtype=float)
    return metrics_from_pnls([pnl], eq)


def soft_pass(m: Metrics, always_net: float) -> bool:
    if m.n_trades < 40:
        return False
    if m.profit_factor < 1.2:
        return False
    if m.net_profit <= 0:
        return False
    if m.max_drawdown_pct > 15.0:
        return False
    # Parentheses keep NaN behaviour of `if x <= y: return False; return True`.
    return not (m.net_profit <= always_net)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "xauusd_data.csv"))
    ap.add_argument(
        "--holdout-eval", action="store_true", help="evaluate holdout once; not for selection"
    )
    args = ap.parse_args()

    h1 = load_h1(Path(args.csv))
    h4 = attach_weekly_permission(resample_h4(h1))
    costs = json.loads((ROOT / "results" / "xau_research_costs.json").read_text())
    slip = float(costs.get("slippage_points") or 0.0)
    comm = float(costs.get("commission_per_lot") or 0.0)

    dev = h4.loc[h4["time"] < HOLDOUT].reset_index(drop=True)
    m = simulate(dev, slippage_points=slip, commission_per_lot=comm)
    al = always_long_metrics(dev, slippage_points=slip, commission_per_lot=comm)
    ok = soft_pass(m, al.net_profit)
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
            "h4_bars": int(len(dev)),
            "h4_start": str(dev["time"].iloc[0]) if len(dev) else None,
            "h4_end": str(dev["time"].iloc[-1]) if len(dev) else None,
        },
        "always_long": {
            "n": al.n_trades,
            "np": al.net_profit,
            "pf": al.profit_factor,
            "dd": al.max_drawdown_pct,
        },
        "beat_always_long": m.net_profit > al.net_profit,
        "costs": {"slippage_points": slip, "commission_per_lot": comm},
        "holdout": None,
    }
    print(
        f"DEVELOP {verdict} n={m.n_trades} WR={m.win_rate:.1f}% PF={m.profit_factor:.3f} "
        f"NP={m.net_profit:.2f} DD={m.max_drawdown_pct:.2f}% | always-long NP={al.net_profit:.2f} "
        f"beat={m.net_profit > al.net_profit}"
    )

    if args.holdout_eval:
        ho = h4.loc[h4["time"] >= HOLDOUT].reset_index(drop=True)
        mh = simulate(ho, slippage_points=slip, commission_per_lot=comm)
        ah = always_long_metrics(ho, slippage_points=slip, commission_per_lot=comm)
        out["holdout"] = {
            "role": "eval_only_not_selection",
            "n": mh.n_trades,
            "wr": mh.win_rate,
            "pf": mh.profit_factor,
            "np": mh.net_profit,
            "dd": mh.max_drawdown_pct,
            "always_long_np": ah.net_profit,
        }
        print(
            f"HOLDOUT eval-only n={mh.n_trades} WR={mh.win_rate:.1f}% PF={mh.profit_factor:.3f} "
            f"NP={mh.net_profit:.2f} | always-long NP={ah.net_profit:.2f}"
        )

    dest = ROOT / "results" / "xau_h4_pullback_weekly_long_only_v1_screen.json"
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print("wrote", dest)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
