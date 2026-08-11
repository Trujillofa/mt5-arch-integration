"""Freeze validation for day_open_reclaim_flat v2 — no family module required.

v1 remains byte-immutable (SUPERSEDED). Correction wave freezes undercut ordering,
capital/cost accounting, and null.base_seed without develop inspection.
"""
from __future__ import annotations

import hashlib
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from xau_charter_protocol import (  # noqa: E402
    DEFAULT_NULL_BASE_SEED,
    is_charter_runnable,
    load_charter,
    null_spec_from_charter,
    validate_charter,
)

CHARTER_V1 = ROOT / "results/xau_charters/2026-08-11_day_open_reclaim_flat_v1.json"
CHARTER_V2 = ROOT / "results/xau_charters/2026-08-11_day_open_reclaim_flat_v2.json"
MEMO_V2 = ROOT / "docs/research/XAU-THESIS-day_open_reclaim_flat_v2.md"

# Exact frozen bytes (adversarial finding: len-only SHA test is insufficient).
V1_SHA = "8eafe48b5f57746dc64188364bd073058dc4fe320decd45c15ef1cb481deebea"
V2_SHA = "961dd3d4794b66b444300716babe80476ce1b58c4b2ccf67eda4eafe04cc95ce"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- charter / registry / immutability -------------------------------------------------


def test_v1_bytes_immutable_and_superseded():
    assert CHARTER_V1.is_file()
    assert _sha(CHARTER_V1) == V1_SHA
    ok, why = is_charter_runnable(CHARTER_V1)
    assert ok is False and "SUPERSEDED" in why


def test_v2_charter_exists_validates_and_pins_sha():
    assert CHARTER_V2.is_file()
    body = CHARTER_V2.read_bytes()
    assert hashlib.sha256(body).hexdigest() == V2_SHA
    ch = load_charter(CHARTER_V2)
    assert validate_charter(ch) == []
    assert ch["family_id"] == "day_open_reclaim_flat"
    assert int(ch["charter_version"]) == 2
    assert ch["n_free_knobs"] == 0
    assert ch["search_cardinality"] == 1
    assert ch["null"]["method"] == "within_day_ohlc_increment_rotate_v1"
    assert int(ch["null"]["n_trials"]) == 999
    assert int(ch["null"]["base_seed"]) == DEFAULT_NULL_BASE_SEED == 20260808
    assert ch["gates"]["primary_n_passers"] == "soft"
    assert ch["kill"]["on_null_fail"] == "KILL_DAY_OPEN_RECLAIM_FLAT"
    assert ch["fixed"]["costs"]["commission_per_lot"] == 0.0
    assert ch["rule"]["intraday_flat"] is True
    assert ch["rule"]["entry_allowed_hours_server"] == list(range(9, 16))
    assert ch["rule"]["flat_hour_server"] == 16
    assert "execution_contract" in ch
    assert ch["execution_contract"]["atr"]["estimator"] == "wilder_ewm"
    assert ch["execution_contract"]["exit"]["priority_same_bar_when_multiple"][0].startswith(
        "1_stop"
    )
    assert ch["execution_contract"]["capital"]["start_balance"] == 10000.0
    assert ch["supersedes"]["sha256"] == V1_SHA


def test_charter_runnable_before_screen():
    ok, why = is_charter_runnable(CHARTER_V2)
    assert ok is True, why


def test_session_shape_rejects_global_return_shuffle():
    ch = load_charter(CHARTER_V2)
    bad = dict(ch)
    bad["null"] = dict(ch["null"])
    bad["null"]["method"] = "global_return_shuffle"
    bad["null"]["forbidden_methods"] = []
    errs = validate_charter(bad)
    assert any("global_return_shuffle" in e for e in errs)
    assert any("within_day_ohlc_increment_rotate_v1" in e for e in errs)
    assert any("session" in e.lower() for e in errs)


def test_dead_lines_list_includes_early_range():
    ch = load_charter(CHARTER_V2)
    dead = set(ch["dead_lines_do_not_revive"])
    for name in (
        "bb_rsi",
        "Donchian",
        "prior_day_high_break",
        "tod_london_ny_flat",
        "server_hour_window_flat",
        "early_server_range_break_flat",
    ):
        assert name in dead


def test_memo_exists_no_develop_metrics():
    assert MEMO_V2.is_file()
    text = MEMO_V2.read_text()
    assert "day_open_reclaim_flat" in text
    assert "FREEZE_ONLY" in text
    assert "undercut_seen_before_i" in text
    assert "20260808" in text
    # Freeze-before-peek: no concrete develop PF/NP line items
    assert "0.7829" not in text
    assert "PF **" not in text


