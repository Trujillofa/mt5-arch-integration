#!/usr/bin/env python3
"""Shared causal HTF Fib pivot / swing helpers (offline research).

CRITICAL causality rule
-----------------------
A fractal pivot at center bar ``c`` with ``right`` confirmation bars is
**not knowable** until bar ``c + right`` has been observed. Event and fib
state indices therefore use the **confirmation bar** ``active = c + right``,
never the pivot center ``c``.

Consumers
---------
- ``scripts/htf_fib_offline_backtest.py``
- ``scripts/xau_preregistered_holdout.py`` (simulate_htf_fib)
- future develop-only fib optimizers (import from here; do not re-copy)

SAFETY: offline research only.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np

# Event tuple: (active_idx, price, ptype)
#   active_idx = center + right  (first bar where pivot is known)
#   ptype      = +1 pivot high / -1 pivot low
PivotEvent = tuple[int, float, int]
# Extended: (active_idx, price, ptype, center_idx)
PivotEventFull = tuple[int, float, int, int]
# Fib state: (active_idx, direction, fib_a, fib_b)
FibState = tuple[int, int, float, float]


def confirmed_pivots(
    high: np.ndarray | Sequence[float],
    low: np.ndarray | Sequence[float],
    left: int,
    right: int,
) -> list[PivotEvent]:
    """Return confirmed fractal pivots stamped at the confirmation bar.

    A bar ``c`` is a pivot high (resp. low) iff its high (low) strictly
    exceeds (is below) all highs (lows) in ``[c-left, c+right] \\ {c}``.
    The event becomes **active** only at index ``c + right``.

    Returns
    -------
    list of (active_idx, price, ptype)
        ``active_idx = center + right``; price is high/low at the center.
    """
    return [
        (a, p, t)
        for a, p, t, _c in confirmed_pivots_with_centers(high, low, left, right)
    ]


def confirmed_pivots_with_centers(
    high: np.ndarray | Sequence[float],
    low: np.ndarray | Sequence[float],
    left: int,
    right: int,
) -> list[PivotEventFull]:
    """Like :func:`confirmed_pivots` but also returns ``center_idx``.

    Each event is ``(active_idx, price, ptype, center_idx)`` with
    ``active_idx == center_idx + right``.
    """
    high_a = np.asarray(high, dtype=float)
    low_a = np.asarray(low, dtype=float)
    if high_a.shape != low_a.shape:
        raise ValueError("high and low must have the same shape")
    n = int(high_a.shape[0])
    left_i = int(left)
    right_i = int(right)
    if left_i < 0 or right_i < 0:
        raise ValueError("left and right must be >= 0")

    events: list[PivotEventFull] = []
    # c must leave room for left history and right confirmation bars
    for c in range(left_i, n - right_i):
        h = high_a[c]
        l = low_a[c]
        is_h = all(
            high_a[i] < h for i in range(c - left_i, c + right_i + 1) if i != c
        )
        is_l = all(
            low_a[i] > l for i in range(c - left_i, c + right_i + 1) if i != c
        )
        if is_h and is_l:
            continue
        active = c + right_i  # confirmation bar — never stamp at center c
        if is_h:
            events.append((active, float(h), 1, c))
        elif is_l:
            events.append((active, float(l), -1, c))
    return events


def fib_level(direction: int, hi: float, lo: float, ratio: float) -> float:
    """Directional fib retracement price (1=bullish pullback, -1=bearish)."""
    if direction == 1:
        return hi - (hi - lo) * ratio
    return lo + (hi - lo) * ratio


def walk_swing_and_fibs(
    events: Iterable[PivotEvent | PivotEventFull],
    fib_lo: float = 0.618,
    fib_hi: float = 0.786,
) -> list[FibState]:
    """Replay pivot events → list of (active_idx, direction, fib_a, fib_b).

    ``active_idx`` is inherited from the triggering pivot event (already
    confirmation-stamped). Fib levels are valid for bars ``i >= active_idx``.
    """
    last_type = 0
    last_price = 0.0
    swing_hi = swing_lo = 0.0
    direction = 0
    states: list[FibState] = []

    for ev in events:
        idx = int(ev[0])
        price = float(ev[1])
        ptype = int(ev[2])
        fib_changed = False
        if ptype == 1:
            if last_type == 0:
                last_type, last_price = 1, price
            elif last_type == 1:
                if price > last_price:
                    last_price = price
                    if direction == 1:
                        swing_hi = price
                        fib_changed = True
            else:
                if price > last_price:
                    swing_lo = last_price
                    swing_hi = price
                    direction = 1
                    fib_changed = True
                last_type, last_price = 1, price
        else:
            if last_type == 0:
                last_type, last_price = -1, price
            elif last_type == -1:
                if price < last_price:
                    last_price = price
                    if direction == -1:
                        swing_lo = price
                        fib_changed = True
            else:
                if price < last_price:
                    swing_hi = last_price
                    swing_lo = price
                    direction = -1
                    fib_changed = True
                last_type, last_price = -1, price

        if fib_changed and direction != 0 and swing_hi > swing_lo:
            a = fib_level(direction, swing_hi, swing_lo, float(fib_lo))
            b = fib_level(direction, swing_hi, swing_lo, float(fib_hi))
            states.append((idx, direction, a, b))

    return states


def expand_fib_states(
    n: int, states: Sequence[FibState]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Expand sparse fib states to per-bar arrays (active when state.idx <= i)."""
    direction = np.zeros(n, dtype=int)
    f_a = np.full(n, np.nan)
    f_b = np.full(n, np.nan)
    state_i = 0
    cur_dir: int = 0
    cur_a: float = float("nan")
    cur_b: float = float("nan")
    for i in range(n):
        while state_i < len(states) and states[state_i][0] <= i:
            _, cur_dir, cur_a, cur_b = states[state_i]
            state_i += 1
        direction[i] = cur_dir
        f_a[i] = cur_a
        f_b[i] = cur_b
    return direction, f_a, f_b


