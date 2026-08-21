"""EURUSD NY-scalp lane tests — every defect the plan review named.

Run with plain python3 (host numpy/pandas), never uv run:
    python3 -m pytest tests/test_eurusd_ny_scalp.py -q
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import date, datetime, timedelta
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


def test_usd_book_tp20_loses_to_friction():
    """3 lots, TP $20 / SL $100: a TP fill nets ~-$46 after 22-pt round-trip."""
    d = build_data([_short_tp_day(date(2026, 3, 2))])
    tp_px = 1.10000 + (20.0 / (3.0 * 1.0)) * 1e-5  # +6.67 points
    d.high[14] = tp_px + 0.00005
    sigs = np.zeros(len(d), dtype=np.int8)
    sigs[SIGNAL_I] = 1
    lock = {
        "book": {
            "balance_usd": 10000,
            "sizing_policy": "fixed_lots",
            "lots": 3.0,
            "point_value_per_lot": 1.0,
        },
        "risk": {"daily_halt_usd": -300},
    }
    from us_index_session_backtest import CostSpec

    costs = CostSpec(
        point_size=1e-5,
        contract_size=100_000.0,
        lots=3.0,
        commission_per_lot=0.0,
        slippage_points=5.0,
        max_spread_points=30.0,
    )
    trades = ar.simulate_config(
        d,
        sigs,
        {"kind": "usd", "tp_usd": 20.0, "sl_usd": 100.0},
        None,
        None,
        atr_all(d),
        costs,
        lock,
    )
    assert len(trades) == 1
    t = trades[0]
    assert t.lots == 3.0
    assert t.reason == "tp"
    # gross +$20 minus (12+10) pt * $3 = $66 -> about -$46
    assert t.pnl == pytest.approx(20.0 - 66.0, abs=0.05)


# ---------------------------------------------------------------------------
# equity floor
# ---------------------------------------------------------------------------


def _crash_day(day: date):
    """Rally-signal then 300-pt crash, twice: two full stop-outs."""
    closes = [1.10000] * 10 + [1.10060] * 6 + [1.10060] + [1.09600] * 6
    closes += [1.10060] * 6 + [1.10060] + [1.09600] * 8
    return (day, make_day(day, closes))


def test_equity_floor_stops_trading_and_keeps_history():
    d = build_data([_crash_day(date(2026, 3, 2))])
    sigs = np.zeros(len(d), dtype=np.int8)
    sigs[12] = 1
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
        start_balance=150.0,
    )
    assert trades
    assert ar.went_bankrupt(trades)
    bust_i = next(i for i, t in enumerate(trades) if t.equity_after <= 0.0)
    assert all(t.equity_after > 0.0 or i == bust_i for i, t in enumerate(trades))
    assert len(trades) == bust_i + 1  # no trade opened after the bust


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

    # effective_levels() is what analysis must diff against. Against the RAW
    # tp field a short's deliberate bid-space shift reads as a full spread of
    # phantom slippage — the trap this helper exists to close.
    eff_tp, _ = ar.effective_levels(t, 1e-5)
    assert eff_tp == pytest.approx(bid_lvl)
    # Against the EFFECTIVE level the fill is exact — zero slippage. (The bar
    # ran 5 pts past it; a TP still books at the level, which is deliberate.)
    assert t.exit - eff_tp == pytest.approx(0.0, abs=1e-9)
    # Against the RAW tp field the same fill looks like one whole spread of
    # slippage that never happened. This is the trap effective_levels closes.
    assert abs(t.exit - t.tp) / 1e-5 == pytest.approx(12.0, abs=0.5)


def test_effective_levels_leaves_longs_unshifted():
    t = ar.SimTrade(
        side=1, fill_i=0, exit_i=1, entry=1.1, exit=1.1, reason="tp",
        et_date="2026-03-02", fill_time="", exit_time="", lots=0.1,
        sl_points=100.0, tp=1.101, sl=1.099, spread_pts=12.0, cost=0.0,
        pnl=0.0, mae=0.0, mfe=0.0, equity_after=10_000.0,
    )
    assert ar.effective_levels(t, 1e-5) == (1.101, 1.099)
    short = replace(t, side=-1)
    eff_tp, eff_sl = ar.effective_levels(short, 1e-5)
    assert eff_tp == pytest.approx(1.101 - 12e-5)
    assert eff_sl == pytest.approx(1.099 - 12e-5)


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


# ---------------------------------------------------------------------------
# HIGH-1 / FIX 2 / FIX 3 regressions
# ---------------------------------------------------------------------------


def _win_day(day: date):
    """Long TP fill at bar 14: high clearly above 0.10% TP."""
    d0 = build_data([_short_tp_day(day)])
    tp = 1.10000 + 0.0010 * 1.10000
    d0.high[14] = tp + 0.00005
    return d0


def test_holdout_bust_cannot_touch_develop_metrics():
    """A config that is develop-profitable and only busts in the holdout
    must keep its develop metrics. Holdout must not be able to void them."""
    holdout = date(2026, 2, 20)
    days = []
    for i in range(45):
        days.append(_short_tp_day(date(2026, 1, 5) + timedelta(days=i)))
    for i in range(25):
        days.append(_crash_day(date(2026, 2, 20) + timedelta(days=i)))
    d = build_data(days)
    n_dev_bars = sum(1 for t in d.times_et if t.date() < holdout)
    tp = 1.10000 + 0.0010 * 1.10000
    i = 0
    while i < n_dev_bars:
        d.high[i + 14] = tp + 0.00005
        key = int(d.et_key[i])
        j = i
        while j < n_dev_bars and int(d.et_key[j]) == key:
            j += 1
        i = j
    sigs = np.zeros(len(d), dtype=np.int8)
    i = 0
    while i < len(d):
        sigs[i + 12] = 1
        key = int(d.et_key[i])
        j = i
        while j < len(d) and int(d.et_key[j]) == key:
            j += 1
        if j - i > 26:
            sigs[i + 25] = 1  # second crash-day signal
        i = j

    lock = synth_lock()
    costs = synth_costs(lock)
    start = 800.0  # develop wins cannot bust this; holdout crash days will
    trades_full = ar.simulate_config(
        d, sigs, PCT_EXIT, None, None, atr_all(d), costs, lock, start_balance=start
    )
    dev = [t for t in trades_full if date.fromisoformat(t.et_date) < holdout]
    ho = [t for t in trades_full if date.fromisoformat(t.et_date) >= holdout]
    assert dev, "develop must have trades"
    dmet = ar.pack_metrics(dev, start, -300.0)
    assert dmet["trades"] >= 40
    assert dmet["net_pnl"] > 0
    assert ar.score_row(dmet) != -1e9
    # bust only in holdout
    bust = ar.bankrupt_at(trades_full)
    assert bust is not None
    assert date.fromisoformat(bust) >= holdout

    # develop-only simulation must match byte-for-byte
    d_only = core.M5Data(
        open=d.open[:n_dev_bars].copy(),
        high=d.high[:n_dev_bars].copy(),
        low=d.low[:n_dev_bars].copy(),
        close=d.close[:n_dev_bars].copy(),
        vol=d.vol[:n_dev_bars].copy(),
        spread=d.spread[:n_dev_bars].copy(),
        et_min=d.et_min[:n_dev_bars].copy(),
        et_key=d.et_key[:n_dev_bars].copy(),
        et_dow=d.et_dow[:n_dev_bars].copy(),
        times_et=d.times_et[:n_dev_bars],
    )
    trades_dev = ar.simulate_config(
        d_only,
        sigs[:n_dev_bars],
        PCT_EXIT,
        None,
        None,
        atr_all(d_only),
        costs,
        lock,
        start_balance=start,
    )
    dmet_only = ar.pack_metrics(trades_dev, start, -300.0)
    assert json.dumps(dmet, sort_keys=True, default=float) == json.dumps(
        dmet_only, sort_keys=True, default=float
    )
    assert ho  # holdout actually traded (and busted)


def test_holdout_pct_uses_carried_equity():
    """Holdout day-percentages must use equity leaving develop, not a fresh $10k."""
    holdout = date(2026, 3, 10)
    d_win = _win_day(date(2026, 3, 2))
    d_win2 = _win_day(date(2026, 3, 10))
    d = core.M5Data(
        open=np.concatenate([d_win.open, d_win2.open]),
        high=np.concatenate([d_win.high, d_win2.high]),
        low=np.concatenate([d_win.low, d_win2.low]),
        close=np.concatenate([d_win.close, d_win2.close]),
        vol=np.concatenate([d_win.vol, d_win2.vol]),
        spread=np.concatenate([d_win.spread, d_win2.spread]),
        et_min=np.concatenate([d_win.et_min, d_win2.et_min]),
        et_key=np.concatenate([d_win.et_key, d_win2.et_key]),
        et_dow=np.concatenate([d_win.et_dow, d_win2.et_dow]),
        times_et=d_win.times_et + d_win2.times_et,
    )
    sigs = np.zeros(len(d), dtype=np.int8)
    sigs[SIGNAL_I] = 1
    sigs[len(d_win) + SIGNAL_I] = 1
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
    dev = [t for t in trades if date.fromisoformat(t.et_date) < holdout]
    ho = [t for t in trades if date.fromisoformat(t.et_date) >= holdout]
    assert len(dev) == 1 and len(ho) == 1
    ho_start = dev[-1].equity_after
    assert ho_start != 10_000.0
    hmet = ar.pack_metrics(ho, ho_start, -300.0)
    expected = ho[0].pnl / ho_start
    assert hmet["median_daily_pct"] == pytest.approx(expected)
    wrong = ho[0].pnl / 10_000.0
    assert hmet["median_daily_pct"] != pytest.approx(wrong)


def test_gap_through_stop_fills_at_bar_open():
    """A bar that opens through the stop fills at the open, not the stop level.
    Realized loss is measured (may exceed risk_per_trade_usd), not capped."""
    d = build_data([_short_tp_day(date(2026, 3, 2))])
    sigs = np.zeros(len(d), dtype=np.int8)
    sigs[SIGNAL_I] = 1
    entry = float(d.open[FILL_I])
    sl = entry - 0.0025 * entry  # 1.09725
    # bar 14 gaps through the stop
    d.open[14] = sl - 0.00100  # 1.09625
    d.high[14] = d.open[14] + 0.00010
    d.low[14] = d.open[14] - 0.00010
    d.close[14] = d.open[14]
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
    assert t.reason == "sl"
    assert t.exit == pytest.approx(d.open[14])  # gapped fill, not sl level
    assert t.exit < sl
    intended = t.sl_points * t.lots * 1.0
    realized = (t.entry - t.exit) * 100_000.0 * t.lots
    assert realized > intended  # measured, not capped
