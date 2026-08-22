#!/usr/bin/env python3
"""Bias-sanity gates for offline research metrics (simulator / diagnostic).

Ported from ctrader-trading-agent ``detect_bias_warnings`` (2026-04-08 same-bar
exit shelving). Compatible with RESEARCH_IDLE — validation only; does not
select, retune, or authorize screens.

Also flags thin-n CLEARS-FRICTION / COST-BOUND on the signal-edge diagnostic so
n≈80–92 “clears” need a skeptic pass (or are auto-warned) before anyone treats
them as actionable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# Thresholds: shapes that historically came from look-ahead / tiny-sample luck.
BIAS_FIRST_BAR_EXIT_MAX = 0.40
BIAS_SMALL_SAMPLE_WR_MAX = 0.75
BIAS_SMALL_SAMPLE_MIN_TRADES = 100
# Diagnostic: do not trust friction-clearing / cost-bound labels below this n.
BIAS_THIN_EDGE_VERDICT_MIN_N = 100


class _HasBiasFields(Protocol):
    trade_count: int
    win_rate: float
    first_bar_exit_pct: float


@dataclass(frozen=True)
class SimBiasMetrics:
    """Minimal metrics bag for simulator-style bias checks."""

    trade_count: int
    win_rate: float
    first_bar_exit_pct: float = 0.0


def detect_bias_warnings(metrics: _HasBiasFields) -> tuple[str, ...]:
    """Flag metric shapes that historically came from look-ahead bias.

    The 2026-04-08 shelving was driven by a backtest whose ~52% same-bar exit
    rate went undetected until manual audit. These gates refuse that class of
    results automatically.
    """
    warnings: list[str] = []
    if metrics.trade_count <= 0:
        return ()
    if metrics.first_bar_exit_pct > BIAS_FIRST_BAR_EXIT_MAX:
        warnings.append(
            f"first_bar_exit_pct={metrics.first_bar_exit_pct:.1%} exceeds "
            f"{BIAS_FIRST_BAR_EXIT_MAX:.0%}: likely look-ahead bias "
            f"(exits clustering on entry-bar evaluation)"
        )
    if (
        metrics.win_rate > BIAS_SMALL_SAMPLE_WR_MAX
        and metrics.trade_count < BIAS_SMALL_SAMPLE_MIN_TRADES
    ):
        warnings.append(
            f"win_rate={metrics.win_rate:.1%} with only {metrics.trade_count} trades "
            f"(need >= {BIAS_SMALL_SAMPLE_MIN_TRADES} before trusting WR > "
            f"{BIAS_SMALL_SAMPLE_WR_MAX:.0%})"
        )
    return tuple(warnings)


def detect_edge_verdict_warnings(*, verdict: str, n_signals: int) -> tuple[str, ...]:
    """Warn when a positive edge label sits on a thin sample.

    Would have auto-flagged the triage CLEARS-FRICTION rows at n=80 and n=92.
    """
    if n_signals <= 0:
        return ()
    if verdict in ("CLEARS-FRICTION", "COST-BOUND", "CLEARS-PAPER-RT") and (
        n_signals < BIAS_THIN_EDGE_VERDICT_MIN_N
    ):
        return (
            f"verdict={verdict} with n_signals={n_signals} "
            f"< {BIAS_THIN_EDGE_VERDICT_MIN_N}: thin-sample positive label — "
            f"require skeptic / multiplicity check before any follow-up",
        )
    return ()
