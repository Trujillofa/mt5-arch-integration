"""Protocol v2.1: immutable charters, within-day null, strict equality."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from xau_charter_protocol import (  # noqa: E402
    CharterError,
    gates_from_charter,
    make_pass_fns,
    validate_charter,
    write_charter_once,
)
from xau_null_core import apply_null_method, null_invariants_ok, pvalue  # noqa: E402


def _days_ohlc(n_days: int = 4, hours: range = range(1, 24)) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    rows = []
    price = 2000.0
    for day in range(n_days):
        for hour in hours:
            price = price * float(np.exp(rng.normal(0, 0.002)))
            ts = pd.Timestamp(f"2024-06-{3 + day:02d} {hour:02d}:00:00", tz="UTC")
            rows.append(
                {
                    "time": ts,
                    "open": price,
                    "high": price * 1.0004,
                    "low": price * 0.9996,
                    "close": price,
                    "spread": 18.0,
                }
            )
    return pd.DataFrame(rows)


def test_write_charter_once_refuses_overwrite(tmp_path: Path):
    p = tmp_path / "2026-08-10_demo_v1.json"
    write_charter_once(p, {"family_id": "demo", "status": "FROZEN"})
    with pytest.raises(CharterError, match="already exists"):
        write_charter_once(p, {"family_id": "demo2"})


def test_tod_v1_marked_protocol_null_invalid():
    p = ROOT / "results/xau_charters/2026-08-10_tod_london_ny_flat_v1.json"
    ch = json.loads(p.read_text())
    assert ch["disposition"] == "PROTOCOL_NULL_INVALID"
    assert ch.get("r1_burned") is False


def test_server_hour_charter_frozen_valid():
    p = ROOT / "results/xau_charters/2026-08-10_server_hour_window_flat_v1.json"
    assert p.is_file()
    ch = json.loads(p.read_text())
    assert ch["family_id"] == "server_hour_window_flat"
    assert ch["n_free_knobs"] == 0
    assert ch["null"]["method"] == "within_day_return_rotate"
    assert int(ch["null"]["n_trials"]) >= 199
    assert ch["rule"]["intraday_flat"] is True
    assert ch["clock_contract"]["london_ny_overlap_claimed"] is False
    assert "day_block_shuffle" in ch["null"]["forbidden_methods"]
    errs = validate_charter(ch)
    assert errs == [], errs


def test_legacy_prior_day_charter_not_deleted():
    p = ROOT / "results/xau_next_design_charter.json"
    assert p.is_file()
    assert json.loads(p.read_text())["family_id"] == "prior_day_high_break"


def test_gates_from_charter_soft_provenance():
    ch = json.loads(
        (ROOT / "results/xau_charters/2026-08-10_server_hour_window_flat_v1.json").read_text()
    )
    g = gates_from_charter(ch)
    assert g["soft"]["profit_factor_min"] == 1.1
    assert "exp>=20" not in (g["description"]["soft"] or "")
    _classic_fn, soft_fn, primary = make_pass_fns(ch)
    assert primary == "soft" and soft_fn is not None

    class M:
        n_trades = 25
        profit_factor = 1.2
        net_profit = 10.0
        win_rate = 40.0
        max_drawdown_pct = 5.0
        wins = 10
        losses = 15

    assert soft_fn(M()) is True


def test_within_day_return_rotate_invariants():
    raw = _days_ohlc(5)
    rng = np.random.default_rng(42)
    scr = apply_null_method(raw, rng, method="within_day_return_rotate")
    inv = null_invariants_ok(
        raw, scr, method="within_day_return_rotate", entry_hour=13, flat_hour=16
    )
    assert inv["same_length"]
    assert inv["time_unchanged"]
    assert inv["spread_calendar_aligned"]
    assert inv["per_day_bar_count_equal"]
    assert inv["within_day_path_continuous"]
    assert inv["entry_hour_closes_moved"]
    assert inv["session_path_association_broken"]
    # per-day bar counts by calendar day identical
    rd = pd.to_datetime(raw["time"], utc=True).dt.strftime("%Y-%m-%d")
    sd = pd.to_datetime(scr["time"], utc=True).dt.strftime("%Y-%m-%d")
    assert rd.tolist() == sd.tolist()
    assert raw.groupby(rd).size().equals(scr.groupby(sd).size())


def test_within_day_preserves_return_multiset_max_jump():
    raw = _days_ohlc(3)
    rng = np.random.default_rng(7)
    scr = apply_null_method(raw, rng, method="within_day_return_rotate")
    rd = pd.to_datetime(raw["time"], utc=True).dt.strftime("%Y-%m-%d").to_numpy()
    for d in np.unique(rd):
        ix = np.where(rd == d)[0]
        if len(ix) < 3:
            continue
        r = np.diff(np.log(raw["close"].to_numpy(float)[ix]))
        s = np.diff(np.log(scr["close"].to_numpy(float)[ix]))
        assert np.sort(r) == pytest.approx(np.sort(s), rel=1e-9, abs=1e-12)


def test_day_block_marked_session_invalid():
    raw = _days_ohlc(3)
    scr = apply_null_method(raw, np.random.default_rng(0), method="day_block_shuffle")
    inv = null_invariants_ok(raw, scr, method="day_block_shuffle")
    assert inv.get("protocol_session_valid") is False


def test_pvalue_add_one_resolution():
    assert pvalue([0.0] * 40, 1.0) == pytest.approx(1 / 41)
    assert pvalue([0.0] * 199, 1.0) == pytest.approx(1 / 200)


def test_server_hour_family_simulate_smoke():
    from xau_family_server_hour_window_flat import build_grid, prepare, simulate

    raw = _days_ohlc(10)
    d = prepare(raw)
    g = build_grid()
    assert len(g) == 1
    m = simulate(d, **g[0], spread_col="spread", commission_per_lot=0.0)
    assert m.n_trades >= 0


def test_sealed_fixture_blocks_family_mismatch():
    from xau_sealed_family_cycle import _assert_family_matches_charter

    ch = {"family_id": "server_hour_window_flat"}
    assert _assert_family_matches_charter("server_hour_window_flat", ch) == (
        "server_hour_window_flat"
    )
    with pytest.raises(SystemExit):
        _assert_family_matches_charter("tod_london_ny_flat", ch)
