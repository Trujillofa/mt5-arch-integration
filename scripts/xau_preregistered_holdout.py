#!/usr/bin/env python3
"""Single-pass holdout evaluation of pre-registered XAU configs.

Loads results/xau_preregistered_registry.json, runs ONLY those configs on
develop (diagnostic) and holdout (promotion) windows. Never expands a grid
and never re-picks configs from holdout results.

Families:
  - vol_gate_bb       (reuse simulate_design)
  - donchian_turtle
  - htf_fib           (H4 pivots from H1 aggregate, risk-sized lots)
  - atr_trail_breakout

SAFETY: offline research only — no --live, no order placement.

Writes: results/xau_preregistered_holdout_eval.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

# Causal HTF Fib pivot/fib math (shared; stamp at c+right)
from htf_fib_core import (  # noqa: E402
    confirmed_pivots,
    expand_fib_states,
    walk_swing_and_fibs,
)
from xau_new_design_search import (  # noqa: E402
    WARMUP,
    extend_indicators,
    metrics_dict,
    simulate_design,
)

from backtest import (  # noqa: E402
    CONTRACT_SIZE,
    START_BALANCE,
    Metrics,
    load_h1,
    metrics_from_pnls,
)

REGISTRY_PATH = ROOT / "results" / "xau_preregistered_registry.json"
OUT_PATH = ROOT / "results" / "xau_preregistered_holdout_eval.json"


def _pct_to_unit(x: float | None) -> float | None:
    if x is None:
        return None
    v = float(x)
    if v > 1.0:
        return v / 100.0
    return v


def hard_pass(m: Metrics, gates: dict[str, float | int]) -> bool:
    """Protocol hard_gates on a metrics object."""
    pf_min = float(gates.get("profit_factor", 1.5))
    wr_min = float(gates.get("win_rate", 55.0))
    dd_max = float(gates.get("max_drawdown_pct", 10.0))
    n_min = int(gates.get("n_trades", 20))
    return (
        m.n_trades >= n_min
        and m.profit_factor > pf_min
        and m.win_rate > wr_min
        and m.max_drawdown_pct < dd_max
    )


def size_lots(
    bal: float,
    stop_dist: float,
    risk_pct: float,
    max_lots: float = 0.5,
) -> float | None:
    """Risk-sized lot size matching backtest.py / simulate_design."""
    if stop_dist <= 1e-9:
        return None
    risk_cash = bal * risk_pct
    raw = risk_cash / (stop_dist * CONTRACT_SIZE)
    lots = float(np.floor(raw * 100 + 1e-12) / 100.0)
    lots = min(lots, max_lots)
    min_lot = 0.01
    min_lot_risk = stop_dist * CONTRACT_SIZE * min_lot
    if lots < min_lot or min_lot_risk > risk_cash + 1e-9:
        return None
    return lots


# ---------------------------------------------------------------------------
# Donchian turtle
# ---------------------------------------------------------------------------
def simulate_donchian_turtle(
    d: pd.DataFrame,
    *,
    entry_N: int = 20,
    exit_N: int = 10,
    atr_sl: float = 2.0,
    atr_tp: float | None = None,
    exit_on_exit_channel: bool = True,
    atr_min_pct: float | None = None,
    trend_filter: bool = False,
    trend_col: str = "ema200",
    long_only: bool = True,
    cooldown: int = 2,
    risk_pct: float = 0.01,
    max_lots: float = 0.5,
    **_extra: Any,
) -> Metrics:
    """Enter long on close > prior donch_hi(entry_N); exit channel or ATR stop."""
    n = len(d)
    close = d["close"].to_numpy(float)
    high = d["high"].to_numpy(float)
    low = d["low"].to_numpy(float)
    atr = d["atr"].to_numpy(float)
    atr_pc = d["atr_pctile"].to_numpy(float) if "atr_pctile" in d.columns else np.full(n, 0.5)

    e_hi_key = f"donch_hi_{int(entry_N)}"
    x_lo_key = f"donch_lo_{int(exit_N)}"
    if e_hi_key in d.columns:
        donch_hi = d[e_hi_key].to_numpy(float)
    else:
        donch_hi = high.astype(float)
        # rolling max of prior window rebuilt
        s = pd.Series(high).rolling(int(entry_N), min_periods=int(entry_N)).max().to_numpy(float)
        donch_hi = s
    if x_lo_key in d.columns:
        donch_lo = d[x_lo_key].to_numpy(float)
    else:
        donch_lo = pd.Series(low).rolling(int(exit_N), min_periods=int(exit_N)).min().to_numpy(float)

    trend = (
        d[trend_col].to_numpy(float)
        if trend_col in d.columns
        else d["ema200"].to_numpy(float)
    )
    atr_min = _pct_to_unit(atr_min_pct)

    bal = START_BALANCE
    eq = np.zeros(n)
    pnls: list[float] = []
    pos = 0
    entry = sl = lots = 0.0
    tp = np.inf  # unused if atr_tp is None
    cool = 0
    use_tp = atr_tp is not None and float(atr_tp) > 0
    tp_mult = float(atr_tp) if use_tp else 0.0

    for i in range(n):
        px = close[i]
        floating = bal + ((px - entry) * CONTRACT_SIZE * lots * pos if pos else 0.0)
        eq[i] = floating

        if pos != 0 and i >= 1 and not np.isnan(atr[i]):
            exit_px = None
            if pos > 0:
                if low[i] <= sl:
                    exit_px = sl
                elif use_tp and high[i] >= tp:
                    exit_px = tp
                elif (
                    exit_on_exit_channel
                    and i >= 1
                    and not np.isnan(donch_lo[i - 1])
                    and close[i] < donch_lo[i - 1]
                ):
                    exit_px = px
            else:
                if high[i] >= sl:
                    exit_px = sl
                elif use_tp and low[i] <= tp:
                    exit_px = tp
                elif (
                    exit_on_exit_channel
                    and i >= 1
                    and not np.isnan(donch_hi[i - 1])
                    and close[i] > donch_hi[i - 1]
                ):
                    exit_px = px

            if exit_px is not None:
                pnl = (exit_px - entry) * CONTRACT_SIZE * lots * pos
                bal += pnl
                pnls.append(pnl)
                pos = 0
                lots = 0.0
                cool = cooldown
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
        if atr_min is not None:
            if np.isnan(atr_pc[i]) or atr_pc[i] < atr_min:
                continue
        if trend_filter and (np.isnan(trend[i]) or close[i] <= trend[i]):
            continue

        long_sig = close[i] > donch_hi[i - 1]
        short_sig = False
        if not long_only:
            # short on close < prior donch_lo(entry_N)
            e_lo_key = f"donch_lo_{int(entry_N)}"
            if e_lo_key in d.columns:
                e_lo = d[e_lo_key].to_numpy(float)[i - 1]
            else:
                e_lo = np.nan
            short_sig = not np.isnan(e_lo) and close[i] < e_lo
            if trend_filter and close[i] >= trend[i]:
                short_sig = False

        if long_only:
            short_sig = False
        if not long_sig and not short_sig:
            continue

        stop_dist = atr[i] * float(atr_sl)
        lots_sz = size_lots(bal, stop_dist, risk_pct, max_lots)
        if lots_sz is None:
            continue
        lots = lots_sz

        if long_sig:
            pos = 1
            entry = px
            sl = entry - stop_dist
            tp = entry + atr[i] * tp_mult if use_tp else np.inf
        else:
            pos = -1
            entry = px
            sl = entry + stop_dist
            tp = entry - atr[i] * tp_mult if use_tp else -np.inf

    if pos != 0:
        pnl = (close[-1] - entry) * CONTRACT_SIZE * lots * pos
        bal += pnl
        pnls.append(pnl)
        eq[-1] = bal

    return metrics_from_pnls(pnls, eq)


# ---------------------------------------------------------------------------
# ATR trail breakout
# ---------------------------------------------------------------------------
def simulate_atr_trail_breakout(
    d: pd.DataFrame,
    *,
    entry_N: int = 20,
    donch_n: int | None = None,
    atr_min_pct: float = 0.55,
    trail_atr: float = 2.5,
    sl_atr: float = 2.0,
    tp_atr: float | None = None,
    use_fixed_tp: bool = False,
    ema_trend: str = "ema100",
    require_uptrend: bool = True,
    long_only: bool = True,
    cooldown: int = 2,
    risk_pct: float = 0.01,
    max_lots: float = 0.5,
    **_extra: Any,
) -> Metrics:
    """Donch breakout; initial SL from sl_atr; trail up by trail_atr; no fixed TP."""
    n = len(d)
    close = d["close"].to_numpy(float)
    high = d["high"].to_numpy(float)
    low = d["low"].to_numpy(float)
    atr = d["atr"].to_numpy(float)
    atr_pc = d["atr_pctile"].to_numpy(float)
    dn = int(donch_n if donch_n is not None else entry_N)
    dn_key = f"donch_hi_{dn}"
    if dn_key in d.columns:
        donch_hi = d[dn_key].to_numpy(float)
    else:
        donch_hi = pd.Series(high).rolling(dn, min_periods=dn).max().to_numpy(float)

    ema_tr = (
        d[ema_trend].to_numpy(float)
        if ema_trend in d.columns
        else d["ema100"].to_numpy(float)
    )
    atr_min = _pct_to_unit(atr_min_pct) or 0.0
    trail_mult = float(trail_atr)
    # Initial SL distance: prefer sl_atr for risk; trail uses trail_atr.
    # Spec also allows initial SL = entry - trail_atr*ATR; use max for safety
    # of risk sizing vs trail start: initial stop = entry - trail_atr * ATR
    # when trail_atr provided, else sl_atr.
    init_sl_mult = float(trail_atr) if trail_atr and float(trail_atr) > 0 else float(sl_atr)
    risk_sl_mult = float(sl_atr) if sl_atr and float(sl_atr) > 0 else init_sl_mult
    use_tp = bool(use_fixed_tp) and tp_atr is not None and float(tp_atr) > 0
    tp_mult = float(tp_atr) if use_tp else 0.0

    bal = START_BALANCE
    eq = np.zeros(n)
    pnls: list[float] = []
    pos = 0
    entry = sl = lots = 0.0
    tp = np.inf
    cool = 0

    for i in range(n):
        px = close[i]
        floating = bal + ((px - entry) * CONTRACT_SIZE * lots * pos if pos else 0.0)
        eq[i] = floating

        if pos != 0 and i >= 1 and not np.isnan(atr[i]):
            # trail stop up on favorable closes (long)
            if pos > 0 and px > entry:
                trail_sl = px - atr[i] * trail_mult
                if trail_sl > sl:
                    sl = trail_sl
            elif pos < 0 and px < entry:
                trail_sl = px + atr[i] * trail_mult
                if trail_sl < sl:
                    sl = trail_sl

            exit_px = None
            if pos > 0:
                if low[i] <= sl:
                    exit_px = sl
                elif use_tp and high[i] >= tp:
                    exit_px = tp
            else:
                if high[i] >= sl:
                    exit_px = sl
                elif use_tp and low[i] <= tp:
                    exit_px = tp

            if exit_px is not None:
                pnl = (exit_px - entry) * CONTRACT_SIZE * lots * pos
                bal += pnl
                pnls.append(pnl)
                pos = 0
                lots = 0.0
                cool = cooldown
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
        if require_uptrend and (np.isnan(ema_tr[i]) or close[i] <= ema_tr[i]):
            continue

        long_sig = close[i] > donch_hi[i - 1]
        if not long_sig:
            continue
        if long_only is False:
            pass  # long-only family by design; shorts not used

        # Risk size on risk_sl_mult; initial stop at trail mult
        stop_dist_risk = atr[i] * risk_sl_mult
        lots_sz = size_lots(bal, stop_dist_risk, risk_pct, max_lots)
        if lots_sz is None:
            continue
        lots = lots_sz
        pos = 1
        entry = px
        sl = entry - atr[i] * init_sl_mult
        tp = entry + atr[i] * tp_mult if use_tp else np.inf

    if pos != 0:
        pnl = (close[-1] - entry) * CONTRACT_SIZE * lots * pos
        bal += pnl
        pnls.append(pnl)
        eq[-1] = bal

    return metrics_from_pnls(pnls, eq)


# ---------------------------------------------------------------------------
# HTF Fib (H4 pivots on XAU H1), risk-sized lots
# ---------------------------------------------------------------------------
# Pivot confirmation: see htf_fib_core.confirmed_pivots (active at c+right).


def simulate_htf_fib(
    d: pd.DataFrame,
    *,
    pivot_left: int = 5,
    pivot_right: int = 5,
    fib_lo: float = 0.618,
    fib_hi: float = 0.786,
    use_rsi_ma_filter: bool = True,
    rsi_long_max: float = 35.0,
    rsi_short_min: float = 65.0,
    sl_atr: float = 1.5,
    tp_atr: float = 2.0,
    require_ema200_bias: bool = True,
    flat_only: bool = True,
    risk_pct: float = 0.01,
    max_lots: float = 0.5,
    cooldown: int = 0,
    **_extra: Any,
) -> Metrics:
    """Port of htf_fib_offline_backtest core onto XAU H1 with risk-sized lots."""
    df = d.copy()
    if "time" not in df.columns:
        raise ValueError("htf_fib requires a time column")
    times = pd.to_datetime(df["time"], utc=True)
    df = df.set_index(times).sort_index()
    # Ensure unique index for resample
    if not df.index.is_unique:
        df = df[~df.index.duplicated(keep="last")]

    close_s = df["close"].astype(float)
    if "rsi" not in df.columns:
        delta = close_s.diff()
        up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        dn = (-delta).clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        df["rsi"] = 100 - (100 / (1 + up / dn.replace(0, np.nan)))
    if "rsi_ma" not in df.columns:
        df["rsi_ma"] = df["rsi"].rolling(14).mean()
    if "ema200" not in df.columns:
        df["ema200"] = close_s.ewm(span=200, adjust=False).mean()
    if "atr" not in df.columns:
        prev = close_s.shift(1)
        tr = pd.concat(
            [
                df["high"].astype(float) - df["low"].astype(float),
                (df["high"].astype(float) - prev).abs(),
                (df["low"].astype(float) - prev).abs(),
            ],
            axis=1,
        ).max(axis=1)
        df["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()

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
        pos = h1_index.searchsorted(ts, side="right") - 1
        if pos >= 0:
            events_h1.append((int(pos), float(price), int(t)))

    # walk swings with custom fib ratios (event idx already = confirmation bar)
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
        elif direction[i] == -1 and bias_short and rsi_short_ok:
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

    bal = START_BALANCE
    eq = np.zeros(n)
    pnls: list[float] = []
    pos = 0
    entry = sl = tp = lots = 0.0
    cool = 0
    sl_m = float(sl_atr)
    tp_m = float(tp_atr)

    for i in range(n):
        px = close[i]
        floating = bal + ((px - entry) * CONTRACT_SIZE * lots * pos if pos else 0.0)
        eq[i] = floating

        if pos != 0 and not np.isnan(atr_v[i]):
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
                pnl = (exit_px - entry) * CONTRACT_SIZE * lots * pos
                bal += pnl
                pnls.append(pnl)
                pos = 0
                lots = 0.0
                cool = cooldown
                eq[i] = bal

        if cool > 0:
            cool -= 1
            continue
        if i < WARMUP:
            continue
        s = int(signal[i])
        if s == 0 or np.isnan(atr_v[i]) or atr_v[i] <= 0:
            continue

        if pos != 0:
            if flat_only:
                continue  # wait for exit; no reverse
            if pos == s:
                continue
            # reverse
            pnl = (px - entry) * CONTRACT_SIZE * lots * pos
            bal += pnl
            pnls.append(pnl)
            pos = 0
            lots = 0.0
            eq[i] = bal

        stop_dist = atr_v[i] * sl_m
        lots_sz = size_lots(bal, stop_dist, risk_pct, max_lots)
        if lots_sz is None:
            continue
        lots = lots_sz
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

    if pos != 0:
        pnl = (close[-1] - entry) * CONTRACT_SIZE * lots * pos
        bal += pnl
        pnls.append(pnl)
        eq[-1] = bal

    return metrics_from_pnls(pnls, eq)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
def run_config(d: pd.DataFrame, params: dict[str, Any]) -> Metrics:
    mode = params.get("mode", "")
    p = dict(params)
    # strip non-simulator keys
    for k in ("symbol", "timeframe", "htf", "family", "id", "rationale"):
        p.pop(k, None)

    if mode == "vol_gate_bb":
        # simulate_design ignores unknown kwargs? No — pass only known
        known = {
            "mode",
            "risk_pct",
            "max_lots",
            "cooldown",
            "long_only",
            "atr_max_pct",
            "rsi_buy",
            "rsi_sell",
            "sl_atr",
            "tp_atr",
            "bb_col",
            "trend_col",
            "require_uptrend",
            "use_macd_filter",
            "exit_on_vol_spike",
            "atr_min_pct",
            "donch_n",
            "ema_trend",
            "rsi_max",
            "trail_atr",
            "require_ema_stack",
            "hours",
        }
        kwargs = {k: v for k, v in p.items() if k in known}
        return simulate_design(d, **kwargs)

    if mode == "donchian_turtle":
        return simulate_donchian_turtle(d, **p)

    if mode == "htf_fib":
        return simulate_htf_fib(d, **p)

    if mode == "atr_trail_breakout":
        return simulate_atr_trail_breakout(d, **p)

    raise ValueError(f"Unknown mode: {mode!r}")


def bar_range(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {"start": None, "end": None, "n_bars": 0}
    t0 = pd.to_datetime(df["time"].iloc[0], utc=True)
    t1 = pd.to_datetime(df["time"].iloc[-1], utc=True)
    return {"start": str(t0), "end": str(t1), "n_bars": int(len(df))}


def main() -> int:
    t0 = time.time()
    if not REGISTRY_PATH.is_file():
        print(f"ERROR: registry missing: {REGISTRY_PATH}", file=sys.stderr)
        return 1

    reg = json.loads(REGISTRY_PATH.read_text())
    protocol = reg.get("protocol", {})
    hard_gates = protocol.get(
        "hard_gates",
        {
            "profit_factor": 1.5,
            "win_rate": 55.0,
            "max_drawdown_pct": 10.0,
            "n_trades": 20,
        },
    )
    holdout_start = pd.Timestamp(protocol["holdout_start"])
    if holdout_start.tzinfo is None:
        holdout_start = holdout_start.tz_localize("UTC")
    else:
        holdout_start = holdout_start.tz_convert("UTC")

    print(f"Loading H1 from {ROOT / 'xauusd_data.csv'} ...")
    raw = load_h1()
    d_all = extend_indicators(raw)
    times = pd.to_datetime(d_all["time"], utc=True)

    develop = d_all.loc[times < holdout_start].reset_index(drop=True)
    holdout = d_all.loc[times >= holdout_start].reset_index(drop=True)
    print(
        f"develop bars={len(develop)} holdout bars={len(holdout)} "
        f"holdout_start={holdout_start}"
    )
    if holdout.empty:
        print("ERROR: empty holdout window", file=sys.stderr)
        return 1

    n_min = int(hard_gates.get("n_trades", 20))
    results: list[dict[str, Any]] = []
    n_hard = n_under = n_fail = 0

    families = reg.get("families", [])
    for fam in families:
        fam_id = fam.get("id", "")
        for cfg in fam.get("configs", []):
            cfg_id = cfg["id"]
            params = dict(cfg.get("params", {}))
            print(f"  eval {cfg_id} ({params.get('mode')}) ...", flush=True)

            m_dev = run_config(develop, params)
            m_ho = run_config(holdout, params)

            underpowered = m_ho.n_trades < n_min
            hp = bool(hard_pass(m_ho, hard_gates)) and not underpowered
            # If underpowered, never hard_pass (protocol soft note)
            if underpowered:
                status = "underpowered"
                n_under += 1
                hp = False
            elif hp:
                status = "hard_pass"
                n_hard += 1
            else:
                status = "fail"
                n_fail += 1

            results.append(
                {
                    "id": cfg_id,
                    "family": cfg.get("family", fam_id),
                    "mode": params.get("mode"),
                    "params": params,
                    "rationale": cfg.get("rationale"),
                    "develop": metrics_dict(m_dev),
                    "holdout": metrics_dict(m_ho),
                    "hard_pass_holdout": hp,
                    "underpowered": underpowered,
                    "status": status,
                }
            )

    summary = {
        "n_configs": len(results),
        "hard_pass": n_hard,
        "underpowered": n_under,
        "fail": n_fail,
        "hard_gates": hard_gates,
    }

    out = {
        "protocol": {
            "holdout_start": str(holdout_start),
            "develop_end": protocol.get("develop_end"),
            "hard_gates": hard_gates,
            "holdout_rule": protocol.get("holdout_rule"),
            "primary_metric_window": protocol.get("primary_metric_window"),
            "selection_policy": "single-pass pre-registered only; no grid; no holdout re-pick",
        },
        "data": {
            "csv": "xauusd_data.csv",
            "all": bar_range(d_all),
            "develop": bar_range(develop),
            "holdout": bar_range(holdout),
        },
        "summary": summary,
        "configs": results,
        "meta": {
            "script": "scripts/xau_preregistered_holdout.py",
            "registry": str(REGISTRY_PATH.relative_to(ROOT)),
            "elapsed_sec": round(time.time() - t0, 2),
            "safety": "offline research only; never --live",
        },
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2) + "\n")
    print(f"\nwrote {OUT_PATH}")
    print(
        f"summary: n={summary['n_configs']} hard_pass={n_hard} "
        f"underpowered={n_under} fail={n_fail} "
        f"elapsed={out['meta']['elapsed_sec']}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
