"""EURUSD NY-scalp lane tests — every defect the plan review named.

Run with plain python3 (host numpy/pandas), never uv run:
    python3 -m pytest tests/test_eurusd_ny_scalp.py -q
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import eurusd_ny_scalp_autoresearch as ar  # noqa: E402
import eurusd_ny_scalp_core as core  # noqa: E402
import us_index_session_backtest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "results" / "eurusd_ny_scalp_lock.json"
TZ = ZoneInfo("America/New_York")

PCT_EXIT = {"kind": "pct", "tp": 0.0010, "sl": 0.0025}


# ---------------------------------------------------------------------------
# synthetic data helpers
# ---------------------------------------------------------------------------


def make_day(
    day: date,
    closes: list[float],
    vol: float = 300.0,
    spread: float = 12.0,
    start_min: int = 7 * 60,
    bar_min: int = 5,
) -> dict[int, tuple[float, float, float, float]]:
    """Bars from start_min ET, one per bar_min, driven by a close path.
    Returns {et_min: (o, h, l, c)}."""
    bars = {}
    prev = closes[0]
    for k, c in enumerate(closes):
        m = start_min + k * bar_min
        o = prev
        h = max(o, c) + 0.00010
        lo = min(o, c) - 0.00010
        bars[m] = (o, h, lo, c)
        prev = c
    return bars


def build_data(
    days: list[tuple[date, dict[int, tuple[float, float, float, float]]]],
    vol: float = 300.0,
    spread: float = 12.0,
) -> core.M5Data:
    arrs: dict[str, list] = {k: [] for k in ("o", "h", "lo", "c", "v", "s", "m", "k", "w", "t")}
    for day, bars in days:
        for m in sorted(bars):
            o, h, lo, c = bars[m]
            arrs["o"].append(o)
            arrs["h"].append(h)
            arrs["lo"].append(lo)
            arrs["c"].append(c)
            arrs["v"].append(vol)
            arrs["s"].append(spread)
            arrs["m"].append(m)
            arrs["k"].append(day.year * 10000 + day.month * 100 + day.day)
            arrs["w"].append(day.weekday())
            arrs["t"].append(datetime(day.year, day.month, day.day, m // 60, m % 60, tzinfo=TZ))
    return core.M5Data(
        open=np.array(arrs["o"]),
        high=np.array(arrs["h"]),
        low=np.array(arrs["lo"]),
        close=np.array(arrs["c"]),
        vol=np.array(arrs["v"], float),
        spread=np.array(arrs["s"], float),
        et_min=np.array(arrs["m"], np.int32),
        et_key=np.array(arrs["k"], np.int32),
        et_dow=np.array(arrs["w"], np.int8),
        times_et=arrs["t"],
    )


def flat_day(
    day: date, n_bars: int = 120, px: float = 1.10000, vol: float = 300.0, spread: float = 12.0
):
    closes = [px + (0.00002 if i % 2 else -0.00002) for i in range(n_bars)]
    return (day, make_day(day, closes, vol, spread))


def synth_lock() -> dict:
    return json.loads(LOCK.read_text())


def synth_costs(lock: dict):
    return ar.require_eurusd_cost_book(lock)


def atr_all(d: core.M5Data, value: float = 0.0010) -> np.ndarray:
    return np.full(len(d), value)


# ---------------------------------------------------------------------------
# C1: clock
# ---------------------------------------------------------------------------


def test_clock_jan_jul_same_et_wall_clock():
    """A fixed session boundary must land at the same ET wall time in US
    winter and summer (constant-offset would put January 1h early)."""
    # server wall clock 15:00 -> ET must be 08:00 in both regimes
    server = pd.Series([datetime(2026, 1, 15, 15, 0), datetime(2026, 7, 15, 15, 0)])
    et = core.et_from_server(server)
    assert et.dt.hour.tolist() == [8, 8]
    assert et.dt.minute.tolist() == [0, 0]
    # and the underlying offsets differ (EST -5 vs EDT -4) — proof of DST tracking
    offs = et.apply(lambda t: t.utcoffset().total_seconds() / 3600).tolist()
    assert offs == [-5.0, -4.0]


# ---------------------------------------------------------------------------
# H2: holdout from the lock
# ---------------------------------------------------------------------------


def test_holdout_comes_from_lock_not_module_default():
    lock = synth_lock()
    hs = ar.effective_holdout_start(lock)
    assert hs == date(2025, 3, 1)
    assert hs != us_index_session_backtest.HOLDOUT_START
    assert str(us_index_session_backtest.HOLDOUT_START) == "2026-06-01"


def test_forbidden_holdout_default_refused():
    lock = synth_lock()
    lock["holdout"]["holdout_start"] = "2026-06-01"
    with pytest.raises(SystemExit):
        ar.effective_holdout_start(lock)


def test_require_eurusd_cost_book_validates():
    lock = synth_lock()
    costs = synth_costs(lock)
    assert costs.point_size == 1e-5
    assert costs.contract_size == 100_000.0
    assert costs.slippage_points == 5.0
    assert costs.max_spread_points == 30.0
    assert costs.commission_per_lot == 0.0


# ---------------------------------------------------------------------------
# C2 / N1: sizing — floor never round, clamps
# ---------------------------------------------------------------------------


def test_sizing_floor_never_round_050_row():
    """SL 0.50%: raw 0.185 lots. Floor -> 0.18 ($97.20). Round would give
    0.19 ($102.60) and BREACH the $100 invariant."""
    lots = ar.size_lots(540, 100)
    assert lots == 0.18
    assert 540 * lots * 1.0 <= 100.0
    assert 540 * 0.19 * 1.0 > 100.0  # why rounding is forbidden


def test_sizing_reference_rows():
    assert ar.size_lots(270, 100) == 0.37  # 99.90 risk
    assert ar.size_lots(1080, 100) == 0.09  # 97.20 risk


def test_lot_cap_direct_unit():
    """lot_cap cannot bind at risk 100 (max uncapped size is 100/80=1.25), so
    it is tested directly on the sizing function, not via a live trade."""
    assert ar.size_lots(30, 100, 1.0, 0.01, 0.01, 2.0, min_sl_points=1.0) == 2.0


def test_min_sl_points_skips_live_path():
    """A stop nearer than min_sl_points (80) is SKIPPED, not resized into."""
    d = build_data([flat_day(date(2026, 3, 2), 40)])
    sigs = np.zeros(len(d), dtype=np.int8)
    sigs[25] = 1  # 09:05 ET bar, inside session
    trades = ar.simulate_config(
        d,
        sigs,
        {"kind": "pct", "tp": 0.0010, "sl": 0.0005},  # 55-pt stop
        None,
        None,
        atr_all(d),
        synth_costs(synth_lock()),
        synth_lock(),
    )
    assert trades == []


def test_per_fill_invariant_holds_in_sim():
    d = build_data([flat_day(date(2026, 3, 2), 60)])
    sigs = np.zeros(len(d), dtype=np.int8)
    sigs[25] = 1
    trades = ar.simulate_config(
        d,
        sigs,
        PCT_EXIT,
        None,
        None,
        atr_all(d),
        synth_costs(synth_lock()),
        synth_lock(),
    )
    assert len(trades) == 1
    t = trades[0]
    assert t.sl_points * t.lots * 1.0 <= 100.0 + 1e-9
    assert t.lots == ar.size_lots(t.sl_points, 100)


# ---------------------------------------------------------------------------
# equity floor
# ---------------------------------------------------------------------------


def _crash_day(day: date):
    """Rally-signal then 300-pt crash, twice: two full stop-outs."""
    closes = [1.10000] * 10 + [1.10060] * 6 + [1.10060] + [1.09600] * 6
    closes += [1.10060] * 6 + [1.10060] + [1.09600] * 8
    return (day, make_day(day, closes))


def test_equity_floor_raises():
    d = build_data([_crash_day(date(2026, 3, 2))])
    sigs = np.zeros(len(d), dtype=np.int8)
    # one signal at 08:00 (idx 12: 7*60 + 12*5 = 08:00) long before the crash
    sigs[12] = 1
    sigs[25] = 1
    with pytest.raises(RuntimeError, match="equity_floor"):
        ar.simulate_config(
            d,
            sigs,
            PCT_EXIT,
            None,
            None,
            atr_all(d),
            synth_costs(synth_lock()),
            synth_lock(),
            start_balance=150.0,
        )


# ---------------------------------------------------------------------------
# H5: bid-space shorts
# ---------------------------------------------------------------------------


SIGNAL_I, FILL_I = 12, 13  # signal on 07:55 close, fill at 08:00 open (bar 13)


def _short_tp_day(day: date):
    """Short signal at bar 12 (close 1.10000 after a decline from 1.10060);
    fill at bar 13 (08:00 ET) open = exactly 1.10000. So PCT_EXIT gives
    TP 0.1% = 1.09890 and SL 0.25% = 1.10275."""
    closes = [1.10060] * 12 + [1.10000] * 7
    return (day, make_day(day, closes))


def test_short_tp_touched_by_exactly_spread_does_not_fill():
    d = build_data([_short_tp_day(date(2026, 3, 2))])
    assert d.open[FILL_I] == pytest.approx(1.10000)  # entry anchor sanity
    d.low[14] = 1.09890  # bar 14 low == TP: bid hit TP, ask (TP+12pt) did NOT
    sigs = np.zeros(len(d), dtype=np.int8)
    sigs[SIGNAL_I] = -1
    trades = ar.simulate_config(
        d,
        sigs,
        PCT_EXIT,
        None,
        None,
        atr_all(d),
        synth_costs(synth_lock()),
        synth_lock(),
    )
    assert len(trades) == 1
    assert trades[0].reason != "tp"


def test_short_tp_fills_at_bid_equivalent_level():
    d = build_data([_short_tp_day(date(2026, 3, 2))])
    tp = 1.10000 - 0.0010 * 1.10000  # 1.09890 (TP 0.1% below entry)
    bid_lvl = tp - 12 * 1e-5  # bid-equivalent TP (spread 12 pt)
    d.low[15] = bid_lvl - 0.00005  # clearly beyond, not float-equal
    sigs = np.zeros(len(d), dtype=np.int8)
    sigs[SIGNAL_I] = -1
    trades = ar.simulate_config(
        d,
        sigs,
        PCT_EXIT,
        None,
        None,
        atr_all(d),
        synth_costs(synth_lock()),
        synth_lock(),
    )
    assert len(trades) == 1
    t = trades[0]
    assert t.reason == "tp"
    assert t.exit == pytest.approx(bid_lvl)  # fill at TP - spread (bid space)


def test_long_tp_unadjusted():
    d = build_data([_short_tp_day(date(2026, 3, 2))])
    tp = 1.10000 + 0.0010 * 1.10000  # 1.10110 (TP 0.1% above entry)
    d.high[14] = tp + 0.00005  # clearly beyond, not float-equal
    sigs = np.zeros(len(d), dtype=np.int8)
    sigs[SIGNAL_I] = 1
    trades = ar.simulate_config(
        d,
        sigs,
        PCT_EXIT,
        None,
        None,
        atr_all(d),
        synth_costs(synth_lock()),
        synth_lock(),
    )
    assert len(trades) == 1
    t = trades[0]
    assert t.reason == "tp"
    assert t.exit == pytest.approx(tp)  # longs: no spread shift


# ---------------------------------------------------------------------------
# M5: both-touch -> SL-first
# ---------------------------------------------------------------------------


def test_both_touch_sl_first():
    d = build_data([_short_tp_day(date(2026, 3, 2))])
    d.low[14] = 1.09700  # long SL 1.09725 pierced
    d.high[14] = 1.10120  # long TP 1.10110 also pierced, same bar
    sigs = np.zeros(len(d), dtype=np.int8)
    sigs[SIGNAL_I] = 1
    trades = ar.simulate_config(
        d,
        sigs,
        PCT_EXIT,
        None,
        None,
        atr_all(d),
        synth_costs(synth_lock()),
        synth_lock(),
    )
    assert len(trades) == 1
    t = trades[0]
    assert t.reason == "sl"  # pessimistic precedence
    assert t.exit == pytest.approx(1.09725)


# ---------------------------------------------------------------------------
# session containment
# ---------------------------------------------------------------------------


def test_session_containment():
    rng = np.random.default_rng(7)
    days = []
    for k in range(6):
        day = date(2026, 3, 2 + k)
        closes = 1.10000 + np.cumsum(rng.normal(0, 0.0004, 132))
        days.append((day, make_day(day, list(closes))))
    d = build_data(days)
    lock = synth_lock()
    costs = synth_costs(lock)
    for fam in ("trend_continuation", "mean_reversion", "breakout"):
        sigs = getattr(core, f"{fam}_signals")(d, one_per_day=False)
        trades = ar.simulate_config(
            d,
            sigs,
            {"kind": "flatten", "hh": 14, "mm": 0, "sl": 0.0050},
            None,
            None,
            atr_all(d),
            costs,
            lock,
        )
        for t in trades:
            fill_min = int(d.et_min[t.fill_i])
            assert fill_min >= core.SESSION_START_MIN
            assert fill_min <= core.SESSION_END_MIN
            assert t.et_date == str(d.times_et[t.exit_i].date())  # same ET day
            assert t.reason in (
                "sl",
                "tp",
                "flat_1400",
                "flat_1645",
                "session_end",
                "bars6",
                "bars12",
            )
    # forced signals (incl. late-day) make containment non-vacuous
    forced = np.zeros(len(d), dtype=np.int8)
    idx = np.flatnonzero(core.entry_ok_mask(d))
    forced[idx[::9]] = 1
    forced[idx[4::11]] = -1
    trades = ar.simulate_config(
        d,
        forced,
        {"kind": "flatten", "hh": 14, "mm": 0, "sl": 0.0050},
        None,
        None,
        atr_all(d),
        costs,
        lock,
    )
    assert trades, "forced signals must trade"
    for t in trades:
        fill_min = int(d.et_min[t.fill_i])
        assert core.SESSION_START_MIN <= fill_min <= core.SESSION_END_MIN
        assert t.et_date == str(d.times_et[t.exit_i].date())


# ---------------------------------------------------------------------------
# causality + warmup
# ---------------------------------------------------------------------------


def _random_days(n_days: int = 30, seed: int = 3):
    rng = np.random.default_rng(seed)
    days = []
    for k in range(n_days):
        day = date(2026, 1, 5) + pd.Timedelta(days=k)
        day = day.date() if hasattr(day, "date") else day
        closes = 1.10000 + np.cumsum(rng.normal(0, 0.0003, 120))
        days.append((day, make_day(day, list(closes))))
    return build_data(days)


def test_future_mutation_causality():
    d = _random_days()
    k = len(d) // 2
    for fam in ("trend_continuation", "mean_reversion", "breakout"):
        s0 = getattr(core, f"{fam}_signals")(d, one_per_day=False)
        d2 = _random_days()
        for arr_name in ("open", "high", "low", "close", "vol"):
            getattr(d2, arr_name)[k:] = getattr(d2, arr_name)[k:] * 1.05
        s1 = getattr(core, f"{fam}_signals")(d2, one_per_day=False)
        assert np.array_equal(s0[:k], s1[:k]), fam


def test_warmup_no_signals_before_indicator_warmup():
    d = _random_days()
    for fam in ("trend_continuation", "mean_reversion", "breakout"):
        s = getattr(core, f"{fam}_signals")(d, one_per_day=False)
        assert int(np.abs(s[:20]).sum()) == 0, fam


def test_entry_window_and_friday_cutoff():
    d = _random_days()
    mask = core.entry_ok_mask(d)
    for i in np.flatnonzero(mask):
        m, dow = int(d.et_min[i]), int(d.et_dow[i])
        assert 480 <= m < 1020
        assert not (dow == 4 and m >= 840)


# ---------------------------------------------------------------------------
# null runner sanity (synthetic)
# ---------------------------------------------------------------------------


def test_rotate_returns_within_days_preserves_day_product_and_metadata():
    d = _random_days(10, seed=11)
    rng = np.random.default_rng(11)
    d2 = core.rotate_returns_within_days(d, rng)
    assert len(d2) == len(d)
    assert np.array_equal(d2.et_key, d.et_key)
    assert np.array_equal(d2.et_min, d.et_min)
    # per ET day: first open unchanged, total day return preserved (circular)
    for key in np.unique(d.et_key):
        idx = np.flatnonzero(d.et_key == key)
        assert d2.open[idx[0]] == d.open[idx[0]]
        assert np.isclose(
            d2.close[idx[-1]] / d.open[idx[0]], d.close[idx[-1]] / d.open[idx[0]], rtol=1e-9
        )
    assert not np.allclose(d2.close, d.close)


def test_run_null_sanity_synthetic():
    d = _random_days(24, seed=5)
    lock = synth_lock()
    costs = synth_costs(lock)
    holdout = ar.effective_holdout_start(lock)
    assert holdout == date(2025, 3, 1)  # used below via run_grid split
    rows = ar.run_grid(d, lock, costs, date(2026, 1, 20))  # split inside sample
    assert len(rows) == 192
    null = ar.run_null(d, lock, costs, date(2026, 1, 20))
    assert len(null["per_seed"]) == 10
    assert list(null["seeds"]) == [11, 23, 37, 41, 53, 67, 79, 97, 113, 127]
    # on a 24-day synthetic sample most seeds cannot reach the 40-trade
    # eligibility bar, so best_develop_median_daily_pct may legitimately be
    # None — the structural contract is that all 10 seeds ran and reported.
    for rec in null["per_seed"]:
        assert rec["best_develop_median_daily_pct"] is None or isinstance(
            rec["best_develop_median_daily_pct"], float
        )


# ---------------------------------------------------------------------------
# loader-level checks
# ---------------------------------------------------------------------------


def test_loader_spread_imputation(tmp_path):
    rows = ["time,timeframe,symbol,open,high,low,close,tick_volume,spread"]
    for k in range(6):
        rows.append(
            f"2026.03.02 {15 + (k * 5) // 60:02d}:{(5 + k * 5) % 60:02d},"
            f"M5,EURUSD,1.10000,1.10010,1.09990,1.10005,100,"
            f"{0 if k == 2 else 12}"
        )
    p = tmp_path / "h.csv"
    p.write_text("\n".join(rows) + "\n")
    d = core.load_eurusd_m5(p)
    assert (d.spread > 0).all()  # zeros imputed
    assert d.spread[2] == 12.0  # ffilled from previous bar
    assert int(d.et_min[0]) == 8 * 60 + 5  # server 15:05 -> 08:05 ET


def test_data_sha_verifies_against_lock():
    csv = ROOT / "results" / "eurusd_data" / "history_EURUSD.csv"
    if not csv.is_file():  # local-only dump; skip on fresh clones
        pytest.skip("results/eurusd_data/history_EURUSD.csv not present")
    ar.verify_data_sha(csv, synth_lock())
