"""Offline HTF Fib runner: fill contract, lock tamper, holdout cap."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from htf_fib_offline_backtest import (  # noqa: E402
    LOCK_PATH,
    load_offline_lock,
    refuse_holdout_selection,
    refuse_mutated_htf_offline_lock,
    simulate_from_signals,
)


def test_htf_offline_lock_stays_research_only():
    lock = load_offline_lock()
    assert lock["promote"] is False
    assert lock["live_go"] is False
    refuse_mutated_htf_offline_lock(lock)
    bad = dict(lock)
    bad["promote"] = True
    with pytest.raises(SystemExit, match="promote"):
        refuse_mutated_htf_offline_lock(bad)
    slip = dict(lock)
    slip["book"] = dict(lock["book"])
    slip["book"]["slippage_points"] = 10.0
    with pytest.raises(SystemExit, match="slippage"):
        refuse_mutated_htf_offline_lock(slip)


def test_htf_offline_holdout_cap_refused_unless_unbounded():
    refuse_holdout_selection("2025-01-01", unbounded=False)
    with pytest.raises(SystemExit, match="holdout"):
        refuse_holdout_selection("2026-01-01", unbounded=False)
    refuse_holdout_selection("2026-08-01", unbounded=True)


def test_htf_offline_does_not_exit_on_entry_bar():
    n = 8
    signal = np.zeros(n, dtype=int)
    signal[3] = 1
    close = np.full(n, 1.10)
    high = np.full(n, 1.10)
    low = np.full(n, 1.10)
    atr = np.full(n, 0.01)
    high[3] = 1.50
    low[3] = 0.50
    trades = simulate_from_signals(signal, close, high, low, atr)
    assert len(trades) == 1
    assert trades[0].entry_i == 3
    assert trades[0].entry == pytest.approx(1.10)
    assert trades[0].exit_i != 3


def test_htf_offline_sl_hits_on_next_bar():
    n = 8
    signal = np.zeros(n, dtype=int)
    signal[3] = 1
    close = np.full(n, 1.10)
    high = np.full(n, 1.10)
    low = np.full(n, 1.10)
    atr = np.full(n, 0.01)
    low[4] = 0.50
    trades = simulate_from_signals(signal, close, high, low, atr)
    assert len(trades) == 1
    assert trades[0].reason == "sl"
    assert trades[0].exit_i == 4


def test_htf_offline_lock_file_is_slim():
    lock = json.loads(LOCK_PATH.read_text())
    assert "trades" not in lock
    assert lock["book"]["lots"] == 0.10
