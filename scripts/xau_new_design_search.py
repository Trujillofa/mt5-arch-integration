#!/usr/bin/env python3
"""New XAU design family search (train-only grid; frozen OOS once).

Modes: vol_gate_bb, atr_breakout, ema_pullback, dual_regime.
Does NOT overwrite strategy_params.json. Offline only — no --live.

Writes: results/xau_new_design_search.json
"""
from __future__ import annotations

import itertools
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest import (  # noqa: E402
    CONTRACT_SIZE,
    START_BALANCE,
    Metrics,
    indicators,
    load_h1,
    metrics_from_pnls,
    passes,
)

SPECS_PATH = ROOT / "results" / "xau_new_design_specs.json"
HOLDOUT_PATH = ROOT / "results" / "xau_oos_holdout.json"
OUT_PATH = ROOT / "results" / "xau_new_design_search.json"

# Cap total train evals for runtime budget (~<3 min)
MAX_EVALS = 3800
WARMUP = 220

# Map design-spec family ids → simulate_design modes
FAMILY_MODE = {
    "vol_gate_meanrev": "vol_gate_bb",
    "vol_gate_bb": "vol_gate_bb",
    "atr_breakout_trend": "atr_breakout",
    "atr_breakout": "atr_breakout",
    "ema_pullback_trend": "ema_pullback",
    "ema_pullback": "ema_pullback",
    "dual_regime_switch": "dual_regime",
    "dual_regime": "dual_regime",
}

CORE_FAMILIES = (
    "vol_gate_bb",
    "atr_breakout",
    "ema_pullback",
    "dual_regime",
)


