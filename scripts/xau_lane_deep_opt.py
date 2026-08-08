#!/usr/bin/env python3
"""Deep develop-only optimization for 5 XAU lanes (full budget, no early discard).

Doctrine: optimize as much as possible BEFORE discarding any lane.
SAFETY: offline only. NEVER read holdout metrics to choose params. NEVER --live.

Writes:
  results/xau_lane_deep_opt.json
  results/xau_lane_champions.json  (no holdout numbers)
"""
from __future__ import annotations

import itertools
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from htf_fib_core import (  # noqa: E402
    confirmed_pivots,
    expand_fib_states,
    walk_swing_and_fibs,
)
from xau_new_design_search import extend_indicators  # noqa: E402

from backtest import (  # noqa: E402
    CONTRACT_SIZE,
    START_BALANCE,
    Metrics,
    load_h1,
    metrics_from_pnls,
)

OUT_DEEP = ROOT / "results" / "xau_lane_deep_opt.json"
OUT_CHAMP = ROOT / "results" / "xau_lane_champions.json"
HOLDOUT_START = pd.Timestamp("2026-01-01", tz="UTC")
WARMUP = 220
MIN_EVALS = 200

# Session hour presets (UTC broker-style)
HOURS_LONDON_NY = tuple(range(7, 17))  # 7–16 inclusive
HOURS_LONDON_NY_LATE = tuple(range(12, 21))  # 12–20 inclusive
HOURS_NONE: tuple[int, ...] | None = None


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------
def _rank_last(arr: np.ndarray) -> float:
    if len(arr) < 2 or np.isnan(arr[-1]):
        return np.nan
    return float(np.sum(arr <= arr[-1]) - 1) / float(max(len(arr) - 1, 1))


