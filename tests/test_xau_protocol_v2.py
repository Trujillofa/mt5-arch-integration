"""Protocol v2: immutable charters, gates, null methods, refuse overwrite."""
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


def _mini_ohlc(n: int = 72) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    times = pd.date_range("2024-06-03", periods=n, freq="h", tz="UTC")
    close = 2000.0 + np.cumsum(rng.normal(0, 0.3, size=n))
    return pd.DataFrame(
        {
            "time": times,
            "open": close,
            "high": close + 0.4,
            "low": close - 0.4,
            "close": close,
            "spread": np.full(n, 18.0),
        }
    )


def test_write_charter_once_refuses_overwrite(tmp_path: Path):
    p = tmp_path / "2026-08-10_demo_v1.json"
    write_charter_once(p, {"family_id": "demo", "status": "FROZEN"})
    with pytest.raises(CharterError, match="already exists"):
        write_charter_once(p, {"family_id": "demo2"})


def test_tod_charter_frozen_and_valid():
    p = ROOT / "results/xau_charters/2026-08-10_tod_london_ny_flat_v1.json"
    assert p.is_file()
    ch = json.loads(p.read_text())
    assert ch["family_id"] == "tod_london_ny_flat"
    assert ch["n_free_knobs"] == 0
    assert ch["null"]["method"] == "day_block_shuffle"
    assert int(ch["null"]["n_trials"]) >= 199
    assert ch["rule"]["intraday_flat"] is True
    errs = validate_charter(ch)
    assert errs == [], errs


def test_legacy_prior_day_charter_not_deleted():
    p = ROOT / "results/xau_next_design_charter.json"
    assert p.is_file()
    ch = json.loads(p.read_text())
    assert ch["family_id"] == "prior_day_high_break"


def test_gates_from_charter_match_soft_not_turtle_default():
    ch = json.loads(
        (ROOT / "results/xau_charters/2026-08-10_tod_london_ny_flat_v1.json").read_text()
    )
    g = gates_from_charter(ch)
    assert g["soft"]["profit_factor_min"] == 1.1
    assert "1.1" in g["description"]["soft"]
    # must not silently report turtle 1.5/40/exp20 as soft for this charter
    assert "exp>=20" not in (g["description"]["soft"] or "")

    classic_fn, soft_fn, primary = make_pass_fns(ch)
    assert primary == "soft"
    assert soft_fn is not None

    class M:
        pass

    good = M()
    good.n_trades = 25
    good.profit_factor = 1.2
    good.net_profit = 10.0
    good.win_rate = 40.0
    good.max_drawdown_pct = 5.0
    good.wins = 10
    good.losses = 15
    assert soft_fn(good) is True

    bad = M()
    bad.n_trades = 25
    bad.profit_factor = 1.05
    bad.net_profit = 10.0
    bad.win_rate = 40.0
    bad.max_drawdown_pct = 5.0
    bad.wins = 10
    bad.losses = 15
    assert soft_fn(bad) is False


def test_day_block_null_preserves_time_and_spread():
    raw = _mini_ohlc(96)
    rng = np.random.default_rng(42)
    scr = apply_null_method(raw, rng, method="day_block_shuffle", block_days=1)
    inv = null_invariants_ok(raw, scr, method="day_block_shuffle")
    assert inv["same_length"]
    assert inv["time_unchanged"]
    assert inv["spread_calendar_aligned"]
    assert inv["day_bar_count_multiset"]


def test_pvalue_add_one_resolution():
    # with n=40, best p when always winning is 1/41 ≈ 0.024
    assert pvalue([0.0] * 40, 1.0) == pytest.approx(1 / 41)
    # protocol wants n>=199 so step is smaller
    assert pvalue([0.0] * 199, 1.0) == pytest.approx(1 / 200)


def test_tod_family_simulate_smoke():
    from xau_family_tod_london_ny_flat import build_grid, prepare, simulate

    raw = _mini_ohlc(200)
    # inject hour 13/16 pattern
    raw["time"] = pd.date_range("2024-01-01", periods=200, freq="h", tz="UTC")
    d = prepare(raw)
    g = build_grid()
    assert len(g) == 1
    m = simulate(d, **g[0], spread_col="spread", commission_per_lot=0.0)
    assert m.n_trades >= 0
