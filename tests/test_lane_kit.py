"""lane_kit tests — the shared pre-registered-lane machinery.

Covers the refusal matrix (promote flips, pinned fields, cost-book equality,
data sha, holdout collisions, grid cardinality), the develop-only rank
semantics (PF None -> 3.0, holdout keys ignored), within-day null rotation
(day product preserved, metadata passthrough), and ny-1330-style clock
admission (lag-0 peak required, shifted tape fails closed).

Run with plain python3 (host numpy/pandas), never uv run:
    python3 -m pytest tests/test_lane_kit.py -q
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import lane_kit as lk  # noqa: E402
from us_index_session_backtest import CostSpec, Trade  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _lock() -> dict:
    """BTC-NY-shaped lock: 3 families x 32 exit/flag cells = 96 configs."""
    return {
        "search_id": "fixture_lane_develop_v1",
        "promote": False,
        "live_go": False,
        "book": {
            "point_size": 0.01,
            "contract_size": 1.0,
            "lots": 1.0,
            "balance_usd": 10000,
        },
        "costs": {
            "commission_per_lot": 0.0,
            "slippage_points": 160.0,
            "max_spread_points": 2000.0,
        },
        "data": {"path": "x.csv", "sha256": "0" * 64},
        "holdout": {"start": "2026-03-01"},
        "families": {
            "search": ["fam_vwap", "fam_drive", "fam_pull"],
            "transfer_never_ranked": ["fam_index"],
        },
        "grid": {
            "sl_atr": [1.0, 1.5],
            "tp_r": [1.0, 1.5],
            "time_stop_bars": [6, 12],
            "nfp_blackout": [False, True],
            "min_atr_pct": [0.00015, 0.0003],
            "or_minutes_atr_drive": 30,
            "or_buffer_atr_frac": 0.1,
            "ema_fast": 9,
            "ema_slow": 21,
            "one_per_day": True,
            "nfp_window_et": "[08:25, 08:40]",
            "max_configs": 192,
            "expected_configs": 96,
        },
    }


def _trade(et_date: str, pnl: float) -> Trade:
    return Trade(
        side=1,
        signal_i=0,
        fill_i=1,
        exit_i=2,
        entry=100.0,
        exit=100.0 + pnl,
        reason="tp",
        et_date=et_date,
        signal_time="t0",
        fill_time="t1",
        exit_time="t2",
        spread_pts=1.0,
        cost=0.0,
        pnl=pnl,
        mae=0.0,
        mfe=0.0,
    )


@dataclass
class _Bars:
    """Minimal rotate_returns duck-type: OHLC arrays + et_key + passthroughs."""

    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    et_key: np.ndarray
    vol: np.ndarray = field(default_factory=lambda: np.zeros(0))
    tag: str = "keepme"


def _two_days() -> _Bars:
    """2 ET-days x 5 bars with a distinct per-day drift."""
    day0 = np.array([100.0, 101.0, 100.5, 102.0, 103.0])
    day1 = np.array([200.0, 199.0, 200.5, 201.0, 200.0])
    close = np.concatenate([day0, day1])
    open_ = np.concatenate([[99.5], day0[:-1], [199.5], day1[:-1]])
    high = close + 1.0
    low = close - 1.0
    et_key = np.array([1] * 5 + [2] * 5)
    return _Bars(open=open_, high=high, low=low, close=close, et_key=et_key, vol=np.arange(10))


# ---------------------------------------------------------------------------
# Lock layer
# ---------------------------------------------------------------------------


def test_sha256_file_matches_hashlib():
    p = Path(__file__).parent / "test_lane_kit.py"
    assert lk.sha256_file(p) == hashlib.sha256(p.read_bytes()).hexdigest()


def test_load_lane_lock_search_id_mismatch_refuses():
    import json
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "lock.json"
        p.write_text(json.dumps(_lock()))
        got = lk.load_lane_lock(p, "fixture_lane_develop_v1")
        assert got["search_id"] == "fixture_lane_develop_v1"
        with pytest.raises(SystemExit, match="search_id mismatch"):
            lk.load_lane_lock(p, "other_lane_v2")


def test_refuse_promote_flips():
    lk.refuse_promote_flips(_lock())
    with pytest.raises(SystemExit, match="promote must stay false"):
        lk.refuse_promote_flips({**_lock(), "promote": True})
    with pytest.raises(SystemExit, match="live_go must stay false"):
        lk.refuse_promote_flips({**_lock(), "live_go": True})


def test_refuse_pinned_exact_float_and_missing():
    lock = _lock()
    lk.refuse_pinned(lock, {"costs.slippage_points": 160.0, "book.lots": 1.0})
    # float tolerance
    lk.refuse_pinned(lock, {"costs.slippage_points": 160.0 + 1e-12})
    with pytest.raises(SystemExit, match="slippage_points"):
        lk.refuse_pinned(lock, {"costs.slippage_points": 5.0})
    with pytest.raises(SystemExit, match="holdout.start"):
        lk.refuse_pinned(lock, {"holdout.start": "2026-01-01"})
    # missing field refuses (deleted pin is a mutation)
    with pytest.raises(SystemExit, match="book.contract_size"):
        lk.refuse_pinned({"book": {}}, {"book.contract_size": 1.0})


def test_costs_from_lock_and_require_locked_book_matrix():
    lock = _lock()
    costs = lk.costs_from_lock(lock)
    assert costs == CostSpec(
        point_size=0.01,
        contract_size=1.0,
        lots=1.0,
        commission_per_lot=0.0,
        slippage_points=160.0,
        max_spread_points=2000.0,
    )
    lk.require_locked_book(lock, costs)
    # The guard exists to catch a CostSpec that diverges from the committed
    # lock (CLI overrides, softer simulator): freeze the costs, then mutate
    # the lock — every field must refuse.
    frozen = lk.costs_from_lock(_lock())
    for mutate, new in [
        ("lots", 2.0),
        ("slippage_points", 5.0),
        ("max_spread_points", 30.0),
        ("point_size", 0.001),
        ("contract_size", 100.0),
    ]:
        bad = _lock()
        if mutate in ("lots", "point_size", "contract_size"):
            bad["book"][mutate] = new
        else:
            bad["costs"][mutate] = new
        with pytest.raises(SystemExit, match=mutate):
            lk.require_locked_book(bad, frozen)
    with pytest.raises(SystemExit, match="promote"):
        lk.require_locked_book({**_lock(), "promote": True}, frozen)


def test_verify_data_sha256(tmp_path):
    p = tmp_path / "book.csv"
    p.write_bytes(b"abc")
    want = hashlib.sha256(b"abc").hexdigest()
    assert lk.verify_data_sha256(p, want) == want
    with pytest.raises(SystemExit, match="sha256 mismatch"):
        lk.verify_data_sha256(p, "0" * 64)


def test_assert_lane_holdout_forbidden_set():
    forbidden = [date(2026, 1, 1), "2026-03-01", date(2026, 6, 1), date(2026, 7, 1)]
    assert lk.assert_lane_holdout(date(2026, 9, 1), forbidden) == date(2026, 9, 1)
    for bad in ("2026-01-01", date(2026, 7, 1)):
        with pytest.raises(SystemExit, match="already used by another lane"):
            lk.assert_lane_holdout(
                bad if isinstance(bad, date) else date.fromisoformat(bad), forbidden
            )


# ---------------------------------------------------------------------------
# Grid layer
# ---------------------------------------------------------------------------


def test_iter_product_grid_btc_shape_96():
    rows = lk.iter_product_grid(_lock())
    assert len(rows) == 96
    assert {r["family"] for r in rows} == {"fam_vwap", "fam_drive", "fam_pull"}
    first = rows[0]
    assert first["family"] == "fam_vwap"
    assert first["sl_atr"] == 1.0 and first["nfp_blackout"] is False
    # scalar grid entries are annotations, never axes
    assert all("ema_fast" not in r and "max_configs" not in r for r in rows)
    lk.assert_cardinality(rows, _lock())


def test_iter_product_grid_ceiling_refuses_widening():
    lock = _lock()
    lock["grid"]["sl_atr"] = [1.0, 1.5, 2.0]  # 144 > 192? no: 3*48=144 ok
    rows = lk.iter_product_grid(lock)
    assert len(rows) == 144
    lock["grid"]["tp_r"] = [1.0, 1.5, 2.0]  # 3*3*2*2*2*3 = 216 > 192
    with pytest.raises(SystemExit, match="exceeds max_configs"):
        lk.iter_product_grid(lock)


def test_assert_cardinality_mismatch_refuses():
    lock = _lock()
    rows = lk.iter_product_grid(lock)
    with pytest.raises(SystemExit, match="cardinality"):
        lk.assert_cardinality(rows[:-1], lock)


def test_grid_cfg_id_stable_and_bool_pinned():
    rows = lk.iter_product_grid(_lock())
    ids = [lk.grid_cfg_id(r) for r in rows]
    assert len(set(ids)) == 96
    assert ids[0].startswith("fam_vwap|")
    assert "nfp_blackout0" in ids[0]  # bool -> int, stable across runs
    assert ids[0] == lk.grid_cfg_id(dict(rows[0]))


# ---------------------------------------------------------------------------
# Rank layer
# ---------------------------------------------------------------------------


def _m(trades, net, pf, exp):
    return {"trades": trades, "net_pnl": net, "profit_factor": pf, "expectancy": exp}


def test_score_pf_expectancy_gates():
    assert lk.score_pf_expectancy(_m(40, 1.0, 1.5, 0.1)) == pytest.approx(1500.1)
    # ineligible pins
    assert lk.score_pf_expectancy(_m(39, 1.0, 9.0, 5.0)) == -1e9
    assert lk.score_pf_expectancy(_m(60, 0.0, 9.0, 5.0)) == -1e9
    assert lk.score_pf_expectancy(_m(60, -1.0, 9.0, 5.0)) == -1e9
    # None PF (no losing trade) pins to 3.0
    assert lk.score_pf_expectancy(_m(50, 10.0, None, 0.2)) == pytest.approx(3000.2)


def test_rank_pf_expectancy_none_pf_pins_to_3():
    rows = [
        {"develop": _m(50, 10.0, 2.5, 0.3), "id": "a"},
        {"develop": _m(50, 10.0, None, 0.2), "id": "b"},  # 3.0 beats 2.5
        {"develop": _m(50, 10.0, 2.5, 0.1), "id": "c"},
    ]
    order = [r["id"] for r in lk.rank_pf_expectancy(rows)]
    assert order == ["b", "a", "c"]


def test_rank_ignores_holdout_keys():
    rows = [
        {"develop": _m(50, 10.0, 1.5, 0.1), "holdout": _m(999, 10**6, 99.0, 10**4), "id": "a"},
        {"develop": _m(50, 10.0, 2.0, 0.1), "holdout": _m(1, -(10**6), 0.0, -(10**4)), "id": "b"},
    ]
    order = [r["id"] for r in lk.rank_pf_expectancy(rows)]
    assert order == ["b", "a"]  # develop PF decides; holdout never enters


def test_split_and_pack_develop_holdout():
    hs = date(2026, 3, 1)
    trades = [
        _trade("2026-02-28", 10.0),
        _trade("2026-02-28", -5.0),
        _trade("2026-03-01", 20.0),
        _trade("2026-03-02", -2.0),
    ]
    pre, post = lk.split_trades_by_holdout(trades, hs)
    assert [t.et_date for t in pre] == ["2026-02-28", "2026-02-28"]
    assert [t.et_date for t in post] == ["2026-03-01", "2026-03-02"]
    packed = lk.pack_develop_holdout(trades, hs)
    assert packed["develop"]["trades"] == 2
    assert packed["develop"]["net_pnl"] == 5.0
    assert packed["holdout"]["trades"] == 2
    assert packed["holdout"]["net_pnl"] == 18.0


# ---------------------------------------------------------------------------
# Null layer
# ---------------------------------------------------------------------------


def test_rotate_returns_preserves_day_product_and_metadata():
    d = _two_days()
    rng = np.random.default_rng(7)
    dn = lk.rotate_returns_within_days(d, rng)
    assert isinstance(dn, _Bars)
    assert dn.tag == "keepme"  # passthrough fields untouched
    assert np.array_equal(dn.vol, d.vol)
    assert np.array_equal(dn.et_key, d.et_key)
    for day in (slice(0, 5), slice(5, 10)):
        # same-day first open and last close => day product preserved
        assert dn.open[day][0] == d.open[day][0]
        assert dn.close[day][-1] == pytest.approx(d.close[day][-1])
        # intra-bar chain: open[k+1] == close[k]
        assert np.allclose(dn.open[day][1:], dn.close[day][:-1])
        # high/low stay on their side of close (ratio-scaled with it)
        assert np.all(dn.high[day] >= dn.close[day] - 1e-9)
        assert np.all(dn.low[day] <= dn.close[day] + 1e-9)
        # bar geometry scales with close: dn.high/d.high == dn.close/d.close
        assert np.allclose(dn.high[day] / d.high[day], dn.close[day] / d.close[day])
    # determinism: same seed, same rotation
    dn2 = lk.rotate_returns_within_days(_two_days(), np.random.default_rng(7))
    assert np.allclose(dn.close, dn2.close)


def test_run_null_rotation_counts_ge_real():
    produced = iter([1.0, 3.0, 2.0, None])

    def null_metric(rng):
        return next(produced)

    out = lk.run_null_rotation([11, 22, 33, 44], null_metric, real_metric=2.0)
    assert [rec["seed"] for rec in out["per_seed"]] == [11, 22, 33, 44]
    # only non-None values count: [1.0, 3.0, 2.0] vs real 2.0 -> 2 of 3 >= 2.0
    assert out["frac_null_ge_real"] == pytest.approx(2.0 / 3.0)
    # real missing -> frac None (never a free pass)
    out2 = lk.run_null_rotation([1], lambda rng: 5.0, real_metric=None)
    assert out2["frac_null_ge_real"] is None


# ---------------------------------------------------------------------------
# Clock admission
# ---------------------------------------------------------------------------


def _hourly_utc(n: int = 200, seed: int = 3) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-02-01", periods=n, freq="h", tz="UTC")
    px = 50000.0 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    return pd.Series(px, index=idx)


def test_admit_clock_lag0_self_and_aligned():
    s = _hourly_utc()
    out = lk.admit_clock_lag0(s, s.copy(), floor=0.95)
    assert out["peak_lag"] == 0
    assert out["admitted"] is True
    # identical books at different sample phase still lag-0 after floor('h')
    s2 = s.copy()
    s2.index = s2.index + pd.Timedelta(minutes=7)
    out2 = lk.admit_clock_lag0(s2, s, floor=0.95)
    assert out2["peak_lag"] == 0
    assert out2["admitted"] is True


def test_admit_clock_rejects_shifted_tape():
    s = _hourly_utc()
    shifted = s.copy()
    shifted.index = shifted.index + pd.Timedelta(hours=1)  # mislabeled "UTC" book
    out = lk.admit_clock_lag0(shifted, s, floor=0.95)
    assert out["peak_lag"] != 0
    assert out["admitted"] is False


def test_admit_clock_fails_closed_on_naive_or_short():
    s = _hourly_utc()
    naive = pd.Series(s.values, index=s.index.tz_localize(None))
    with pytest.raises(SystemExit, match="tz-aware"):
        lk.admit_clock_lag0(naive, s)
    tiny = _hourly_utc(10)
    with pytest.raises(SystemExit, match="no overlap"):
        lk.admit_clock_lag0(tiny, tiny.iloc[::-1].head(3))