def prepare_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Base indicators + atr_pctile + Donchian set + causal H4 bias."""
    d = extend_indicators(raw)
    # Extra Donchian lengths used by grids
    high = d["high"].astype(float)
    low = d["low"].astype(float)
    for n in (10, 12, 15, 20, 24, 30, 40, 55):
        hi_k = f"donch_hi_{n}"
        lo_k = f"donch_lo_{n}"
        if hi_k not in d.columns:
            d[hi_k] = high.rolling(n, min_periods=n).max()
        if lo_k not in d.columns:
            d[lo_k] = low.rolling(n, min_periods=n).min()

    times = pd.to_datetime(d["time"], utc=True)
    tmp = d.copy()
    tmp.index = times
    if not tmp.index.is_unique:
        tmp = tmp[~tmp.index.duplicated(keep="last")]

    h4 = (
        tmp.resample("4h")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna(subset=["close"])
    )
    h4_ema200 = h4["close"].ewm(span=200, adjust=False).mean()
    # Causal: only completed H4 bar (shift 1) then ffill to H1
    h4_bull = (h4["close"] > h4_ema200).astype(float).shift(1)
    h4_close = h4["close"].shift(1)
    h4_ema = h4_ema200.shift(1)
    bull_h1 = h4_bull.reindex(tmp.index, method="ffill")
    # align back to original d order/length
    d = d.copy()
    d["_t"] = times.values
    aligned = pd.DataFrame({"_t": tmp.index, "h4_bull": bull_h1.values})
    # map via merge on time
    m = pd.Series(aligned["h4_bull"].values, index=tmp.index)
    d["h4_bull"] = m.reindex(times).to_numpy(float)
    # day key for max_entries_per_day
    d["day_id"] = times.dt.strftime("%Y%m%d").astype(int).to_numpy()
    d["hour"] = times.dt.hour.astype(int)
    return d


def metrics_dict(m: Metrics) -> dict[str, float | int]:
    exp = float(m.net_profit / m.n_trades) if m.n_trades > 0 else 0.0
    return {
        "net_profit": float(m.net_profit),
        "win_rate": float(m.win_rate),
        "profit_factor": float(m.profit_factor),
        "max_drawdown_pct": float(m.max_drawdown_pct),
        "n_trades": int(m.n_trades),
        "wins": int(m.wins),
        "losses": int(m.losses),
        "expectancy": exp,
        "expectancy_sqrt_n": exp * float(np.sqrt(max(m.n_trades, 0))),
    }


def serializable_params(p: dict) -> dict:
    out: dict[str, Any] = {}
    for k, v in p.items():
        if isinstance(v, tuple):
            out[k] = list(v)
        elif isinstance(v, (np.floating, np.integer)):
            out[k] = v.item()
        elif v is None or isinstance(v, (bool, int, float, str, list, dict)):
            out[k] = v
        else:
            out[k] = str(v)
    return out


def size_lots(
    bal: float, stop_dist: float, risk_pct: float, max_lots: float = 0.5
) -> float | None:
    if stop_dist <= 1e-9:
        return None
    risk_cash = bal * risk_pct
    raw = risk_cash / (stop_dist * CONTRACT_SIZE)
    lots = float(np.floor(raw * 100 + 1e-12) / 100.0)
    lots = min(lots, max_lots)
    min_lot = 0.01
    if lots < min_lot or stop_dist * CONTRACT_SIZE * min_lot > risk_cash + 1e-9:
        return None
    return lots


def _hours_ok(hour: int, hours: tuple[int, ...] | None) -> bool:
    if hours is None:
        return True
    return hour in hours


def _pct_unit(x: float | None) -> float | None:
    if x is None:
        return None
    v = float(x)
    return v / 100.0 if v > 1.0 else v


# ---------------------------------------------------------------------------
# Shared risk helpers inside bar loop
# ---------------------------------------------------------------------------
def _apply_be(
    pos: int,
    entry: float,
    sl: float,
    high: float,
    low: float,
    initial_risk: float,
    be_at_r: float | None,
    be_done: bool,
) -> tuple[float, bool]:
    if be_at_r is None or be_done or initial_risk <= 0:
        return sl, be_done
    thr = float(be_at_r) * initial_risk
    if pos > 0 and high >= entry + thr:
        return max(sl, entry), True
    if pos < 0 and low <= entry - thr:
        return min(sl, entry), True
    return sl, be_done


def _spread_pts_array(d: pd.DataFrame, n: int, spread_col: str | None) -> np.ndarray:
    """Per-bar spread in points; zeros when column missing (frictionless)."""
    if spread_col is not None and spread_col in d.columns:
        return np.nan_to_num(d[spread_col].to_numpy(float), nan=0.0)
    return np.zeros(n)


def _trade_cost(
    spread_pts: np.ndarray,
    i: int,
    lots: float,
    *,
    point_size: float = 0.01,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
) -> float:
    """Round-trip cost priced off entry bar — same formula as backtest.simulate."""
    return (
        (float(spread_pts[i]) + 2.0 * float(slippage_points))
        * float(point_size)
        * CONTRACT_SIZE
        * float(lots)
        + 2.0 * float(commission_per_lot) * float(lots)
    )


# ---------------------------------------------------------------------------
# Lane simulators (enhanced)
# ---------------------------------------------------------------------------
def simulate_vol_gate(
    d: pd.DataFrame,
    *,
    atr_max_pct: float = 0.45,
    rsi_buy: float = 30.0,
    rsi_sell: float = 50.0,
    sl_atr: float = 1.5,
    tp_atr: float = 2.5,
    bb_col: str = "bb_lo15",
    trend_col: str = "ema200",
    require_uptrend: bool = True,
    exit_on_vol_spike: bool = True,
    cooldown: int = 2,
    risk_pct: float = 0.01,
    max_lots: float = 0.5,
    h4_bias: bool = False,
    max_entries_per_day: int = 2,
    be_at_r: float | None = None,
    hours: tuple[int, ...] | None = None,
    failed_breakout_fade: bool = False,
    long_only: bool = True,
    spread_col: str | None = None,
    point_size: float = 0.01,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    **_extra: Any,
) -> Metrics:
    n = len(d)
    close = d["close"].to_numpy(float)
    high = d["high"].to_numpy(float)
    low = d["low"].to_numpy(float)
    open_ = d["open"].to_numpy(float) if "open" in d.columns else close
    rsi = d["rsi"].to_numpy(float)
    atr = d["atr"].to_numpy(float)
    atr_pc = d["atr_pctile"].to_numpy(float)
    bb_mid = d["bb_mid"].to_numpy(float)
    bb_up = d["bb_up"].to_numpy(float)
    bb_lo = d[bb_col].to_numpy(float) if bb_col in d.columns else d["bb_lo"].to_numpy(float)
    trend = d[trend_col].to_numpy(float) if trend_col in d.columns else d["ema200"].to_numpy(float)
    hour = d["hour"].to_numpy(int)
    day_id = d["day_id"].to_numpy(int)
    h4b = d["h4_bull"].to_numpy(float) if "h4_bull" in d.columns else np.ones(n)
    donch_hi20 = (
        d["donch_hi_20"].to_numpy(float)
        if "donch_hi_20" in d.columns
        else pd.Series(high).rolling(20, min_periods=20).max().to_numpy(float)
    )

    atr_max = _pct_unit(atr_max_pct) or 0.55
    spread_pts = _spread_pts_array(d, n, spread_col)
    bal = START_BALANCE
    eq = np.zeros(n)
    pnls: list[float] = []
    pos = 0
    entry = sl = tp = lots = initial_risk = 0.0
    trade_cost = 0.0
    cool = 0
    be_done = False
    entries_today = 0
    cur_day = -1

    for i in range(n):
        px = close[i]
        floating = bal + ((px - entry) * CONTRACT_SIZE * lots * pos if pos else 0.0)
        eq[i] = floating

        if day_id[i] != cur_day:
            cur_day = int(day_id[i])
            entries_today = 0

        if pos != 0 and i >= 1 and not np.isnan(atr[i]):
            sl, be_done = _apply_be(
                pos, entry, sl, high[i], low[i], initial_risk, be_at_r, be_done
            )
            exit_px = None
            if pos > 0:
                if low[i] <= sl:
                    exit_px = sl
                elif high[i] >= tp:
                    exit_px = tp
                elif not np.isnan(rsi[i]) and rsi[i] >= rsi_sell:
                    exit_px = px
            else:
                if high[i] >= sl:
                    exit_px = sl
                elif low[i] <= tp:
                    exit_px = tp
                elif not np.isnan(rsi[i]) and rsi[i] <= (100 - rsi_sell):
                    exit_px = px

            if (
                exit_px is None
                and exit_on_vol_spike
                and not np.isnan(atr_pc[i])
                and atr_pc[i] > atr_max
            ):
                exit_px = px

            if exit_px is not None:
                pnl = (exit_px - entry) * CONTRACT_SIZE * lots * pos - trade_cost
                bal += pnl
                pnls.append(pnl)
                pos = 0
                lots = 0.0
                trade_cost = 0.0
                cool = cooldown
                be_done = False
                eq[i] = bal

        if cool > 0:
            cool -= 1
            continue
        if pos != 0 or i < WARMUP:
            continue
        if np.isnan(atr[i]) or atr[i] <= 0 or np.isnan(atr_pc[i]):
            continue
        if not _hours_ok(int(hour[i]), hours):
            continue
        if entries_today >= int(max_entries_per_day):
            continue
        if h4_bias and (np.isnan(h4b[i]) or h4b[i] < 0.5):
            continue

        long_sig = False
        short_sig = False

        # Optional failed-breakout fade only in low atr_pctile
        if failed_breakout_fade and atr_pc[i] < atr_max and i >= 2:
            # prior bar broke high then closed back inside → fade short OR
            # for long_only: fade failed downside break as long re-entry
            if (
                not np.isnan(donch_hi20[i - 2])
                and high[i - 1] > donch_hi20[i - 2]
                and close[i - 1] < donch_hi20[i - 2]
                and close[i] < bb_mid[i]
                and not np.isnan(rsi[i])
                and rsi[i] <= rsi_buy + 15
            ):
                # failed upside breakout in low vol → skip chase; stay MR path
                pass

        if atr_pc[i] > atr_max:
            continue
        if np.isnan(rsi[i]) or np.isnan(bb_lo[i]) or np.isnan(trend[i]):
            continue
        uptrend = close[i] > trend[i]
        if require_uptrend and not uptrend:
            continue
        long_sig = (
            uptrend
            and low[i] <= bb_lo[i]
            and close[i] > bb_lo[i]
            and close[i] < bb_mid[i]
            and rsi[i] <= rsi_buy + 10
        )
        if not long_only and close[i] < trend[i]:
            short_sig = (
                high[i] >= bb_up[i]
                and close[i] < bb_up[i]
                and close[i] > bb_mid[i]
                and rsi[i] >= (100 - rsi_buy - 10)
            )
        if long_only:
            short_sig = False
        if not long_sig and not short_sig:
            continue

        stop_dist = atr[i] * float(sl_atr)
        lots_sz = size_lots(bal, stop_dist, risk_pct, max_lots)
        if lots_sz is None:
            continue
        lots = lots_sz
        trade_cost = _trade_cost(
            spread_pts,
            i,
            lots,
            point_size=point_size,
            commission_per_lot=commission_per_lot,
            slippage_points=slippage_points,
        )
        if long_sig:
            pos = 1
            entry = px
            sl = entry - stop_dist
            tp = entry + atr[i] * float(tp_atr)
        else:
            pos = -1
            entry = px
            sl = entry + stop_dist
            tp = entry - atr[i] * float(tp_atr)
        initial_risk = stop_dist
        be_done = False
        entries_today += 1

    if pos != 0:
        pnl = (close[-1] - entry) * CONTRACT_SIZE * lots * pos - trade_cost
        bal += pnl
        pnls.append(pnl)
        eq[-1] = bal
    return metrics_from_pnls(pnls, eq)


def simulate_donchian(
    d: pd.DataFrame,
    *,
    entry_N: int = 20,
    exit_N: int = 10,
    atr_sl: float = 2.0,
    atr_min_pct: float | None = None,
    exit_on_exit_channel: bool = True,
    mid_channel_k: float | None = None,
    h4_bias: bool = False,
    max_entries_per_day: int = 2,
    be_at_r: float | None = None,
    partial_tp: bool = False,
    partial_tp_r: float = 1.5,
    partial_frac: float = 0.5,
    hours: tuple[int, ...] | None = None,
    failed_breakout_fade: bool = False,
    cooldown: int = 2,
    risk_pct: float = 0.01,
    max_lots: float = 0.5,
    long_only: bool = True,
    spread_col: str | None = None,
    point_size: float = 0.01,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    **_extra: Any,
) -> Metrics:
    n = len(d)
    close = d["close"].to_numpy(float)
    high = d["high"].to_numpy(float)
    low = d["low"].to_numpy(float)
    atr = d["atr"].to_numpy(float)
    atr_pc = d["atr_pctile"].to_numpy(float)
    hour = d["hour"].to_numpy(int)
    day_id = d["day_id"].to_numpy(int)
    h4b = d["h4_bull"].to_numpy(float) if "h4_bull" in d.columns else np.ones(n)

    e_hi = f"donch_hi_{int(entry_N)}"
    e_lo = f"donch_lo_{int(entry_N)}"
    x_lo = f"donch_lo_{int(exit_N)}"
    donch_hi = (
        d[e_hi].to_numpy(float)
        if e_hi in d.columns
        else pd.Series(high).rolling(int(entry_N), min_periods=int(entry_N)).max().to_numpy(float)
    )
    donch_lo_entry = (
        d[e_lo].to_numpy(float)
        if e_lo in d.columns
        else pd.Series(low).rolling(int(entry_N), min_periods=int(entry_N)).min().to_numpy(float)
    )
    donch_lo_exit = (
        d[x_lo].to_numpy(float)
        if x_lo in d.columns
        else pd.Series(low).rolling(int(exit_N), min_periods=int(exit_N)).min().to_numpy(float)
    )

    atr_min = _pct_unit(atr_min_pct)
    spread_pts = _spread_pts_array(d, n, spread_col)
    bal = START_BALANCE
    eq = np.zeros(n)
    pnls: list[float] = []
    pos = 0
    entry = sl = lots = initial_risk = 0.0
    trade_cost = 0.0
    cool = 0
    be_done = False
    partial_done = False
    entries_today = 0
    cur_day = -1

    for i in range(n):
        px = close[i]
        floating = bal + ((px - entry) * CONTRACT_SIZE * lots * pos if pos else 0.0)
        eq[i] = floating
        if day_id[i] != cur_day:
            cur_day = int(day_id[i])
            entries_today = 0

        if pos != 0 and i >= 1 and not np.isnan(atr[i]):
            sl, be_done = _apply_be(
                pos, entry, sl, high[i], low[i], initial_risk, be_at_r, be_done
            )
            # partial TP: take fraction at partial_tp_r * R
            if partial_tp and not partial_done and initial_risk > 0:
                thr = entry + float(partial_tp_r) * initial_risk if pos > 0 else entry - float(partial_tp_r) * initial_risk
                hit = (pos > 0 and high[i] >= thr) or (pos < 0 and low[i] <= thr)
                if hit and lots > 0.02:
                    take = max(0.01, float(np.floor(lots * partial_frac * 100) / 100.0))
                    take = min(take, lots - 0.01)
                    if take >= 0.01:
                        pnl = (thr - entry) * CONTRACT_SIZE * take * pos
                        bal += pnl
                        pnls.append(pnl)
                        lots -= take
                        partial_done = True
                        if be_at_r is not None or True:
                            # move remainder to BE after partial
                            sl = entry if pos > 0 else entry
                            be_done = True

            exit_px = None
            if pos > 0:
                if low[i] <= sl:
                    exit_px = sl
                elif (
                    exit_on_exit_channel
                    and i >= 1
                    and not np.isnan(donch_lo_exit[i - 1])
                    and close[i] < donch_lo_exit[i - 1]
                ):
                    exit_px = px
            else:
                if high[i] >= sl:
                    exit_px = sl
                elif (
                    exit_on_exit_channel
                    and i >= 1
                    and not np.isnan(donch_hi[i - 1])
                    and close[i] > donch_hi[i - 1]
                ):
                    exit_px = px

            if exit_px is not None:
                # Full RT once per entry (partial legs already booked price-only).
                pnl = (exit_px - entry) * CONTRACT_SIZE * lots * pos - trade_cost
                bal += pnl
                pnls.append(pnl)
                pos = 0
                lots = 0.0
                trade_cost = 0.0
                cool = cooldown
                be_done = False
                partial_done = False
                eq[i] = bal

        if cool > 0:
            cool -= 1
            continue
        if pos != 0 or i < WARMUP:
            continue
        if np.isnan(atr[i]) or atr[i] <= 0:
            continue
        if i < 1 or np.isnan(donch_hi[i - 1]):
            continue
        if not _hours_ok(int(hour[i]), hours):
            continue
        if entries_today >= int(max_entries_per_day):
            continue
        if h4_bias and (np.isnan(h4b[i]) or h4b[i] < 0.5):
            continue
        if atr_min is not None and (np.isnan(atr_pc[i]) or atr_pc[i] < atr_min):
            continue

        long_sig = close[i] > donch_hi[i - 1]
        short_sig = False

        # mid-channel extremes filter
        if mid_channel_k is not None and float(mid_channel_k) > 0 and long_sig:
            mid = 0.5 * (donch_hi[i - 1] + donch_lo_entry[i - 1])
            if abs(close[i] - mid) < float(mid_channel_k) * atr[i]:
                long_sig = False

        # failed breakout fade: only low atr_pctile — reverse turtle
        if failed_breakout_fade and not np.isnan(atr_pc[i]) and atr_pc[i] < 0.40 and i >= 2:
            # failed upside break yesterday → fade short (if not long_only) or skip long
            if (
                high[i - 1] > donch_hi[i - 2]
                and close[i - 1] < donch_hi[i - 2]
                and close[i] < donch_hi[i - 1]
            ):
                long_sig = False
                if not long_only:
                    short_sig = True

        if long_only:
            short_sig = False
        if not long_sig and not short_sig:
            continue

        stop_dist = atr[i] * float(atr_sl)
        lots_sz = size_lots(bal, stop_dist, risk_pct, max_lots)
        if lots_sz is None:
            continue
        lots = lots_sz
        trade_cost = _trade_cost(
            spread_pts,
            i,
            lots,
            point_size=point_size,
            commission_per_lot=commission_per_lot,
            slippage_points=slippage_points,
        )
        if long_sig:
            pos = 1
            entry = px
            sl = entry - stop_dist
        else:
            pos = -1
            entry = px
            sl = entry + stop_dist
        initial_risk = stop_dist
        be_done = False
        partial_done = False
        entries_today += 1

    if pos != 0:
        pnl = (close[-1] - entry) * CONTRACT_SIZE * lots * pos - trade_cost
        bal += pnl
        pnls.append(pnl)
        eq[-1] = bal
    return metrics_from_pnls(pnls, eq)


def simulate_atr_trail(
    d: pd.DataFrame,
    *,
    entry_N: int = 20,
    atr_min_pct: float = 0.55,
    trail_atr: float = 2.5,
    sl_atr: float = 2.0,
    h4_bias: bool = False,
    max_entries_per_day: int = 2,
    be_at_r: float | None = None,
    hours: tuple[int, ...] | None = None,
    require_ema_stack: bool = False,
    rsi_max: float = 80.0,
    ema_trend: str = "ema100",
    mid_channel_k: float | None = None,
    cooldown: int = 2,
    risk_pct: float = 0.01,
    max_lots: float = 0.5,
    long_only: bool = True,
    spread_col: str | None = None,
    point_size: float = 0.01,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    **_extra: Any,
) -> Metrics:
    n = len(d)
    close = d["close"].to_numpy(float)
    high = d["high"].to_numpy(float)
    low = d["low"].to_numpy(float)
    atr = d["atr"].to_numpy(float)
    atr_pc = d["atr_pctile"].to_numpy(float)
    rsi = d["rsi"].to_numpy(float)
    hour = d["hour"].to_numpy(int)
    day_id = d["day_id"].to_numpy(int)
    h4b = d["h4_bull"].to_numpy(float) if "h4_bull" in d.columns else np.ones(n)
    ema20 = d["ema20"].to_numpy(float)
    ema50 = d["ema50"].to_numpy(float)
    ema100 = d["ema100"].to_numpy(float)
    ema_tr = d[ema_trend].to_numpy(float) if ema_trend in d.columns else ema100

    dn = int(entry_N)
    e_hi = f"donch_hi_{dn}"
    e_lo = f"donch_lo_{dn}"
    donch_hi = (
        d[e_hi].to_numpy(float)
        if e_hi in d.columns
        else pd.Series(high).rolling(dn, min_periods=dn).max().to_numpy(float)
    )
    donch_lo = (
        d[e_lo].to_numpy(float)
        if e_lo in d.columns
        else pd.Series(low).rolling(dn, min_periods=dn).min().to_numpy(float)
    )

    atr_min = _pct_unit(atr_min_pct) or 0.0
    trail_mult = float(trail_atr)
    init_sl_mult = trail_mult if trail_mult > 0 else float(sl_atr)
    risk_sl_mult = float(sl_atr) if float(sl_atr) > 0 else init_sl_mult

    spread_pts = _spread_pts_array(d, n, spread_col)
    bal = START_BALANCE
    eq = np.zeros(n)
    pnls: list[float] = []
    pos = 0
    entry = sl = lots = initial_risk = 0.0
    trade_cost = 0.0
    cool = 0
    be_done = False
    entries_today = 0
    cur_day = -1

    for i in range(n):
        px = close[i]
        floating = bal + ((px - entry) * CONTRACT_SIZE * lots * pos if pos else 0.0)
        eq[i] = floating
        if day_id[i] != cur_day:
            cur_day = int(day_id[i])
            entries_today = 0

        if pos != 0 and i >= 1 and not np.isnan(atr[i]):
            sl, be_done = _apply_be(
                pos, entry, sl, high[i], low[i], initial_risk, be_at_r, be_done
            )
            if pos > 0 and px > entry:
                trail_sl = px - atr[i] * trail_mult
                if trail_sl > sl:
                    sl = trail_sl
            exit_px = None
            if pos > 0 and low[i] <= sl or pos < 0 and high[i] >= sl:
                exit_px = sl
            if exit_px is not None:
                pnl = (exit_px - entry) * CONTRACT_SIZE * lots * pos - trade_cost
                bal += pnl
                pnls.append(pnl)
                pos = 0
                lots = 0.0
                trade_cost = 0.0
                cool = cooldown
                be_done = False
                eq[i] = bal

        if cool > 0:
            cool -= 1
            continue
        if pos != 0 or i < WARMUP:
            continue
        if np.isnan(atr[i]) or atr[i] <= 0 or np.isnan(atr_pc[i]):
            continue
        if atr_pc[i] < atr_min:
            continue
        if i < 1 or np.isnan(donch_hi[i - 1]):
            continue
        if not _hours_ok(int(hour[i]), hours):
            continue
        if entries_today >= int(max_entries_per_day):
            continue
        if h4_bias and (np.isnan(h4b[i]) or h4b[i] < 0.5):
            continue
        if require_ema_stack and not (ema20[i] > ema50[i] > ema100[i]):
            continue
        if not np.isnan(rsi[i]) and rsi[i] >= float(rsi_max):
            continue
        if np.isnan(ema_tr[i]) or close[i] <= ema_tr[i]:
            continue

        long_sig = close[i] > donch_hi[i - 1]
        if mid_channel_k is not None and float(mid_channel_k) > 0 and long_sig:
            mid = 0.5 * (donch_hi[i - 1] + donch_lo[i - 1])
            if abs(close[i] - mid) < float(mid_channel_k) * atr[i]:
                long_sig = False
        if not long_sig:
            continue

        stop_dist_risk = atr[i] * risk_sl_mult
        lots_sz = size_lots(bal, stop_dist_risk, risk_pct, max_lots)
        if lots_sz is None:
            continue
        lots = lots_sz
        trade_cost = _trade_cost(
            spread_pts,
            i,
            lots,
            point_size=point_size,
            commission_per_lot=commission_per_lot,
            slippage_points=slippage_points,
        )
        pos = 1
        entry = px
        sl = entry - atr[i] * init_sl_mult
        initial_risk = atr[i] * init_sl_mult
        be_done = False
        entries_today += 1

    if pos != 0:
        pnl = (close[-1] - entry) * CONTRACT_SIZE * lots * pos - trade_cost
        bal += pnl
        pnls.append(pnl)
        eq[-1] = bal
    return metrics_from_pnls(pnls, eq)


def simulate_htf_fib_enhanced(
    d: pd.DataFrame,
    *,
    pivot_left: int = 5,
    pivot_right: int = 5,
    fib_lo: float = 0.618,
    fib_hi: float = 0.786,
    use_rsi_ma_filter: bool = True,
    rsi_long_max: float = 40.0,
    rsi_short_min: float = 60.0,
    sl_atr: float = 1.5,
    tp_atr: float = 2.5,
    require_ema200_bias: bool = True,
    h4_bias: bool = False,
    flat_only: bool = True,
    max_entries_per_day: int = 2,
    be_at_r: float | None = None,
    hours: tuple[int, ...] | None = None,
    risk_pct: float = 0.01,
    max_lots: float = 0.5,
    cooldown: int = 1,
    long_only: bool = True,
    spread_col: str | None = None,
    point_size: float = 0.01,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    **_extra: Any,
) -> Metrics:
    """Causal HTF fib (c+right stamp) with portable risk filters."""
    df = d.copy()
    times = pd.to_datetime(df["time"], utc=True)
    df = df.set_index(times).sort_index()
    if not df.index.is_unique:
        df = df[~df.index.duplicated(keep="last")]

    close_s = df["close"].astype(float)
    if "rsi_ma" not in df.columns:
        df["rsi_ma"] = df["rsi"].rolling(14).mean()

    h4 = (
        df.resample("4h")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )
    events = confirmed_pivots(
        h4["high"].values, h4["low"].values, int(pivot_left), int(pivot_right)
    )
    h4_times = h4.index.to_list()
    events_ts = [(h4_times[i], price, t) for i, price, t in events if i < len(h4_times)]
    h1_index = df.index
    events_h1 = []
    for ts, price, t in events_ts:
        pos_i = h1_index.searchsorted(ts, side="right") - 1
        if pos_i >= 0:
            events_h1.append((int(pos_i), float(price), int(t)))

    states = walk_swing_and_fibs(events_h1, float(fib_lo), float(fib_hi))
    n = len(df)
    direction, f_a, f_b = expand_fib_states(n, states)

    close = df["close"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    ema200 = df["ema200"].to_numpy(float)
    r = df["rsi"].to_numpy(float)
    rma = df["rsi_ma"].to_numpy(float)
    atr_v = df["atr"].to_numpy(float)
    hour = df["hour"].to_numpy(int) if "hour" in df.columns else np.zeros(n, dtype=int)
    day_id = (
        df["day_id"].to_numpy(int)
        if "day_id" in df.columns
        else pd.Series(df.index).dt.strftime("%Y%m%d").astype(int).to_numpy()
    )
    h4b = df["h4_bull"].to_numpy(float) if "h4_bull" in df.columns else np.ones(n)

    signal = np.zeros(n, dtype=int)
    for i in range(1, n):
        if np.isnan(f_a[i]) or direction[i] == 0 or np.isnan(r[i]):
            continue
        if use_rsi_ma_filter and np.isnan(rma[i]):
            continue
        c = close[i]
        lo_z, hi_z = min(f_a[i], f_b[i]), max(f_a[i], f_b[i])
        if not (lo_z <= c <= hi_z):
            continue
        rsi_long_ok = r[i] <= rsi_long_max
        rsi_short_ok = r[i] >= rsi_short_min
        if use_rsi_ma_filter:
            if not (r[i] > rma[i]):
                rsi_long_ok = False
            if not (r[i] < rma[i]):
                rsi_short_ok = False
        bias_long = (not require_ema200_bias) or (not np.isnan(ema200[i]) and c > ema200[i])
        bias_short = (not require_ema200_bias) or (not np.isnan(ema200[i]) and c < ema200[i])
        if direction[i] == 1 and bias_long and rsi_long_ok:
            c1 = close[i - 1]
            prev_ok = r[i - 1] <= rsi_long_max
            if use_rsi_ma_filter:
                prev_ok = prev_ok and (r[i - 1] > rma[i - 1])
            prev_bias = (not require_ema200_bias) or (
                not np.isnan(ema200[i - 1]) and c1 > ema200[i - 1]
            )
            prev = (
                direction[i] == 1
                and min(f_a[i], f_b[i]) <= c1 <= max(f_a[i], f_b[i])
                and prev_bias
                and prev_ok
            )
            if not prev:
                signal[i] = 1
        elif (not long_only) and direction[i] == -1 and bias_short and rsi_short_ok:
            c1 = close[i - 1]
            prev_ok = r[i - 1] >= rsi_short_min
            if use_rsi_ma_filter:
                prev_ok = prev_ok and (r[i - 1] < rma[i - 1])
            prev_bias = (not require_ema200_bias) or (
                not np.isnan(ema200[i - 1]) and c1 < ema200[i - 1]
            )
            prev = (
                direction[i] == -1
                and min(f_a[i], f_b[i]) <= c1 <= max(f_a[i], f_b[i])
                and prev_bias
                and prev_ok
            )
            if not prev:
                signal[i] = -1

    spread_pts = _spread_pts_array(df, n, spread_col)
    bal = START_BALANCE
    eq = np.zeros(n)
    pnls: list[float] = []
    pos = 0
    entry = sl = tp = lots = initial_risk = 0.0
    trade_cost = 0.0
    cool = 0
    be_done = False
    entries_today = 0
    cur_day = -1
    sl_m = float(sl_atr)
    tp_m = float(tp_atr)

    for i in range(n):
        px = close[i]
        floating = bal + ((px - entry) * CONTRACT_SIZE * lots * pos if pos else 0.0)
        eq[i] = floating
        if day_id[i] != cur_day:
            cur_day = int(day_id[i])
            entries_today = 0

        if pos != 0 and not np.isnan(atr_v[i]):
            sl, be_done = _apply_be(
                pos, entry, sl, high[i], low[i], initial_risk, be_at_r, be_done
            )
            exit_px = None
            if pos > 0:
                if low[i] <= sl:
                    exit_px = sl
                elif high[i] >= tp:
                    exit_px = tp
            else:
                if high[i] >= sl:
                    exit_px = sl
                elif low[i] <= tp:
                    exit_px = tp
            if exit_px is not None:
                pnl = (exit_px - entry) * CONTRACT_SIZE * lots * pos - trade_cost
                bal += pnl
                pnls.append(pnl)
                pos = 0
                lots = 0.0
                trade_cost = 0.0
                cool = cooldown
                be_done = False
                eq[i] = bal

        if cool > 0:
            cool -= 1
            continue
        if i < WARMUP:
            continue
        s = int(signal[i])
        if s == 0 or np.isnan(atr_v[i]) or atr_v[i] <= 0:
            continue
        if not _hours_ok(int(hour[i]), hours):
            continue
        if entries_today >= int(max_entries_per_day):
            continue
        if h4_bias and s > 0 and (np.isnan(h4b[i]) or h4b[i] < 0.5):
            continue
        if long_only and s < 0:
            continue

        if pos != 0:
            if flat_only:
                continue
            if pos == s:
                continue
            pnl = (px - entry) * CONTRACT_SIZE * lots * pos - trade_cost
            bal += pnl
            pnls.append(pnl)
            pos = 0
            lots = 0.0
            trade_cost = 0.0
            eq[i] = bal

        stop_dist = atr_v[i] * sl_m
        lots_sz = size_lots(bal, stop_dist, risk_pct, max_lots)
        if lots_sz is None:
            continue
        lots = lots_sz
        trade_cost = _trade_cost(
            spread_pts,
            i,
            lots,
            point_size=point_size,
            commission_per_lot=commission_per_lot,
            slippage_points=slippage_points,
        )
        if s > 0:
            pos = 1
            entry = px
            sl = entry - stop_dist
            tp = entry + atr_v[i] * tp_m
        else:
            pos = -1
            entry = px
            sl = entry + stop_dist
            tp = entry - atr_v[i] * tp_m
        initial_risk = stop_dist
        be_done = False
        entries_today += 1

    if pos != 0:
        pnl = (close[-1] - entry) * CONTRACT_SIZE * lots * pos - trade_cost
        bal += pnl
        pnls.append(pnl)
        eq[-1] = bal
    return metrics_from_pnls(pnls, eq)


def simulate_htf_pullback(
    d: pd.DataFrame,
    *,
    ema_pull: str = "ema20",
    rsi_lo: float = 40.0,
    rsi_hi: float = 60.0,
    rsi_sell: float = 70.0,
    sl_atr: float = 1.5,
    tp_atr: float = 2.5,
    atr_pctile_lo: float = 0.0,
    atr_pctile_hi: float = 0.85,
    atr_buffer: float = 0.25,
    stack_mode: str = "h4_up",  # h4_up | close_gt_ema200 | ema_stack
    use_fvg_proxy: bool = False,
    fvg_lookback: int = 3,
    h4_bias: bool = True,
    max_entries_per_day: int = 2,
    be_at_r: float | None = 1.0,
    hours: tuple[int, ...] | None = None,
    cooldown: int = 2,
    risk_pct: float = 0.01,
    max_lots: float = 0.5,
    long_only: bool = True,
    spread_col: str | None = None,
    point_size: float = 0.01,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    **_extra: Any,
) -> Metrics:
    """NEW: H4 up + pull to ema20/50 + RSI band + optional FVG-proxy."""
    n = len(d)
    close = d["close"].to_numpy(float)
    high = d["high"].to_numpy(float)
    low = d["low"].to_numpy(float)
    open_ = d["open"].to_numpy(float) if "open" in d.columns else close
    rsi = d["rsi"].to_numpy(float)
    atr = d["atr"].to_numpy(float)
    atr_pc = d["atr_pctile"].to_numpy(float)
    ema20 = d["ema20"].to_numpy(float)
    ema50 = d["ema50"].to_numpy(float)
    ema100 = d["ema100"].to_numpy(float)
    ema200 = d["ema200"].to_numpy(float)
    pull = d[ema_pull].to_numpy(float) if ema_pull in d.columns else ema20
    hour = d["hour"].to_numpy(int)
    day_id = d["day_id"].to_numpy(int)
    h4b = d["h4_bull"].to_numpy(float) if "h4_bull" in d.columns else np.ones(n)

    atr_lo = _pct_unit(atr_pctile_lo) or 0.0
    atr_hi = _pct_unit(atr_pctile_hi) or 1.0

    spread_pts = _spread_pts_array(d, n, spread_col)
    bal = START_BALANCE
    eq = np.zeros(n)
    pnls: list[float] = []
    pos = 0
    entry = sl = tp = lots = initial_risk = 0.0
    trade_cost = 0.0
    cool = 0
    be_done = False
    entries_today = 0
    cur_day = -1

    for i in range(n):
        px = close[i]
        floating = bal + ((px - entry) * CONTRACT_SIZE * lots * pos if pos else 0.0)
        eq[i] = floating
        if day_id[i] != cur_day:
            cur_day = int(day_id[i])
            entries_today = 0

        if pos != 0 and i >= 1 and not np.isnan(atr[i]):
            sl, be_done = _apply_be(
                pos, entry, sl, high[i], low[i], initial_risk, be_at_r, be_done
            )
            exit_px = None
            if pos > 0:
                if low[i] <= sl:
                    exit_px = sl
                elif high[i] >= tp:
                    exit_px = tp
                elif not np.isnan(rsi[i]) and rsi[i] >= rsi_sell:
                    exit_px = px
            if exit_px is not None:
                pnl = (exit_px - entry) * CONTRACT_SIZE * lots * pos - trade_cost
                bal += pnl
                pnls.append(pnl)
                pos = 0
                lots = 0.0
                trade_cost = 0.0
                cool = cooldown
                be_done = False
                eq[i] = bal

        if cool > 0:
            cool -= 1
            continue
        if pos != 0 or i < WARMUP:
            continue
        if np.isnan(atr[i]) or atr[i] <= 0 or np.isnan(atr_pc[i]):
            continue
        if not (atr_lo <= atr_pc[i] <= atr_hi):
            continue
        if not _hours_ok(int(hour[i]), hours):
            continue
        if entries_today >= int(max_entries_per_day):
            continue
        if np.isnan(rsi[i]) or np.isnan(pull[i]):
            continue

        # structure / HTF bias
        if stack_mode == "ema_stack":
            structure = ema20[i] > ema50[i] > ema100[i]
        elif stack_mode == "close_gt_ema200":
            structure = close[i] > ema200[i]
        else:  # h4_up
            structure = (not np.isnan(h4b[i]) and h4b[i] >= 0.5) or close[i] > ema200[i]
        if h4_bias and (np.isnan(h4b[i]) or h4b[i] < 0.5):
            continue
        if not structure:
            continue

        buf = float(atr_buffer) * atr[i]
        touched = low[i] <= pull[i] + buf
        near_ma = low[i] <= ema20[i] + buf or low[i] <= ema50[i] + buf
        recovered = close[i] > pull[i] or close[i] > open_[i]
        rsi_ok = float(rsi_lo) <= rsi[i] <= float(rsi_hi)

        fvg_ok = True
        if use_fvg_proxy and i >= int(fvg_lookback) + 1:
            # FVG-proxy: prior 3-bar bullish impulse (close[i-1] >> open of window)
            # and current bar dips into the impulse body / gap region
            j0 = i - int(fvg_lookback)
            impulse = close[i - 1] - open_[j0]
            gap_low = min(low[j0 : i])  # noqa: E203
            # require impulse of at least 1.0 ATR and touch of impulse zone
            fvg_ok = impulse >= 1.0 * atr[i - 1] and low[i] <= close[i - 1] - 0.25 * atr[i]

        long_sig = (
            (touched or near_ma)
            and recovered
            and close[i] > ema20[i]
            and rsi_ok
            and fvg_ok
        )
        if not long_sig:
            continue

        stop_dist = atr[i] * float(sl_atr)
        lots_sz = size_lots(bal, stop_dist, risk_pct, max_lots)
        if lots_sz is None:
            continue
        lots = lots_sz
        trade_cost = _trade_cost(
            spread_pts,
            i,
            lots,
            point_size=point_size,
            commission_per_lot=commission_per_lot,
            slippage_points=slippage_points,
        )
        pos = 1
        entry = px
        sl = entry - stop_dist
        tp = entry + atr[i] * float(tp_atr)
        initial_risk = stop_dist
        be_done = False
        entries_today += 1

    if pos != 0:
        pnl = (close[-1] - entry) * CONTRACT_SIZE * lots * pos - trade_cost
        bal += pnl
        pnls.append(pnl)
        eq[-1] = bal
    return metrics_from_pnls(pnls, eq)


# ---------------------------------------------------------------------------
# Objectives / soft floors
# ---------------------------------------------------------------------------
def _pf_cap(pf: float, cap: float = 5.0) -> float:
    """Cap infinite/no-loss PF so tiny samples cannot dominate ranking."""
    if pf <= 0 or not np.isfinite(pf):
        return 0.0
    return float(min(pf, cap))


def score_vol_gate(m: Metrics) -> float:
    """maximize min(n,40) subject to PF/WR/DD soft shape; soft penalty if gates fail."""
    n = int(m.n_trades)
    pf = _pf_cap(m.profit_factor, 4.0)
    n_score = min(n, 40)
    # Primary: sample size (target n>=25); PF secondary but capped
    base = n_score * 25.0 + pf * 40.0 + m.win_rate * 0.8 + m.net_profit / 40.0
    if m.profit_factor < 1.3:
        base -= 80.0 * (1.3 - min(m.profit_factor, 1.3))
    if m.win_rate < 55.0 and n >= 5:
        base -= 3.0 * (55.0 - m.win_rate)
    if m.max_drawdown_pct > 8.0:
        base -= 8.0 * (m.max_drawdown_pct - 8.0)
    # Hard soft-penalties for underpowered cells (cannot win on PF=99 n=2)
    if n < 10:
        base -= 200.0
    elif n < 15:
        base -= 120.0
    elif n < 20:
        base -= 60.0
    elif n < 25:
        base -= 20.0
    if n >= 25 and m.profit_factor >= 1.3 and m.win_rate >= 55.0:
        base += 80.0
    if n >= 25 and m.profit_factor >= 1.3:
        base += 40.0
    return float(base)


def score_expectancy_sqrt(m: Metrics, pf_floor: float = 1.3, dd_cap: float = 12.0) -> float:
    n = int(m.n_trades)
    if n < 5:
        return -500.0 + n
    exp = m.net_profit / n
    pf = _pf_cap(m.profit_factor, 5.0)
    s = exp * np.sqrt(n) + pf * 15.0 + m.net_profit / 80.0
    if m.profit_factor < pf_floor:
        s -= 50.0 * (pf_floor - m.profit_factor)
    if m.max_drawdown_pct > dd_cap:
        s -= 10.0 * (m.max_drawdown_pct - dd_cap)
    if n < 15:
        s -= 30.0
    return float(s)


def score_fib(m: Metrics) -> float:
    n = int(m.n_trades)
    pf = _pf_cap(m.profit_factor, 4.0)
    if n == 0:
        return -1000.0
    exp = m.net_profit / n
    s = exp * np.sqrt(n) + pf * 20.0 + m.net_profit / 60.0
    # require develop n>=15 and PF>1.2 after bug fix
    if n < 15:
        s -= 50.0 * (15 - n) / 15.0
        s -= 80.0  # strong underpowered penalty
    if m.profit_factor < 1.2:
        s -= 50.0 * (1.2 - min(m.profit_factor, 1.2))
    if n >= 15 and m.profit_factor >= 1.2:
        s += 100.0
    return float(s)


def score_pullback(m: Metrics) -> float:
    n = int(m.n_trades)
    pf = _pf_cap(m.profit_factor, 4.0)
    n_score = min(n, 40)
    base = n_score * 20.0 + pf * 35.0 + m.win_rate * 0.6 + m.net_profit / 40.0
    if m.profit_factor < 1.3:
        base -= 60.0 * (1.3 - min(m.profit_factor, 1.3))
    if m.win_rate < 50.0 and n >= 5:
        base -= 2.0 * (50.0 - m.win_rate)
    if m.max_drawdown_pct > 10.0:
        base -= 6.0 * (m.max_drawdown_pct - 10.0)
    if n < 10:
        base -= 150.0
    elif n < 15:
        base -= 80.0
    if n >= 25 and m.profit_factor >= 1.3:
        base += 50.0
    return float(base)


def soft_floor_fail(m: Metrics) -> bool:
    """Universal soft floor: PF<1.1 AND n<15 AND NP<=0 → struggling."""
    return m.profit_factor < 1.1 and m.n_trades < 15 and m.net_profit <= 0


# ---------------------------------------------------------------------------
# Search helpers
# ---------------------------------------------------------------------------
def product_grid(axes: dict[str, list], fixed: dict | None = None) -> list[dict]:
    keys = list(axes.keys())
    vals = [axes[k] for k in keys]
    out: list[dict] = []
    for combo in itertools.product(*vals):
        p = dict(fixed or {})
        for k, v in zip(keys, combo):
            p[k] = v
        out.append(p)
    return out


def hours_variants() -> list[tuple[int, ...] | None]:
    return [None, HOURS_LONDON_NY, HOURS_LONDON_NY_LATE]


def run_eval(
    sim: Callable[..., Metrics],
    d: pd.DataFrame,
    params: dict,
    pseudo_slice: slice | None = None,
) -> tuple[Metrics, Metrics | None]:
    m = sim(d, **params)
    m_pv = None
    if pseudo_slice is not None:
        d_pv = d.iloc[pseudo_slice].reset_index(drop=True)
        if len(d_pv) > WARMUP + 50:
            m_pv = sim(d_pv, **params)
    return m, m_pv


def neighborhood_refine(
    best_params: dict,
    axes_local: dict[str, list],
    fixed_keys: set[str] | None = None,
) -> list[dict]:
    """Local grid around best: vary each axis near best value."""
    fixed_keys = fixed_keys or set()
    base = dict(best_params)
    # pick axes present in best
    axes: dict[str, list] = {}
    for k, candidates in axes_local.items():
        if k in fixed_keys:
            continue
        cur = base.get(k)
        if cur is None and None not in candidates:
            # include None variants if in candidates
            near = list(candidates)[:4]
        else:
            # values near cur in list + neighbors
            near = []
            for c in candidates:
                if c == cur:
                    near.append(c)
                elif isinstance(c, (int, float)) and isinstance(cur, (int, float)):
                    if abs(float(c) - float(cur)) <= abs(float(cur)) * 0.35 + 1e-9:
                        near.append(c)
                elif c is cur:
                    near.append(c)
            if cur not in near and cur is not None:
                near.append(cur)
            if not near:
                near = list(candidates)[:3]
        # unique preserve order
        seen = set()
        uniq = []
        for v in near:
            key = str(v)
            if key not in seen:
                seen.add(key)
                uniq.append(v)
        axes[k] = uniq[:4]
    # cap cartesian
    grids = product_grid(axes, {k: v for k, v in base.items() if k not in axes})
    if len(grids) > 120:
        # subsample deterministically
        step = max(1, len(grids) // 100)
        grids = grids[::step][:120]
    # ensure best included
    grids.insert(0, base)
    # dedupe
    seen_p: set[str] = set()
    out = []
    for g in grids:
        key = json.dumps(serializable_params(g), sort_keys=True, default=str)
        if key not in seen_p:
            seen_p.add(key)
            out.append(g)
    return out


def optimize_lane(
    lane_id: str,
    sim: Callable[..., Metrics],
    grid: list[dict],
    score_fn: Callable[[Metrics], float],
    d_dev: pd.DataFrame,
    pseudo_slice: slice,
    budget: int,
    refine_axes: dict[str, list],
) -> dict[str, Any]:
    t0 = time.time()
    # stage 1: full designed grid (or subsample to budget)
    if len(grid) > budget:
        # stratified subsample
        step = max(1, len(grid) // budget)
        grid_use = grid[::step][:budget]
    else:
        grid_use = list(grid)

    n_evals = 0
    best_score = -1e99
    best_params: dict | None = None
    best_m: Metrics | None = None
    best_pv: Metrics | None = None
    history_top: list[dict] = []

    print(f"[{lane_id}] stage1 grid={len(grid_use)} (designed={len(grid)})", flush=True)
    for p in grid_use:
        m, m_pv = run_eval(sim, d_dev, p, pseudo_slice)
        n_evals += 1
        sc = score_fn(m)
        # blend tiny pseudo-val for ranking only (not selection gate)
        if m_pv is not None and m_pv.n_trades >= 3:
            sc = 0.85 * sc + 0.15 * score_fn(m_pv)
        if sc > best_score:
            best_score = sc
            best_params = dict(p)
            best_m = m
            best_pv = m_pv
        if n_evals % 50 == 0:
            bp = best_m.profit_factor if best_m else 0
            bn = best_m.n_trades if best_m else 0
            print(f"  [{lane_id}] evals={n_evals} best_PF={bp:.3f} n={bn} score={best_score:.2f}", flush=True)

    assert best_params is not None and best_m is not None

    # stage 2: neighborhood refine ALWAYS (doctrine: full budget before discard)
    print(f"[{lane_id}] stage2 refine around best...", flush=True)
    refine_grid = neighborhood_refine(best_params, refine_axes)
    for p in refine_grid:
        key = json.dumps(serializable_params(p), sort_keys=True, default=str)
        # skip exact duplicates of already eval'd best path cheaply
        m, m_pv = run_eval(sim, d_dev, p, pseudo_slice)
        n_evals += 1
        sc = score_fn(m)
        if m_pv is not None and m_pv.n_trades >= 3:
            sc = 0.85 * sc + 0.15 * score_fn(m_pv)
        if sc > best_score:
            best_score = sc
            best_params = dict(p)
            best_m = m
            best_pv = m_pv

    # if still short of MIN_EVALS, expand random-ish neighbors from refine_axes
    rng = np.random.default_rng(42 + sum(ord(c) for c in lane_id))
    while n_evals < MIN_EVALS:
        p = dict(best_params)
        for k, cands in refine_axes.items():
            if rng.random() < 0.4 and cands:
                p[k] = cands[int(rng.integers(0, len(cands)))]
        m, m_pv = run_eval(sim, d_dev, p, pseudo_slice)
        n_evals += 1
        sc = score_fn(m)
        if m_pv is not None and m_pv.n_trades >= 3:
            sc = 0.85 * sc + 0.15 * score_fn(m_pv)
        if sc > best_score:
            best_score = sc
            best_params = dict(p)
            best_m = m
            best_pv = m_pv

    struggling = soft_floor_fail(best_m)
    result = {
        "lane_id": lane_id,
        "n_evals": n_evals,
        "best_params": serializable_params(best_params),
        "develop_metrics": metrics_dict(best_m),
        "pseudo_val_metrics": metrics_dict(best_pv) if best_pv else None,
        "develop_score": float(best_score),
        "exhausted": True,
        "kill_candidate": bool(struggling),
        "status": "struggling" if struggling else "viable",
        "seconds": round(time.time() - t0, 2),
    }
    print(
        f"[{lane_id}] DONE n_evals={n_evals} PF={best_m.profit_factor:.3f} "
        f"n={best_m.n_trades} WR={best_m.win_rate:.1f} DD={best_m.max_drawdown_pct:.2f} "
        f"NP={best_m.net_profit:.1f} status={result['status']} ({result['seconds']}s)",
        flush=True,
    )
    return result


# ---------------------------------------------------------------------------
# Grids per lane
# ---------------------------------------------------------------------------
def grid_vol_gate() -> tuple[list[dict], dict[str, list]]:
    axes = {
        "atr_max_pct": [0.35, 0.40, 0.45, 0.50, 0.55, 0.60],
        "rsi_buy": [28.0, 30.0, 32.0, 35.0, 38.0],
        "rsi_sell": [48.0, 50.0, 55.0, 60.0],
        "sl_atr": [1.2, 1.5, 1.8],
        "tp_atr": [2.0, 2.5, 3.0],
        "bb_col": ["bb_lo", "bb_lo15", "bb_lo25"],
        "cooldown": [1, 2, 3],
        "exit_on_vol_spike": [True, False],
        "h4_bias": [False, True],
        "max_entries_per_day": [1, 2],
        "be_at_r": [None, 1.0],
        "hours": hours_variants(),
        "failed_breakout_fade": [False, True],
    }
    # full cartesian is huge; use compact multi-block design ~400–600
    blocks: list[dict] = []
    # block A: core MR expand atr/rsi/bb
    blocks += product_grid(
        {
            "atr_max_pct": [0.35, 0.40, 0.45, 0.50, 0.55],
            "rsi_buy": [28.0, 30.0, 35.0],
            "rsi_sell": [50.0, 55.0],
            "bb_col": ["bb_lo15", "bb_lo"],
            "exit_on_vol_spike": [True, False],
            "cooldown": [1, 2],
            "be_at_r": [None, 1.0],
        },
        {
            "sl_atr": 1.5,
            "tp_atr": 2.5,
            "h4_bias": False,
            "max_entries_per_day": 2,
            "hours": None,
            "failed_breakout_fade": False,
            "require_uptrend": True,
            "trend_col": "ema200",
            "risk_pct": 0.01,
        },
    )  # 5*3*2*2*2*2*2 = 480
    # block B: structure variants hours / h4 / max_entries
    blocks += product_grid(
        {
            "atr_max_pct": [0.40, 0.50],
            "rsi_buy": [30.0, 35.0],
            "hours": hours_variants(),
            "h4_bias": [False, True],
            "max_entries_per_day": [1, 2],
            "be_at_r": [None, 1.0],
            "failed_breakout_fade": [False, True],
            "bb_col": ["bb_lo15", "bb_lo25"],
        },
        {
            "rsi_sell": 50.0,
            "sl_atr": 1.5,
            "tp_atr": 2.5,
            "cooldown": 2,
            "exit_on_vol_spike": True,
            "require_uptrend": True,
            "trend_col": "ema200",
            "risk_pct": 0.01,
        },
    )
    # block C: sl/tp neighborhood
    blocks += product_grid(
        {
            "sl_atr": [1.2, 1.5, 1.8, 2.0],
            "tp_atr": [1.8, 2.0, 2.5, 3.0],
            "atr_max_pct": [0.40, 0.50],
            "rsi_buy": [30.0, 35.0],
            "be_at_r": [None, 1.0],
        },
        {
            "rsi_sell": 50.0,
            "bb_col": "bb_lo15",
            "cooldown": 2,
            "exit_on_vol_spike": True,
            "h4_bias": False,
            "max_entries_per_day": 2,
            "hours": None,
            "failed_breakout_fade": False,
            "require_uptrend": True,
            "trend_col": "ema200",
            "risk_pct": 0.01,
        },
    )
    # dedupe
    seen: set[str] = set()
    grid = []
    for p in blocks:
        k = json.dumps(serializable_params(p), sort_keys=True, default=str)
        if k not in seen:
            seen.add(k)
            grid.append(p)
    return grid, axes


def grid_donchian() -> tuple[list[dict], dict[str, list]]:
    axes = {
        "entry_N": [10, 15, 20, 24, 30, 55],
        "exit_N": [5, 10, 12, 15, 20],
        "atr_sl": [1.5, 2.0, 2.5, 3.0],
        "atr_min_pct": [None, 0.40, 0.50, 0.55],
        "mid_channel_k": [None, 0.5, 1.0, 1.5],
        "h4_bias": [False, True],
        "be_at_r": [None, 1.0],
        "partial_tp": [False, True],
        "hours": hours_variants(),
        "failed_breakout_fade": [False, True],
        "max_entries_per_day": [1, 2],
    }
    blocks: list[dict] = []
    blocks += product_grid(
        {
            "entry_N": [10, 20, 24, 55],
            "exit_N": [5, 10, 15],
            "atr_sl": [1.5, 2.0, 2.5, 3.0],
            "h4_bias": [False, True],
            "mid_channel_k": [None, 0.5, 1.0],
            "be_at_r": [None, 1.0],
            "partial_tp": [False, True],
        },
        {
            "atr_min_pct": None,
            "hours": None,
            "failed_breakout_fade": False,
            "max_entries_per_day": 2,
            "exit_on_exit_channel": True,
            "risk_pct": 0.01,
            "long_only": True,
        },
    )  # 4*3*4*2*3*2*2 = 1152 → will subsample by budget
    blocks += product_grid(
        {
            "entry_N": [20, 55],
            "exit_N": [10, 20],
            "atr_sl": [2.0, 2.5],
            "atr_min_pct": [None, 0.50],
            "hours": hours_variants(),
            "h4_bias": [True],
            "be_at_r": [None, 1.0],
            "partial_tp": [False, True],
            "failed_breakout_fade": [False, True],
            "max_entries_per_day": [1, 2],
            "mid_channel_k": [None, 1.0],
        },
        {
            "exit_on_exit_channel": True,
            "risk_pct": 0.01,
            "long_only": True,
        },
    )
    seen: set[str] = set()
    grid = []
    for p in blocks:
        k = json.dumps(serializable_params(p), sort_keys=True, default=str)
        if k not in seen:
            seen.add(k)
            grid.append(p)
    return grid, axes


def grid_atr_trail() -> tuple[list[dict], dict[str, list]]:
    axes = {
        "entry_N": [10, 15, 20, 24, 30, 55],
        "atr_min_pct": [0.45, 0.55, 0.60, 0.65, 0.70],
        "trail_atr": [1.5, 2.0, 2.5, 3.0, 3.5],
        "sl_atr": [1.5, 2.0, 2.5],
        "h4_bias": [False, True],
        "be_at_r": [None, 1.0],
        "hours": hours_variants(),
        "require_ema_stack": [False, True],
        "rsi_max": [70.0, 75.0, 80.0],
        "mid_channel_k": [None, 0.5, 1.0],
        "max_entries_per_day": [1, 2],
        "ema_trend": ["ema50", "ema100", "ema200"],
    }
    blocks: list[dict] = []
    blocks += product_grid(
        {
            "entry_N": [10, 20, 24, 55],
            "atr_min_pct": [0.50, 0.55, 0.65, 0.70],
            "trail_atr": [2.0, 2.5, 3.0, 3.5],
            "h4_bias": [False, True],
            "be_at_r": [None, 1.0],
            "hours": [None, HOURS_LONDON_NY],
            "require_ema_stack": [False, True],
        },
        {
            "sl_atr": 2.0,
            "rsi_max": 75.0,
            "mid_channel_k": None,
            "max_entries_per_day": 2,
            "ema_trend": "ema100",
            "risk_pct": 0.01,
            "long_only": True,
        },
    )  # 4*4*4*2*2*2*2 = 1024
    blocks += product_grid(
        {
            "entry_N": [20, 30],
            "atr_min_pct": [0.55, 0.65],
            "trail_atr": [2.5, 3.0],
            "sl_atr": [1.5, 2.0, 2.5],
            "h4_bias": [True],
            "be_at_r": [1.0],
            "hours": hours_variants(),
            "mid_channel_k": [None, 1.0],
            "rsi_max": [70.0, 80.0],
            "ema_trend": ["ema50", "ema100"],
            "max_entries_per_day": [1, 2],
        },
        {"require_ema_stack": False, "risk_pct": 0.01, "long_only": True},
    )
    seen: set[str] = set()
    grid = []
    for p in blocks:
        k = json.dumps(serializable_params(p), sort_keys=True, default=str)
        if k not in seen:
            seen.add(k)
            grid.append(p)
    return grid, axes


def grid_htf_fib() -> tuple[list[dict], dict[str, list]]:
    axes = {
        "pivot_left": [3, 5, 8],
        "pivot_right": [3, 5, 8],
        "fib_lo": [0.5, 0.618],
        "fib_hi": [0.786, 0.886],
        "use_rsi_ma_filter": [True, False],
        "rsi_long_max": [35.0, 40.0, 45.0, 50.0],
        "sl_atr": [1.2, 1.5, 2.0, 2.5],
        "tp_atr": [2.0, 2.5, 3.0, 4.0],
        "require_ema200_bias": [True, False],
        "h4_bias": [False, True],
        "be_at_r": [None, 1.0],
        "hours": hours_variants(),
        "max_entries_per_day": [1, 2],
        "cooldown": [0, 1, 2],
    }
    blocks: list[dict] = []
    # After pivot fix: full budget even if prior n=0
    blocks += product_grid(
        {
            "pivot_left": [3, 5],
            "pivot_right": [3, 5],
            "use_rsi_ma_filter": [True, False],
            "rsi_long_max": [35.0, 40.0, 50.0],
            "sl_atr": [1.2, 1.5, 2.0, 2.5],
            "tp_atr": [2.0, 2.5, 3.0, 4.0],
            "require_ema200_bias": [True, False],
            "be_at_r": [None, 1.0],
        },
        {
            "fib_lo": 0.618,
            "fib_hi": 0.786,
            "h4_bias": False,
            "hours": None,
            "max_entries_per_day": 2,
            "cooldown": 1,
            "flat_only": True,
            "long_only": True,
            "risk_pct": 0.01,
        },
    )  # 2*2*2*3*4*4*2*2 = 1536 → subsample
    blocks += product_grid(
        {
            "fib_lo": [0.5, 0.618],
            "fib_hi": [0.786, 0.886],
            "sl_atr": [1.5, 2.0],
            "tp_atr": [2.5, 3.0],
            "use_rsi_ma_filter": [False, True],
            "h4_bias": [False, True],
            "hours": hours_variants(),
            "be_at_r": [None, 1.0],
            "max_entries_per_day": [1, 2],
            "rsi_long_max": [40.0, 50.0],
        },
        {
            "pivot_left": 5,
            "pivot_right": 5,
            "require_ema200_bias": True,
            "cooldown": 1,
            "flat_only": True,
            "long_only": True,
            "risk_pct": 0.01,
        },
    )
    seen: set[str] = set()
    grid = []
    for p in blocks:
        k = json.dumps(serializable_params(p), sort_keys=True, default=str)
        if k not in seen:
            seen.add(k)
            grid.append(p)
    return grid, axes


def grid_htf_pullback() -> tuple[list[dict], dict[str, list]]:
    axes = {
        "ema_pull": ["ema20", "ema50"],
        "rsi_lo": [35.0, 40.0, 45.0],
        "rsi_hi": [55.0, 60.0, 65.0],
        "rsi_sell": [65.0, 70.0, 75.0],
        "sl_atr": [1.2, 1.5, 2.0],
        "tp_atr": [2.0, 2.5, 3.0],
        "atr_pctile_lo": [0.0, 0.20, 0.30],
        "atr_pctile_hi": [0.70, 0.85, 1.0],
        "atr_buffer": [0.0, 0.25, 0.5],
        "stack_mode": ["h4_up", "close_gt_ema200", "ema_stack"],
        "use_fvg_proxy": [False, True],
        "h4_bias": [True, False],
        "be_at_r": [None, 1.0],
        "hours": hours_variants(),
        "max_entries_per_day": [1, 2],
        "cooldown": [1, 2],
    }
    blocks: list[dict] = []
    blocks += product_grid(
        {
            "ema_pull": ["ema20", "ema50"],
            "rsi_lo": [35.0, 40.0, 45.0],
            "rsi_hi": [55.0, 60.0, 65.0],
            "sl_atr": [1.2, 1.5, 2.0],
            "tp_atr": [2.0, 2.5, 3.0],
            "stack_mode": ["h4_up", "close_gt_ema200", "ema_stack"],
            "use_fvg_proxy": [False, True],
            "be_at_r": [None, 1.0],
        },
        {
            "rsi_sell": 70.0,
            "atr_pctile_lo": 0.0,
            "atr_pctile_hi": 0.85,
            "atr_buffer": 0.25,
            "h4_bias": True,
            "hours": None,
            "max_entries_per_day": 2,
            "cooldown": 2,
            "risk_pct": 0.01,
            "long_only": True,
        },
    )  # 2*3*3*3*3*3*2*2 = 1944
    blocks += product_grid(
        {
            "ema_pull": ["ema20", "ema50"],
            "rsi_lo": [40.0, 45.0],
            "rsi_hi": [55.0, 60.0],
            "hours": hours_variants(),
            "h4_bias": [True],
            "be_at_r": [1.0],
            "atr_pctile_lo": [0.0, 0.30],
            "atr_pctile_hi": [0.75, 1.0],
            "atr_buffer": [0.0, 0.5],
            "use_fvg_proxy": [False, True],
            "max_entries_per_day": [1, 2],
            "sl_atr": [1.5],
            "tp_atr": [2.5],
        },
        {
            "rsi_sell": 70.0,
            "stack_mode": "h4_up",
            "cooldown": 2,
            "risk_pct": 0.01,
            "long_only": True,
        },
    )
    seen: set[str] = set()
    grid = []
    for p in blocks:
        k = json.dumps(serializable_params(p), sort_keys=True, default=str)
        if k not in seen:
            seen.add(k)
            grid.append(p)
    return grid, axes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    t_all = time.time()
    print("Loading H1 + indicators ...", flush=True)
    raw = load_h1()
    d_all = prepare_frame(raw)
    times = pd.to_datetime(d_all["time"], utc=True)
    develop = d_all.loc[times < HOLDOUT_START].reset_index(drop=True)
    # NEVER touch holdout for param choice
    holdout_n = int((times >= HOLDOUT_START).sum())
    print(
        f"develop bars={len(develop)} sealed_holdout_bars={holdout_n} (UNUSED)",
        flush=True,
    )

    # pseudo-val = last 20% of develop (ranking only)
    n_dev = len(develop)
    pv_start = int(n_dev * 0.80)
    pseudo_slice = slice(pv_start, n_dev)
    print(f"pseudo-val bars={n_dev - pv_start} (last 20% develop)", flush=True)

    lanes_cfg = [
        {
            "id": "vol_gate_sparse",
            "sim": simulate_vol_gate,
            "grid_fn": grid_vol_gate,
            "score": score_vol_gate,
            "budget": 500,
            "mode": "vol_gate_bb",
        },
        {
            "id": "donchian_turtle",
            "sim": simulate_donchian,
            "grid_fn": grid_donchian,
            "score": score_expectancy_sqrt,
            "budget": 600,
            "mode": "donchian_turtle",
        },
        {
            "id": "atr_trail_breakout",
            "sim": simulate_atr_trail,
            "grid_fn": grid_atr_trail,
            "score": score_expectancy_sqrt,
            "budget": 500,
            "mode": "atr_trail_breakout",
        },
        {
            "id": "htf_fib_xau",
            "sim": simulate_htf_fib_enhanced,
            "grid_fn": grid_htf_fib,
            "score": score_fib,
            "budget": 400,
            "mode": "htf_fib",
        },
        {
            "id": "htf_pullback_new",
            "sim": simulate_htf_pullback,
            "grid_fn": grid_htf_pullback,
            "score": score_pullback,
            "budget": 500,
            "mode": "htf_pullback",
        },
    ]

    lane_results: list[dict] = []
    for lc in lanes_cfg:
        grid, refine_axes = lc["grid_fn"]()
        # attach mode tag for champions
        for p in grid:
            p.setdefault("mode", lc["mode"])
        res = optimize_lane(
            lane_id=lc["id"],
            sim=lc["sim"],
            grid=grid,
            score_fn=lc["score"],
            d_dev=develop,
            pseudo_slice=pseudo_slice,
            budget=int(lc["budget"]),
            refine_axes=refine_axes,
        )
        res["mode"] = lc["mode"]
        res["budget_target"] = lc["budget"]
        res["designed_grid_size"] = len(grid)
        lane_results.append(res)

    # champions: top 1 per lane + top 2 overall by develop_score
    per_lane = []
    for r in lane_results:
        per_lane.append(
            {
                "lane_id": r["lane_id"],
                "mode": r["mode"],
                "params": r["best_params"],
                "develop_metrics": r["develop_metrics"],
                "develop_score": r["develop_score"],
                "pseudo_val_metrics": r["pseudo_val_metrics"],
                "status": r["status"],
                "n_evals": r["n_evals"],
            }
        )
    overall_sorted = sorted(per_lane, key=lambda x: x["develop_score"], reverse=True)
    top2 = overall_sorted[:2]

    deep_out = {
        "meta": {
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "develop_end": "2025-12-31",
            "holdout_start": "2026-01-01",
            "holdout_used": False,
            "safety": "offline research only; never --live",
            "doctrine": "never discard lane until develop opt budget exhausted",
            "develop_bars": len(develop),
            "pseudo_val_frac": 0.20,
            "total_seconds": round(time.time() - t_all, 2),
        },
        "lanes": lane_results,
    }
    OUT_DEEP.parent.mkdir(parents=True, exist_ok=True)
    OUT_DEEP.write_text(json.dumps(deep_out, indent=2, default=str))
    print(f"Wrote {OUT_DEEP}", flush=True)

    champ_out = {
        "meta": {
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "holdout_numbers": "NONE — sealed until promote pass",
            "selection_window": "develop only",
            "note": "top 1 per lane + top 2 overall by develop objective",
        },
        "per_lane_champions": per_lane,
        "top2_overall": top2,
    }
    OUT_CHAMP.write_text(json.dumps(champ_out, indent=2, default=str))
    print(f"Wrote {OUT_CHAMP}", flush=True)

    all_exhausted = all(r["exhausted"] for r in lane_results)
    summary_bits = []
    for r in lane_results:
        m = r["develop_metrics"]
        summary_bits.append(
            f"{r['lane_id']}: PF={m['profit_factor']:.3f} n={m['n_trades']} "
            f"WR={m['win_rate']:.1f} NP={m['net_profit']:.0f} status={r['status']}"
        )
    print("SUMMARY:", " | ".join(summary_bits), flush=True)
    print(f"all_exhausted={all_exhausted} total_s={time.time() - t_all:.1f}", flush=True)
    return 0 if all_exhausted else 1


if __name__ == "__main__":
    raise SystemExit(main())
