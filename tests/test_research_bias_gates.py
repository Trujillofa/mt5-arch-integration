"""Regression tests for research bias-sanity gates.

Ported from ctrader-trading-agent tests/test_backtest_bias_gates.py.
Origin: 2026-04-08 same-bar exit shelving (~52% first-bar exits).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from research_bias_gates import (  # noqa: E402
    BIAS_FIRST_BAR_EXIT_MAX,
    BIAS_SMALL_SAMPLE_MIN_TRADES,
    BIAS_SMALL_SAMPLE_WR_MAX,
    BIAS_THIN_EDGE_VERDICT_MIN_N,
    SimBiasMetrics,
    detect_bias_warnings,
    detect_edge_verdict_warnings,
)


def test_high_first_bar_exit_rate_is_flagged():
    metrics = SimBiasMetrics(trade_count=500, win_rate=0.5, first_bar_exit_pct=0.52)
    warnings = detect_bias_warnings(metrics)
    assert any("first_bar_exit_pct" in w for w in warnings), warnings


def test_normal_first_bar_exit_rate_is_clean():
    metrics = SimBiasMetrics(trade_count=500, win_rate=0.5, first_bar_exit_pct=0.15)
    warnings = detect_bias_warnings(metrics)
    assert not any("first_bar_exit_pct" in w for w in warnings), warnings


def test_exactly_at_first_bar_threshold_is_clean():
    metrics = SimBiasMetrics(
        trade_count=500, win_rate=0.5, first_bar_exit_pct=BIAS_FIRST_BAR_EXIT_MAX
    )
    warnings = detect_bias_warnings(metrics)
    assert not any("first_bar_exit_pct" in w for w in warnings)


def test_high_win_rate_on_tiny_sample_is_flagged():
    metrics = SimBiasMetrics(trade_count=50, win_rate=0.80, first_bar_exit_pct=0.0)
    warnings = detect_bias_warnings(metrics)
    assert any("win_rate" in w for w in warnings), warnings


def test_high_win_rate_on_adequate_sample_is_clean():
    metrics = SimBiasMetrics(
        trade_count=BIAS_SMALL_SAMPLE_MIN_TRADES,
        win_rate=0.80,
        first_bar_exit_pct=0.0,
    )
    warnings = detect_bias_warnings(metrics)
    assert not any("win_rate" in w for w in warnings), warnings


def test_low_win_rate_on_tiny_sample_is_clean():
    metrics = SimBiasMetrics(trade_count=20, win_rate=0.55, first_bar_exit_pct=0.0)
    assert detect_bias_warnings(metrics) == ()


def test_empty_backtest_produces_no_warnings():
    metrics = SimBiasMetrics(trade_count=0, win_rate=0.0, first_bar_exit_pct=0.0)
    assert detect_bias_warnings(metrics) == ()


def test_thresholds_are_reasonable():
    assert BIAS_SMALL_SAMPLE_WR_MAX >= 0.70
    assert BIAS_FIRST_BAR_EXIT_MAX <= 0.50
    assert BIAS_THIN_EDGE_VERDICT_MIN_N >= 100


def test_thin_clears_friction_is_flagged():
    """Triage false CLEARS were n=80 and n=92 — must warn without skeptic."""
    for n in (80, 92):
        w = detect_edge_verdict_warnings(verdict="CLEARS-FRICTION", n_signals=n)
        assert w and "thin-sample" in w[0], (n, w)


def test_adequate_clears_is_clean():
    w = detect_edge_verdict_warnings(
        verdict="CLEARS-FRICTION", n_signals=BIAS_THIN_EDGE_VERDICT_MIN_N
    )
    assert w == ()


def test_dead_thin_is_clean():
    assert detect_edge_verdict_warnings(verdict="DEAD", n_signals=20) == ()
