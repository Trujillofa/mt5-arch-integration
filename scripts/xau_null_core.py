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
    lo: np.ndarray,
    o: np.ndarray,
    new_c: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Scale original bar geometry onto a new close path."""
    up = np.maximum(h - c, 0.0)
    dn = np.maximum(c - lo, 0.0)
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
    within_day_return_rotate
        **Preferred for server-hour / session rules.** Per calendar day, circularly
        rotate the within-day close-to-close log-return sequence by k≥1, rebuild a
        continuous price path (rebase from the day's first close), and re-attach
        bar geometry. Timestamps and spreads stay fixed. Destroys hour↔return
        association while preserving day bar counts and continuous daily geometry.
    day_block_shuffle / circular_day_shift
        **PROTOCOL_NULL_INVALID for session hypotheses** (variable-length days,
        absolute-price blocks, hour misalignment). Kept only for legacy docs;
        prefer within_day_return_rotate.
    """
    method = (method or "global_return_shuffle").strip().lower()
    if method in ("global_return_shuffle", "return_shuffle", "global"):
        return _null_global_return_shuffle(raw, rng)
    if method in (
        "within_day_return_rotate",
        "within_day_hour_rotate",
        "session_return_rotate",
        "intraday_return_rotate",
    ):
        return _null_within_day_return_rotate(raw, rng)
    if method in ("day_block_shuffle", "block_shuffle", "block"):
        return _null_day_block_permute(raw, rng, block_days=block_days, circular=False)
    if method in ("circular_day_shift", "circular", "circular_shift"):
        return _null_day_block_permute(raw, rng, block_days=block_days, circular=True)
    raise ValueError(
        f"unknown null method {method!r}; "
        "use global_return_shuffle | within_day_return_rotate | "
        "day_block_shuffle | circular_day_shift"
    )


