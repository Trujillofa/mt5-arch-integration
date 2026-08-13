#!/usr/bin/env python3
"""Zero-knob joint three-symbol London-proxy open cosign fade (multi-instrument v4).

Charter (runnable): ``results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v4.json``

Dedicated multi-instrument harness only. Do **not** route through single-frame
``xau_family_null_maxstat`` / ``xau_sealed_family_cycle`` (they refuse this family).

Execution contract (frozen v4):
* Joint calendar I = timestamp intersection of XAUUSD, EURUSD, GBPUSD.
* Per day D: T* = earliest joint bar with hour in {7,8,9}.
* Cosign at T*: all three (close-open) nonzero and same sign.
* Fade all three at open of next joint bar T*+1 (same day); all-or-none basket.
* ATR14 Wilder on joint frame; SL 1.5 / TP 2.0 × atr[T*]; exits on j >= T*+1:
  SL before TP before time-flat (hour>=16 or last bar of day).
* Sizing: raw_lots = risk_cash / (sl_distance_price * contract_size); floor step;
  cap max; never force lot_min; any invalid leg cancels the joint signal.
* Costs: full RT spread at entry (points × point_size × contract × lots), deduct at exit.
* Account/P&L USD; start balance 10k per symbol book; joint start equity 30k.

SAFETY: offline only. Fixtures/implement only; no develop screen / null / live.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from backtest import Metrics, metrics_from_pnls

FAMILY = "joint_london_open_cosign_fade_flat"
NAME = FAMILY
kill_label = "KILL_JOINT_LONDON_OPEN_COSIGN_FADE_FLAT"
use_soft_primary = True
harness_kind = "multi_instrument_joint_v1"

SYMBOLS: tuple[str, ...] = ("XAUUSD", "EURUSD", "GBPUSD")
PER_SYMBOL_META: dict[str, dict[str, float]] = {
    "XAUUSD": {"point_size": 0.01, "contract_size": 100.0},
    "EURUSD": {"point_size": 1e-5, "contract_size": 100_000.0},
    "GBPUSD": {"point_size": 1e-5, "contract_size": 100_000.0},
}

COINCIDENT_HOURS = frozenset({7, 8, 9})
FLAT_HOUR = 16
SL_ATR = 1.5
TP_ATR = 2.0
RISK_PCT = 0.01
LOT_MAX = 0.5
LOT_MIN = 0.01
LOT_STEP = 0.01
ATR_PERIOD = 14
WARMUP = 30
START_BALANCE = 10_000.0
JOINT_START_EQUITY = 30_000.0

# Joint soft (primary) and per-symbol soft from charter gates
JOINT_SOFT_N = 60
JOINT_SOFT_PF = 1.1
JOINT_SOFT_NP = 0.0
JOINT_SOFT_DD = 25.0
PER_SYMBOL_SOFT_N = 20
PER_SYMBOL_SOFT_PF = 1.1
PER_SYMBOL_SOFT_NP = 0.0


@dataclass
class JointResult:
    """Per-symbol books + joint aggregate metrics (house PF zero-denom)."""

    per_symbol: dict[str, Metrics]
    joint: Metrics
    trade_log: list[dict[str, Any]] = field(default_factory=list)
    joint_equity: list[float] = field(default_factory=list)
    n_signals_cosign: int = 0
    n_signals_entered: int = 0
    n_signals_skipped_partial: int = 0


def build_grid() -> list[dict]:
    """Exactly one config — zero free knobs."""
    return [
        {
            "coincident_hours": sorted(COINCIDENT_HOURS),
            "flat_hour": FLAT_HOUR,
            "sl_atr": SL_ATR,
            "tp_atr": TP_ATR,
            "risk_pct": RISK_PCT,
            "lot_max": LOT_MAX,
            "lot_min": LOT_MIN,
            "lot_step": LOT_STEP,
        }
    ]


def grid(*, max_n: int = 1200, seed: int = 42) -> list[dict]:
    _ = max_n, seed
    return build_grid()


def prepare_symbol(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize OHLCV + server hour/day (timezone-naive server_clock_as_stored).

    ATR is recomputed after joint align. Does **not** invent missing spreads —
    the ``spread`` column must already be present (fail-closed costs).
    """
    d = raw.copy()
    if "time" not in d.columns:
        raise ValueError("frame requires time column")
    # Fail closed: never attach UTC to server timestamps; require naive wall clock.
    t = pd.to_datetime(d["time"])
    tz = getattr(t.dtype, "tz", None)
    if tz is not None:
        raise ValueError(
            "time must be timezone-naive server_clock_as_stored "
            "(do not label server bars as UTC)"
        )
    d["time"] = t
    d = d.sort_values("time").drop_duplicates(subset=["time"], keep="last")
    d["hour"] = d["time"].dt.hour.astype(int)
    d["day_id"] = d["time"].dt.strftime("%Y-%m-%d")
    for col in ("open", "high", "low", "close"):
        if col not in d.columns:
            raise ValueError(f"frame requires {col} column")
        d[col] = d[col].astype(float)
    if "spread" not in d.columns:
        raise ValueError(
            "frame requires spread column (points); missing costs must not default to 0"
        )
    d["spread"] = d["spread"].astype(float)
    return d.reset_index(drop=True)


