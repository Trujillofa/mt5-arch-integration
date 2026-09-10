"""Causal gold session scalp — London OR, not NY cash 09:30."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

TZ_ET = ZoneInfo("America/New_York")
TZ_LON = ZoneInfo("Europe/London")

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from xau_session_scalp_core import (  # noqa: E402
    FAMILY_ID,
    OR_MINUTES,
    SUPERSEDED_FAMILY_ID,
    GoldSessionId,
    SessionBox,
    friday_entry_blocked,
    in_london_entry,
    in_ny_entry,
    is_ny_metals,
    looks_like_gold,
    opening_range_at,
    scalp_signal_at,
    scalp_signal_series,
    session_box_at,
    session_id,
    to_et,
    to_london,
)


def _m5_from(start_local: datetime, n: int, *, base: float = 2400.0):
    t0 = start_local.astimezone(UTC)
    times = [t0 + timedelta(minutes=5 * i) for i in range(n)]
    close = np.full(n, base, dtype=float)
    high = close + 1.0
    low = close - 1.0
    vol = np.ones(n, dtype=float)
    return times, high, low, close, vol


def test_looks_like_gold_not_index():
    assert looks_like_gold("XAUUSD")
    assert looks_like_gold("XAUUSD.r")
    assert looks_like_gold("GOLD")
    assert not looks_like_gold("US100")
    assert not looks_like_gold("EURUSD")


def test_family_is_new_not_index_orb():
    assert FAMILY_ID == "xau_london_defined_r_be_flat_v1"
    assert SUPERSEDED_FAMILY_ID == "xau_london_orb_overlap_vwap_ema_flat"
    assert FAMILY_ID != "ny_cash_orb_vwap_ema_flat"


def test_ny_metals_starts_0800_not_cash_0930():
    # 2026-03-16 Monday EDT: 08:00 ET = 12:00 UTC; 09:29 ET is still metals.
    ny0800 = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
    assert to_et(ny0800).hour == 8
    assert is_ny_metals(ny0800)
    cash_open = datetime(2026, 3, 16, 13, 30, tzinfo=UTC)  # 09:30 ET
    assert is_ny_metals(cash_open)
    pre_metals = datetime(2026, 3, 16, 11, 30, tzinfo=UTC)  # 07:30 ET
    assert not is_ny_metals(pre_metals)


def test_london_or_not_known_until_range_complete():
    # 2026-03-16: BST. London 08:00 = 07:00 UTC.
    start = datetime(2026, 3, 16, 7, 0, tzinfo=TZ_LON)  # 08:00 London? wait 7:00 local
    # Start at 07:30 London so we have a pre-OR bar, then 08:00.
    start = datetime(2026, 3, 16, 7, 30, tzinfo=TZ_LON)
    times, high, low, close, vol = _m5_from(start, n=40, base=2400.0)
    # bar 0 = 07:30, bar 6 = 08:00, bar 11 = 08:25, bar 12 = 08:30
    assert to_london(times[6]).hour == 8 and to_london(times[6]).minute == 0
    high[6] = 2410.0
    high[7] = 2408.0
    high[11] = 2412.0
    low[6] = 2390.0

    or_at_0800 = opening_range_at(times, high, low, 6, or_minutes=30)
    assert or_at_0800.complete is False
    assert np.isnan(or_at_0800.high)

    or_at_0825 = opening_range_at(times, high, low, 11, or_minutes=30)
    assert or_at_0825.complete is False

    or_at_0830 = opening_range_at(times, high, low, 12, or_minutes=30)
    assert or_at_0830.complete is True
    assert or_at_0830.high == 2412.0
    assert or_at_0830.low == 2390.0


def test_or_does_not_use_ny_cash_0930():
    # Plant a spike only in NY 09:30-09:45 ET; London OR must ignore it.
    start = datetime(2026, 3, 16, 7, 30, tzinfo=TZ_LON)
    times, high, low, close, vol = _m5_from(start, n=80, base=2400.0)
    for i, t in enumerate(times):
        et = to_et(t)
        if et.hour == 9 and et.minute in (30, 35, 40):
            high[i] = 2500.0
            low[i] = 2300.0
    # First bar with London open >= 08:30
    idx = next(i for i, t in enumerate(times) if to_london(t).hour == 8 and to_london(t).minute == 30)
    ors = opening_range_at(times, high, low, idx, or_minutes=30)
    assert ors.complete is True
    assert ors.high < 2450.0


def test_london_entry_and_ny_box():
    lon_0830 = datetime(2026, 3, 16, 8, 30, tzinfo=TZ_LON)
    assert in_london_entry(lon_0830, 30)
    assert session_box_at(lon_0830) == SessionBox.LONDON
    lon_1100 = datetime(2026, 3, 16, 11, 0, tzinfo=TZ_LON)
    assert not in_london_entry(lon_1100, 30)
    ny_0800 = datetime(2026, 3, 16, 8, 0, tzinfo=TZ_ET)
    assert in_ny_entry(ny_0800)
    assert session_box_at(ny_0800) == SessionBox.NY
    ny_1100 = datetime(2026, 3, 16, 11, 0, tzinfo=TZ_ET)
    assert not in_ny_entry(ny_1100)
    assert session_box_at(ny_1100) == SessionBox.NONE


def test_overlap_session_id_is_not_ny_cash():
    # 2026-03-16 13:00 UTC = 09:00 EDT / 14:00 BST — both desks open.
    ts = datetime(2026, 3, 16, 13, 0, tzinfo=UTC)
    assert session_id(ts) == GoldSessionId.OVERLAP


def test_signal_uses_only_bars_through_i():
    start = datetime(2026, 3, 16, 7, 30, tzinfo=TZ_LON)
    times, high, low, close, vol = _m5_from(start, n=50, base=2400.0)
    # Trend up after OR so a long can fire, then a future spike that must not leak.
    idx_0830 = next(
        i for i, t in enumerate(times) if to_london(t).hour == 8 and to_london(t).minute == 30
    )
    close[idx_0830:] = 2410.0
    high[idx_0830:] = 2411.0
    low[idx_0830:] = 2409.0
    future = min(idx_0830 + 8, len(times) - 1)
    high[future] = 2600.0
    close[future] = 2600.0
    sig_now = scalp_signal_at(times, high, low, close, vol, idx_0830 + 1)
    # Future spike must not change the earlier bar's OR high.
    ors = opening_range_at(times, high, low, idx_0830 + 1, or_minutes=30)
    assert ors.high < 2500.0
    assert sig_now.reason in {
        "london_orb_vwap_ema_long",
        "no_confluence",
        "ema_warmup",
        "atr_warmup",
        "dead_atr",
        "or_incomplete",
        "or_width",
        "no_vwap",
    }


def test_one_signal_per_box_and_forming_bar_zero():
    start = datetime(2026, 3, 16, 7, 30, tzinfo=TZ_LON)
    times, high, low, close, vol = _m5_from(start, n=60, base=2400.0)
    close[:] = np.linspace(2390.0, 2450.0, 60)
    high[:] = close + 2.0
    low[:] = close - 2.0
    series = scalp_signal_series(
        times, high, low, close, vol, exclude_forming=True,
        or_width_atr_min=0.0, or_width_atr_max=99.0,
    )
    assert series[-1] == 0
    longs = int(np.sum(series == 1))
    assert longs <= 2  # London box + maybe NY box, not one per bar


def test_friday_cutoff():
    fri = datetime(2026, 3, 20, 14, 0, tzinfo=TZ_ET)
    assert friday_entry_blocked(fri)
    thu = datetime(2026, 3, 19, 14, 0, tzinfo=TZ_ET)
    assert not friday_entry_blocked(thu)


def test_or_minutes_default_is_thirty_not_index_fifteen():
    assert OR_MINUTES == 30


def test_or_width_rejects_extreme_range():
    start = datetime(2026, 3, 16, 7, 30, tzinfo=TZ_LON)
    times, high, low, close, vol = _m5_from(start, n=50, base=2400.0)
    high[6:12] = 2500.0
    low[6:12] = 2300.0
    # Evaluate after EMA21 warmup, still inside London [08:30, 11:00).
    idx = next(
        i for i, t in enumerate(times) if to_london(t).hour == 9 and to_london(t).minute == 30
    )
    close[idx] = 2510.0
    high[idx] = 2512.0
    low[idx] = 2508.0
    sig = scalp_signal_at(times, high, low, close, vol, idx)
    assert sig.value == 0
    assert sig.reason == "or_width"