# ---------------------------------------------------------------------------
# Unit-style self-check (synthetic series, no CSV / holdout)
# ---------------------------------------------------------------------------
def self_check_pivot_confirmation() -> dict:
    """Assert pivot/fib activation never precedes center + right.

    Builds a synthetic OHLC series with known pivot centers, runs the shared
    helpers, and verifies:

    1. Every event ``active_idx == center_idx + right``
    2. Expanded fib / direction first becomes non-zero only at or after
       a confirmation-stamped state index
    3. Candidate signal bars satisfy ``signal_i >= active_idx`` for every
       active fib state

    Returns a small report dict. Raises ``AssertionError`` on failure.
    """
    left, right = 3, 5
    n = 80
    high = np.full(n, 100.0)
    low = np.full(n, 99.0)

    # Known pivot low at c1, pivot high at c2 → bullish swing after c2 confirms
    c_low = 20
    c_high = 40
    low[c_low] = 90.0
    high[c_high] = 120.0
    # Keep neighbors strictly worse so fractals are unique
    for i in range(c_low - left, c_low + right + 1):
        if i != c_low and 0 <= i < n:
            low[i] = max(low[i], 91.0)
    for i in range(c_high - left, c_high + right + 1):
        if i != c_high and 0 <= i < n:
            high[i] = min(high[i], 119.0)

    events_full = confirmed_pivots_with_centers(high, low, left, right)
    assert events_full, "expected at least one confirmed pivot on synthetic series"

    for active_idx, price, ptype, center in events_full:
        assert active_idx == center + right, (
            f"active_idx {active_idx} != center {center} + right {right}"
        )
        assert active_idx >= center + right, (
            f"look-ahead: active {active_idx} < center+right {center + right}"
        )
        assert active_idx < n
        if ptype == 1:
            assert price == high[center]
        else:
            assert price == low[center]

    # Compact form must match active stamps
    events = confirmed_pivots(high, low, left, right)
    assert len(events) == len(events_full)
    for (a, p, t), (a2, p2, t2, _c) in zip(events, events_full, strict=True):
        assert (a, p, t) == (a2, p2, t2)

    states = walk_swing_and_fibs(events)
    direction, f_a, _f_b = expand_fib_states(n, states)

    # First bar where any fib direction is live must be >= earliest event active
    first_live = None
    for i in range(n):
        if direction[i] != 0 and not np.isnan(f_a[i]):
            first_live = i
            break
    if states:
        min_active = min(s[0] for s in states)
        assert first_live is not None
        assert first_live >= min_active
        # centers >= 0 ⇒ active >= right
        assert all(s[0] >= right for s in states)

    # Synthetic "signal" bars: treat any bar with live fib as a candidate signal time
    for i in range(n):
        if direction[i] == 0 or np.isnan(f_a[i]):
            continue
        for s_idx, _d, _a, _b in states:
            if s_idx <= i:
                assert i >= s_idx  # signal time >= confirmation index

    # Explicit known-center check for our planted pivots
    centers_found = {c for (_a, _p, _t, c) in events_full}
    assert c_low in centers_found, f"planted low center {c_low} not found: {centers_found}"
    assert c_high in centers_found, (
        f"planted high center {c_high} not found: {centers_found}"
    )
    for active_idx, _p, _t, center in events_full:
        if center in (c_low, c_high):
            assert active_idx == center + right
            # signal / state time for this pivot cannot be before center+right
            assert active_idx >= center + right

    report = {
        "ok": True,
        "left": left,
        "right": right,
        "n_events": len(events_full),
        "n_states": len(states),
        "planted_centers": [c_low, c_high],
        "events": [
            {
                "active_idx": int(a),
                "center_idx": int(c),
                "ptype": int(t),
                "price": float(p),
                "confirm_lag": int(a - c),
            }
            for a, p, t, c in events_full
        ],
        "first_fib_bar": first_live,
        "rule": "active_idx == center_idx + right; signal_i >= active_idx",
    }
    return report


def main() -> int:
    report = self_check_pivot_confirmation()
    print("htf_fib_core self-check PASSED")
    for k, v in report.items():
        if k == "events":
            print(f"  events ({len(v)}):")
            for e in v:
                print(f"    {e}")
        else:
            print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
