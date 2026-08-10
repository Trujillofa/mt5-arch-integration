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


def _rebuild_ohlc_from_close(
    c: np.ndarray,
    h: np.ndarray,
    l: np.ndarray,
    o: np.ndarray,
    new_c: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Scale original bar geometry onto a new close path."""
    up = np.maximum(h - c, 0.0)
    dn = np.maximum(c - l, 0.0)
    open_off = o - c
    scale = new_c / np.clip(c, 1e-12, None)
    new_o = new_c + open_off * scale
    new_h = new_c + up * scale
    new_l = new_c - dn * scale
    new_h = np.maximum.reduce([new_h, new_o, new_c])
    new_l = np.minimum.reduce([new_l, new_o, new_c])
    return new_o, new_h, new_l


def scramble_ohlc(raw: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Global shuffle of close-to-close log-returns; rebuild OHLC; keep time/spread.

    Destroys timing between indicators and subsequent moves. Also destroys
    volatility clustering and session structure — **not** appropriate as the
    sole null for pure session / multi-instrument hypotheses. Prefer
    ``apply_null_method`` with a charter-declared method.
    """
    return apply_null_method(raw, rng, method="global_return_shuffle")


def apply_null_method(
    raw: pd.DataFrame,
    rng: np.random.Generator,
    *,
    method: str = "global_return_shuffle",
    block_days: int = 1,
) -> pd.DataFrame:
    """Apply a preregistered null transform.

    Methods
    -------
    global_return_shuffle
        Shuffle all close-to-close log returns (legacy). Breaks session structure.
    day_block_shuffle
        Shuffle calendar-day blocks of OHLC (size ``block_days``) as units.
        Preserves intra-day path shape and session geometry; destroys day order.
    circular_day_shift
        Circular-shift day blocks by a random offset (preserves adjacency better
        than full shuffle; still kills absolute calendar alignment of signals).
    """
    method = (method or "global_return_shuffle").strip().lower()
    if method in ("global_return_shuffle", "return_shuffle", "global"):
        return _null_global_return_shuffle(raw, rng)
    if method in ("day_block_shuffle", "block_shuffle", "block"):
        return _null_day_block_permute(raw, rng, block_days=block_days, circular=False)
    if method in ("circular_day_shift", "circular", "circular_shift"):
        return _null_day_block_permute(raw, rng, block_days=block_days, circular=True)
    raise ValueError(
        f"unknown null method {method!r}; "
        "use global_return_shuffle | day_block_shuffle | circular_day_shift"
    )


def _null_global_return_shuffle(raw: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    out = raw.copy()
    c = out["close"].to_numpy(dtype=float)
    h = out["high"].to_numpy(dtype=float)
    l = out["low"].to_numpy(dtype=float)
    o = out["open"].to_numpy(dtype=float)

    log_c = np.log(np.clip(c, 1e-12, None))
    rets = np.diff(log_c)
    rng.shuffle(rets)
    new_c = np.empty_like(c)
    new_c[0] = c[0]
    new_c[1:] = c[0] * np.exp(np.cumsum(rets))
    new_o, new_h, new_l = _rebuild_ohlc_from_close(c, h, l, o, new_c)
    out["open"], out["high"], out["low"], out["close"] = new_o, new_h, new_l, new_c
    return out


def _day_keys(times: pd.Series) -> np.ndarray:
    t = pd.to_datetime(times, utc=True)
    # calendar day in the series' timezone (broker/server stamps as stored)
    return t.dt.strftime("%Y-%m-%d").to_numpy()


def _null_day_block_permute(
    raw: pd.DataFrame,
    rng: np.random.Generator,
    *,
    block_days: int = 1,
    circular: bool = False,
) -> pd.DataFrame:
    """Permute or circular-shift day blocks; keep time index and spread columns."""
    if block_days < 1:
        block_days = 1
    out = raw.copy()
    n = len(out)
    if n == 0:
        return out

    days = _day_keys(out["time"])
    # group bar indices by day
    order: list[str] = []
    groups: dict[str, list[int]] = {}
    for i, d in enumerate(days):
        if d not in groups:
            groups[d] = []
            order.append(str(d))
        groups[d].append(i)

    # pack into blocks of block_days consecutive calendar days in original order
    blocks: list[list[int]] = []
    for i in range(0, len(order), block_days):
        idxs: list[int] = []
        for d in order[i : i + block_days]:
            idxs.extend(groups[d])
        if idxs:
            blocks.append(idxs)

    if len(blocks) <= 1:
        return out

    if circular:
        shift = int(rng.integers(1, len(blocks)))
        new_blocks = blocks[shift:] + blocks[:shift]
    else:
        perm = rng.permutation(len(blocks))
        new_blocks = [blocks[int(j)] for j in perm]

    # Map new OHLC sequence onto original time positions: take OHLC from permuted
    # bars in order, assign to fixed timestamps (spread stays with calendar time).
    src_idx = np.concatenate([np.asarray(b, dtype=int) for b in new_blocks])
    # length may match; if not (shouldn't), clip
    src_idx = src_idx[:n]
    if len(src_idx) < n:
        # pad with last
        pad = np.full(n - len(src_idx), src_idx[-1], dtype=int)
        src_idx = np.concatenate([src_idx, pad])

    for col in ("open", "high", "low", "close"):
        if col in out.columns:
            vals = out[col].to_numpy()
            out[col] = vals[src_idx]
    return out


def null_invariants_ok(
    raw: pd.DataFrame,
    scrambled: pd.DataFrame,
    *,
    method: str,
) -> dict[str, bool]:
    """Cheap checks that a null transform preserved intended structure."""
    method = method.lower()
    checks: dict[str, bool] = {
        "same_length": len(raw) == len(scrambled),
        "time_unchanged": bool(
            np.array_equal(
                pd.to_datetime(raw["time"], utc=True).to_numpy(),
                pd.to_datetime(scrambled["time"], utc=True).to_numpy(),
            )
        )
        if "time" in raw.columns and "time" in scrambled.columns
        else False,
    }
    if "spread" in raw.columns and "spread" in scrambled.columns:
        checks["spread_calendar_aligned"] = bool(
            np.allclose(
                raw["spread"].to_numpy(dtype=float),
                scrambled["spread"].to_numpy(dtype=float),
                equal_nan=True,
            )
        )
    if method in ("day_block_shuffle", "block_shuffle", "block", "circular_day_shift", "circular"):
        # each calendar day in scrambled should have same bar count as some day in raw
        raw_counts = pd.Series(_day_keys(raw["time"])).value_counts().sort_values().to_numpy()
        scr_counts = pd.Series(_day_keys(scrambled["time"])).value_counts().sort_values().to_numpy()
        checks["day_bar_count_multiset"] = bool(np.array_equal(raw_counts, scr_counts))
    return checks


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
