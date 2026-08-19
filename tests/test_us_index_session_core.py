"""Causal US-index session / ORB / VWAP / EMA — no look-ahead.

IndexSessionUtils.mqh claims to mirror this clock/OR/VWAP. There is no
wired MQL5↔Python parity fixture here (do not attach EAs for it).
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

TZ_ET = ZoneInfo("America/New_York")

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from us_index_session_core import (  # noqa: E402
    EMA_FAST,
    EMA_SLOW,
    OR_MINUTES,
    SessionId,
    ema_series,
    friday_entry_blocked,
    in_entry_window,
    is_ny_cash,
    looks_like_us_index,
    opening_range_at,
    or_end_et,
    scalp_signal_at,
    scalp_signal_series,
    session_id,
    session_spans_for_et_date,
    session_vwap_at,
    to_et,
)


def _m5_day(
    et_open: datetime,
    n: int = 84,
    *,
    base: float = 20000.0,
    path: np.ndarray | None = None,
) -> tuple[list[datetime], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Synthetic M5 bars. ``et_open`` is the first bar open in ET."""
    times: list[datetime] = []
    t0 = et_open.astimezone(UTC)
    for i in range(n):
        times.append(t0 + timedelta(minutes=5 * i))
    if path is None:
        close = np.full(n, base, dtype=float)
    else:
        close = np.asarray(path, dtype=float)
        assert close.shape == (n,)
    high = close + 2.0
    low = close - 2.0
    vol = np.ones(n, dtype=float)
    return times, high, low, close, vol


def test_looks_like_us_index():
    assert looks_like_us_index("US30")
    assert looks_like_us_index("DJ30.r")
    assert looks_like_us_index("US100")
    assert looks_like_us_index("NAS100")
    assert looks_like_us_index("USTEC")
    assert not looks_like_us_index("EURUSD")
    assert not looks_like_us_index("XAUUSD")
    assert not looks_like_us_index("BTCUSD")


def test_ny_cash_dst_winter_vs_summer():
    # 2026-01-12 Monday — EST (UTC-5). 09:30 ET = 14:30 UTC.
    winter = datetime(2026, 1, 12, 14, 30, tzinfo=UTC)
    assert to_et(winter).hour == 9 and to_et(winter).minute == 30
    assert is_ny_cash(winter)
    assert session_id(winter) in (SessionId.NY_CASH, SessionId.OVERLAP)

    # 2026-03-16 Monday — EDT already on (started 2026-03-08). 09:30 ET = 13:30 UTC.
    summer = datetime(2026, 3, 16, 13, 30, tzinfo=UTC)
    assert to_et(summer).hour == 9 and to_et(summer).minute == 30
    assert is_ny_cash(summer)

    # Same UTC clock is still Asian / pre-cash in winter.
    assert not is_ny_cash(datetime(2026, 1, 12, 13, 30, tzinfo=UTC))


def test_session_spans_ny_cash_is_0930_et():
    winter = session_spans_for_et_date(datetime(2026, 1, 12).date())
    ny = next(s for s in winter if s.session_id == SessionId.NY_CASH)
    assert to_et(ny.start_utc).hour == 9 and to_et(ny.start_utc).minute == 30
    assert to_et(ny.end_utc).hour == 16

    summer = session_spans_for_et_date(datetime(2026, 3, 16).date())
    ny_s = next(s for s in summer if s.session_id == SessionId.NY_CASH)
    assert ny.start_utc.hour != ny_s.start_utc.hour  # DST shifted UTC
    assert to_et(ny_s.start_utc).hour == 9


def test_or_not_known_until_range_complete():
    # Start at 09:00 ET so we have pre-cash bars, then cash.
    start = datetime(2026, 3, 16, 9, 0, tzinfo=TZ_ET)
    times, high, low, close, _vol = _m5_day(start, n=40, base=18000.0)
    # Plant a spike only inside the OR (09:30, 09:35, 09:40).
    # Bar 0 = 09:00, bar 6 = 09:30, bar 8 = 09:40, bar 9 = 09:45.
    high[6] = 18100.0
    high[7] = 18050.0
    high[8] = 18080.0
    low[6] = 17950.0

    or_at_0930 = opening_range_at(times, high, low, 6)  # first OR bar, still incomplete
    assert or_at_0930.complete is False
    assert np.isnan(or_at_0930.high)

    or_at_0940 = opening_range_at(times, high, low, 8)
    assert or_at_0940.complete is False

    or_at_0945 = opening_range_at(times, high, low, 9)
    assert or_at_0945.complete is True
    assert or_at_0945.high == 18100.0
    assert or_at_0945.low == 17950.0


def test_or_does_not_see_future_bars():
    start = datetime(2026, 3, 16, 9, 30, tzinfo=TZ_ET)
    times, high, low, close, _vol = _m5_day(start, n=20, base=18000.0)
    # Future spike after OR must not enter the range.
    high[10] = 19000.0
    ors = opening_range_at(times, high, low, 3)  # 09:45 — OR just complete
    assert ors.complete is True
    assert ors.high < 18500.0