def _null_global_return_shuffle(raw: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    out = raw.copy()
    c = out["close"].to_numpy(dtype=float)
    h = out["high"].to_numpy(dtype=float)
    lo = out["low"].to_numpy(dtype=float)
    o = out["open"].to_numpy(dtype=float)

    log_c = np.log(np.clip(c, 1e-12, None))
    rets = np.diff(log_c)
    rng.shuffle(rets)
    new_c = np.empty_like(c)
    new_c[0] = c[0]
    new_c[1:] = c[0] * np.exp(np.cumsum(rets))
    new_o, new_h, new_l = _rebuild_ohlc_from_close(c, h, lo, o, new_c)
    out["open"], out["high"], out["low"], out["close"] = new_o, new_h, new_l, new_c
    return out


def _day_keys(times: pd.Series) -> np.ndarray:
    t = pd.to_datetime(times, utc=True)
    # calendar day in the series' timezone (broker/server stamps as stored)
    return np.asarray(t.dt.strftime("%Y-%m-%d").to_numpy())


def _null_within_day_return_rotate(
    raw: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Per-day circular rotation of within-day log-returns; continuous rebase.

    For each calendar day with m bars and closes c[0..m-1]:
      rets[i] = log(c[i+1]/c[i])  (m-1 returns)
      rotate rets left by k ~ Uniform{1..m-2} when m>=3 else skip day
      rebuild c' from c[0] with cumsum of rotated rets
      rebuild OHLC geometry scaled onto c'

    Timestamps and spreads are unchanged. No cross-day absolute-price paste.
    """
    out = raw.copy()
    n = len(out)
    if n == 0:
        return out

    c = out["close"].to_numpy(dtype=float)
    h = out["high"].to_numpy(dtype=float)
    lo = out["low"].to_numpy(dtype=float)
    o = out["open"].to_numpy(dtype=float)
    days = _day_keys(out["time"])

    new_c = c.copy()
    new_o = o.copy()
    new_h = h.copy()
    new_l = lo.copy()

    # group indices per day preserving order
    groups: dict[str, list[int]] = {}
    order: list[str] = []
    for i, d in enumerate(days):
        ds = str(d)
        if ds not in groups:
            groups[ds] = []
            order.append(ds)
        groups[ds].append(i)

    for d in order:
        idxs = groups[d]
        m = len(idxs)
        if m < 3:
            # cannot rotate returns meaningfully; leave day as-is
            continue
        ix = np.asarray(idxs, dtype=int)
        cc = c[ix]
        # within-day log returns
        rets = np.diff(np.log(np.clip(cc, 1e-12, None)))
        k = int(rng.integers(1, m - 1))  # 1..m-2 inclusive via high=m-1 exclusive in integers
        # numpy integers(low, high) is [low, high)
        rets_r = np.concatenate([rets[k:], rets[:k]])
        cc_new = np.empty(m, dtype=float)
        cc_new[0] = cc[0]  # rebase: keep day's first close
        cc_new[1:] = cc[0] * np.exp(np.cumsum(rets_r))
        oo, hh, ll = _rebuild_ohlc_from_close(cc, h[ix], lo[ix], o[ix], cc_new)
        new_c[ix] = cc_new
        new_o[ix] = oo
        new_h[ix] = hh
        new_l[ix] = ll

    out["open"] = new_o
    out["high"] = new_h
    out["low"] = new_l
    out["close"] = new_c
    return out


def _null_day_block_permute(
    raw: pd.DataFrame,
    rng: np.random.Generator,
    *,
    block_days: int = 1,
    circular: bool = False,
) -> pd.DataFrame:
    """LEGACY — invalid for session-hour tests (see protocol v2.1).

    Pastes absolute-price day blocks onto fixed timestamps without rebasing;
    variable-length days misalign hours. Prefer ``within_day_return_rotate``.
    """
    if block_days < 1:
        block_days = 1
    out = raw.copy()
    n = len(out)
    if n == 0:
        return out

    days = _day_keys(out["time"])
    order: list[str] = []
    groups: dict[str, list[int]] = {}
    for i, d in enumerate(days):
        if d not in groups:
            groups[d] = []
            order.append(str(d))
        groups[d].append(i)

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

    src_idx = np.concatenate([np.asarray(b, dtype=int) for b in new_blocks])
    src_idx = src_idx[:n]
    if len(src_idx) < n:
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
    entry_hour: int | None = None,
    flat_hour: int | None = None,
) -> dict[str, bool]:
    """Checks that a null transform preserved intended structure."""
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

    raw_days = _day_keys(raw["time"])
    scr_days = _day_keys(scrambled["time"])
    # per-day bar counts must match *by calendar day* (not just multiset)
    if len(raw_days) == len(scr_days):
        raw_by = pd.Series(1, index=range(len(raw))).groupby(raw_days).size()
        scr_by = pd.Series(1, index=range(len(scrambled))).groupby(scr_days).size()
        checks["per_day_bar_count_equal"] = bool(raw_by.equals(scr_by))
    else:
        checks["per_day_bar_count_equal"] = False

    if method in (
        "within_day_return_rotate",
        "within_day_hour_rotate",
        "session_return_rotate",
        "intraday_return_rotate",
    ):
        # continuous within-day: no huge artificial jump mid-day beyond original max jump*factor
        checks["within_day_path_continuous"] = _within_day_jumps_bounded(raw, scrambled)
        # destroy hour-path association: close series at fixed hours should differ on some days
        if entry_hour is not None:
            checks["entry_hour_closes_moved"] = _hour_closes_differ(
                raw, scrambled, hour=int(entry_hour)
            )
        else:
            checks["entry_hour_closes_moved"] = True
        if flat_hour is not None and entry_hour is not None:
            checks["session_path_association_broken"] = _session_path_differs(
                raw, scrambled, entry_hour=int(entry_hour), flat_hour=int(flat_hour)
            )
        else:
            checks["session_path_association_broken"] = True

    if method in ("day_block_shuffle", "block_shuffle", "block", "circular_day_shift", "circular"):
        # document that multiset-only check is weak (timestamps fixed)
        raw_counts = pd.Series(raw_days).value_counts().sort_values().to_numpy()
        scr_counts = pd.Series(scr_days).value_counts().sort_values().to_numpy()
        checks["day_bar_count_multiset"] = bool(np.array_equal(raw_counts, scr_counts))
        checks["protocol_session_valid"] = False  # explicitly invalid for hour rules

    return checks


def _within_day_jumps_bounded(raw: pd.DataFrame, scr: pd.DataFrame, factor: float = 5.0) -> bool:
    """True if max |Δlog c| within each day is not wildly above original (no paste gaps)."""
    rd = _day_keys(raw["time"])
    rc = raw["close"].to_numpy(float)
    sc = scr["close"].to_numpy(float)
    for d in np.unique(rd):
        ix = np.where(rd == d)[0]
        if len(ix) < 2:
            continue
        r_j = np.abs(np.diff(np.log(np.clip(rc[ix], 1e-12, None))))
        s_j = np.abs(np.diff(np.log(np.clip(sc[ix], 1e-12, None))))
        if r_j.size == 0:
            continue
        if float(s_j.max()) > float(r_j.max()) * factor + 1e-12 and not np.isclose(
            float(s_j.max()), float(r_j.max()), rtol=1e-6, atol=1e-9
        ):
            return False
    return True


def _hour_closes_differ(raw: pd.DataFrame, scr: pd.DataFrame, *, hour: int) -> bool:
    t = pd.to_datetime(raw["time"], utc=True)
    h = t.dt.hour.to_numpy()
    mask = h == int(hour)
    if not mask.any():
        return True
    rc = raw["close"].to_numpy(float)[mask]
    sc = scr["close"].to_numpy(float)[mask]
    return bool(np.mean(np.abs(rc - sc) > 1e-9) > 0.1)  # >10% of hour bars moved


def _session_path_differs(
    raw: pd.DataFrame,
    scr: pd.DataFrame,
    *,
    entry_hour: int,
    flat_hour: int,
) -> bool:
    """Fraction of days where close path over [entry, flat] hours differs."""
    t = pd.to_datetime(raw["time"], utc=True)
    days = t.dt.strftime("%Y-%m-%d").to_numpy()
    hours = t.dt.hour.to_numpy()
    rc = raw["close"].to_numpy(float)
    sc = scr["close"].to_numpy(float)
    changed = 0
    total = 0
    for d in np.unique(days):
        ix = np.where(
            (days == d) & (hours >= entry_hour) & (hours <= flat_hour)
        )[0]
        if len(ix) < 2:
            continue
        total += 1
        if not np.allclose(rc[ix], sc[ix], rtol=0, atol=1e-9):
            changed += 1
    if total == 0:
        return True
    return (changed / total) > 0.5


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
