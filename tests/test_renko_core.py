"""Renko event clock — builder, ADX, Bollinger and screen-contract fixtures.

Pins the ``required_fixtures`` list in
``results/xau_charters/2026-09-19_renko_event_clock_vendor_v1.json`` and the
behavioural parity points against the vendored MQL5 sources under
``mql5/Experts/vendor/``. Stdlib only, like the module under test.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import renko_core as rc  # noqa: E402
import renko_event_clock_screen as screen  # noqa: E402

TICK = 0.01
CHARTER = _ROOT / "results" / "xau_charters" / "2026-09-19_renko_event_clock_vendor_v1.json"


def _builder(brick_size: float) -> rc.RenkoBuilder:
    return rc.RenkoBuilder(TICK, rc.size_in_tick_units(brick_size, TICK))


def _up_brick(open_: float, size: float, run: int = 1) -> rc.Brick:
    return rc.Brick(open=open_, close=open_ + size, direction=1, run=run)


# --------------------------------------------------------------------------
# builder
# --------------------------------------------------------------------------


def test_renko_builder_matches_mql5_two_brick_reversal() -> None:
    """A reversal spends two bricks turning round; the first printed brick opens
    one brick back from the previous close, exactly as ``CRenkoBuilder`` does."""
    b = _builder(16.0)
    assert b.push_price(2000.0) == []  # first price only anchors
    assert [(x.open, x.close, x.direction, x.run) for x in b.push_price(2016.0)] == [
        (2000.0, 2016.0, 1, 1)
    ]
    assert [(x.open, x.close, x.direction, x.run) for x in b.push_price(2032.0)] == [
        (2016.0, 2032.0, 1, 2)
    ]
    # one brick back down is not enough to reverse
    assert b.push_price(2017.0) == []
    # two bricks against trend reverse; only the excess prints
    assert [(x.open, x.close, x.direction, x.run) for x in b.push_price(2000.0)] == [
        (2016.0, 2000.0, -1, 1)
    ]


def test_renko_builder_multi_brick_single_push() -> None:
    """One price may complete several bricks; runs increment across them."""
    b = _builder(10.0)
    b.push_price(100.0)
    bricks = b.push_price(135.0)
    assert [(x.open, x.close, x.run) for x in bricks] == [
        (100.0, 110.0, 1),
        (110.0, 120.0, 2),
        (120.0, 130.0, 3),
    ]
    assert b.direction == 1


def test_renko_builder_gap_above_cap_fails_closed() -> None:
    """A gap larger than the vendor's 4096-brick cap raises instead of
    materialising the run, mirroring the EA pausing new entries."""
    b = _builder(0.01)
    b.push_price(100.0)
    with pytest.raises(rc.RenkoOverflowError):
        b.push_price(100.0 + 0.01 * (rc.MAX_BRICKS_PER_PUSH + 5))


def test_brick_size_quantizes_to_whole_ticks() -> None:
    b = rc.RenkoBuilder(TICK, rc.size_in_tick_units(16.004, TICK))
    assert b.brick_size == pytest.approx(16.0)
    with pytest.raises(ValueError):
        rc.size_in_tick_units(0.0, TICK)


# --------------------------------------------------------------------------
# ADX
# --------------------------------------------------------------------------


def test_adx_wilder_warmup_matches_vendor_state_machine() -> None:
    """Not ready before 2*period bricks; ready at exactly 2*period+1 pushes.

    The vendor consumes one brick to seed ``prev``, ``period`` more to fill the
    Wilder sums, then ``period`` DX values to seed the ADX average.
    """
    period = 5
    adx = rc.RenkoADX(period)
    px = 1000.0
    for _ in range(2 * period - 1):
        adx.push(_up_brick(px, 10.0))
        px += 10.0
        assert not adx.ready
    adx.push(_up_brick(px, 10.0))
    assert adx.ready  # exactly 2*period pushes: 1 seeds prev, period fills the
    # Wilder sums and yields the first DX, period-1 more complete the DX average
    # a pure uptrend has no -DM at all
    assert adx.plus_di > adx.minus_di
    assert adx.minus_di == pytest.approx(0.0)


def test_adx_exit_ignores_threshold_on_di_flip() -> None:
    """``raw_direction`` reports the DI side even when ADX is below the entry gate.

    The vendor applies the strength threshold to entries only, so a position is
    closed on a DI flip after ADX has decayed. Losing that asymmetry would make
    exits stickier than the source.
    """
    adx = rc.RenkoADX(3)
    px = 1000.0
    for _ in range(9):
        adx.push(_up_brick(px, 10.0))
        px += 10.0
    assert adx.ready
    impossible_threshold = adx.adx + 1000.0
    assert adx.direction(impossible_threshold, 0.0) == 0
    assert adx.raw_direction() == 1


# --------------------------------------------------------------------------
# Bollinger
# --------------------------------------------------------------------------


def test_bollinger_excludes_current_brick() -> None:
    """Bands are evaluated before the new close is appended, so the brick being
    judged never contributes to the band that judges it."""
    bb = rc.RenkoBollinger(2)
    bb.push(rc.Brick(0.0, 10.0, 1, 1), rc.BollingerMode.BREAKOUT, 1.0, 10.0, 1e9)
    bb.push(rc.Brick(10.0, 30.0, 1, 2), rc.BollingerMode.BREAKOUT, 1.0, 10.0, 1e9)
    assert not bb.ready  # only two closes banked, still no band on the 2nd push
    bb.push(rc.Brick(30.0, 1000.0, 1, 3), rc.BollingerMode.BREAKOUT, 1.0, 10.0, 1e9)
    # mid is the mean of the two PREVIOUS closes (10, 30), untouched by 1000
    assert bb.ready
    assert bb.mid == pytest.approx(20.0)


def test_bollinger_population_stdev() -> None:
    """Population stdev (÷N), matching the vendor. Sample stdev would widen the
    band enough to suppress this signal."""
    bb = rc.RenkoBollinger(2)
    bb.push(rc.Brick(0.0, 0.0, 1, 1), rc.BollingerMode.BREAKOUT, 1.0, 10.0, 1e9)
    bb.push(rc.Brick(0.0, 20.0, 1, 2), rc.BollingerMode.BREAKOUT, 1.0, 10.0, 1e9)
    # closes [0, 20]: mid 10, population sd 10 -> upper 20; sample sd 14.14 -> upper 24.14
    signal = bb.push(rc.Brick(20.0, 22.0, 1, 3), rc.BollingerMode.BREAKOUT, 1.0, 10.0, 1e9)
    assert signal == 1  # 22 > 20 clears the population band only


def test_squeeze_width_gate_blocks_wide_bands() -> None:
    """Mode 4 refuses a breakout when the band is wider than the squeeze limit."""
    args = (rc.BollingerMode.SQUEEZE_BREAKOUT, 1.0, 10.0)
    wide = rc.RenkoBollinger(2)
    wide.push(rc.Brick(0.0, 0.0, 1, 1), *args, 0.5)
    wide.push(rc.Brick(0.0, 20.0, 1, 2), *args, 0.5)
    assert wide.push(rc.Brick(20.0, 22.0, 1, 3), *args, 0.5) == 0  # width 2 bricks > 0.5

    narrow = rc.RenkoBollinger(2)
    narrow.push(rc.Brick(0.0, 0.0, 1, 1), *args, 50.0)
    narrow.push(rc.Brick(0.0, 20.0, 1, 2), *args, 50.0)
    assert narrow.push(rc.Brick(20.0, 22.0, 1, 3), *args, 50.0) == 1


def test_midline_cross_needs_a_crossing_not_a_side() -> None:
    bb = rc.RenkoBollinger(2)
    m = rc.BollingerMode.MIDLINE_CROSS
    bb.push(rc.Brick(0.0, 10.0, 1, 1), m, 1.0, 10.0, 1e9)
    bb.push(rc.Brick(10.0, 30.0, 1, 2), m, 1.0, 10.0, 1e9)
    # first banded brick establishes the side; no cross yet
    assert bb.push(rc.Brick(30.0, 40.0, 1, 3), m, 1.0, 10.0, 1e9) == 0
    # drop below the midline: a down cross on a down brick signals short
    assert bb.push(rc.Brick(40.0, 5.0, -1, 1), m, 1.0, 10.0, 1e9) == -1


# --------------------------------------------------------------------------
# path conventions
# --------------------------------------------------------------------------


def test_path_convention_reversed_is_reported_not_selected() -> None:
    """Both conventions exist; the reversed one is a falsifier, so it must
    actually differ from the default rather than being a silent alias."""
    bull = (10.0, 12.0, 9.0, 11.0)
    assert rc.bar_path(*bull) == (10.0, 9.0, 12.0, 11.0)
    assert rc.bar_path(*bull, convention="reversed") == (10.0, 12.0, 9.0, 11.0)
    bear = (10.0, 12.0, 9.0, 9.5)
    assert rc.bar_path(*bear) == (10.0, 12.0, 9.0, 9.5)
    assert rc.bar_path(*bear, convention="reversed") == (10.0, 9.0, 12.0, 9.5)
    with pytest.raises(ValueError):
        rc.bar_path(*bull, convention="whatever")


# --------------------------------------------------------------------------
# screen contract
# --------------------------------------------------------------------------

_T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _bars(ohlc: list[tuple[float, float, float, float]], spread: float = 11.0) -> list[screen.Bar]:
    return [
        screen.Bar(_T0 + timedelta(minutes=15 * i), o, h, low, c, spread)
        for i, (o, h, low, c) in enumerate(ohlc)
    ]


def _breakout_vehicle(**over: object) -> screen.Vehicle:
    base: dict[str, object] = {
        "key": "t",
        "label": "t",
        "engine": "bb",
        "brick_size": 1.0,
        "tp_bricks": 2.0,
        "sl_bricks": 3.0,
        "max_hold_minutes": 0,
        "cooldown_bricks": 0,
        "entry_run": 1,
        "bb_mode": rc.BollingerMode.BREAKOUT,
        "bb_period": 2,
        "deviation": 0.01,
    }
    base.update(over)
    return screen.Vehicle(**base)  # type: ignore[arg-type]


def _run(bars: list[screen.Bar], vehicle: screen.Vehicle, **over: object) -> screen.Stats:
    kwargs: dict[str, object] = {
        "convention": "ohlc_tester_default",
        "slippage_points": 0.0,
        "commission_per_lot": 0.0,
        "point_size": 0.01,
        "lots": 0.01,
    }
    kwargs.update(over)
    return screen.simulate(bars, vehicle, **kwargs)  # type: ignore[arg-type]


def _rising(n: int, start: float = 100.0, step: float = 1.0) -> list[tuple[float, float, float, float]]:
    return [(start + i * step, start + (i + 1) * step, start + i * step, start + (i + 1) * step) for i in range(n)]


def test_entry_run_below_minimum_is_no_signal() -> None:
    """A run requirement the brick series never reaches produces no trade."""
    bars = _bars(_rising(12))
    assert _run(bars, _breakout_vehicle(entry_run=1)).trades
    assert not _run(bars, _breakout_vehicle(entry_run=99)).trades


def test_cooldown_blocks_entry_for_n_bricks() -> None:
    """Cooldown is counted in completed bricks, not bars or time."""
    bars = _bars(_rising(40))
    hot = _run(bars, _breakout_vehicle(max_hold_minutes=15))
    cold = _run(bars, _breakout_vehicle(max_hold_minutes=15, cooldown_bricks=10))
    assert len(cold.trades) < len(hot.trades)


def test_virtual_sl_priority_over_tp_same_bar() -> None:
    """On a bar that reaches both levels, the one the assumed path reaches first
    wins — and SL is evaluated before TP at every evaluation point."""
    v = _breakout_vehicle(tp_bricks=40.0, sl_bricks=3.0)
    rise = _rising(8)
    last = rise[-1][3]

    # bullish bar: path is open -> low -> high -> close, so the stop comes first
    bull = (last, last + 50.0, last - 50.0, last + 1.0)
    stats = _run(_bars([*rise, bull]), v)
    assert stats.trades[0].reason == "SL"
    assert stats.trades[0].exit_px == pytest.approx(stats.trades[0].entry_px - 3.0)

    # mirror: a bar that closed down is traversed high-first, so the target comes
    # first. Which level the bar reaches first is decided by the assumed path, and
    # that is exactly why the screen must report both conventions.
    bear = (last, last + 50.0, last - 50.0, last - 1.0)
    stats = _run(_bars([*rise, bear]), v)
    assert stats.trades[0].reason == "TP"


def test_max_hold_forces_exit() -> None:
    """Time stop fires at the first bar at or beyond max_hold_minutes."""
    bars = _bars(_rising(6) + [(106.0, 106.1, 105.9, 106.0)] * 20)
    stats = _run(bars, _breakout_vehicle(max_hold_minutes=30))
    assert stats.exit_reasons.get("TIME", 0) >= 1
    held = [(t.exit_time - t.entry_time).total_seconds() / 60.0 for t in stats.trades if t.reason == "TIME"]
    assert all(h >= 30.0 for h in held)


def test_cost_measured_at_entry_deducted_at_exit() -> None:
    """Round-trip cost is computed from the entry bar's spread and charged once."""
    bars = _bars(_rising(8), spread=30.0)
    stats = _run(bars, _breakout_vehicle())
    trade = stats.trades[0] if stats.trades else None
    assert trade is not None
    expected = (30.0 + 2 * 0.0) * 0.01 * screen.CONTRACT_SIZE * 0.01
    assert trade.cost == pytest.approx(expected)
    gross = (trade.exit_px - trade.entry_px) * screen.CONTRACT_SIZE * 0.01 * trade.direction
    assert trade.pnl == pytest.approx(gross - expected)