def metrics_dict(m: Metrics) -> dict[str, float | int]:
    return {
        "net_profit": float(m.net_profit),
        "win_rate": float(m.win_rate),
        "profit_factor": float(m.profit_factor),
        "max_drawdown_pct": float(m.max_drawdown_pct),
        "n_trades": int(m.n_trades),
        "wins": int(m.wins),
        "losses": int(m.losses),
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
            out[k] = v
    return out


def _pct_to_unit(x: float) -> float:
    """Normalize atr_pctile thresholds: specs use 0–100, modes use 0–1."""
    v = float(x)
    if v > 1.0:
        return v / 100.0
    return v


def extend_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Base indicators + atr_pctile (rolling-100 rank 0–1) + Donchian 20/55 (+10/24)."""
    d = indicators(df)
    atr = d["atr"].astype(float)

    def _rank_last(arr: np.ndarray) -> float:
        if len(arr) < 2 or np.isnan(arr[-1]):
            return np.nan
        # inclusive percentile of last value within window, scale 0–1
        return float(np.sum(arr <= arr[-1]) - 1) / float(max(len(arr) - 1, 1))

    d["atr_pctile"] = atr.rolling(100, min_periods=30).apply(_rank_last, raw=True)

    high = d["high"].astype(float)
    low = d["low"].astype(float)
    for n in (10, 20, 24, 30, 55):
        d[f"donch_hi_{n}"] = high.rolling(n, min_periods=n).max()
        d[f"donch_lo_{n}"] = low.rolling(n, min_periods=n).min()
    # aliases for default N=20
    d["donch_hi"] = d["donch_hi_20"]
    d["donch_lo"] = d["donch_lo_20"]
    return d


def simulate_design(
    d: pd.DataFrame,
    *,
    mode: str = "vol_gate_bb",
    # shared risk / execution
    risk_pct: float = 0.01,
    max_lots: float = 0.5,
    cooldown: int = 2,
    long_only: bool = True,
    # vol_gate_bb / dual mean-rev
    atr_max_pct: float = 0.55,
    rsi_buy: float = 30.0,
    rsi_sell: float = 55.0,
    sl_atr: float = 1.5,
    tp_atr: float = 2.0,
    bb_col: str = "bb_lo",
    trend_col: str = "ema200",
    require_uptrend: bool = True,
    use_macd_filter: bool = False,
    exit_on_vol_spike: bool = False,
    # atr_breakout / dual breakout
    atr_min_pct: float = 0.60,
    donch_n: int = 20,
    ema_trend: str = "ema50",
    rsi_max: float = 75.0,
    trail_atr: float | None = None,
    require_ema_stack: bool = False,
    # ema_pullback
    ema_pull: str = "ema20",
    rsi_lo: float = 40.0,
    rsi_hi: float = 60.0,
    atr_pctile_lo: float = 0.0,
    atr_pctile_hi: float = 1.0,
    atr_buffer: float = 0.0,
    use_macd_rising: bool = False,
    stack_mode: str = "close_gt_ema200",
    # dual_regime
    switch_pct: float = 0.65,
    sl_atr_bo: float = 2.0,
    tp_atr_bo: float = 3.0,
    sl_atr_mr: float = 1.5,
    tp_atr_mr: float = 2.0,
    deadband: float = 0.0,
    hours: tuple[int, ...] | None = None,
) -> Metrics:
    """Bar-loop simulator for new design families (long-biased, risk-sized)."""
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
    macd_h = d["macd_hist"].to_numpy(float)
    hour = d["hour"].to_numpy(int)
    ema20 = d["ema20"].to_numpy(float)
    ema50 = d["ema50"].to_numpy(float)
    ema100 = d["ema100"].to_numpy(float)
    ema200 = d["ema200"].to_numpy(float)

    bb_lo = d[bb_col].to_numpy(float) if bb_col in d.columns else d["bb_lo"].to_numpy(float)
    trend = d[trend_col].to_numpy(float) if trend_col in d.columns else ema200
    ema_tr = d[ema_trend].to_numpy(float) if ema_trend in d.columns else ema50
    pull = d[ema_pull].to_numpy(float) if ema_pull in d.columns else ema20

    dn_key = f"donch_hi_{int(donch_n)}"
    if dn_key in d.columns:
        donch_hi = d[dn_key].to_numpy(float)
    else:
        donch_hi = d["high"].astype(float).rolling(int(donch_n), min_periods=int(donch_n)).max().to_numpy(float)

    atr_max = _pct_to_unit(atr_max_pct)
    atr_min = _pct_to_unit(atr_min_pct)
    atr_lo = _pct_to_unit(atr_pctile_lo)
    atr_hi = _pct_to_unit(atr_pctile_hi)
    sw = _pct_to_unit(switch_pct)
    db = _pct_to_unit(deadband) if deadband else 0.0

    bal = START_BALANCE
    eq = np.zeros(n)
    pnls: list[float] = []
    pos = 0
    entry = sl = tp = lots = 0.0
    cool = 0
    entry_mode = ""  # "bo" | "mr" for dual exits
    use_trail = trail_atr is not None and float(trail_atr) > 0
    trail_mult = float(trail_atr) if use_trail else 0.0

    for i in range(n):
        px = close[i]
        floating = bal + ((px - entry) * CONTRACT_SIZE * lots * pos if pos else 0.0)
        eq[i] = floating

        if pos != 0 and i >= 1 and not np.isnan(atr[i]):
            # optional trail for breakout: ratchet SL up once in profit
            if use_trail and pos > 0 and px > entry:
                trail_sl = px - atr[i] * trail_mult
                if trail_sl > sl:
                    sl = trail_sl

            exit_px = None
            soft_sell = rsi_sell
            if entry_mode == "bo":
                # breakout soft: close under ema20
                if not np.isnan(ema20[i]) and close[i] < ema20[i]:
                    exit_px = px
            elif entry_mode == "mr" or mode in ("vol_gate_bb", "ema_pullback"):
                if not np.isnan(rsi[i]) and rsi[i] >= soft_sell:
                    exit_px = px
            else:
                if not np.isnan(rsi[i]) and rsi[i] >= soft_sell:
                    exit_px = px

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

            # vol spike flatten for mean-rev
            if (
                exit_px is None
                and exit_on_vol_spike
                and entry_mode in ("mr", "")
                and mode in ("vol_gate_bb", "dual_regime")
                and not np.isnan(atr_pc[i])
                and atr_pc[i] > atr_max
            ):
                exit_px = px

            if exit_px is not None:
                pnl = (exit_px - entry) * CONTRACT_SIZE * lots * pos
                bal += pnl
                pnls.append(pnl)
                pos = 0
                lots = 0.0
                cool = cooldown
                entry_mode = ""
                eq[i] = bal

        if cool > 0:
            cool -= 1
            continue
        if pos != 0 or i < WARMUP:
            continue
        if np.isnan(atr[i]) or atr[i] <= 0:
            continue
        if np.isnan(atr_pc[i]):
            continue
        if hours is not None and hour[i] not in hours:
            continue

        long_sig = False
        short_sig = False
        this_mode = mode
        sl_m = sl_atr
        tp_m = tp_atr

        if mode == "vol_gate_bb":
            if atr_pc[i] > atr_max:
                continue
            if np.isnan(rsi[i]) or np.isnan(bb_lo[i]) or np.isnan(trend[i]):
                continue
            uptrend = close[i] > trend[i]
            if require_uptrend and not uptrend:
                continue
            if use_macd_filter and macd_h[i] < 0:
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
            this_mode = "mr"
            sl_m, tp_m = sl_atr, tp_atr

        elif mode == "atr_breakout":
            if atr_pc[i] < atr_min:
                continue
            if i < 1 or np.isnan(donch_hi[i - 1]) or np.isnan(ema_tr[i]):
                continue
            if np.isnan(rsi[i]) or rsi[i] >= rsi_max:
                continue
            if require_ema_stack and not (ema20[i] > ema50[i] > ema100[i]):
                continue
            long_sig = close[i] > donch_hi[i - 1] and close[i] > ema_tr[i]
            this_mode = "bo"
            sl_m, tp_m = sl_atr, tp_atr

        elif mode == "ema_pullback":
            if not (atr_lo <= atr_pc[i] <= atr_hi):
                continue
            if np.isnan(rsi[i]) or np.isnan(pull[i]) or np.isnan(ema200[i]):
                continue
            if stack_mode == "ema20_gt_ema50_gt_ema100":
                structure = ema20[i] > ema50[i] > ema100[i]
            else:
                structure = close[i] > ema200[i]
            if not structure:
                continue
            buf = atr_buffer * atr[i]
            touched = low[i] <= pull[i] + buf
            recovered = close[i] > pull[i] or close[i] > open_[i]
            # user: low<=ema20 or ema50, close>ema20, rsi band
            near_ma = low[i] <= ema20[i] + buf or low[i] <= ema50[i] + buf
            long_sig = (
                structure
                and (touched or near_ma)
                and close[i] > ema20[i]
                and recovered
                and rsi_lo <= rsi[i] <= rsi_hi
            )
            if use_macd_rising and i >= 1:
                if not (macd_h[i] > macd_h[i - 1]):
                    long_sig = False
            this_mode = "mr"
            sl_m, tp_m = sl_atr, tp_atr

        elif mode == "dual_regime":
            if db > 0 and abs(atr_pc[i] - sw) < db:
                continue
            if atr_pc[i] >= sw:
                # breakout module
                if i < 1 or np.isnan(donch_hi[i - 1]):
                    continue
                if np.isnan(rsi[i]) or rsi[i] >= 78:
                    continue
                long_sig = close[i] > donch_hi[i - 1] and close[i] > ema50[i]
                this_mode = "bo"
                sl_m, tp_m = sl_atr_bo, tp_atr_bo
            else:
                # mean-rev module (vol-gated by construction)
                if np.isnan(rsi[i]) or np.isnan(bb_lo[i]):
                    continue
                if close[i] <= ema200[i]:
                    continue
                long_sig = (
                    low[i] <= bb_lo[i]
                    and close[i] > bb_lo[i]
                    and close[i] < bb_mid[i]
                    and rsi[i] <= rsi_buy + 10
                )
                this_mode = "mr"
                sl_m, tp_m = sl_atr_mr, tp_atr_mr
        else:
            continue

        if long_only:
            short_sig = False
        if not long_sig and not short_sig:
            continue

        stop_dist = atr[i] * sl_m
        if stop_dist <= 1e-9:
            continue
        risk_cash = bal * risk_pct
        raw = risk_cash / (stop_dist * CONTRACT_SIZE)
        lots = float(np.floor(raw * 100 + 1e-12) / 100.0)
        lots = min(lots, max_lots)
        min_lot = 0.01
        min_lot_risk = stop_dist * CONTRACT_SIZE * min_lot
        if lots < min_lot or min_lot_risk > risk_cash + 1e-9:
            continue

        if long_sig:
            pos = 1
            entry = px
            sl = entry - stop_dist
            tp = entry + atr[i] * tp_m
            entry_mode = this_mode if this_mode in ("bo", "mr") else "mr"
        else:
            pos = -1
            entry = px
            sl = entry + stop_dist
            tp = entry - atr[i] * tp_m
            entry_mode = this_mode if this_mode in ("bo", "mr") else "mr"

    if pos != 0:
        pnl = (close[-1] - entry) * CONTRACT_SIZE * lots * pos
        bal += pnl
        pnls.append(pnl)
        eq[-1] = bal

    return metrics_from_pnls(pnls, eq)


def is_better(m: Metrics, best_m: Metrics, best_ok: bool) -> bool:
    """Prefer passes(train) then net_profit; secondary score if none pass."""
    m_ok = passes(m)
    if m_ok and not best_ok:
        return True
    if m_ok and best_ok:
        if m.net_profit > best_m.net_profit:
            return True
        if abs(m.net_profit - best_m.net_profit) < 1e-9 and m.profit_factor > best_m.profit_factor:
            return True
        return False
    if not m_ok and best_ok:
        return False
    # neither passes: secondary score
    def sec(x: Metrics) -> float:
        return (
            x.profit_factor * 10.0
            + x.win_rate * 0.5
            + max(x.n_trades, 0) * 0.05
            + x.net_profit / 100.0
            - x.max_drawdown_pct * 0.5
        )

    return sec(m) > sec(best_m)


def train_score(m: Metrics) -> float:
    """Sort key: passers first, then net_profit / secondary."""
    base = 1e9 if passes(m) else 0.0
    return base + m.net_profit + m.profit_factor * 10.0 + m.n_trades * 0.01


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


def compact_grids() -> dict[str, list[dict]]:
    """Hardcoded compact grids per family (~<4k total evals)."""
    shared = dict(risk_pct=0.01, max_lots=0.5, long_only=True, hours=None)

    vol = product_grid(
        {
            "atr_max_pct": [0.5, 0.6, 0.7],
            "rsi_buy": [28.0, 30.0, 35.0],
            "rsi_sell": [50.0, 55.0, 60.0],
            "sl_atr": [1.2, 1.5],
            "tp_atr": [1.8, 2.0, 2.5],
            "bb_col": ["bb_lo", "bb_lo15"],
            "trend_col": ["ema200", "ema100"],
            "cooldown": [1, 2],
            "exit_on_vol_spike": [False, True],
        },
        {**shared, "mode": "vol_gate_bb", "require_uptrend": True, "use_macd_filter": False},
    )
    # 3*3*3*2*3*2*2*2*2 = 2592 — too big; subsample later globally
    # shrink:
    vol = product_grid(
        {
            "atr_max_pct": [0.5, 0.6, 0.7],
            "rsi_buy": [30.0, 35.0],
            "rsi_sell": [50.0, 55.0, 60.0],
            "sl_atr": [1.2, 1.5],
            "tp_atr": [1.8, 2.0, 2.5],
            "bb_col": ["bb_lo", "bb_lo15"],
            "trend_col": ["ema200"],
            "cooldown": [2],
            "exit_on_vol_spike": [False, True],
        },
        {**shared, "mode": "vol_gate_bb", "require_uptrend": True, "use_macd_filter": False},
    )  # 3*2*3*2*3*2*1*1*2 = 432

    bo = product_grid(
        {
            "donch_n": [10, 20, 55],
            "atr_min_pct": [0.5, 0.6, 0.7],
            "ema_trend": ["ema50", "ema100"],
            "sl_atr": [1.8, 2.0, 2.5],
            "tp_atr": [2.5, 3.0, 4.0],
            "rsi_max": [70.0, 75.0, 80.0],
            "trail_atr": [None, 1.5],
            "cooldown": [2, 3],
        },
        {**shared, "mode": "atr_breakout", "require_ema_stack": False},
    )  # 3*3*2*3*3*3*2*2 = 1944 — shrink
    bo = product_grid(
        {
            "donch_n": [10, 20, 55],
            "atr_min_pct": [0.55, 0.6, 0.7],
            "ema_trend": ["ema50", "ema100"],
            "sl_atr": [1.8, 2.0, 2.5],
            "tp_atr": [2.5, 3.0, 4.0],
            "rsi_max": [75.0],
            "trail_atr": [None, 2.0],
            "cooldown": [2],
        },
        {**shared, "mode": "atr_breakout", "require_ema_stack": False},
    )  # 3*3*2*3*3*1*2*1 = 324

    ema = product_grid(
        {
            "ema_pull": ["ema20", "ema50"],
            "rsi_lo": [35.0, 40.0, 45.0],
            "rsi_hi": [55.0, 60.0, 65.0],
            "rsi_sell": [65.0, 70.0],
            "atr_pctile_lo": [0.0, 0.3],
            "atr_pctile_hi": [0.75, 1.0],
            "sl_atr": [1.2, 1.5, 2.0],
            "tp_atr": [2.0, 2.5, 3.0],
            "atr_buffer": [0.0, 0.25],
            "use_macd_rising": [False, True],
            "cooldown": [1, 2],
        },
        {
            **shared,
            "mode": "ema_pullback",
            "stack_mode": "close_gt_ema200",
        },
    )  # huge — compact:
    ema = product_grid(
        {
            "ema_pull": ["ema20", "ema50"],
            "rsi_lo": [35.0, 40.0, 45.0],
            "rsi_hi": [55.0, 60.0, 65.0],
            "rsi_sell": [65.0, 70.0],
            "atr_pctile_lo": [0.0, 0.3],
            "atr_pctile_hi": [0.75, 1.0],
            "sl_atr": [1.2, 1.5, 2.0],
            "tp_atr": [2.0, 2.5, 3.0],
            "cooldown": [2],
        },
        {
            **shared,
            "mode": "ema_pullback",
            "stack_mode": "close_gt_ema200",
            "atr_buffer": 0.25,
            "use_macd_rising": False,
        },
    )
    # filter rsi_lo < rsi_hi
    ema = [p for p in ema if p["rsi_lo"] < p["rsi_hi"]]
    # 2*3*3*2*2*2*3*3*1 ≈ 1296 → still high; take key combos
    ema = product_grid(
        {
            "ema_pull": ["ema20", "ema50"],
            "rsi_lo": [35.0, 40.0, 45.0],
            "rsi_hi": [60.0, 65.0],
            "rsi_sell": [65.0, 70.0],
            "atr_pctile_lo": [0.0, 0.3],
            "atr_pctile_hi": [0.75, 1.0],
            "sl_atr": [1.5, 2.0],
            "tp_atr": [2.0, 2.5, 3.0],
            "cooldown": [2],
        },
        {
            **shared,
            "mode": "ema_pullback",
            "stack_mode": "close_gt_ema200",
            "atr_buffer": 0.25,
            "use_macd_rising": False,
        },
    )
    ema = [p for p in ema if p["rsi_lo"] < p["rsi_hi"]]  # 2*3*2*2*2*2*2*3 = 576

    dual = product_grid(
        {
            "switch_pct": [0.6, 0.65, 0.7],
            "donch_n": [10, 20],
            "rsi_buy": [30.0, 35.0],
            "rsi_sell": [50.0, 55.0, 60.0],
            "sl_atr_bo": [1.8, 2.0, 2.5],
            "tp_atr_bo": [2.5, 3.0, 4.0],
            "sl_atr_mr": [1.2, 1.5],
            "tp_atr_mr": [1.8, 2.0, 2.5],
            "deadband": [0.0, 0.05],
            "cooldown": [2],
        },
        {**shared, "mode": "dual_regime", "bb_col": "bb_lo"},
    )  # 3*2*2*3*3*3*2*3*2*1 = 3888 — shrink
    dual = product_grid(
        {
            "switch_pct": [0.6, 0.65, 0.7],
            "donch_n": [10, 20],
            "rsi_buy": [30.0, 35.0],
            "rsi_sell": [50.0, 55.0, 60.0],
            "sl_atr_bo": [1.8, 2.0],
            "tp_atr_bo": [2.5, 3.0],
            "sl_atr_mr": [1.2, 1.5],
            "tp_atr_mr": [1.8, 2.0],
            "deadband": [0.0],
            "cooldown": [2],
        },
        {**shared, "mode": "dual_regime", "bb_col": "bb_lo"},
    )  # 3*2*2*3*2*2*2*2*1*1 = 576

    return {
        "vol_gate_bb": vol,
        "atr_breakout": bo,
        "ema_pullback": ema,
        "dual_regime": dual,
    }


def grids_from_specs(specs: dict) -> dict[str, list[dict]] | None:
    """Build grids from xau_new_design_specs.json for core families only."""
    families = specs.get("families") or []
    out: dict[str, list[dict]] = {k: [] for k in CORE_FAMILIES}
    shared = dict(risk_pct=0.01, max_lots=0.5, long_only=True, hours=None)

    for fam in families:
        fid = fam.get("id", "")
        mode = FAMILY_MODE.get(fid)
        if mode is None or mode not in CORE_FAMILIES:
            continue
        pg = fam.get("param_grid") or {}
        if not pg:
            continue

        # normalize keys → simulate_design kwargs
        axes: dict[str, list] = {}
        for k, vals in pg.items():
            if not isinstance(vals, list) or not vals:
                continue
            if k == "atr_pctile_max":
                axes["atr_max_pct"] = [_pct_to_unit(v) for v in vals]
            elif k == "atr_pctile_min":
                axes["atr_min_pct"] = [_pct_to_unit(v) for v in vals]
            elif k == "high_thresh":
                axes["switch_pct"] = [_pct_to_unit(v) for v in vals]
            elif k == "N" or k == "entry_N":
                axes["donch_n"] = [int(v) for v in vals]
            elif k == "ema_trend":
                axes["ema_trend"] = list(vals)
            elif k == "trail_atr":
                axes["trail_atr"] = [None if v is None else float(v) for v in vals]
            elif k == "atr_lookback":
                continue  # fixed rolling-100 atr_pctile
            elif k in (
                "rsi_buy",
                "rsi_sell",
                "sl_atr",
                "tp_atr",
                "cooldown",
                "rsi_max",
                "rsi_lo",
                "rsi_hi",
                "atr_buffer",
                "deadband",
                "sl_atr_bo",
                "tp_atr_bo",
                "sl_atr_mr",
                "tp_atr_mr",
                "atr_pctile_lo",
                "atr_pctile_hi",
            ):
                if k in ("atr_pctile_lo", "atr_pctile_hi", "deadband"):
                    axes[k] = [_pct_to_unit(v) for v in vals]
                else:
                    axes[k] = [float(v) if not isinstance(v, bool) else v for v in vals]
            elif k in (
                "bb_col",
                "trend_col",
                "ema_pull",
                "stack_mode",
                "require_uptrend",
                "require_ema_stack",
                "exit_on_vol_spike",
                "use_macd_rising",
                "long_only",
            ):
                axes[k] = list(vals)
            # skip pivot/fib etc.

        if not axes:
            continue
        fixed = {**shared, "mode": mode}
        if mode == "dual_regime":
            fixed.setdefault("bb_col", "bb_lo")
        combos = product_grid(axes, fixed)
        # light prune
        pruned = []
        for p in combos:
            if "rsi_lo" in p and "rsi_hi" in p and p["rsi_lo"] >= p["rsi_hi"]:
                continue
            if "sl_atr" in p and "tp_atr" in p and p["tp_atr"] is not None:
                if float(p["tp_atr"]) < float(p["sl_atr"]) * 0.8:
                    continue
            pruned.append(p)
        out[mode].extend(pruned)

    if all(len(v) == 0 for v in out.values()):
        return None
    return out


def subsample_grids(grids: dict[str, list[dict]], max_total: int) -> dict[str, list[dict]]:
    total = sum(len(v) for v in grids.values())
    if total <= max_total:
        return grids
    rng = np.random.default_rng(42)
    # proportional subsample, min 50 per family if available
    out: dict[str, list[dict]] = {}
    n_fam = sum(1 for v in grids.values() if v)
    for k, v in grids.items():
        if not v:
            out[k] = []
            continue
        share = max(50, int(max_total * len(v) / total))
        share = min(share, len(v))
        if share >= len(v):
            out[k] = v
        else:
            idx = sorted(rng.choice(len(v), size=share, replace=False).tolist())
            out[k] = [v[i] for i in idx]
    # rebalance if still over
    total2 = sum(len(v) for v in out.values())
    if total2 > max_total:
        scale = max_total / total2
        for k in list(out.keys()):
            n = max(20, int(len(out[k]) * scale))
            if n < len(out[k]):
                idx = sorted(rng.choice(len(out[k]), size=n, replace=False).tolist())
                out[k] = [out[k][i] for i in idx]
    return out


def resolve_split(times: pd.Series) -> pd.Timestamp:
    """70% time split; prefer holdout JSON split if present (same cut)."""
    t_start = times.iloc[0]
    t_end = times.iloc[-1]
    split_70 = t_start + 0.7 * (t_end - t_start)
    if HOLDOUT_PATH.is_file():
        try:
            h = json.loads(HOLDOUT_PATH.read_text())
            if h.get("split"):
                return pd.Timestamp(h["split"])
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return split_70


def main() -> int:
    t0 = time.perf_counter()
    raw = load_h1()
    d = extend_indicators(raw)
    times = pd.to_datetime(d["time"], utc=True)
    split_ts = resolve_split(times)

    train = d.loc[times < split_ts].reset_index(drop=True)
    oos = d.loc[times >= split_ts].reset_index(drop=True)
    print(
        f"bars={len(d)} train={len(train)} oos={len(oos)} "
        f"split={split_ts} range={times.iloc[0]} → {times.iloc[-1]}"
    )

    grids: dict[str, list[dict]] | None = None
    grid_source = "compact_hardcoded"
    if SPECS_PATH.is_file():
        try:
            specs = json.loads(SPECS_PATH.read_text())
            grids = grids_from_specs(specs)
            if grids and sum(len(v) for v in grids.values()) > 0:
                grid_source = "xau_new_design_specs.json"
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            print(f"specs load failed ({e}); using compact grids")
            grids = None
    if grids is None:
        grids = compact_grids()

    # fill empty families from compact
    compact = compact_grids()
    for k in CORE_FAMILIES:
        if not grids.get(k):
            grids[k] = compact[k]

    grids = subsample_grids(grids, MAX_EVALS)
    total_evals = sum(len(v) for v in grids.values())
    print(f"grid_source={grid_source} total_evals={total_evals}")
    for k, v in grids.items():
        print(f"  {k}: {len(v)}")

    family_results: dict[str, Any] = {}
    all_candidates: list[dict] = []  # for global top-3
    all_passers_train = 0

    for fam in CORE_FAMILIES:
        g = grids.get(fam) or []
        if not g:
            family_results[fam] = {"n_evals": 0, "n_passers": 0, "best": None}
            continue
        best_p = g[0]
        best_m = simulate_design(train, **best_p)
        best_ok = passes(best_m)
        n_pass = 1 if best_ok else 0
        if best_ok:
            all_passers_train += 1

        for i, p in enumerate(g):
            if i == 0:
                continue
            m = simulate_design(train, **p)
            ok = passes(m)
            if ok:
                n_pass += 1
                all_passers_train += 1
            if is_better(m, best_m, best_ok):
                best_p, best_m, best_ok = p, m, ok
            if (i + 1) % 100 == 0:
                print(
                    f"  [{fam}] {i+1}/{len(g)} passers={n_pass} "
                    f"best_PF={best_m.profit_factor:.3f} NP={best_m.net_profit:.1f} "
                    f"n={best_m.n_trades} gates={best_ok}"
                )

        rec = {
            "id": fam,
            "params": serializable_params(best_p),
            "train": metrics_dict(best_m),
            "train_gates": best_ok,
            "score": train_score(best_m),
        }
        all_candidates.append(rec)
        family_results[fam] = {
            "n_evals": len(g),
            "n_passers": n_pass,
            "best": rec,
        }
        print(
            f"--- {fam} best train PF={best_m.profit_factor:.3f} WR={best_m.win_rate:.1f} "
            f"DD={best_m.max_drawdown_pct:.2f} n={best_m.n_trades} NP={best_m.net_profit:.1f} "
            f"gates={best_ok} ---"
        )

    # shortlist: top 1 per family + global top 3 (unique by json params)
    shortlist_ids: list[str] = []
    shortlist: list[dict] = []
    seen: set[str] = set()

    def _key(rec: dict) -> str:
        return json.dumps({"id": rec["id"], "params": rec["params"]}, sort_keys=True)

    for fam in CORE_FAMILIES:
        best = family_results.get(fam, {}).get("best")
        if best is None:
            continue
        k = _key(best)
        if k not in seen:
            seen.add(k)
            shortlist_ids.append(f"family_best:{fam}")
            shortlist.append(dict(best))

    ranked = sorted(all_candidates, key=lambda r: r["score"], reverse=True)
    for rec in ranked[:3]:
        k = _key(rec)
        if k in seen:
            continue
        seen.add(k)
        shortlist_ids.append(f"global_top:{rec['id']}")
        shortlist.append(dict(rec))
    # always include global top 3 even if already family bests — annotate rank
    for rank, rec in enumerate(ranked[:3], start=1):
        k = _key(rec)
        # mark global rank on existing shortlist entry
        for s in shortlist:
            if _key(s) == k:
                s["global_rank"] = rank

    # Frozen OOS once per shortlist entry
    print("--- frozen OOS eval ---")
    for s in shortlist:
        p = dict(s["params"])
        # restore None trail etc.
        oos_m = simulate_design(oos, **p)
        s["oos"] = metrics_dict(oos_m)
        s["oos_gates"] = bool(passes(oos_m))
        print(
            f"  {s['id']} train_PF={s['train']['profit_factor']:.3f} "
            f"oos_PF={oos_m.profit_factor:.3f} oos_n={oos_m.n_trades} "
            f"oos_gates={s['oos_gates']}"
        )

    search_s = time.perf_counter() - t0
    out = {
        "meta": {
            "split": str(split_ts),
            "train_bars": int(len(train)),
            "oos_bars": int(len(oos)),
            "grid_source": grid_source,
            "total_evals": int(total_evals),
            "search_seconds": round(search_s, 2),
            "atr_pctile": "rolling_100_rank_0_1",
            "safety": "offline research only; never --live; never place orders",
            "note": "Train-only selection; OOS evaluated once on frozen shortlist. "
            "Do not claim profitability without OOS metrics.",
        },
        "families": {
            k: {
                "n_evals": v.get("n_evals", 0),
                "n_passers": v.get("n_passers", 0),
                "best_id": (v.get("best") or {}).get("id"),
                "best_params": (v.get("best") or {}).get("params"),
                "best_train": (v.get("best") or {}).get("train"),
                "train_gates": (v.get("best") or {}).get("train_gates"),
            }
            for k, v in family_results.items()
        },
        "all_passers_train": int(all_passers_train),
        "shortlist": [
            {
                "id": s["id"],
                "params": s["params"],
                "train": s["train"],
                "oos": s.get("oos"),
                "oos_gates": s.get("oos_gates"),
                "train_gates": s.get("train_gates"),
                "global_rank": s.get("global_rank"),
                "tag": shortlist_ids[i] if i < len(shortlist_ids) else None,
            }
            for i, s in enumerate(shortlist)
        ],
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2) + "\n")
    print(f"Wrote {OUT_PATH} in {search_s:.1f}s")

    # summary head
    if shortlist:
        head = shortlist[0]
        print(
            f"SUMMARY head id={head['id']} "
            f"train_PF={head['train']['profit_factor']:.3f} "
            f"oos_PF={head.get('oos', {}).get('profit_factor', float('nan')):.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