# --- finding 1: undercut ordering (pure semantics from freeze) -------------------------


def undercut_seen_before_i(lows: list[float], day_open: float, i: int) -> bool:
    """Frozen rule: any(low[j] < day_open for j < i)."""
    return any(float(lows[j]) < float(day_open) for j in range(i))


def test_same_bar_undercut_reclaim_rejected():
    """Bar i undercuts and reclaims on the same bar → undercut_seen_before_i is False."""
    day_open = 2000.0
    # j=0: first bar, low == day_open (no undercut); j=1: low under + would reclaim
    lows = [2000.0, 1995.0]
    closes = [2001.0, 2002.0]  # close > day_open on bar 1
    i = 1
    assert undercut_seen_before_i(lows, day_open, i) is False
    reclaim = closes[i] > day_open
    assert reclaim is True
    # Entry requires undercut_seen_before_i AND reclaim → reject
    assert not (undercut_seen_before_i(lows, day_open, i) and reclaim)


def test_prior_bar_undercut_reclaim_accepted():
    """Prior bar undercuts; later bar reclaims → undercut_seen_before_i True."""
    day_open = 2000.0
    # j=0 open bar; j=1 undercut only; j=2 reclaim close > day_open
    lows = [2000.0, 1990.0, 1998.0]
    closes = [2000.5, 1992.0, 2005.0]
    i = 2
    assert undercut_seen_before_i(lows, day_open, i) is True
    assert closes[i] > day_open
    assert undercut_seen_before_i(lows, day_open, i) and closes[i] > day_open


def test_charter_freezes_prior_bar_undercut_wording():
    ch = load_charter(CHARTER_V2)
    und = str(ch["rule"]["undercut"]) + str(ch["rule"].get("undercut_ordering", ""))
    assert "j < i" in und
    assert "undercut_seen_before_i" in und
    assert "same-bar" in und.lower() or "Same-bar" in und


# --- finding 2: capital / cost formulas (pure arithmetic fixtures) ---------------------


def _floor_lots(raw: float, max_lots: float = 0.5, min_lot: float = 0.01) -> float:
    lots = math.floor(raw * 100 + 1e-12) / 100
    lots = min(lots, max_lots)
    return lots if lots >= min_lot else 0.0


def test_two_trade_realized_balance_sizing_fixture():
    """Trade2 sizes off post-trade1 realized balance, not start_balance or equity."""
    start = 10000.0
    risk_pct = 0.01
    contract = 100.0
    stop_dist_1 = 10.0  # price units
    stop_dist_2 = 10.0

    bal = start
    risk1 = bal * risk_pct
    lots1 = _floor_lots(risk1 / (stop_dist_1 * contract))
    assert lots1 == pytest.approx(0.10)

    # Book trade1: +$50 net of cost (cost deducted at exit booking)
    trade_cost_1 = 2.0
    gross1 = 52.0
    pnl1 = gross1 - trade_cost_1
    bal += pnl1
    assert bal == pytest.approx(10050.0)

    risk2 = bal * risk_pct  # compounded
    lots2 = _floor_lots(risk2 / (stop_dist_2 * contract))
    # risk2=100.5 → raw=0.1005 → floor to 0.10 (same lot step); still uses bal not start
    assert risk2 == pytest.approx(100.50)
    assert lots2 == pytest.approx(0.10)
    # Contrast: if someone wrongly used start_balance, risk would be 100.0 — same lots here;
    # force a larger compound so lots differ: simulate bigger win
    bal_big = start + 500.0  # after large win
    risk_big = bal_big * risk_pct  # 105
    lots_big = _floor_lots(risk_big / (5.0 * contract))  # stop_dist=5 → raw=0.21
    lots_from_start = _floor_lots((start * risk_pct) / (5.0 * contract))  # 0.20
    assert lots_big == pytest.approx(0.21)
    assert lots_from_start == pytest.approx(0.20)
    assert lots_big != lots_from_start


