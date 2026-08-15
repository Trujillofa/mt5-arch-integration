"""Phase B synthetic tests for multi_instrument_exogenous_predictor_v1.

No develop package, no thesis charter scoring, no registry, no paper/live.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import xau_exogenous_predictor_accounting as acct  # noqa: E402
import xau_exogenous_predictor_core as core  # noqa: E402
from xau_charter_protocol import (  # noqa: E402
    EXOGENOUS_NULL_IMPLEMENTATION_ID,
    EXOGENOUS_PREDICTOR_HARNESS_KIND,
    exogenous_joint_screen_refuse_message,
    multi_instrument_single_frame_refuse_message,
    validate_charter,
    validate_exogenous_predictor_charter,
)

# ---------------------------------------------------------------------------
# Fixtures / synthetic market
# ---------------------------------------------------------------------------


def _synthetic_bars(
    n: int = 80,
    *,
    start: str = "2024-01-02 00:00:00",
    seed: int = 0,
) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    times = pd.date_range(start, periods=n, freq="h")
    # mild random walk
    close = 2000.0 + np.cumsum(rng.normal(0, 0.5, size=n))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) + rng.uniform(0.1, 0.8, size=n)
    low = np.minimum(open_, close) - rng.uniform(0.1, 0.8, size=n)
    spread = np.full(n, 20.0)  # points
    day_id = core.day_ids_from_times(times)
    return {
        "time": times.to_numpy(),
        "open": open_.astype(float),
        "high": high.astype(float),
        "low": low.astype(float),
        "close": close.astype(float),
        "spread": spread,
        "day_id": day_id,
    }


def _minimal_exogenous_charter(**overrides: object) -> dict:
    ch: dict = {
        "family_id": "exog_synth_phase_b_only",
        "n_free_knobs": 0,
        "free_knobs": [],
        "frozen_at": "2026-08-14",
        "protocol_version": 2.2,
        "harness": {"kind": EXOGENOUS_PREDICTOR_HARNESS_KIND},
        "instrument": {
            "symbols": ["XAUUSD", "EURUSD"],
            "traded_symbols": ["XAUUSD"],
            "predictor_symbols": ["EURUSD"],
            "multi_symbol_in_scope": True,
            "per_symbol_meta": {
                "XAUUSD": {
                    "point_size": 0.01,
                    "contract_size": 100.0,
                    "digits": 2,
                },
                "EURUSD": {
                    "point_size": 1e-5,
                    "contract_size": 100_000.0,
                    "digits": 5,
                },
            },
            "data_package": {"package_id": "synth_not_scored"},
        },
        "analysis_calendar": {"mode": "intersection_only"},
        "gates": {
            "primary_n_passers": "soft",
            "soft": {
                "n_trades_min": 1,
                "profit_factor_min": 1.0,
                "net_profit_gt": -1e9,
                "max_drawdown_pct_max": 99.0,
            },
        },
        "null": {
            "method": EXOGENOUS_NULL_IMPLEMENTATION_ID,
            "implementation_id": EXOGENOUS_NULL_IMPLEMENTATION_ID,
            "n_trials": 999,
            "base_seed": 20260814,
        },
        "multiplicity": {
            "method": "finite_catalog_bonferroni_open_catalog",
            "K_prior": 8,
            "K": 9,
            "alpha_uncorrected": 0.05,
            "alpha_adjusted": 0.05 / 9,
            "prior_scored_family_ids": [
                "tod_london_ny_flat",
                "server_hour_window_flat",
                "early_server_range_break_flat",
                "day_open_reclaim_flat",
                "joint_london_open_cosign_fade_flat",
                "bb_rsi",
                "Donchian",
                "prior_day_high_break",
            ],
            "pass_status": "provisional_while_catalog_open",
            "paper_live_while_open": False,
            "revalidation_on_K_increase": True,
            "identity_excluded_from_null_trials": True,
        },
        "fixed": {
            "costs": {
                "commission_per_lot": 0.0,
                "slippage_points": 0.0,
                "spread_col": "spread",
                "account_type": "STANDARD_STP",
                "login": 27496181,
                "server": "VantageMarkets-Live 5",
                "cost_label": "account_matched_spread_commission_only",
                "costs_document_sha256": "a" * 64,
            },
            "H": 3,
            "entry": "next_bar_open",
            "same_day_hold": True,
        },
        "rule": {
            "intraday_flat": True,
            "exit": "sl_tp_time_h3",
            "hold_bars": 3,
            "entry": "next_bar_open",
            "same_day_hold": True,
        },
    }
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(ch.get(k), dict):
            ch[k] = {**ch[k], **v}
        else:
            ch[k] = v
    return ch


# ---------------------------------------------------------------------------
# Geometry / packing
# ---------------------------------------------------------------------------


def test_segment_overlap_adjacent_h3():
    assert core.segment_overlap(0, 1, 3) is True
    assert core.segment_overlap(0, 2, 3) is True
    assert core.segment_overlap(0, 3, 3) is False
    assert core.segment_overlap(0, 0, 3) is True


def test_pack_capacity_adjacent_donors_h3_m2_refuses():
    d = [0, 1, 2]
    assert core.pack_capacity(d, 3) == 1
    assert core.preflight_pack_ok(d, m=2, h=3) is False


def test_pack_capacity_spaced_donors():
    d = [0, 3, 6]
    assert core.pack_capacity(d, 3) == 3
    assert core.preflight_pack_ok(d, m=2, h=3) is True


def test_assign_null_never_segment_overlaps():
    d = [0, 3, 6, 9, 12]
    m = 2
    identity = [0, 3]
    for j in range(50):
        rng = np.random.Generator(np.random.PCG64(1000 + j))
        a = core.assign_null_donors(d, m, identity, rng, h=3)
        assert len(a) == m
        assert a != identity
        assert not core.segment_overlap(a[0], a[1], 3)


def test_forced_identity_redraw():
    """RNG that would yield identity-first must redraw; stored ≠ identity."""
    d = [0, 3, 6]
    m = 2
    identity = [0, 3]

    class IdentityFirstRng(np.random.Generator):
        def __init__(self):
            super().__init__(np.random.PCG64(0))
            self.calls = 0

        def permutation(self, n):  # type: ignore[override]
            self.calls += 1
            if self.calls == 1:
                # order that packs to identity [0,3]
                return np.array([0, 1, 2])
            return np.array([2, 0, 1])  # packs [6,0] or similar non-identity

    rng = IdentityFirstRng()
    a = core.assign_null_donors(d, m, identity, rng, h=3)
    assert a != identity
    assert rng.calls >= 2


# ---------------------------------------------------------------------------
# Real path occupancy / lookahead
# ---------------------------------------------------------------------------


def test_occupancy_rejects_adjacent_entries():
    bars = _synthetic_bars(60, seed=1)
    n = len(bars["open"])
    signals = np.zeros(n, dtype=int)
    # signal at 20 and 21 → entries 21 and 22 (adjacent) with H=3
    signals[20] = 1
    signals[21] = 1
    real = core.admit_and_simulate_real(
        open_=bars["open"],
        high=bars["high"],
        low=bars["low"],
        close=bars["close"],
        spread=bars["spread"],
        day_id=bars["day_id"],
        signal_sides=signals,
        h=3,
    )
    assert len(real.events) == 1
    assert real.events[0].t_entry_idx == 21
    assert len(real.trades) == 1


def test_early_exit_does_not_free_interval():
    bars = _synthetic_bars(60, seed=2)
    n = len(bars["open"])
    # Force SL on entry+1 by slamming low after a long entry
    open_ = bars["open"].copy()
    high = bars["high"].copy()
    low = bars["low"].copy()
    close = bars["close"].copy()
    i_entry = 25
    open_[i_entry] = 2000.0
    high[i_entry] = 2000.5
    low[i_entry] = 1999.5
    close[i_entry] = 2000.0
    # bar entry+1: deep low → SL
    open_[i_entry + 1] = 2000.0
    high[i_entry + 1] = 2000.2
    low[i_entry + 1] = 1000.0  # hit any reasonable SL
    close[i_entry + 1] = 1000.0
    signals = np.zeros(n, dtype=int)
    signals[i_entry - 1] = 1  # entry at 25
    signals[i_entry + 1] = 1  # would want entry 26 — still inside reserved [25,27]
    real = core.admit_and_simulate_real(
        open_=open_,
        high=high,
        low=low,
        close=close,
        spread=bars["spread"],
        day_id=bars["day_id"],
        signal_sides=signals,
        h=3,
        sl_atr=1.0,
        tp_atr=2.0,
        risk_pct=0.01,
    )
    assert len(real.events) == 1
    assert real.trades[0].exit_reason == "sl"
    assert real.trades[0].exit_idx == i_entry + 1


def test_lots_use_b_in_not_post_sl_on_entry_bar():
    # Stay within one calendar day so H-window same-day checks pass.
    bars = _synthetic_bars(24, seed=3, start="2024-01-03 00:00:00")
    n = len(bars["open"])
    open_ = bars["open"].copy()
    high = bars["high"].copy()
    low = bars["low"].copy()
    close = bars["close"].copy()
    # First: signal 5 → entry 6, reserved [6,8]
    # Second: signal 8 → entry 9 (=6+H)
    signals = np.zeros(n, dtype=int)
    signals[5] = 1
    signals[8] = 1
    real = core.admit_and_simulate_real(
        open_=open_,
        high=high,
        low=low,
        close=close,
        spread=bars["spread"],
        day_id=bars["day_id"],
        signal_sides=signals,
        h=3,
        start_balance=10_000.0,
    )
    assert len(real.events) == 2
    assert real.events[1].t_entry_idx == real.events[0].t_entry_idx + 3
    # Mutate entry-bar extremes for second event — frozen lots must not change
    e1 = real.events[1]
    lots_frozen = e1.lots
    high2 = high.copy()
    low2 = low.copy()
    low2[e1.t_entry_idx] = low2[e1.t_entry_idx] - 500.0
    high2[e1.t_entry_idx] = high2[e1.t_entry_idx] + 500.0
    real2 = core.admit_and_simulate_real(
        open_=open_,
        high=high2,
        low=low2,
        close=close,
        spread=bars["spread"],
        day_id=bars["day_id"],
        signal_sides=signals,
        h=3,
        start_balance=10_000.0,
    )
    assert len(real2.events) == 2
    assert real2.events[1].lots == lots_frozen


def test_h_disjoint_pair_t_equals_m():
    bars = _synthetic_bars(70, seed=4)
    n = len(bars["open"])
    signals = np.zeros(n, dtype=int)
    signals[30] = 1
    signals[33] = 1  # entry 31 and 34 = 31+3
    real = core.admit_and_simulate_real(
        open_=bars["open"],
        high=bars["high"],
        low=bars["low"],
        close=bars["close"],
        spread=bars["spread"],
        day_id=bars["day_id"],
        signal_sides=signals,
        h=3,
    )
    assert len(real.events) == 2
    assert len(real.trades) == 2
    e0, e1 = real.events
    assert not core.segment_overlap(e0.t_entry_idx, e1.t_entry_idx, 3)
    assert real.metrics["n_trades"] == 2


def test_null_trials_t_equals_m_and_no_identity():
    bars = _synthetic_bars(100, seed=5)
    n = len(bars["open"])
    signals = np.zeros(n, dtype=int)
    for t in (20, 30, 40, 50):
        signals[t] = 1
    real = core.admit_and_simulate_real(
        open_=bars["open"],
        high=bars["high"],
        low=bars["low"],
        close=bars["close"],
        spread=bars["spread"],
        day_id=bars["day_id"],
        signal_sides=signals,
        h=3,
    )
    assert len(real.events) >= 2
    donors = core.eligible_donors(
        bars["open"],
        bars["high"],
        bars["low"],
        bars["close"],
        bars["spread"],
        bars["day_id"],
        h=3,
    )
    m = len(real.events)
    assert core.preflight_pack_ok(donors, m, 3)
    trials = core.run_null_trials(
        real.events,
        donors,
        open_=bars["open"],
        high=bars["high"],
        low=bars["low"],
        close=bars["close"],
        spread=bars["spread"],
        day_id=bars["day_id"],
        base_seed=42,
        n_trials=999,
        sl_atr=1.5,
        tp_atr=2.0,
        point_size=0.01,
        contract_size=100.0,
        h=3,
    )
    assert len(trials) == 999
    identity = [e.t_entry_idx for e in real.events]
    for tr in trials:
        assert tr.metrics["n_trades"] == m
        assert tr.assignment != identity
        for a in range(m):
            for b in range(a + 1, m):
                assert not core.segment_overlap(
                    tr.assignment[a], tr.assignment[b], 3
                )


def test_preflight_refuse_before_null_started(tmp_path: Path):
    """pack_capacity < M → no NULL_STARTED, r1 unburned."""
    d = [0, 1, 2]
    assert core.preflight_pack_ok(d, m=2, h=3) is False
    # accounting: screen may exist; null not armed
    acct.write_screen_started(tmp_path, family_id="synth")
    assert not (tmp_path / acct.NULL_STARTED_NAME).exists()
    # simulate preflight fail path
    report = acct.screen_phase_failure_report(
        tmp_path, reason="donor_preflight_pack_capacity", family_id="synth"
    )
    body = acct.load_json(report)
    assert body["r1_burned"] is False
    assert body["sealed_null_attempt"] is False


# ---------------------------------------------------------------------------
# Dual accounting
# ---------------------------------------------------------------------------


def test_screen_started_before_load_failure_no_r1_burn(tmp_path: Path):
    acct.write_screen_started(tmp_path, family_id="f1", package_id="p")
    assert (tmp_path / "SCREEN_STARTED.json").is_file()
    marker = acct.load_json(tmp_path / "SCREEN_STARTED.json")
    assert marker["execution_state"] == "SCREEN_STARTED"
    assert marker["r1_burned"] is False
    # crash mid-score
    rep = acct.screen_phase_failure_report(tmp_path, reason="mid_score_raise", family_id="f1")
    body = acct.load_json(rep)
    assert body["disposition"] == "FAILED_RUN_UNKNOWN"
    assert body["r1_burned"] is False
    assert body["sealed_null_attempt"] is False


def test_null_started_failure_burns_r1(tmp_path: Path):
    acct.write_screen_started(tmp_path, family_id="f1")
    acct.write_null_started(tmp_path, family_id="f1", m=2, n_null_planned=999)
    rep = acct.null_phase_failure_report(tmp_path, reason="mid_trial_raise", family_id="f1")
    body = acct.load_json(rep)
    assert body["r1_burned"] is True
    assert body["sealed_null_attempt"] is True
    assert body["n_null_executed"] is None


def test_refuse_overwrite_started(tmp_path: Path):
    acct.write_screen_started(tmp_path, family_id="f1")
    with pytest.raises(FileExistsError):
        acct.write_screen_started(tmp_path, family_id="f1")


# ---------------------------------------------------------------------------
# Validator / refuse dispatch
# ---------------------------------------------------------------------------


def test_validate_exogenous_charter_ok():
    ch = _minimal_exogenous_charter()
    errs = validate_exogenous_predictor_charter(ch)
    assert errs == [], errs


def test_zero_predictors_rejected():
    ch = _minimal_exogenous_charter()
    ch["instrument"]["predictor_symbols"] = []
    ch["instrument"]["symbols"] = ["XAUUSD"]
    errs = validate_exogenous_predictor_charter(ch)
    assert any("predictor" in e for e in errs)


def test_multi_traded_rejected():
    ch = _minimal_exogenous_charter()
    ch["instrument"]["traded_symbols"] = ["XAUUSD", "EURUSD"]
    ch["instrument"]["predictor_symbols"] = ["GBPUSD"]
    ch["instrument"]["symbols"] = ["XAUUSD", "EURUSD", "GBPUSD"]
    ch["instrument"]["per_symbol_meta"]["GBPUSD"] = {
        "point_size": 1e-5,
        "contract_size": 100_000.0,
        "digits": 5,
    }
    errs = validate_exogenous_predictor_charter(ch)
    assert any("exactly one" in e for e in errs)


def test_overlap_roles_rejected():
    ch = _minimal_exogenous_charter()
    ch["instrument"]["predictor_symbols"] = ["XAUUSD"]
    errs = validate_exogenous_predictor_charter(ch)
    assert any("disjoint" in e for e in errs)


def test_wrong_null_method_rejected():
    ch = _minimal_exogenous_charter()
    ch["null"]["method"] = "within_day_ohlc_increment_rotate_v1"
    ch["null"]["implementation_id"] = "within_day_ohlc_increment_rotate_v1"
    errs = validate_exogenous_predictor_charter(ch)
    assert any("conditional_fixed_signal_events_fixed_trades_v1" in e for e in errs)


def test_paper_live_while_open_rejected():
    ch = _minimal_exogenous_charter()
    ch["multiplicity"]["paper_live_while_open"] = True
    errs = validate_exogenous_predictor_charter(ch)
    assert any("paper_live" in e for e in errs)


def test_single_frame_refuses_exogenous():
    ch = _minimal_exogenous_charter()
    msg = multi_instrument_single_frame_refuse_message(ch)
    assert msg is not None
    assert "REFUSE_SINGLE_FRAME" in msg
    assert EXOGENOUS_PREDICTOR_HARNESS_KIND in msg


def test_joint_screen_refuses_exogenous():
    ch = _minimal_exogenous_charter()
    msg = exogenous_joint_screen_refuse_message(ch)
    assert msg is not None
    assert "REFUSE_JOINT_SCREEN" in msg


def test_validate_charter_routes_exogenous():
    ch = _minimal_exogenous_charter()
    errs = validate_charter(ch)
    # may still have other protocol fields; ensure not joint-only errors
    assert not any("joint_dependency_preserving" in e for e in errs)
    assert not any("binary_joint_gate_success" in e for e in errs)
    # method present and floor ok — should be clean or only unrelated
    exo_errs = [e for e in errs if "exogenous" in e.lower() or "predictor" in e.lower()]
    assert exo_errs == [], errs


def test_soft_pass_binary_n_passers():
    m_ok = {
        "n_trades": 5,
        "profit_factor": 1.2,
        "net_profit": 10.0,
        "max_drawdown_pct": 5.0,
    }
    soft = {
        "n_trades_min": 1,
        "profit_factor_min": 1.1,
        "net_profit_gt": 0.0,
        "max_drawdown_pct_max": 25.0,
    }
    assert core.soft_pass_traded(m_ok, soft) is True
    m_bad = {**m_ok, "profit_factor": 0.5}
    assert core.soft_pass_traded(m_bad, soft) is False
    n_passers = 1 if core.soft_pass_traded(m_ok, soft) else 0
    assert n_passers in (0, 1)


# ---------------------------------------------------------------------------
# Adversarial regressions (PR #11 re-review blockers)
# ---------------------------------------------------------------------------


def test_identity_metrics_match_real_mtm_dd():
    """Null identity must use full floating MTM equity (same DD as real)."""
    bars = _synthetic_bars(48, seed=11, start="2024-01-04 00:00:00")
    n = len(bars["open"])
    # Force a temporary adverse float before exit so MTM DD > 0.
    open_ = bars["open"].copy()
    high = bars["high"].copy()
    low = bars["low"].copy()
    close = bars["close"].copy()
    signals = np.zeros(n, dtype=int)
    signals[10] = 1  # entry 11
    open_[11] = 2000.0
    high[11] = 2001.0
    low[11] = 1999.0
    close[11] = 2000.5
    # mid-hold adverse mark (not SL if SL is wide)
    open_[12] = 2000.0
    high[12] = 2000.5
    low[12] = 1990.0
    close[12] = 1990.0
    open_[13] = 1990.0
    high[13] = 2005.0
    low[13] = 1989.0
    close[13] = 2004.0
    real = core.admit_and_simulate_real(
        open_=open_,
        high=high,
        low=low,
        close=close,
        spread=bars["spread"],
        day_id=bars["day_id"],
        signal_sides=signals,
        h=3,
        sl_atr=5.0,
        tp_atr=5.0,
        start_balance=10_000.0,
    )
    assert len(real.events) == 1
    assert float(real.metrics["max_drawdown_pct"]) > 0.0
    identity = [e.t_entry_idx for e in real.events]
    diag = core.identity_diagnostic(
        real.events,
        open_=open_,
        high=high,
        low=low,
        close=close,
        spread=bars["spread"],
        sl_atr=5.0,
        tp_atr=5.0,
        point_size=0.01,
        contract_size=100.0,
        h=3,
        start_balance=10_000.0,
    )
    assert diag.assignment == identity
    assert core.metrics_close(real.metrics, diag.metrics), (
        real.metrics,
        diag.metrics,
    )


def test_round_trip_cost_house_formula_and_rejects_invalid():
    # spread=10, slip=4, comm=4, lots=1, ps=0.01, cs=100 → RT=26 (not old 18)
    cost = core.round_trip_cost_cash(
        10.0,
        lots=1.0,
        point_size=0.01,
        contract_size=100.0,
        commission_per_lot=4.0,
        slippage_points=4.0,
    )
    assert cost == pytest.approx(26.0)
    with pytest.raises(core.ProtocolError, match="negative"):
        core.round_trip_cost_cash(
            -1.0,
            lots=1.0,
            point_size=0.01,
            contract_size=100.0,
            commission_per_lot=0.0,
            slippage_points=0.0,
        )
    with pytest.raises(core.ProtocolError, match="non-finite"):
        core.round_trip_cost_cash(
            float("nan"),
            lots=1.0,
            point_size=0.01,
            contract_size=100.0,
            commission_per_lot=0.0,
            slippage_points=0.0,
        )


def test_null_started_extra_cannot_override_reserved(tmp_path: Path):
    acct.write_null_started(
        tmp_path,
        family_id="f1",
        extra={
            "execution_state": "OK",
            "r1_burned": False,
            "sealed_null_attempt": False,
            "arms_r1_burn_on_failure": False,
            "note": "caller diagnostic ok",
        },
    )
    body = acct.load_json(tmp_path / "NULL_STARTED.json")
    assert body["execution_state"] == "NULL_STARTED"
    assert body["r1_burned"] is True  # consumed at arm time
    assert body["r1_burn_armed"] is True
    assert body["arms_r1_burn_on_failure"] is True
    assert body["sealed_null_attempt"] is True
    assert body["note"] == "caller diagnostic ok"


def test_null_failure_extra_cannot_unburn(tmp_path: Path):
    acct.write_null_started(tmp_path, family_id="f1")
    acct.null_phase_failure_report(
        tmp_path,
        reason="boom",
        family_id="f1",
        extra={
            "execution_state": "OK",
            "r1_burned": False,
            "sealed_null_attempt": False,
            "disposition": "PASS",
        },
    )
    body = acct.load_json(tmp_path / "FAILED_RUN_UNKNOWN.json")
    assert body["execution_state"] == "UNKNOWN"
    assert body["r1_burned"] is True
    assert body["sealed_null_attempt"] is True
    assert body["disposition"] == "FAILED_RUN_UNKNOWN"


def test_null_started_marker_only_crash_is_burned(tmp_path: Path):
    """Process dies after NULL_STARTED with no terminal → r1 burned."""
    acct.write_null_started(tmp_path, family_id="f1", m=2, n_null_planned=999)
    assert (tmp_path / "NULL_STARTED.json").is_file()
    assert not (tmp_path / "FAILED_RUN_UNKNOWN.json").exists()
    assert acct.infer_r1_burned_from_outdir(tmp_path) is True


def test_screen_started_marker_only_not_burned(tmp_path: Path):
    acct.write_screen_started(tmp_path, family_id="f1")
    assert acct.infer_r1_burned_from_outdir(tmp_path) is False


def test_validator_mutation_matrix_fail_closed():
    ch = _minimal_exogenous_charter()
    assert validate_exogenous_predictor_charter(ch) == []

    # missing multiplicity
    bad = _minimal_exogenous_charter()
    del bad["multiplicity"]
    assert any("multiplicity" in e for e in validate_exogenous_predictor_charter(bad))

    # string gate threshold
    bad = _minimal_exogenous_charter()
    bad["gates"]["soft"]["profit_factor_min"] = "1.1"
    assert any("profit_factor_min" in e for e in validate_exogenous_predictor_charter(bad))

    # NaN gate
    bad = _minimal_exogenous_charter()
    bad["gates"]["soft"]["max_drawdown_pct_max"] = float("nan")
    assert any(
        "max_drawdown_pct_max" in e for e in validate_exogenous_predictor_charter(bad)
    )

    # NaN point_size
    bad = _minimal_exogenous_charter()
    bad["instrument"]["per_symbol_meta"]["XAUUSD"]["point_size"] = float("nan")
    assert any("point_size" in e for e in validate_exogenous_predictor_charter(bad))

    # missing package pin
    bad = _minimal_exogenous_charter()
    del bad["instrument"]["data_package"]
    assert any("data_package" in e for e in validate_exogenous_predictor_charter(bad))

    # mismatched method vs implementation_id
    bad = _minimal_exogenous_charter()
    bad["null"]["method"] = "within_day_ohlc_increment_rotate_v1"
    # implementation_id remains canonical
    errs = validate_exogenous_predictor_charter(bad)
    assert any("must match" in e or "null.method" in e for e in errs)

    # missing H / entry contract
    bad = _minimal_exogenous_charter()
    bad["rule"] = {"intraday_flat": True}
    bad["fixed"] = {"costs": bad["fixed"]["costs"]}
    errs = validate_exogenous_predictor_charter(bad)
    assert any("hold_bars" in e or "H" in e for e in errs)
    assert any("entry" in e for e in errs)

    # K != K_prior+1
    bad = _minimal_exogenous_charter()
    bad["multiplicity"]["K"] = 8
    assert any("K_prior+1" in e for e in validate_exogenous_predictor_charter(bad))

    # noncanonical multiplicity method alias
    bad = _minimal_exogenous_charter()
    bad["multiplicity"]["method"] = "finite_catalog_bonferroni"
    assert any("aliases forbidden" in e for e in validate_exogenous_predictor_charter(bad))

    # bad costs
    bad = _minimal_exogenous_charter()
    bad["fixed"]["costs"]["commission_per_lot"] = "bad"
    assert any("commission_per_lot" in e for e in validate_exogenous_predictor_charter(bad))
    bad = _minimal_exogenous_charter()
    bad["fixed"]["costs"]["slippage_points"] = float("nan")
    assert any("slippage_points" in e for e in validate_exogenous_predictor_charter(bad))

    # contradictory H fields
    bad = _minimal_exogenous_charter()
    bad["rule"]["H"] = 3
    bad["fixed"]["H"] = 99
    assert any("disagree" in e for e in validate_exogenous_predictor_charter(bad))

    # duplicate symbols
    bad = _minimal_exogenous_charter()
    bad["instrument"]["symbols"] = ["XAUUSD", "XAUUSD"]
    bad["instrument"]["predictor_symbols"] = ["XAUUSD"]
    assert any("unique" in e for e in validate_exogenous_predictor_charter(bad))


def test_reversed_donor_assignment_event_order_dd():
    """Equity/DD follow frozen event chronology, not donor wall-clock order.

    Event0 reserved early, Event1 later. Reversed donors would reorder if
    executed by donor time; transplant keeps event-order realization.
    """
    n = 40
    open_ = np.full(n, 100.0)
    high = np.full(n, 101.0)
    low = np.full(n, 99.0)
    close = np.full(n, 100.0)
    spread = np.zeros(n)
    # Build two H=3 windows with deterministic P&L if entered long:
    # Window A at 10: time-exit +20 cash path via close mark...
    # Use fixed absolute prices so transplant is obvious.
    # Event0 entry=10: win +20 gross on 1 lot before costs if exit close=120...
    # Simpler: use simulate path with known pnls via execute after transplant.

    # Donor windows:
    # d=10: flat then exit at +20 price move (long)
    # d=20: flat then exit at -10 price move (long)
    for base, end_close in ((10, 120.0), (20, 90.0)):
        open_[base] = 100.0
        high[base] = 101.0
        low[base] = 99.0
        close[base] = 100.0
        open_[base + 1] = 100.0
        high[base + 1] = 101.0
        low[base + 1] = 99.0
        close[base + 1] = 100.0
        open_[base + 2] = 100.0
        high[base + 2] = max(100.0, end_close) + 1
        low[base + 2] = min(100.0, end_close) - 1
        close[base + 2] = end_close

    # Real events at reserved 10 and 20 (identity donors) — construct Event objs
    e0 = core.Event(
        event_id=0,
        t_star_idx=9,
        t_entry_idx=10,
        side=1,
        atr_tstar=1.0,
        lots=1.0,
        spread_entry=0.0,
        i_start=10,
        i_end=12,
    )
    e1 = core.Event(
        event_id=1,
        t_star_idx=19,
        t_entry_idx=20,
        side=1,
        atr_tstar=1.0,
        lots=1.0,
        spread_entry=0.0,
        i_start=20,
        i_end=22,
    )
    events = [e0, e1]
    # Identity first: event-order pnls [+20*cs, -10*cs] with cs=1
    id_trial = core.run_null_trial(
        events,
        [10, 20],
        open_=open_,
        high=high,
        low=low,
        close=close,
        spread=spread,
        sl_atr=100.0,  # no SL
        tp_atr=100.0,  # no TP
        point_size=1.0,
        contract_size=1.0,
        commission_per_lot=0.0,
        slippage_points=0.0,
        start_balance=100.0,
        h=3,
    )
    assert [t.pnl for t in id_trial.trades] == pytest.approx([20.0, -10.0])
    # Event-order equity peaks: 100 → ... → 120 → ... → 110; peak 120 DD=10/120≈8.333%
    assert id_trial.metrics["max_drawdown_pct"] == pytest.approx(100.0 * 10.0 / 120.0)

    # Reversed donors: still realize event0 first with donor-20 path (-10), then +20
    # Wait — transplant puts donor OHLC into event windows. Event0 window gets donor20
    # OHLC (lose 10 first), event1 window gets donor10 (win 20). Event-order DD:
    # 100 → 90 (dd 10%) → 110. peak 100 then 110, max dd from peak 100 is 10%.
    # Event-order stored P&L list is still by event_id: first trade is event0 = -10.
    rev = core.run_null_trial(
        events,
        [20, 10],
        open_=open_,
        high=high,
        low=low,
        close=close,
        spread=spread,
        sl_atr=100.0,
        tp_atr=100.0,
        point_size=1.0,
        contract_size=1.0,
        start_balance=100.0,
        h=3,
    )
    assert [t.pnl for t in rev.trades] == pytest.approx([-10.0, 20.0])
    assert rev.assignment == [20, 10]
    # Must NOT report donor-time order DD of 10% from wrong reordering as if
    # event-order +20 then -10 (that would be 8.33% from peak 120).
    # Correct event-order with reversed donors: -10 then +20 → DD 10%.
    assert rev.metrics["max_drawdown_pct"] == pytest.approx(10.0)
    # Discriminator vs wrong donor-time execution of assignment [20,10] on
    # wall clock (would process donor20 first then donor10... same bars as
    # event order here). Stronger check: entry_idx remain event reserved times.
    assert rev.trades[0].entry_idx == 10
    assert rev.trades[1].entry_idx == 20
    assert rev.trades[0].donor_id == 20
    assert rev.trades[1].donor_id == 10


def test_terminal_write_once_refuses_overwrite(tmp_path: Path):
    acct.write_null_started(tmp_path, family_id="f1")
    acct.null_phase_failure_report(tmp_path, reason="first", family_id="f1")
    with pytest.raises(FileExistsError):
        acct.screen_phase_failure_report(tmp_path, reason="cleanup", family_id="f1")
    body = acct.load_json(tmp_path / "FAILED_RUN_UNKNOWN.json")
    assert body["r1_burned"] is True
    assert body["reason"] == "first"


def test_null_started_authoritative_over_contradictory_terminal(tmp_path: Path):
    acct.write_null_started(tmp_path, family_id="f1")
    # Manually plant a contradictory terminal that claims unburned (legacy/corrupt).
    bad = {
        "disposition": "FAILED_RUN_UNKNOWN",
        "execution_state": "UNKNOWN",
        "r1_burned": False,
        "sealed_null_attempt": False,
    }
    (tmp_path / "FAILED_RUN_UNKNOWN.json").write_text(
        __import__("json").dumps(bad) + "\n"
    )
    assert acct.infer_r1_burned_from_outdir(tmp_path) is True


def _fake_trial_evidence(n: int, *, m: int = 1) -> list[dict]:
    """Minimal auditable trial rows (not bare id list)."""
    rows = []
    for j in range(n):
        rows.append(
            {
                "trial_id": j,
                "assignment": list(range(0, m * 3, 3)),
                "trade_pnls": [1.0] * m,
                "metrics": {
                    "n_trades": m,
                    "net_profit": float(m),
                    "profit_factor": 99.0,
                    "max_drawdown_pct": 0.0,
                },
            }
        )
    return rows


def test_cross_terminal_exclusivity_success_then_fail(tmp_path: Path):
    acct.write_null_started(tmp_path, family_id="f1", n_null_planned=999, m=1)
    acct.write_null_success(
        tmp_path, family_id="f1", trials=_fake_trial_evidence(999), expected_m=1
    )
    with pytest.raises(FileExistsError, match="one terminal"):
        acct.null_phase_failure_report(tmp_path, reason="late", family_id="f1")
    assert (tmp_path / "null_success.json").is_file()
    assert (tmp_path / "null_trials_evidence.json").is_file()
    assert not (tmp_path / "FAILED_RUN_UNKNOWN.json").exists()


def test_null_success_requires_started_family_and_real_trials(tmp_path: Path):
    fake = _fake_trial_evidence(999)
    with pytest.raises(acct.AccountingError, match="NULL_STARTED"):
        acct.write_null_success(tmp_path, family_id="f1", trials=fake)
    acct.write_null_started(tmp_path, family_id="f1", n_null_planned=999, m=1)
    with pytest.raises(acct.AccountingError, match="family_id"):
        acct.write_null_success(tmp_path, family_id="other", trials=fake)
    with pytest.raises(acct.AccountingError, match="len\\(trials\\)|trial"):
        acct.write_null_success(
            tmp_path, family_id="f1", trials=_fake_trial_evidence(10)
        )


def test_geometry_rejects_mismatched_entry_vs_reserved():
    ev = core.Event(
        event_id=0,
        t_star_idx=4,
        t_entry_idx=5,  # wrong: not equal to i_start
        side=1,
        atr_tstar=1.0,
        lots=0.01,
        spread_entry=0.0,
        i_start=10,
        i_end=12,
    )
    with pytest.raises(core.ProtocolError, match="t_entry_idx"):
        core.validate_events_and_assignment([ev], [10], h=3, n_bars=20)


def test_geometry_rejects_overlapping_donors():
    e0 = core.Event(
        event_id=0,
        t_star_idx=9,
        t_entry_idx=10,
        side=1,
        atr_tstar=1.0,
        lots=0.01,
        spread_entry=0.0,
        i_start=10,
        i_end=12,
    )
    e1 = core.Event(
        event_id=1,
        t_star_idx=19,
        t_entry_idx=20,
        side=1,
        atr_tstar=1.0,
        lots=0.01,
        spread_entry=0.0,
        i_start=20,
        i_end=22,
    )
    with pytest.raises(core.ProtocolError, match="donor intervals overlap"):
        core.validate_events_and_assignment([e0, e1], [20, 21], h=3, n_bars=40)


def test_validator_rejects_k_prior_zero_self_attest():
    bad = _minimal_exogenous_charter()
    bad["multiplicity"]["K_prior"] = 0
    bad["multiplicity"]["K"] = 1
    bad["multiplicity"]["prior_scored_family_ids"] = []
    bad["multiplicity"]["alpha_adjusted"] = 0.05
    errs = validate_exogenous_predictor_charter(bad)
    assert any("K_prior" in e and "8" in e for e in errs)
    assert any("baseline" in e or "prior_scored" in e for e in errs)


def test_validator_requires_cost_identity():
    bad = _minimal_exogenous_charter()
    bad["fixed"]["costs"] = {
        "commission_per_lot": 0.0,
        "slippage_points": 0.0,
        "spread_col": "spread",
    }
    errs = validate_exogenous_predictor_charter(bad)
    assert any("account_type" in e for e in errs)
    assert any("login" in e for e in errs)
    assert any("costs_document_sha256" in e for e in errs)


def test_exogenous_n_trials_floor_999_both_validators():
    from xau_charter_protocol import MIN_NULL_TRIALS_EXOGENOUS, validate_charter

    assert MIN_NULL_TRIALS_EXOGENOUS == 999
    bad = _minimal_exogenous_charter()
    bad["null"]["n_trials"] = 199
    errs_exo = validate_exogenous_predictor_charter(bad)
    assert any("999" in e for e in errs_exo)
    errs_top = validate_charter(bad)
    assert any("999" in e for e in errs_top)

    bad998 = _minimal_exogenous_charter()
    bad998["null"]["n_trials"] = 998
    assert any(
        "999" in e for e in validate_exogenous_predictor_charter(bad998)
    )
    assert any("999" in e for e in validate_charter(bad998))

    ok = _minimal_exogenous_charter()
    ok["null"]["n_trials"] = 999
    assert validate_exogenous_predictor_charter(ok) == []
    # top-level may still have non-exogenous requirements; ensure no N floor hit
    assert not any("999" in e and "n_trials" in e for e in validate_charter(ok))


def test_null_success_refuses_fabricated_id_list(tmp_path: Path):
    acct.write_null_started(tmp_path, family_id="f1", n_null_planned=999, m=1)
    # Fabricated range alone (or bare counts) must not certify
    with pytest.raises(TypeError):
        acct.write_null_success(
            tmp_path, family_id="f1", trial_ids=list(range(999))
        )  # type: ignore[call-arg]
    with pytest.raises(acct.AccountingError, match="trades|trade_pnls|trials"):
        acct.write_null_success(
            tmp_path,
            family_id="f1",
            trials=[{"trial_id": j, "assignment": [0]} for j in range(999)],
        )
    tmp2 = tmp_path / "z"
    tmp2.mkdir()
    acct.write_null_started(tmp2, family_id="f1", n_null_planned=0)
    with pytest.raises(acct.AccountingError, match="999"):
        acct.write_null_success(tmp2, family_id="f1", trials=[])


def test_marker_refused_after_terminal(tmp_path: Path):
    acct.write_screen_started(tmp_path, family_id="f1")
    acct.screen_phase_failure_report(tmp_path, reason="fail", family_id="f1")
    with pytest.raises(FileExistsError, match="one terminal|terminal"):
        acct.write_null_started(tmp_path, family_id="f1", n_null_planned=999)


def test_geometry_rejects_bool_side_and_non_contiguous_ids():
    ev = core.Event(
        event_id=7,
        t_star_idx=25,
        t_entry_idx=5,
        side=True,  # type: ignore[arg-type]
        atr_tstar=1.0,
        lots=0.01,
        spread_entry=0.0,
        i_start=5,
        i_end=7,
    )
    with pytest.raises(core.ProtocolError):
        core.validate_events_and_assignment([ev], [5], h=3, n_bars=40)


def test_geometry_requires_next_bar_entry_and_ordered_ids():
    e0 = core.Event(
        event_id=0,
        t_star_idx=10,
        t_entry_idx=10,  # should be 11
        side=1,
        atr_tstar=1.0,
        lots=0.01,
        spread_entry=0.0,
        i_start=10,
        i_end=12,
    )
    with pytest.raises(core.ProtocolError, match="t_star_idx\\+1"):
        core.validate_events_and_assignment([e0], [10], h=3, n_bars=40)

    e1 = core.Event(
        event_id=1,  # must be 0 for M=1
        t_star_idx=9,
        t_entry_idx=10,
        side=1,
        atr_tstar=1.0,
        lots=0.01,
        spread_entry=0.0,
        i_start=10,
        i_end=12,
    )
    with pytest.raises(core.ProtocolError, match="0..M-1"):
        core.validate_events_and_assignment([e1], [10], h=3, n_bars=40)


def test_cost_login_positive_and_exact_sha_key():
    bad = _minimal_exogenous_charter()
    bad["fixed"]["costs"]["login"] = -1
    assert any("login" in e for e in validate_exogenous_predictor_charter(bad))

    bad2 = _minimal_exogenous_charter()
    del bad2["fixed"]["costs"]["costs_document_sha256"]
    bad2["fixed"]["costs"]["research_costs_sha256"] = "b" * 64
    errs = validate_exogenous_predictor_charter(bad2)
    assert any("research_costs_sha256" in e or "forbidden" in e for e in errs)
    assert any("costs_document_sha256" in e for e in errs)


def test_signal_sides_reject_float_and_bool():
    bars = _synthetic_bars(40, seed=9, start="2024-01-06 00:00:00")
    n = len(bars["open"])
    signals = np.zeros(n, dtype=object)
    signals[10] = 1.5
    with pytest.raises(core.ProtocolError, match="signal_sides"):
        core.admit_and_simulate_real(
            open_=bars["open"],
            high=bars["high"],
            low=bars["low"],
            close=bars["close"],
            spread=bars["spread"],
            day_id=bars["day_id"],
            signal_sides=signals,
            h=3,
        )
    signals2 = np.zeros(n, dtype=object)
    signals2[10] = True
    with pytest.raises(core.ProtocolError, match="signal_sides"):
        core.admit_and_simulate_real(
            open_=bars["open"],
            high=bars["high"],
            low=bars["low"],
            close=bars["close"],
            spread=bars["spread"],
            day_id=bars["day_id"],
            signal_sides=signals2,
            h=3,
        )


def test_run_null_trials_requires_day_id_and_rejects_nan_donor_and_n0():
    bars = _synthetic_bars(48, seed=12, start="2024-01-07 00:00:00")
    n = len(bars["open"])
    signals = np.zeros(n, dtype=int)
    signals[10] = 1
    signals[20] = 1
    real = core.admit_and_simulate_real(
        open_=bars["open"],
        high=bars["high"],
        low=bars["low"],
        close=bars["close"],
        spread=bars["spread"],
        day_id=bars["day_id"],
        signal_sides=signals,
        h=3,
    )
    donors = core.eligible_donors(
        bars["open"],
        bars["high"],
        bars["low"],
        bars["close"],
        bars["spread"],
        bars["day_id"],
        h=3,
    )
    with pytest.raises(TypeError):
        core.run_null_trials(
            real.events,
            donors,
            open_=bars["open"],
            high=bars["high"],
            low=bars["low"],
            close=bars["close"],
            spread=bars["spread"],
            base_seed=1,
            n_trials=999,
            sl_atr=1.5,
            tp_atr=2.0,
            point_size=0.01,
            contract_size=100.0,
        )  # type: ignore[call-arg]
    with pytest.raises(core.ProtocolError, match="MIN_NULL_TRIALS|n_trials"):
        core.run_null_trials(
            real.events,
            donors,
            open_=bars["open"],
            high=bars["high"],
            low=bars["low"],
            close=bars["close"],
            spread=bars["spread"],
            day_id=bars["day_id"],
            base_seed=1,
            n_trials=0,
            sl_atr=1.5,
            tp_atr=2.0,
            point_size=0.01,
            contract_size=100.0,
        )
    open_bad = bars["open"].copy()
    open_bad[donors[0]] = float("nan")
    with pytest.raises(core.ProtocolError, match="eligible|non-finite"):
        core.run_null_trials(
            real.events,
            donors,
            open_=open_bad,
            high=bars["high"],
            low=bars["low"],
            close=bars["close"],
            spread=bars["spread"],
            day_id=bars["day_id"],
            base_seed=1,
            n_trials=999,
            sl_atr=1.5,
            tp_atr=2.0,
            point_size=0.01,
            contract_size=100.0,
        )


def test_duplicate_n_trials_and_costs_must_agree():
    bad = _minimal_exogenous_charter()
    bad["null"]["n_trials"] = 999
    bad["null"]["min_null_trials"] = 1
    assert any(
        "disagrees" in e for e in validate_exogenous_predictor_charter(bad)
    )
    bad2 = _minimal_exogenous_charter()
    bad2["costs"] = dict(bad2["fixed"]["costs"])
    bad2["costs"]["commission_per_lot"] = 9.9
    assert any(
        "disagrees" in e or "disagree" in e
        for e in validate_exogenous_predictor_charter(bad2)
    )