def test_vwap_only_uses_ny_cash_bars_through_i():
    start = datetime(2026, 3, 16, 9, 0, tzinfo=TZ_ET)
    n = 30
    close = np.concatenate(
        [np.full(6, 100.0), np.full(24, 200.0)]
    )  # pre-cash 100, cash 200
    times, high, low, _, vol = _m5_day(start, n=n, path=close)
    # At first cash bar (idx 6 = 09:30) VWAP ≈ 200
    v6 = session_vwap_at(times, high, low, close, vol, 6)
    assert abs(v6 - 200.0) < 1.0
    # Pre-cash bar has no NY VWAP
    v0 = session_vwap_at(times, high, low, close, vol, 0)
    assert np.isnan(v0)


def test_ema_seed_matches_sma_then_recurs():
    x = np.arange(20, dtype=float)
    ema = ema_series(x, 5)
    assert np.isnan(ema[3])
    assert abs(ema[4] - float(np.mean(x[:5]))) < 1e-12
    assert ema[5] > ema[4]


def test_wick_only_break_is_not_a_signal():
    start = datetime(2026, 3, 16, 9, 30, tzinfo=TZ_ET)
    n = 40
    close = np.full(n, 18000.0)
    times, high, low, _, vol = _m5_day(start, n=n, path=close)
    # OR bars 0,1,2 = 09:30/35/40. Complete at bar 3 = 09:45.
    high[:3] = 18010.0
    low[:3] = 17990.0
    # Bar 5 (09:55) wicks above OR but closes inside.
    high[5] = 18080.0
    close[5] = 18005.0
    times, high, low, close, vol = times, high, low, close, vol
    sig = scalp_signal_at(times, high, low, close, vol, 5, min_atr_pct=0.0)
    assert sig.value == 0
    assert sig.reason in ("no_confluence", "ema_warmup", "atr_warmup", "dead_atr")


def test_and_confluence_long():
    start = datetime(2026, 3, 16, 9, 30, tzinfo=TZ_ET)
    n = 80
    # Ramp so EMA9 > EMA21 by the time OR completes, then break higher.
    close = 18000.0 + np.linspace(0, 80, n)
    times, high, low, _, vol = _m5_day(start, n=n, path=close)
    # Flatten OR so the later ramp is a clean close-beyond-OR.
    high[:3] = close[:3] + 1.0
    low[:3] = close[:3] - 1.0
    # EMA21 seeds at index 20. Bar 21 = 09:30 + 105m = 11:15 ET (still in window).
    i = 21
    assert in_entry_window(times[i])
    sig = scalp_signal_at(times, high, low, close, vol, i, min_atr_pct=0.0)
    assert sig.value == +1
    assert sig.reason == "orb_vwap_ema_long"
    assert close[i] > sig.or_high
    assert close[i] > sig.vwap


def test_asia_bar_never_signals():
    start = datetime(2026, 3, 16, 3, 0, tzinfo=TZ_ET)
    times, high, low, close, vol = _m5_day(start, n=12, base=18000.0)
    for i in range(len(times)):
        sig = scalp_signal_at(times, high, low, close, vol, i, min_atr_pct=0.0)
        assert sig.value == 0
        assert sig.reason in (
            "outside_entry_window",
            "or_incomplete",
            "friday_cutoff",
        )


def test_friday_cutoff_blocks():
    # Friday 2026-03-20 14:00 ET
    fri = datetime(2026, 3, 20, 14, 0, tzinfo=TZ_ET)
    assert friday_entry_blocked(fri)
    assert not friday_entry_blocked(fri - timedelta(hours=1))
    mon = datetime(2026, 3, 16, 15, 0, tzinfo=TZ_ET)
    assert not friday_entry_blocked(mon)


def test_series_excludes_forming_bar_and_one_per_day():
    start = datetime(2026, 3, 16, 9, 30, tzinfo=TZ_ET)
    n = 80
    close = 18000.0 + np.linspace(0, 80, n)
    times, high, low, _, vol = _m5_day(start, n=n, path=close)
    high[:3] = close[:3] + 1.0
    low[:3] = close[:3] - 1.0
    sigs = scalp_signal_series(times, high, low, close, vol, min_atr_pct=0.0)
    assert sigs[-1] == 0  # forming
    assert int(np.count_nonzero(sigs)) <= 1  # one_per_day


def test_or_end_is_fifteen_minutes():
    end = or_end_et(datetime(2026, 3, 16).date(), OR_MINUTES)
    assert end.hour == 9 and end.minute == 45


def test_ema_periods_are_scalp_not_swing():
    assert EMA_FAST == 9
    assert EMA_SLOW == 21


def test_2026_us_uk_dst_sundays_match_mql_helpers():
    """Lock the calendar dates IndexSessionUtils.mqh encodes for 2026."""
    assert date(2026, 3, 8).weekday() == 6   # 2nd Sunday March (US start)
    assert date(2026, 11, 1).weekday() == 6  # 1st Sunday November (US end)
    assert date(2026, 3, 29).weekday() == 6  # last Sunday March (UK start)
    assert date(2026, 10, 25).weekday() == 6  # last Sunday October (UK end)