def test_entry_exit_equity_cost_timing_fixture():
    """Cost measured at entry but not deducted from balance/equity until exit booking."""
    bal = 10000.0
    entry = 2000.0
    lots = 0.10
    contract = 100.0
    trade_cost = 15.0  # computed at entry, stored
    # At entry fill: balance unchanged
    bal_after_entry = bal
    assert bal_after_entry == 10000.0
    # While open at close=2010: floating MTM without subtracting trade_cost
    px = 2010.0
    eq_open = bal + (px - entry) * contract * lots * 1
    assert eq_open == pytest.approx(10000.0 + 10.0 * 100 * 0.10)  # +100
    assert eq_open == pytest.approx(10100.0)
    # Wrong (charge-on-entry balance debit) would be bal-cost at entry:
    wrong_eq = (bal - trade_cost) + (px - entry) * contract * lots
    assert wrong_eq != eq_open
    # Exit at 2010: pnl = gross - trade_cost; balance updates once
    exit_px = 2010.0
    gross = (exit_px - entry) * contract * lots
    pnl = gross - trade_cost
    bal_after_exit = bal + pnl
    assert gross == pytest.approx(100.0)
    assert pnl == pytest.approx(85.0)
    assert bal_after_exit == pytest.approx(10085.0)
    eq_flat = bal_after_exit
    assert eq_flat == pytest.approx(10085.0)


def test_charter_capital_and_cost_contract_fields():
    ch = load_charter(CHARTER_V2)
    cap = ch["execution_contract"]["capital"]
    assert float(cap["start_balance"]) == 10000.0
    assert cap["compounding"] == "realized_balance"
    assert cap["no_balance_change_at_entry"] is True
    costs = ch["execution_contract"]["entry"]["costs"]
    assert costs["measured_at"].startswith("entry")
    assert "exit" in costs["deducted_at"].lower()
    assert "NOT deducted from balance" in costs["deducted_at"] or "not" in costs[
        "deducted_at"
    ].lower()


# --- finding 3: null.base_seed protocol ------------------------------------------------


def test_validate_charter_requires_base_seed_for_v2_freeze():
    ch = load_charter(CHARTER_V2)
    bad = dict(ch)
    bad["null"] = dict(ch["null"])
    del bad["null"]["base_seed"]
    errs = validate_charter(bad)
    assert any("base_seed" in e for e in errs)


def test_future_v1_freeze_without_base_seed_rejected():
    """Cutover is freeze date, not charter_version — new family v1 must pin seed."""
    ch = load_charter(CHARTER_V2)
    future = dict(ch)
    future["charter_version"] = 1
    future["frozen_at"] = "2026-08-12"
    future["null"] = dict(ch["null"])
    del future["null"]["base_seed"]
    errs = validate_charter(future)
    assert any("base_seed" in e for e in errs), errs
    assert any("charter_version" not in e or "not charter_version" in e for e in errs)


def test_validate_charter_rejects_invalid_base_seed_types_and_negative():
    ch = load_charter(CHARTER_V2)
    cases = [
        1.5,  # float
        "20260808",  # numeric string (int() would coerce — must reject)
        True,  # bool is int subclass — must reject
        -1,  # negative
        None,
    ]
    for bad_val in cases:
        bad = dict(ch)
        bad["null"] = dict(ch["null"])
        bad["null"]["base_seed"] = bad_val
        errs = validate_charter(bad)
        assert any("base_seed" in e for e in errs), (bad_val, errs)


def test_null_spec_exposes_base_seed():
    ch = load_charter(CHARTER_V2)
    ns = null_spec_from_charter(ch)
    assert int(ns["base_seed"]) == 20260808
    assert type(ns["base_seed"]) is int


def test_strict_harness_rejects_null_seed_divergence(monkeypatch, tmp_path: Path):
    """--strict-charter + --null-seed 7 must die before scoring when charter pins seed."""
    import xau_family_null_maxstat as harness

    # Patch harness-local bindings (imported names, not the protocol module).
    monkeypatch.setattr(harness, "assert_charter_path_for_sealed", lambda p: None)
    monkeypatch.setattr(
        harness, "assert_clean_dispositional_tree", lambda: {"clean": True}
    )
    monkeypatch.setattr(harness, "is_charter_runnable", lambda p: (True, "ok"))
    # If we get past seed check into data load, fail loud
    monkeypatch.setattr(
        harness,
        "load_h1",
        lambda: (_ for _ in ()).throw(AssertionError("must not score after seed reject")),
    )

    with pytest.raises(SystemExit, match="null-seed") as ei:
        harness.main(
            [
                "--family",
                "day_open_reclaim_flat",
                "--charter",
                str(CHARTER_V2),
                "--strict-charter",
                "--screen-only",
                "--null-seed",
                "7",
                "--out-dir",
                str(tmp_path / "should_not_exist"),
            ]
        )
    assert "20260808" in str(ei.value)


def test_historical_charters_without_base_seed_still_validate():
    """Grandfather pre-gap freezes (immutable) — must not break closed family tests."""
    early = load_charter(
        ROOT / "results/xau_charters/2026-08-10_early_server_range_break_flat_v2.json"
    )
    assert "base_seed" not in (early.get("null") or {})
    assert validate_charter(early) == []
