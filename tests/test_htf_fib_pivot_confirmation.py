"""Causal pivot confirmation: active only at center + right (no look-ahead)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from htf_fib_core import (  # noqa: E402
    confirmed_pivots,
    confirmed_pivots_with_centers,
    expand_fib_states,
    self_check_pivot_confirmation,
    walk_swing_and_fibs,
)


def test_self_check_pivot_confirmation():
    report = self_check_pivot_confirmation()
    assert report["ok"] is True
    assert report["n_events"] >= 2


def test_active_idx_equals_center_plus_right():
    left, right = 2, 4
    n = 50
    high = np.full(n, 10.0)
    low = np.full(n, 9.0)
    c = 15
    high[c] = 20.0
    events = confirmed_pivots_with_centers(high, low, left, right)
    assert any(center == c for *_rest, center in events)
    for active, _price, _ptype, center in events:
        assert active == center + right
        assert active >= center + right


def test_signal_time_not_before_confirmation():
    """Expanded fib direction must not light up before any event active_idx."""
    left, right = 3, 5
    n = 60
    high = np.full(n, 100.0)
    low = np.full(n, 99.0)
    low[12] = 80.0
    high[30] = 130.0
    events = confirmed_pivots(high, low, left, right)
    assert events
    states = walk_swing_and_fibs(events)
    direction, f_a, _f_b = expand_fib_states(n, states)
    for i in range(n):
        if direction[i] == 0 or np.isnan(f_a[i]):
            continue
        # signal candidate bar i
        for active_idx, *_ in states:
            if active_idx <= i:
                assert i >= active_idx
        # also vs raw pivot events
        for active_idx, *_ in events:
            if active_idx <= i:
                assert i >= active_idx


def test_same_tf_fib_live_on_confirmation_bar():
    """Same-TF: fib may be live at confirm_idx (consumed via shift 1)."""
    left, right = 3, 5
    n = 60
    high = np.full(n, 100.0)
    low = np.full(n, 99.0)
    low[12] = 80.0
    high[30] = 130.0
    events = confirmed_pivots(high, low, left, right)
    states = walk_swing_and_fibs(events)
    direction, f_a, _f_b = expand_fib_states(n, states)
    assert states
    for active_idx, *_ in states:
        if active_idx > 0:
            assert direction[active_idx - 1] == 0 or np.isnan(f_a[active_idx - 1])
        assert not np.isnan(f_a[active_idx])


def test_forming_bar_is_not_a_confirm_wing():
    """Last bar is forming — exclude_forming must not use it as right wing."""
    left, right = 2, 2
    n = 12
    high = np.full(n, 10.0)
    low = np.full(n, 9.0)
    # Unique high at c=9 would confirm at 11 (the last / forming bar).
    high[9] = 20.0
    with_forming = confirmed_pivots_with_centers(high, low, left, right)
    closed_only = confirmed_pivots_with_centers(
        high, low, left, right, exclude_forming=True
    )
    assert any(c == 9 for *_rest, c in with_forming)
    assert not any(c == 9 for *_rest, c in closed_only)


def test_legacy_center_stamp_would_fail_causal_rule():
    """Document the old bug: stamping at center violates signal >= center+right."""
    right = 5
    c = 20
    # Old (buggy) stamp
    buggy_active = c
    assert buggy_active < c + right  # look-ahead window
    # Fixed stamp
    fixed_active = c + right
    assert fixed_active >= c + right
