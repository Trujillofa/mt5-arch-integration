"""Phase B synthetic tests for multi_instrument_exogenous_predictor_v1.

No develop package, no thesis charter scoring, no registry, no paper/live.
"""
from __future__ import annotations

import json
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
            "pass_status": "provisional_while_catalog_open",
            "paper_live_while_open": False,
        },
        "fixed": {
            "costs": {
                "commission_per_lot": 0.0,
                "slippage_points": 0.0,
                "spread_col": "spread",
            }
        },
        "rule": {"intraday_flat": True, "exit": "sl_tp_time_h3"},
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
        base_seed=42,
        n_trials=20,
        sl_atr=1.5,
        tp_atr=2.0,
        point_size=0.01,
        contract_size=100.0,
        h=3,
    )
    assert len(trials) == 20
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
