#!/usr/bin/env python3
"""Canonical multi_instrument_exogenous_predictor_v1 engine (Phase B).

Implements the executable algorithm from
``docs/research/MULTI-INSTRUMENT-EXOGENOUS-PREDICTOR-PROTOCOL-V1.md``:

* fixed-H occupancy on the real path (no concurrent books)
* causal open-bar lot sizing (carry-in balance only)
* conditional_fixed_signal_events_fixed_trades_v1 null pairing
* pack_capacity / segment non-overlap (not distinct-id-only)

Synthetic / library surface only — no package load, no thesis charter scoring,
no registry writes. Dispositional harnesses come later.

SAFETY: offline research only.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
import pandas as pd

HARNESS_KIND = "multi_instrument_exogenous_predictor_v1"
NULL_IMPLEMENTATION_ID = "conditional_fixed_signal_events_fixed_trades_v1"
H_DEFAULT = 3
ATR_PERIOD = 14
MAX_ASSIGNMENT_REDRAWS = 1000


class AssignmentError(RuntimeError):
    """Null donor assignment failed after max redraws (or empty pack)."""


# Back-compat alias used in early Phase B drafts
AssignmentFailure = AssignmentError  # noqa: N818


class ProtocolError(ValueError):
    """Hard protocol / input contract error."""


# ---------------------------------------------------------------------------
# Interval geometry
# ---------------------------------------------------------------------------


def segment_overlap(i: int, j: int, h: int = H_DEFAULT) -> bool:
    """True iff fixed-H intervals [i, i+H-1] and [j, j+H-1] intersect."""
    if h < 1:
        raise ProtocolError(f"h must be >= 1, got {h}")
    return not (i + h - 1 < j or j + h - 1 < i)


def pack_capacity(donors: Sequence[int], h: int = H_DEFAULT) -> int:
    """Max pairwise non-segment-overlapping subset (greedy earliest-start)."""
    accepted: list[int] = []
    for i in sorted(int(x) for x in donors):
        if all(not segment_overlap(i, a, h) for a in accepted):
            accepted.append(i)
    return len(accepted)


def greedy_pack_from_order(
    order: Sequence[int], m: int, h: int = H_DEFAULT
) -> list[int] | None:
    """Walk order L→R; accept non-overlapping donors until m accepted."""
    accepted: list[int] = []
    for d in order:
        di = int(d)
        if all(not segment_overlap(di, a, h) for a in accepted):
            accepted.append(di)
        if len(accepted) == m:
            return accepted
    return None


def assign_null_donors(
    donors: Sequence[int],
    m: int,
    identity: Sequence[int],
    rng: np.random.Generator,
    *,
    h: int = H_DEFAULT,
    max_redraws: int = MAX_ASSIGNMENT_REDRAWS,
) -> list[int]:
    """§5.5 assignment: permute → greedy pack → reject full identity."""
    if m < 0:
        raise ProtocolError(f"m must be >= 0, got {m}")
    if m == 0:
        return []
    d_sorted = sorted(int(x) for x in donors)
    ident = [int(x) for x in identity]
    if len(ident) != m:
        raise ProtocolError(f"identity length {len(ident)} != m={m}")
    if pack_capacity(d_sorted, h) < m:
        raise AssignmentError(
            f"pack_capacity={pack_capacity(d_sorted, h)} < m={m} (preflight should have refused)"
        )
    redraws = 0
    while True:
        perm = rng.permutation(len(d_sorted))
        order = [d_sorted[int(k)] for k in perm]
        accepted = greedy_pack_from_order(order, m, h)
        if accepted is None:
            redraws += 1
            if redraws >= max_redraws:
                raise AssignmentError(
                    f"failed to pack m={m} non-overlapping donors after {max_redraws} redraws"
                )
            continue
        if accepted == ident:
            redraws += 1
            if redraws >= max_redraws:
                raise AssignmentError(
                    f"only identity packing found after {max_redraws} redraws"
                )
            continue
        # invariant: pairwise non-overlap
        for a in range(len(accepted)):
            for b in range(a + 1, len(accepted)):
                if segment_overlap(accepted[a], accepted[b], h):
                    raise AssignmentError("internal: overlapping assignment produced")
        return accepted


def preflight_pack_ok(donors: Sequence[int], m: int, h: int = H_DEFAULT) -> bool:
    """True iff pack_capacity(D) >= M (mandatory before NULL_STARTED when M>=1)."""
    if m == 0:
        return True
    return pack_capacity(donors, h) >= m


# ---------------------------------------------------------------------------
# Market helpers
# ---------------------------------------------------------------------------


def wilder_atr(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = ATR_PERIOD,
) -> np.ndarray:
    """Wilder ATR via ewm(alpha=1/period, adjust=False) on true range."""
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    n = len(close)
    tr = np.empty(n, dtype=float)
    tr[0] = high[0] - low[0]
    prev_c = close[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - prev_c), abs(low[i] - prev_c))
        prev_c = close[i]
    # pandas ewm matches protocol pin
    s = pd.Series(tr)
    atr = s.ewm(alpha=1.0 / period, adjust=False).mean().to_numpy(dtype=float)
    return atr


def day_ids_from_times(times: Sequence[Any]) -> np.ndarray:
    """Naive server day_id: YYYYMMDD int from timestamp (no tz conversion)."""
    ts = pd.to_datetime(pd.Series(list(times)))
    return (ts.dt.year * 10000 + ts.dt.month * 100 + ts.dt.day).to_numpy(dtype=np.int64)


def size_lots(
    balance: float,
    atr: float,
    *,
    sl_atr: float,
    risk_pct: float,
    lot_min: float,
    lot_step: float,
    lot_max: float,
    contract_size: float,
) -> float | None:
    """Risk-based lots; floor to step; cap max; never force min. None if invalid."""
    if not (np.isfinite(balance) and balance > 0):
        return None
    if not (np.isfinite(atr) and atr > 0):
        return None
    if not (np.isfinite(sl_atr) and sl_atr > 0 and contract_size > 0 and lot_step > 0):
        return None
    risk_cash = risk_pct * balance
    denom = sl_atr * atr * contract_size
    if denom <= 0 or not np.isfinite(denom):
        return None
    raw = risk_cash / denom
    if not np.isfinite(raw) or raw < lot_min:
        return None
    # floor to lot_step
    steps = np.floor(raw / lot_step + 1e-12)
    lots = float(steps * lot_step)
    lots = min(lots, lot_max)
    if lots < lot_min - 1e-15:
        return None
    # re-floor after cap
    lots = float(np.floor(lots / lot_step + 1e-12) * lot_step)
    if lots < lot_min - 1e-15:
        return None
    return float(lots)


# ---------------------------------------------------------------------------
# Events / trades
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Event:
    event_id: int
    t_star_idx: int
    t_entry_idx: int
    side: int
    atr_tstar: float
    lots: float
    spread_entry: float
    i_start: int
    i_end: int  # inclusive; = i_start + H - 1


@dataclass
class TradeResult:
    event_id: int
    entry_idx: int
    exit_idx: int
    side: int
    lots: float
    entry_price: float
    exit_price: float
    exit_reason: str
    pnl: float
    donor_id: int | None = None


@dataclass
class RealPathResult:
    events: list[Event]
    trades: list[TradeResult]
    equity: list[float]
    balances_at_entry: list[float]  # B_in used for each event (lot freeze)
    final_balance: float
    metrics: dict[str, float | int]


@dataclass
class NullTrialResult:
    trial_id: int
    assignment: list[int]
    trades: list[TradeResult]
    metrics: dict[str, float | int]
    equity: list[float] = field(default_factory=list)
    final_balance: float = 0.0


def round_trip_cost_cash(
    spread_points: float,
    *,
    lots: float,
    point_size: float,
    contract_size: float,
    commission_per_lot: float,
    slippage_points: float,
) -> float:
    """House RT cost (matches joint/single-frame families).

    ``(spread + 2*slippage) * point_size * contract_size * lots
      + 2 * commission_per_lot * lots``

    Rejects non-finite or negative inputs (no abs() laundering).
    """
    vals = {
        "spread_points": spread_points,
        "lots": lots,
        "point_size": point_size,
        "contract_size": contract_size,
        "commission_per_lot": commission_per_lot,
        "slippage_points": slippage_points,
    }
    for name, raw in vals.items():
        try:
            v = float(raw)
        except (TypeError, ValueError) as e:
            raise ProtocolError(f"invalid cost input {name}={raw!r}") from e
        if not np.isfinite(v):
            raise ProtocolError(f"non-finite cost input {name}={raw!r}")
        if v < 0:
            raise ProtocolError(f"negative cost input {name}={v}")
        vals[name] = v
    return (
        (vals["spread_points"] + 2.0 * vals["slippage_points"])
        * vals["point_size"]
        * vals["contract_size"]
        * vals["lots"]
        + 2.0 * vals["commission_per_lot"] * vals["lots"]
    )


def simulate_h_trade(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    *,
    entry_idx: int,
    side: int,
    lots: float,
    atr_tstar: float,
    sl_atr: float,
    tp_atr: float,
    spread_points: float,
    point_size: float,
    contract_size: float,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    h: int = H_DEFAULT,
    event_id: int = 0,
    donor_id: int | None = None,
) -> TradeResult:
    """Enter at open(entry_idx); SL→TP per bar; time-flat at close of entry+H-1."""
    n = len(open_)
    if entry_idx < 0 or entry_idx + h - 1 >= n:
        raise ProtocolError("entry window out of range")
    if side not in (-1, 1):
        raise ProtocolError(f"side must be ±1, got {side}")
    entry_price = float(open_[entry_idx])
    sl_dist = float(sl_atr) * float(atr_tstar)
    tp_dist = float(tp_atr) * float(atr_tstar)
    if side > 0:
        sl_price = entry_price - sl_dist
        tp_price = entry_price + tp_dist
    else:
        sl_price = entry_price + sl_dist
        tp_price = entry_price - tp_dist

    exit_idx = entry_idx + h - 1
    exit_price = float(close[exit_idx])
    exit_reason = "time"

    for k in range(h):
        i = entry_idx + k
        hi = float(high[i])
        lo = float(low[i])
        if side > 0:
            hit_sl = lo <= sl_price
            hit_tp = hi >= tp_price
        else:
            hit_sl = hi >= sl_price
            hit_tp = lo <= tp_price
        if hit_sl:
            exit_idx = i
            exit_price = sl_price
            exit_reason = "sl"
            break
        if hit_tp:
            exit_idx = i
            exit_price = tp_price
            exit_reason = "tp"
            break
        if k == h - 1:
            exit_idx = i
            exit_price = float(close[i])
            exit_reason = "time"

    gross = (exit_price - entry_price) * side * lots * contract_size
    cost = round_trip_cost_cash(
        spread_points,
        lots=lots,
        point_size=point_size,
        contract_size=contract_size,
        commission_per_lot=commission_per_lot,
        slippage_points=slippage_points,
    )
    pnl = float(gross - cost)
    return TradeResult(
        event_id=event_id,
        entry_idx=entry_idx,
        exit_idx=exit_idx,
        side=side,
        lots=lots,
        entry_price=entry_price,
        exit_price=exit_price,
        exit_reason=exit_reason,
        pnl=pnl,
        donor_id=donor_id,
    )


def metrics_from_pnls(
    pnls: Sequence[float],
    equity: Sequence[float] | None = None,
    *,
    start_balance: float = 10_000.0,
) -> dict[str, float | int]:
    """House PF: 0 if no trades; 99 if gross_loss==0 and gross_profit>0."""
    arr = [float(x) for x in pnls]
    n = len(arr)
    if n == 0:
        return {
            "n_trades": 0,
            "wins": 0,
            "losses": 0,
            "net_profit": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
        }
    wins = sum(1 for x in arr if x > 0)
    losses = sum(1 for x in arr if x < 0)
    gp = float(sum(x for x in arr if x > 0))
    gl = float(-sum(x for x in arr if x < 0))
    net = float(sum(arr))
    if gl == 0.0 and gp > 0.0:
        pf = 99.0
    elif gl == 0.0 and gp == 0.0:
        pf = 0.0
    else:
        pf = gp / gl if gl > 0 else 0.0
    if equity is None:
        eq = [start_balance]
        b = start_balance
        for p in arr:
            b += p
            eq.append(b)
    else:
        eq = [float(x) for x in equity]
    peak = eq[0]
    max_dd = 0.0
    for e in eq:
        peak = max(peak, e)
        if peak > 0:
            max_dd = max(max_dd, (peak - e) / peak)
    return {
        "n_trades": n,
        "wins": wins,
        "losses": losses,
        "net_profit": net,
        "win_rate": 100.0 * wins / n if n else 0.0,
        "profit_factor": float(pf),
        "max_drawdown_pct": float(max_dd * 100.0),
        "gross_profit": gp,
        "gross_loss": gl,
    }


def soft_pass_traded(
    metrics: dict[str, float | int],
    soft: dict[str, Any],
) -> bool:
    """Binary soft gate on the single traded book."""
    n_min = int(soft.get("n_trades_min", 0))
    pf_min = float(soft.get("profit_factor_min", 0.0))
    np_gt = float(soft.get("net_profit_gt", float("-inf")))
    dd_max = float(soft.get("max_drawdown_pct_max", 100.0))
    return (
        int(metrics["n_trades"]) >= n_min
        and float(metrics["profit_factor"]) >= pf_min
        and float(metrics["net_profit"]) > np_gt
        and float(metrics["max_drawdown_pct"]) <= dd_max
    )


# ---------------------------------------------------------------------------
# Real path
# ---------------------------------------------------------------------------


def admit_and_simulate_real(
    *,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    spread: np.ndarray,
    day_id: np.ndarray,
    signal_sides: np.ndarray,
    # signal_sides[i] in {-1,0,+1}; nonzero ⇒ candidate at bar i (t*)
    sl_atr: float = 1.5,
    tp_atr: float = 2.0,
    risk_pct: float = 0.01,
    lot_min: float = 0.01,
    lot_step: float = 0.01,
    lot_max: float = 0.5,
    contract_size: float = 100.0,
    point_size: float = 0.01,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    start_balance: float = 10_000.0,
    h: int = H_DEFAULT,
    atr_period: int = ATR_PERIOD,
) -> RealPathResult:
    """Build E under fixed-H occupancy + B_in lot sizing; execute T=M trades."""
    n = len(open_)
    if not (
        len(high) == n
        and len(low) == n
        and len(close) == n
        and len(spread) == n
        and len(day_id) == n
        and len(signal_sides) == n
    ):
        raise ProtocolError("OHLC/spread/day_id/signal length mismatch")
    atr = wilder_atr(high, low, close, period=atr_period)
    balance = float(start_balance)
    equity: list[float] = []
    events: list[Event] = []
    trades: list[TradeResult] = []
    balances_at_entry: list[float] = []
    reserved: list[tuple[int, int]] = []  # (i_start, i_end)
    open_trade: dict[str, Any] | None = None
    pending: Event | None = None

    def interval_free(i_start: int) -> bool:
        return all(not segment_overlap(i_start, a, h) for a, _b in reserved)

    for i in range(n):
        # --- entries at open (use carry-in balance already in `balance`) ---
        if pending is not None and pending.t_entry_idx == i:
            # lots already frozen at admission from B_in; do not recompute after exits
            open_trade = {
                "event": pending,
                "entry_price": float(open_[i]),
                "sl_price": (
                    float(open_[i]) - sl_atr * pending.atr_tstar
                    if pending.side > 0
                    else float(open_[i]) + sl_atr * pending.atr_tstar
                ),
                "tp_price": (
                    float(open_[i]) + tp_atr * pending.atr_tstar
                    if pending.side > 0
                    else float(open_[i]) - tp_atr * pending.atr_tstar
                ),
            }
            pending = None

        # --- intrabar exits ---
        if open_trade is not None:
            ev: Event = open_trade["event"]
            side = ev.side
            hi = float(high[i])
            lo = float(low[i])
            exit_price = None
            exit_reason = None
            if side > 0:
                if lo <= open_trade["sl_price"]:
                    exit_price = open_trade["sl_price"]
                    exit_reason = "sl"
                elif hi >= open_trade["tp_price"]:
                    exit_price = open_trade["tp_price"]
                    exit_reason = "tp"
            else:
                if hi >= open_trade["sl_price"]:
                    exit_price = open_trade["sl_price"]
                    exit_reason = "sl"
                elif lo <= open_trade["tp_price"]:
                    exit_price = open_trade["tp_price"]
                    exit_reason = "tp"
            if exit_price is None and i == ev.i_end:
                exit_price = float(close[i])
                exit_reason = "time"
            if exit_price is not None:
                gross = (exit_price - open_trade["entry_price"]) * side * ev.lots * contract_size
                cost = round_trip_cost_cash(
                    ev.spread_entry,
                    lots=ev.lots,
                    point_size=point_size,
                    contract_size=contract_size,
                    commission_per_lot=commission_per_lot,
                    slippage_points=slippage_points,
                )
                pnl = float(gross - cost)
                balance += pnl
                trades.append(
                    TradeResult(
                        event_id=ev.event_id,
                        entry_idx=ev.t_entry_idx,
                        exit_idx=i,
                        side=side,
                        lots=ev.lots,
                        entry_price=open_trade["entry_price"],
                        exit_price=float(exit_price),
                        exit_reason=str(exit_reason),
                        pnl=pnl,
                        donor_id=ev.t_entry_idx,
                    )
                )
                open_trade = None

        # mark equity (after exits; at most one open) — full floating MTM
        floating = 0.0
        if open_trade is not None:
            ev = open_trade["event"]
            floating = (
                (float(close[i]) - open_trade["entry_price"])
                * ev.side
                * ev.lots
                * contract_size
            )
        equity.append(balance + floating)

        # --- signal at close of i → candidate entry i+1 ---
        side_sig = int(signal_sides[i])
        if side_sig in (-1, 1) and pending is None:
            i_e = i + 1
            if i_e + h - 1 >= n:
                continue
            if int(day_id[i_e]) != int(day_id[i]):
                continue
            if any(int(day_id[i_e + k]) != int(day_id[i_e]) for k in range(h)):
                continue
            a = float(atr[i])
            if not (np.isfinite(a) and a > 0):
                continue
            if not interval_free(i_e):
                continue
            sp = float(spread[i_e])
            if not (np.isfinite(sp) and sp >= 0):
                continue
            # B_in(i_e) = balance after processing bar i (carry-in for next open)
            b_in = float(balance)
            lots = size_lots(
                b_in,
                a,
                sl_atr=sl_atr,
                risk_pct=risk_pct,
                lot_min=lot_min,
                lot_step=lot_step,
                lot_max=lot_max,
                contract_size=contract_size,
            )
            if lots is None:
                continue
            ev = Event(
                event_id=len(events),
                t_star_idx=i,
                t_entry_idx=i_e,
                side=side_sig,
                atr_tstar=a,
                lots=float(lots),
                spread_entry=sp,
                i_start=i_e,
                i_end=i_e + h - 1,
            )
            events.append(ev)
            reserved.append((ev.i_start, ev.i_end))
            balances_at_entry.append(b_in)
            pending = ev

    if len(trades) != len(events):
        raise ProtocolError(
            f"T={len(trades)} != M={len(events)}: admitted event failed to complete"
        )
    # order trades by event_id
    trades_sorted = sorted(trades, key=lambda t: t.event_id)
    m = metrics_from_pnls([t.pnl for t in trades_sorted], equity, start_balance=start_balance)
    return RealPathResult(
        events=events,
        trades=trades_sorted,
        equity=equity,
        balances_at_entry=balances_at_entry,
        final_balance=float(balance),
        metrics=m,
    )


def eligible_donors(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    spread: np.ndarray,
    day_id: np.ndarray,
    *,
    h: int = H_DEFAULT,
) -> list[int]:
    """§5.4 donor pool: same-day finite OHLC H-window, spread at entry ok."""
    n = len(open_)
    out: list[int] = []
    for i in range(0, n - h + 1):
        if any(int(day_id[i + k]) != int(day_id[i]) for k in range(h)):
            continue
        ok = True
        for k in range(h):
            j = i + k
            if not all(
                np.isfinite(float(x))
                for x in (open_[j], high[j], low[j], close[j])
            ):
                ok = False
                break
        if not ok:
            continue
        sp = float(spread[i])
        if not (np.isfinite(sp) and sp >= 0):
            continue
        out.append(i)
    return out


def execute_fixed_events_mtm(
    events: Sequence[Event],
    *,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    sl_atr: float,
    tp_atr: float,
    point_size: float,
    contract_size: float,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    start_balance: float = 10_000.0,
    h: int = H_DEFAULT,
    donor_by_event_id: dict[int, int] | None = None,
) -> tuple[list[TradeResult], list[float], float]:
    """Execute a fixed event list on a path with full floating-MTM equity.

    Chronology is **event reserved intervals** on the analysis calendar
    (``t_entry_idx`` / ``i_start`` / ``i_end``), not donor wall-clock order.
    Same bar order as the real path (§4.2): open entries → SL/TP → mark.
    """
    n = len(open_)
    by_entry: dict[int, Event] = {}
    for ev in events:
        if ev.t_entry_idx in by_entry:
            raise ProtocolError("duplicate entry index in fixed event list")
        by_entry[int(ev.t_entry_idx)] = ev

    balance = float(start_balance)
    equity: list[float] = []
    trades: list[TradeResult] = []
    open_trade: dict[str, Any] | None = None

    for i in range(n):
        if open_trade is None and i in by_entry:
            pending = by_entry[i]
            d_id = (
                int(donor_by_event_id[pending.event_id])
                if donor_by_event_id is not None
                else int(pending.t_entry_idx)
            )
            open_trade = {
                "event": pending,
                "entry_price": float(open_[i]),
                "sl_price": (
                    float(open_[i]) - sl_atr * pending.atr_tstar
                    if pending.side > 0
                    else float(open_[i]) + sl_atr * pending.atr_tstar
                ),
                "tp_price": (
                    float(open_[i]) + tp_atr * pending.atr_tstar
                    if pending.side > 0
                    else float(open_[i]) - tp_atr * pending.atr_tstar
                ),
                "donor_id": d_id,
            }

        if open_trade is not None:
            ev = open_trade["event"]
            side = ev.side
            hi = float(high[i])
            lo = float(low[i])
            exit_price = None
            exit_reason = None
            if side > 0:
                if lo <= open_trade["sl_price"]:
                    exit_price = open_trade["sl_price"]
                    exit_reason = "sl"
                elif hi >= open_trade["tp_price"]:
                    exit_price = open_trade["tp_price"]
                    exit_reason = "tp"
            else:
                if hi >= open_trade["sl_price"]:
                    exit_price = open_trade["sl_price"]
                    exit_reason = "sl"
                elif lo <= open_trade["tp_price"]:
                    exit_price = open_trade["tp_price"]
                    exit_reason = "tp"
            if exit_price is None and i == ev.i_end:
                exit_price = float(close[i])
                exit_reason = "time"
            if exit_price is not None:
                gross = (
                    (exit_price - open_trade["entry_price"])
                    * side
                    * ev.lots
                    * contract_size
                )
                cost = round_trip_cost_cash(
                    ev.spread_entry,
                    lots=ev.lots,
                    point_size=point_size,
                    contract_size=contract_size,
                    commission_per_lot=commission_per_lot,
                    slippage_points=slippage_points,
                )
                pnl = float(gross - cost)
                balance += pnl
                trades.append(
                    TradeResult(
                        event_id=ev.event_id,
                        entry_idx=ev.t_entry_idx,
                        exit_idx=i,
                        side=side,
                        lots=ev.lots,
                        entry_price=open_trade["entry_price"],
                        exit_price=float(exit_price),
                        exit_reason=str(exit_reason),
                        pnl=pnl,
                        donor_id=int(open_trade["donor_id"]),
                    )
                )
                open_trade = None

        floating = 0.0
        if open_trade is not None:
            ev = open_trade["event"]
            floating = (
                (float(close[i]) - open_trade["entry_price"])
                * ev.side
                * ev.lots
                * contract_size
            )
        equity.append(balance + floating)

    if len(trades) != len(events):
        raise ProtocolError(
            f"T={len(trades)} != M={len(events)}: fixed event failed to complete"
        )
    trades_sorted = sorted(trades, key=lambda t: t.event_id)
    return trades_sorted, equity, float(balance)


def _require_strict_int(name: str, val: Any) -> int:
    """JSON/python int only — reject bool (bool is a subclass of int)."""
    if isinstance(val, bool) or not isinstance(val, int):
        raise ProtocolError(f"{name} must be a non-bool int (got {val!r})")
    return int(val)


def validate_events_and_assignment(
    events: Sequence[Event],
    assignment: Sequence[int],
    *,
    h: int = H_DEFAULT,
    n_bars: int | None = None,
) -> None:
    """Structural invariants before any counted null trial (fail closed)."""
    if h < 1:
        raise ProtocolError(f"h must be >= 1, got {h}")
    m = len(events)
    if len(assignment) != m:
        raise ProtocolError(f"assignment length {len(assignment)} != M={m}")
    if m == 0:
        return

    event_ids: list[int] = []
    for i, ev in enumerate(events):
        eid = _require_strict_int(f"events[{i}].event_id", ev.event_id)
        event_ids.append(eid)
        i_start = _require_strict_int(f"events[{i}].i_start", ev.i_start)
        i_end = _require_strict_int(f"events[{i}].i_end", ev.i_end)
        t_entry = _require_strict_int(f"events[{i}].t_entry_idx", ev.t_entry_idx)
        if t_entry != i_start:
            raise ProtocolError(
                f"event_id={eid}: t_entry_idx={t_entry} must equal i_start={i_start}"
            )
        if i_end != i_start + h - 1:
            raise ProtocolError(
                f"event_id={eid}: i_end={i_end} must equal i_start+H-1="
                f"{i_start + h - 1}"
            )
        if n_bars is not None and (i_start < 0 or i_end >= n_bars):
            raise ProtocolError(
                f"event_id={eid}: reserved window [{i_start},{i_end}] "
                f"out of range for n_bars={n_bars}"
            )
        if ev.side not in (-1, 1):
            raise ProtocolError(f"event_id={eid}: side must be ±1 (got {ev.side!r})")
    if len(event_ids) != len(set(event_ids)):
        raise ProtocolError("event_id values must be unique")

    # Pairwise H-disjoint reserved event intervals
    starts = [int(ev.i_start) for ev in events]
    for a in range(m):
        for b in range(a + 1, m):
            if segment_overlap(starts[a], starts[b], h):
                raise ProtocolError(
                    f"event reserved intervals overlap: "
                    f"event_ids {event_ids[a]}@{starts[a]} and "
                    f"{event_ids[b]}@{starts[b]} (H={h})"
                )

    donors: list[int] = []
    for j, raw in enumerate(assignment):
        d = _require_strict_int(f"assignment[{j}]", raw)
        if d < 0:
            raise ProtocolError(f"assignment[{j}] donor_id={d} must be >= 0")
        if n_bars is not None and d + h - 1 >= n_bars:
            raise ProtocolError(
                f"assignment[{j}] donor_id={d} window out of range for n_bars={n_bars}"
            )
        donors.append(d)
    if len(donors) != len(set(donors)):
        raise ProtocolError(
            "assignment donor_ids must be unique (without-replacement packing)"
        )
    for a in range(m):
        for b in range(a + 1, m):
            if segment_overlap(donors[a], donors[b], h):
                raise ProtocolError(
                    f"assignment donor intervals overlap: "
                    f"{donors[a]} and {donors[b]} (H={h})"
                )


def transplant_donor_ohlc_into_event_windows(
    events: Sequence[Event],
    assignment: Sequence[int],
    *,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    spread: np.ndarray,
    h: int = H_DEFAULT,
) -> tuple[list[Event], np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[int, int]]:
    """§5.6: copy each donor's H-bar OHLC into the event's **reserved** interval.

    Preserves frozen event chronology (``t_entry_idx`` / ``i_start`` / ``i_end``).
    Does **not** re-time events to donor wall-clock indices — that would reorder
    equity realization relative to event order and distort DD.
    """
    n = len(open_)
    validate_events_and_assignment(events, assignment, h=h, n_bars=n)
    open_t = np.array(open_, dtype=float, copy=True)
    high_t = np.array(high, dtype=float, copy=True)
    low_t = np.array(low, dtype=float, copy=True)
    close_t = np.array(close, dtype=float, copy=True)
    out_events: list[Event] = []
    donor_by_event_id: dict[int, int] = {}
    for ev, donor in zip(events, assignment, strict=True):
        d = int(donor)
        for k in range(h):
            dst = ev.i_start + k
            src = d + k
            open_t[dst] = float(open_[src])
            high_t[dst] = float(high[src])
            low_t[dst] = float(low[src])
            close_t[dst] = float(close[src])
        sp = float(spread[d])
        if not (np.isfinite(sp) and sp >= 0):
            raise ProtocolError(f"invalid donor spread at {d}")
        # Keep real reserved indices; only costs source (spread) and OHLC path change.
        out_events.append(replace(ev, spread_entry=sp))
        donor_by_event_id[int(ev.event_id)] = d
    return out_events, open_t, high_t, low_t, close_t, donor_by_event_id


def run_null_trial(
    events: Sequence[Event],
    assignment: Sequence[int],
    *,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    spread: np.ndarray,
    sl_atr: float,
    tp_atr: float,
    point_size: float,
    contract_size: float,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    start_balance: float = 10_000.0,
    h: int = H_DEFAULT,
    trial_id: int = 0,
) -> NullTrialResult:
    """§5.6 path transplant; event-order MTM equity; require T=M.

    Donor H-bar OHLC is spliced into each event's reserved calendar window so
    trade realization order follows frozen event chronology (not donor time order).
    """
    mapped, o_t, h_t, l_t, c_t, donor_map = transplant_donor_ohlc_into_event_windows(
        events,
        assignment,
        open_=open_,
        high=high,
        low=low,
        close=close,
        spread=spread,
        h=h,
    )
    trades, equity, final_bal = execute_fixed_events_mtm(
        mapped,
        open_=o_t,
        high=h_t,
        low=l_t,
        close=c_t,
        sl_atr=sl_atr,
        tp_atr=tp_atr,
        point_size=point_size,
        contract_size=contract_size,
        commission_per_lot=commission_per_lot,
        slippage_points=slippage_points,
        start_balance=start_balance,
        h=h,
        donor_by_event_id=donor_map,
    )
    # Trades already event_id-sorted; P&L list must match that order for PF,
    # while equity/DD follows calendar event chronology (same order for H-disjoint).
    m = metrics_from_pnls(
        [t.pnl for t in trades], equity, start_balance=start_balance
    )
    return NullTrialResult(
        trial_id=trial_id,
        assignment=[int(x) for x in assignment],
        trades=trades,
        metrics=m,
        equity=equity,
        final_balance=final_bal,
    )


def metrics_close(
    a: dict[str, float | int],
    b: dict[str, float | int],
    *,
    atol: float = 1e-9,
    rtol: float = 1e-9,
) -> bool:
    """Float-tolerant metric equality for identity diagnostic."""
    keys = (
        "n_trades",
        "wins",
        "losses",
        "net_profit",
        "win_rate",
        "profit_factor",
        "max_drawdown_pct",
        "gross_profit",
        "gross_loss",
    )
    for k in keys:
        if k not in a or k not in b:
            return False
        av, bv = a[k], b[k]
        if isinstance(av, int) and isinstance(bv, int) and not isinstance(av, bool):
            if av != bv:
                return False
        else:
            if not np.isclose(float(av), float(bv), atol=atol, rtol=rtol):
                return False
    return True


def run_null_trials(
    events: Sequence[Event],
    donors: Sequence[int],
    *,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    spread: np.ndarray,
    base_seed: int,
    n_trials: int,
    sl_atr: float,
    tp_atr: float,
    point_size: float,
    contract_size: float,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    start_balance: float = 10_000.0,
    h: int = H_DEFAULT,
    max_redraws: int = MAX_ASSIGNMENT_REDRAWS,
) -> list[NullTrialResult]:
    """N counted trials with PCG64(base_seed+j); rejects full identity."""
    m = len(events)
    if m == 0:
        return []
    if not preflight_pack_ok(donors, m, h):
        raise AssignmentError(
            f"preflight pack_capacity={pack_capacity(donors, h)} < M={m}"
        )
    identity = [e.t_entry_idx for e in events]
    out: list[NullTrialResult] = []
    for j in range(n_trials):
        rng = np.random.Generator(np.random.PCG64(int(base_seed) + j))
        assignment = assign_null_donors(
            donors, m, identity, rng, h=h, max_redraws=max_redraws
        )
        trial = run_null_trial(
            events,
            assignment,
            open_=open_,
            high=high,
            low=low,
            close=close,
            spread=spread,
            sl_atr=sl_atr,
            tp_atr=tp_atr,
            point_size=point_size,
            contract_size=contract_size,
            commission_per_lot=commission_per_lot,
            slippage_points=slippage_points,
            start_balance=start_balance,
            h=h,
            trial_id=j,
        )
        out.append(trial)
    return out


def identity_diagnostic(
    events: Sequence[Event],
    *,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    spread: np.ndarray,
    sl_atr: float,
    tp_atr: float,
    point_size: float,
    contract_size: float,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
    start_balance: float = 10_000.0,
    h: int = H_DEFAULT,
) -> NullTrialResult:
    """Full identity assignment — diagnostic only, not a counted trial."""
    identity = [e.t_entry_idx for e in events]
    return run_null_trial(
        events,
        identity,
        open_=open_,
        high=high,
        low=low,
        close=close,
        spread=spread,
        sl_atr=sl_atr,
        tp_atr=tp_atr,
        point_size=point_size,
        contract_size=contract_size,
        commission_per_lot=commission_per_lot,
        slippage_points=slippage_points,
        start_balance=start_balance,
        h=h,
        trial_id=-1,
    )


def pvalue_one_sided(null_vals: Sequence[float], real: float) -> float:
    """(hits+1)/(n+1) where hits = count(null >= real)."""
    n = len(null_vals)
    if n == 0:
        return 1.0
    hits = sum(1 for v in null_vals if float(v) >= float(real))
    return float(hits + 1) / float(n + 1)