def _wilder_atr(d: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    h = d["high"].astype(float)
    lo = d["low"].astype(float)
    c = d["close"].astype(float)
    prev = c.shift(1)
    tr = pd.concat([(h - lo), (h - prev).abs(), (lo - prev).abs()], axis=1).max(axis=1)
    out = tr.ewm(alpha=1 / period, adjust=False).mean()
    return pd.Series(out, index=d.index, dtype=float)


def _sma_atr(d: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    """Forbidden alternative estimator — exposed only for fixture discrimination."""
    h = d["high"].astype(float)
    lo = d["low"].astype(float)
    c = d["close"].astype(float)
    prev = c.shift(1)
    tr = pd.concat([(h - lo), (h - prev).abs(), (lo - prev).abs()], axis=1).max(axis=1)
    return pd.Series(tr.rolling(period).mean(), index=d.index, dtype=float)


class EmptyJointIntersectionError(ValueError):
    """Raised when the three-symbol joint calendar I is empty (not a zero-trade result)."""


def align_joint(
    frames: dict[str, pd.DataFrame],
    *,
    symbols: tuple[str, ...] = SYMBOLS,
) -> dict[str, pd.DataFrame]:
    """Restrict to timestamp intersection I and recompute Wilder ATR on I.

    Empty intersection is a hard error (``EmptyJointIntersectionError``), never a
    silent zero-trade JointResult (would masquerade as SCREEN_FAIL).
    """
    if set(symbols) - set(frames):
        missing = set(symbols) - set(frames)
        raise ValueError(f"missing symbols: {sorted(missing)}")
    prepared = {s: prepare_symbol(frames[s]) for s in symbols}
    # Schema on prepared frames even if intersection will be empty
    for s in symbols:
        for col in ("time", "open", "high", "low", "close", "spread", "hour", "day_id"):
            if col not in prepared[s].columns:
                raise ValueError(f"{s} missing required column {col!r} before align")
    # Intersection of times (ordered)
    sets = [set(prepared[s]["time"].tolist()) for s in symbols]
    common = sets[0].intersection(*sets[1:])
    if not common:
        raise EmptyJointIntersectionError(
            "EMPTY_JOINT_INTERSECTION: no common timestamps across "
            f"{list(symbols)}; refuse evaluation (not a zero-trade result)"
        )
    out: dict[str, pd.DataFrame] = {}
    common_list = sorted(common)
    for s in symbols:
        d = prepared[s]
        d = d.loc[d["time"].isin(common_list)].sort_values("time").reset_index(drop=True)
        d = d.copy()
        d["atr"] = _wilder_atr(d)
        out[s] = d
    validate_joint_frames(out, symbols=symbols, require_atr=True)
    return out


def validate_joint_frames(
    frames: dict[str, pd.DataFrame],
    *,
    symbols: tuple[str, ...] = SYMBOLS,
    require_atr: bool = True,
) -> None:
    """Fail closed: identical ordered timestamps, row counts, day/hour, required cols.

    Prevents ``already_aligned=True`` from bypassing the intersection calendar.
    Empty frames are invalid (``EmptyJointIntersectionError``), not a zero-trade pass.
    hour/day_id must derive from time; timestamps must be unique and strictly increasing.
    """
    if set(symbols) - set(frames):
        missing = set(symbols) - set(frames)
        raise ValueError(f"missing symbols for joint frames: {sorted(missing)}")
    required = ["time", "open", "high", "low", "close", "spread", "hour", "day_id"]
    if require_atr:
        required = [*required, "atr"]
    # Schema first (including empty frames)
    for s in symbols:
        d = frames[s]
        for col in required:
            if col not in d.columns:
                raise ValueError(f"{s} missing required joint column {col!r}")
    ref = frames[symbols[0]]
    n = len(ref)
    for s in symbols[1:]:
        if len(frames[s]) != n:
            raise ValueError(
                f"joint frame row count mismatch: {s} has {len(frames[s])}, expected {n}"
            )
    if n == 0:
        raise EmptyJointIntersectionError(
            "EMPTY_JOINT_INTERSECTION: joint frames have zero rows; "
            "refuse evaluation (not a zero-trade result)"
        )
    t0 = pd.to_datetime(ref["time"])
    if getattr(t0.dtype, "tz", None) is not None:
        raise ValueError("joint time must be timezone-naive server_clock_as_stored")
    t0 = t0.reset_index(drop=True)
    # Strictly increasing + unique on ref (shared by all symbols after identity check)
    t_ns = t0.astype("int64").to_numpy()
    if t_ns.size >= 2 and np.any(np.diff(t_ns) <= 0):
        raise ValueError(
            "joint timestamps must be strictly increasing and unique "
            "(duplicate or out-of-order time)"
        )
    for s in symbols:
        d = frames[s]
        ts = pd.to_datetime(d["time"]).reset_index(drop=True)
        if getattr(ts.dtype, "tz", None) is not None:
            raise ValueError(
                f"{s} time must be timezone-naive server_clock_as_stored"
            )
        if not ts.equals(t0):
            raise ValueError(
                f"joint timestamps not identical for {s} (intersection calendar required)"
            )
        # hour / day_id must derive from time (not free-floating labels)
        exp_hour = ts.dt.hour.to_numpy(dtype=int)
        exp_day = ts.dt.strftime("%Y-%m-%d").to_numpy()
        got_hour = d["hour"].to_numpy(dtype=int)
        got_day = d["day_id"].astype(str).to_numpy()
        if not np.array_equal(got_hour, exp_hour):
            raise ValueError(
                f"{s}.hour must equal time.dt.hour (derived server clock; got mismatch)"
            )
        if not np.array_equal(got_day, exp_day):
            raise ValueError(
                f"{s}.day_id must equal time.dt.strftime('%Y-%m-%d') "
                "(derived server clock; got mismatch)"
            )
        # Spreads fail-closed here; OHLC non-finite is handled at entry/exit use
        # (invalid entry fill cancels the basket rather than partial entry).
        spr = d["spread"].to_numpy(float)
        if not np.all(np.isfinite(spr)):
            raise ValueError(
                f"{s}.spread contains non-finite values (NaN/Inf costs refuse evaluation)"
            )
        if np.any(spr < 0):
            raise ValueError(
                f"{s}.spread contains negative points (costs refuse evaluation)"
            )
        if require_atr:
            atr = d["atr"].to_numpy(float)
            # ATR may be NaN during warmup; only non-finite Inf is hard-fail globally.
            if np.any(np.isinf(atr)):
                raise ValueError(f"{s}.atr contains Inf")

def _floor_lots(raw_lots: float, *, lot_step: float, lot_max: float) -> float:
    if raw_lots <= 0 or not np.isfinite(raw_lots):
        return 0.0
    steps = float(np.floor(raw_lots / lot_step + 1e-12))
    lots = steps * lot_step
    return float(min(lots, lot_max))


def size_lots(
    *,
    balance: float,
    atr_tstar: float,
    contract_size: float,
    risk_pct: float = RISK_PCT,
    sl_atr: float = SL_ATR,
    lot_min: float = LOT_MIN,
    lot_step: float = LOT_STEP,
    lot_max: float = LOT_MAX,
) -> float | None:
    """Return lots or None if leg_invalid (never force lot_min)."""
    if not np.isfinite(atr_tstar) or atr_tstar <= 0:
        return None
    if not np.isfinite(balance) or balance <= 0:
        return None
    if contract_size <= 0:
        return None
    sl_distance = float(sl_atr) * float(atr_tstar)
    if sl_distance <= 1e-15:
        return None
    risk_cash = float(risk_pct) * float(balance)
    raw = risk_cash / (sl_distance * float(contract_size))
    lots = _floor_lots(raw, lot_step=lot_step, lot_max=lot_max)
    if lots < float(lot_min) - 1e-15:
        return None
    return lots


def _metrics_dict(m: Metrics) -> dict[str, float | int]:
    return {
        "n_trades": int(m.n_trades),
        "profit_factor": float(m.profit_factor),
        "net_profit": float(m.net_profit),
        "max_drawdown_pct": float(m.max_drawdown_pct),
        "win_rate": float(m.win_rate),
    }


def soft_pass_per_symbol(m: Metrics) -> bool:
    md = _metrics_dict(m)
    return (
        int(md["n_trades"]) >= PER_SYMBOL_SOFT_N
        and float(md["profit_factor"]) >= PER_SYMBOL_SOFT_PF
        and float(md["net_profit"]) > PER_SYMBOL_SOFT_NP
    )


def soft_pass_joint(m: Metrics) -> bool:
    md = _metrics_dict(m)
    return (
        int(md["n_trades"]) >= JOINT_SOFT_N
        and float(md["profit_factor"]) >= JOINT_SOFT_PF
        and float(md["net_profit"]) > JOINT_SOFT_NP
        and float(md["max_drawdown_pct"]) <= JOINT_SOFT_DD
    )


def joint_gate_success(result: JointResult) -> bool:
    """Binary primary: all three per-symbol soft AND joint soft."""
    if not all(soft_pass_per_symbol(result.per_symbol[s]) for s in SYMBOLS):
        return False
    return soft_pass_joint(result.joint)


def n_passers_binary(result: JointResult) -> int:
    return 1 if joint_gate_success(result) else 0


def simulate(d: pd.DataFrame, **_params: Any) -> Metrics:
    """Single-frame simulate is forbidden for this multi-instrument family."""
    raise RuntimeError(
        "REFUSE_SINGLE_FRAME_SIMULATE: use simulate_joint(frames) for "
        f"{FAMILY} (harness_kind={harness_kind})"
    )


def simulate_joint(
    frames: dict[str, pd.DataFrame],
    *,
    coincident_hours: list[int] | frozenset[int] | None = None,
    flat_hour: int = FLAT_HOUR,
    sl_atr: float = SL_ATR,
    tp_atr: float = TP_ATR,
    risk_pct: float = RISK_PCT,
    lot_max: float = LOT_MAX,
    lot_min: float = LOT_MIN,
    lot_step: float = LOT_STEP,
    start_balance: float = START_BALANCE,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    spread_col: str = "spread",
    already_aligned: bool = False,
    trade_log: list[dict[str, Any]] | None = None,
    **_extra: Any,
) -> JointResult:
    """Simulate all-or-none three-leg fade on joint calendar I.

    Costs are fail-closed: every symbol must expose ``spread_col`` with finite
    nonnegative points at every bar; commission/slippage must be finite and >= 0.
    Invalid costs refuse evaluation (raise) rather than defaulting to zero.
    """
    symbols = SYMBOLS
    hours_ok = frozenset(coincident_hours or COINCIDENT_HOURS)
    if not np.isfinite(float(commission_per_lot)) or float(commission_per_lot) < 0:
        raise ValueError("commission_per_lot must be finite and nonnegative")
    if not np.isfinite(float(slippage_points)) or float(slippage_points) < 0:
        raise ValueError("slippage_points must be finite and nonnegative")
    if already_aligned:
        # Never trust caller alignment without verifying the intersection contract.
        validate_joint_frames(frames, symbols=symbols, require_atr=True)
        aligned = frames
    else:
        aligned = align_joint(frames, symbols=symbols)
    ref = aligned[symbols[0]]
    n = len(ref)
    # validate_joint_frames already refuses n==0; belt-and-suspenders
    if n == 0:
        raise EmptyJointIntersectionError(
            "EMPTY_JOINT_INTERSECTION: refuse evaluation (not a zero-trade result)"
        )

    # Arrays per symbol — spreads required, finite, nonnegative (no nan_to_num)
    open_a = {s: aligned[s]["open"].to_numpy(float) for s in symbols}
    high_a = {s: aligned[s]["high"].to_numpy(float) for s in symbols}
    low_a = {s: aligned[s]["low"].to_numpy(float) for s in symbols}
    close_a = {s: aligned[s]["close"].to_numpy(float) for s in symbols}
    atr_a = {s: aligned[s]["atr"].to_numpy(float) for s in symbols}
    spread_a: dict[str, np.ndarray] = {}
    for s in symbols:
        if spread_col not in aligned[s].columns:
            raise ValueError(
                f"{s} missing cost column {spread_col!r}; refuse evaluation "
                "(missing costs must not become zero)"
            )
        spr = aligned[s][spread_col].to_numpy(float)
        if not np.all(np.isfinite(spr)):
            raise ValueError(
                f"{s}.{spread_col} has non-finite values; refuse evaluation"
            )
        if np.any(spr < 0):
            raise ValueError(
                f"{s}.{spread_col} has negative points; refuse evaluation"
            )
        spread_a[s] = spr

    hour = ref["hour"].to_numpy(int)
    day = ref["day_id"].to_numpy()
    times = ref["time"]

    # Last bar index per day
    last_of_day: dict[str, int] = {}
    for i in range(n):
        last_of_day[str(day[i])] = i

    bal = {s: float(start_balance) for s in symbols}
    pnls: dict[str, list[float]] = {s: [] for s in symbols}
    # Position state per symbol
    pos = dict.fromkeys(symbols, 0)  # +1 long, -1 short, 0 flat
    entry_px = dict.fromkeys(symbols, 0.0)
    sl_px = dict.fromkeys(symbols, 0.0)
    tp_px = dict.fromkeys(symbols, 0.0)
    lots = dict.fromkeys(symbols, 0.0)
    trade_cost = dict.fromkeys(symbols, 0.0)
    entry_bar = dict.fromkeys(symbols, -1)
    pos_day = dict.fromkeys(symbols)  # type: ignore[var-annotated]
    bal_at_entry = dict.fromkeys(symbols, 0.0)

    if trade_log is None:
        log: list[dict[str, Any]] = []
    else:
        log = trade_log
        log.clear()

    joint_eq = np.zeros(n)
    n_cosign = 0
    n_entered = 0
    n_skipped = 0
    entered_days: set[str] = set()

    # Precompute T* per day (earliest hour in coincident set)
    t_star_for_day: dict[str, int] = {}
    for i in range(n):
        dkey = str(day[i])
        if dkey in t_star_for_day:
            continue
        # scan day's bars
        # we'll fill when we first see a qualifying hour
    for i in range(n):
        dkey = str(day[i])
        if dkey not in t_star_for_day and int(hour[i]) in hours_ok:
            t_star_for_day[dkey] = i

    def _open_pnl(s: str, px: float) -> float:
        if pos[s] == 0:
            return 0.0
        cs = PER_SYMBOL_META[s]["contract_size"]
        return (px - entry_px[s]) * cs * lots[s] * pos[s]

    def _close_leg(s: str, i: int, exit_px: float, reason: str) -> None:
        cs = PER_SYMBOL_META[s]["contract_size"]
        gross = (exit_px - entry_px[s]) * cs * lots[s] * pos[s]
        pnl = gross - trade_cost[s]
        bal[s] += pnl
        pnls[s].append(pnl)
        log.append(
            {
                "symbol": s,
                "entry_bar": entry_bar[s],
                "exit_bar": i,
                "entry": entry_px[s],
                "exit": float(exit_px),
                "lots": lots[s],
                "pos": pos[s],
                "trade_cost": trade_cost[s],
                "gross": gross,
                "pnl": pnl,
                "bal_at_entry": bal_at_entry[s],
                "bal_after_exit": bal[s],
                "reason": reason,
                "day": pos_day[s],
            }
        )
        pos[s] = 0
        lots[s] = 0.0
        trade_cost[s] = 0.0
        entry_bar[s] = -1
        pos_day[s] = None

    for i in range(n):
        dkey = str(day[i])
        h_i = int(hour[i])
        is_last = last_of_day.get(dkey) == i

        # --- exits first (on j >= entry_bar; SL before TP before time flat) ---
        for s in symbols:
            if pos[s] == 0:
                continue
            # Fail-closed no overnight: if day rolled, force close at prior logic —
            # should not happen if we flat EOD; discard without booking overnight.
            if pos_day[s] is not None and dkey != pos_day[s]:
                pos[s] = 0
                lots[s] = 0.0
                trade_cost[s] = 0.0
                entry_bar[s] = -1
                pos_day[s] = None
                continue
            if i < entry_bar[s]:
                continue
            # Never use T* bar for exit: entry is T*+1; T* is entry_bar-1
            exit_px = None
            reason = ""
            p = pos[s]
            lo = low_a[s][i]
            hi = high_a[s][i]
            if p > 0:
                # long: SL below, TP above
                hit_sl = lo <= sl_px[s]
                hit_tp = hi >= tp_px[s]
                if hit_sl:
                    exit_px = sl_px[s]
                    reason = "sl"
                elif hit_tp:
                    exit_px = tp_px[s]
                    reason = "tp"
            else:
                # short: SL above, TP below
                hit_sl = hi >= sl_px[s]
                hit_tp = lo <= tp_px[s]
                if hit_sl:
                    exit_px = sl_px[s]
                    reason = "sl"
                elif hit_tp:
                    exit_px = tp_px[s]
                    reason = "tp"
            if exit_px is None and (h_i >= int(flat_hour) or is_last):
                exit_px = float(close_a[s][i])
                reason = "time_flat" if h_i >= int(flat_hour) else "day_end_flat"
            if exit_px is not None:
                _close_leg(s, i, float(exit_px), reason)

        # --- entries: only at bar that is T*+1 for this day ---
        t_star = t_star_for_day.get(dkey)
        if (
            t_star is not None
            and i == t_star + 1
            and str(day[t_star]) == dkey
            and dkey not in entered_days
            and all(pos[s] == 0 for s in symbols)
            and t_star >= WARMUP
        ):
            # Cosign at T*
            signs: list[int] = []
            cosign_ok = True
            for s in symbols:
                r = float(close_a[s][t_star] - open_a[s][t_star])
                if r == 0.0 or not np.isfinite(r):
                    cosign_ok = False
                    break
                signs.append(1 if r > 0 else -1)
            if cosign_ok and len(set(signs)) == 1:
                n_cosign += 1
                fade = -signs[0]  # opposite cosign
                # Preflight all legs (size + fill + cost) before mutating any position.
                planned_lots: dict[str, float] = {}
                planned_fill: dict[str, float] = {}
                planned_cost: dict[str, float] = {}
                planned_sl: dict[str, float] = {}
                planned_tp: dict[str, float] = {}
                leg_ok = True
                for s in symbols:
                    atr_v = float(atr_a[s][t_star])
                    cs = PER_SYMBOL_META[s]["contract_size"]
                    lots_s = size_lots(
                        balance=bal[s],
                        atr_tstar=atr_v,
                        contract_size=cs,
                        risk_pct=risk_pct,
                        sl_atr=sl_atr,
                        lot_min=lot_min,
                        lot_step=lot_step,
                        lot_max=lot_max,
                    )
                    if lots_s is None:
                        leg_ok = False
                        break
                    fill = float(open_a[s][i])
                    if not np.isfinite(fill) or fill <= 0.0:
                        leg_ok = False
                        break
                    stop_dist = float(sl_atr) * atr_v
                    if not np.isfinite(stop_dist) or stop_dist <= 0.0:
                        leg_ok = False
                        break
                    ps = PER_SYMBOL_META[s]["point_size"]
                    spr_i = float(spread_a[s][i])
                    if not np.isfinite(spr_i) or spr_i < 0.0:
                        # Should already be caught at load; belt-and-suspenders
                        raise ValueError(
                            f"{s} entry spread invalid at bar {i}; refuse evaluation"
                        )
                    cost = (
                        (spr_i + 2.0 * float(slippage_points))
                        * ps
                        * cs
                        * lots_s
                        + 2.0 * float(commission_per_lot) * lots_s
                    )
                    if not np.isfinite(cost) or cost < 0.0:
                        raise ValueError(
                            f"{s} trade cost non-finite or negative; refuse evaluation"
                        )
                    if fade > 0:
                        sl_v = fill - stop_dist
                        tp_v = fill + float(tp_atr) * atr_v
                    else:
                        sl_v = fill + stop_dist
                        tp_v = fill - float(tp_atr) * atr_v
                    if not (np.isfinite(sl_v) and np.isfinite(tp_v)):
                        leg_ok = False
                        break
                    planned_lots[s] = lots_s
                    planned_fill[s] = fill
                    planned_cost[s] = cost
                    planned_sl[s] = sl_v
                    planned_tp[s] = tp_v
                if not leg_ok:
                    n_skipped += 1
                    entered_days.add(dkey)  # no re-try same day
                else:
                    # Commit all three only after full preflight
                    for s in symbols:
                        bal_at_entry[s] = bal[s]
                        pos[s] = int(fade)
                        entry_px[s] = planned_fill[s]
                        lots[s] = planned_lots[s]
                        trade_cost[s] = planned_cost[s]
                        entry_bar[s] = i
                        pos_day[s] = dkey
                        sl_px[s] = planned_sl[s]
                        tp_px[s] = planned_tp[s]
                    n_entered += 1
                    entered_days.add(dkey)
                    # Same-bar exit allowed on entry bar (j >= T*+1)
                    for s in symbols:
                        if pos[s] == 0:
                            continue
                        p = pos[s]
                        lo = low_a[s][i]
                        hi = high_a[s][i]
                        exit_px = None
                        reason = ""
                        if p > 0:
                            if lo <= sl_px[s]:
                                exit_px, reason = sl_px[s], "sl"
                            elif hi >= tp_px[s]:
                                exit_px, reason = tp_px[s], "tp"
                        else:
                            if hi >= sl_px[s]:
                                exit_px, reason = sl_px[s], "sl"
                            elif lo <= tp_px[s]:
                                exit_px, reason = tp_px[s], "tp"
                        if exit_px is None and (h_i >= int(flat_hour) or is_last):
                            exit_px = float(close_a[s][i])
                            reason = "time_flat" if h_i >= int(flat_hour) else "day_end_flat"
                        if exit_px is not None:
                            _close_leg(s, i, float(exit_px), reason)

        # Joint MTM equity
        joint_eq[i] = sum(
            bal[s] + _open_pnl(s, float(close_a[s][i])) for s in symbols
        )

    # End of series: close remaining same-day positions at last close
    for s in symbols:
        if pos[s] != 0 and pos_day[s] is not None and str(day[-1]) == pos_day[s]:
            _close_leg(s, n - 1, float(close_a[s][-1]), "end_of_series")
            joint_eq[-1] = sum(bal[s2] for s2 in symbols)

    per_m: dict[str, Metrics] = {}
    for s in symbols:
        # Per-symbol equity for DD: realized + floating approx using joint times
        # Use step equity from closed trades only for simplicity on book metrics;
        # rebuild simple equity from cumulative pnl + start.
        eq_s = np.full(n, float(start_balance))
        # Approximate: mark realized balance only (flat-book path for DD on symbol)
        # For fixtures, n_trades/PF/NP matter most; DD uses cumulative closed pnl path.
        if pnls[s]:
            # Build equity path: start + cumulative closed at exit bars
            bal_path = float(start_balance)
            eq_path = np.full(n, bal_path)
            # Sort trades by exit bar
            exits = sorted(
                (t for t in log if t["symbol"] == s),
                key=lambda t: int(t["exit_bar"]),
            )
            j = 0
            for i in range(n):
                while j < len(exits) and int(exits[j]["exit_bar"]) == i:
                    bal_path = float(exits[j]["bal_after_exit"])
                    j += 1
                eq_path[i] = bal_path
            per_m[s] = metrics_from_pnls(pnls[s], eq_path)
        else:
            per_m[s] = metrics_from_pnls([], eq_s)

    all_pnls = [t["pnl"] for t in log]
    joint_m = metrics_from_pnls(all_pnls, joint_eq)

    result = JointResult(
        per_symbol=per_m,
        joint=joint_m,
        trade_log=list(log),
        joint_equity=[float(x) for x in joint_eq.tolist()],
        n_signals_cosign=n_cosign,
        n_signals_entered=n_entered,
        n_signals_skipped_partial=n_skipped,
    )
    _ = times  # reserved for future provenance
    return result