def test_spread_gate_blocks_entry_above_max_fraction() -> None:
    """Ported for fidelity: spread above ``max_spread_fraction * brick`` blocks a
    new entry. On XAUUSD at the frozen brick sizes this never binds (threshold
    490-1050 points vs ~11 measured), but a 1.0 brick makes it observable."""
    cheap = _run(_bars(_rising(8), spread=30.0), _breakout_vehicle())  # 0.30 <= 0.35
    dear = _run(_bars(_rising(8), spread=40.0), _breakout_vehicle())  # 0.40 > 0.35
    assert cheap.trades
    assert not dear.trades


def test_slippage_only_moves_cost_not_fills() -> None:
    bars = _bars(_rising(8))
    a = _run(bars, _breakout_vehicle())
    b = _run(bars, _breakout_vehicle(), slippage_points=20.0)
    assert [t.exit_px for t in a.trades] == [t.exit_px for t in b.trades]
    assert sum(t.pnl for t in b.trades) < sum(t.pnl for t in a.trades)


def test_reentry_exits_at_midline() -> None:
    """Mode 2 banks at the band midline rather than waiting for an opposite flip."""
    v = _breakout_vehicle(bb_mode=rc.BollingerMode.REENTRY, bb_period=3, deviation=1.0, max_hold_minutes=0)
    ohlc = _rising(10) + [(110.0, 110.5, 100.0, 101.0)] + _rising(10, start=101.0)
    stats = _run(_bars(ohlc), v)
    assert stats.exit_reasons.get("BB_MID", 0) >= 1


