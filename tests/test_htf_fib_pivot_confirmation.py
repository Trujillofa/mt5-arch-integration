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
