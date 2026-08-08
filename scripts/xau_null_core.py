#!/usr/bin/env python3
"""Shared helpers for XAU return-shuffle null / max-stat tests.

Used by ``xau_null_maxstat``, ``xau_donchian_null_maxstat``, and the
family-generic harness ``xau_family_null_maxstat``.

SAFETY: offline only — no live orders, no holdout selection.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# Soft / classic gate floors (mirror xau_frozen_multi_year_eval).
HARD_PASS_CLASSIC = {
    "profit_factor": 1.5,  # PF > 1.5
    "win_rate": 55.0,  # WR > 55
    "max_drawdown_pct": 10.0,  # DD < 10
    "n_trades": 20,  # n >= 20
}

SOFT_PASS_EXPECTANCY = {
    "profit_factor": 1.5,  # PF >= 1.5
    "n_trades": 40,  # n >= 40
    "max_drawdown_pct": 12.0,  # DD <= 12
    "expectancy": 20.0,  # exp >= 20
}

MIN_TRADES_MAX_STAT = 20


def scramble_ohlc(raw: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Shuffle log-returns of close; rebuild OHLC; keep time/spread fixed.

    Destroys the timing link between indicator state and subsequent price moves
    while preserving the marginal return distribution and each bar's relative
    high/low geometry (scaled to the new close).
    """
    out = raw.copy()
    c = out["close"].to_numpy(dtype=float)
    h = out["high"].to_numpy(dtype=float)
    l = out["low"].to_numpy(dtype=float)
    o = out["open"].to_numpy(dtype=float)

    up = np.maximum(h - c, 0.0)
    dn = np.maximum(c - l, 0.0)
    open_off = o - c

    log_c = np.log(np.clip(c, 1e-12, None))
    rets = np.diff(log_c)
    rng.shuffle(rets)
    new_c = np.empty_like(c)
    new_c[0] = c[0]
    new_c[1:] = c[0] * np.exp(np.cumsum(rets))

    scale = new_c / np.clip(c, 1e-12, None)
    new_o = new_c + open_off * scale
    new_h = new_c + up * scale
    new_l = new_c - dn * scale
    # enforce OHLC consistency
    new_h = np.maximum.reduce([new_h, new_o, new_c])
    new_l = np.minimum.reduce([new_l, new_o, new_c])

    out["open"] = new_o
    out["high"] = new_h
    out["low"] = new_l
    out["close"] = new_c
    return out


def pvalue(null_vals: list[float], real: float) -> float:
    """One-sided: P(null >= real). Add-one smoothing so p never hits 0."""
    if not null_vals:
        return 1.0
    hits = sum(1 for v in null_vals if v >= real)
    return (hits + 1) / (len(null_vals) + 1)


def dist_summary(vals: list[float]) -> dict[str, float]:
    a = np.asarray(vals, dtype=float)
    if len(a) == 0:
        return {"max": 0.0, "p50": 0.0, "p90": 0.0, "mean": 0.0}
    return {
        "max": float(a.max()),
        "p50": float(np.median(a)),
        "p90": float(np.quantile(a, 0.90)),
        "mean": float(a.mean()),
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


def metrics_dict(m: Any) -> dict[str, float | int]:
    """Normalize Metrics (or duck-typed) → plain dict incl. expectancy."""
    n = int(getattr(m, "n_trades", 0) or 0)
    net = float(getattr(m, "net_profit", 0.0) or 0.0)
    exp = float(net / n) if n > 0 else 0.0
    return {
        "net_profit": net,
        "win_rate": float(getattr(m, "win_rate", 0.0) or 0.0),
        "profit_factor": float(getattr(m, "profit_factor", 0.0) or 0.0),
        "max_drawdown_pct": float(getattr(m, "max_drawdown_pct", 0.0) or 0.0),
        "n_trades": n,
        "wins": int(getattr(m, "wins", 0) or 0),
        "losses": int(getattr(m, "losses", 0) or 0),
        "expectancy": exp,
        "expectancy_sqrt_n": exp * float(np.sqrt(max(n, 0))),
    }


def hard_pass_classic(md: dict[str, Any] | Any) -> bool:
    """PF>1.5 WR>55 DD<10 n>=20."""
    if not isinstance(md, dict):
        md = metrics_dict(md)
    return (
        float(md["profit_factor"]) > HARD_PASS_CLASSIC["profit_factor"]
        and float(md["win_rate"]) > HARD_PASS_CLASSIC["win_rate"]
        and float(md["max_drawdown_pct"]) < HARD_PASS_CLASSIC["max_drawdown_pct"]
        and int(md["n_trades"]) >= int(HARD_PASS_CLASSIC["n_trades"])
    )


def soft_pass_expectancy(md: dict[str, Any] | Any) -> bool:
    """PF>=1.5 n>=40 DD<=12 exp>=20 (WR diagnostic only)."""
    if not isinstance(md, dict):
        md = metrics_dict(md)
    return (
        float(md["profit_factor"]) >= SOFT_PASS_EXPECTANCY["profit_factor"]
        and int(md["n_trades"]) >= int(SOFT_PASS_EXPECTANCY["n_trades"])
        and float(md["max_drawdown_pct"]) <= SOFT_PASS_EXPECTANCY["max_drawdown_pct"]
        and float(md["expectancy"]) >= SOFT_PASS_EXPECTANCY["expectancy"]
    )


def subsample_grid(
    grid: list[dict],
    *,
    max_n: int,
    seed: int = 42,
) -> list[dict]:
    """Deterministic subsample when the family grid exceeds max_n."""
    if max_n <= 0 or len(grid) <= max_n:
        return list(grid)
    rng = np.random.default_rng(seed)
    idx = np.sort(rng.choice(len(grid), size=max_n, replace=False))
    return [grid[int(i)] for i in idx]


def param_key(p: dict) -> str:
    import json

    return json.dumps(serializable_params(p), sort_keys=True, default=str)


def prepend_unique(head: list[dict], tail: list[dict]) -> list[dict]:
    """Prepend head configs then tail, deduped by serializable param key."""
    out: list[dict] = []
    seen: set[str] = set()
    for p in head + tail:
        k = param_key(p)
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out