# --------------------------------------------------------------------------
# charter integrity
# --------------------------------------------------------------------------


def test_charter_is_frozen_and_matches_its_sidecar() -> None:
    """A frozen charter must never be edited in place; the screen refuses to run
    if it was, and this pins the same invariant in CI."""
    sidecar = CHARTER.with_suffix(".json.sha256")
    assert sidecar.exists()
    assert hashlib.sha256(CHARTER.read_bytes()).hexdigest() == sidecar.read_text().strip()
    charter = json.loads(CHARTER.read_text(encoding="utf-8"))
    assert charter["status"] == "FROZEN"
    assert charter["n_free_knobs"] == 0
    assert charter["safety"] == {
        "offline_only": True,
        "promote_default": "no",
        "live_go": False,
        "vendor_ea_orders_disabled_in_repo": charter["safety"]["vendor_ea_orders_disabled_in_repo"],
    }


def test_screen_vehicles_come_from_the_charter_not_from_code() -> None:
    """Every frozen number is read from the charter, so a tuned value cannot be
    slipped into the runner without editing a sealed file."""
    charter = json.loads(CHARTER.read_text(encoding="utf-8"))
    vehicles = screen.vehicles_from_charter(charter)
    assert len(vehicles) == charter["search_cardinality"] == 5
    adx = next(v for v in vehicles if v.key == "adx")
    assert adx.adx_threshold == charter["rule"]["vehicle_adx"]["adx_threshold"]
    assert adx.sl_bricks == charter["rule"]["vehicle_adx"]["sl_bricks"]
    squeeze = next(v for v in vehicles if v.key == "bb_squeeze")
    assert squeeze.squeeze_max_width == charter["rule"]["vehicle_bb_squeeze"]["squeeze_max_width_bricks"]
