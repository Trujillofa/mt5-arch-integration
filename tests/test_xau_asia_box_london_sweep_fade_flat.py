"""Synthetic fixture tests for asia_box_london_sweep_fade_flat (v2 charter).

No develop-screen / real-data evaluation. Offline only.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import xau_family_asia_box_london_sweep_fade_flat as fam  # noqa: E402
from xau_charter_protocol import (  # noqa: E402
    is_charter_runnable,
    validate_charter_file,
)

from backtest import START_BALANCE  # noqa: E402

CHARTER_V2 = ROOT / "results/xau_charters/2026-08-19_asia_box_london_sweep_fade_flat_v2.json"
CHARTER_V1 = ROOT / "results/xau_charters/2026-08-19_asia_box_london_sweep_fade_flat_v1.json"
V2_SHA = "d2f0b7becca0c489aa06275ea37af143e24449d34907c217d6f99877c0d578b4"
V1_SHA = "7cf9f46fd5ddd44c171f04260f8d4fac167cb005bf3f6d4d03c1c137c1399b7e"


def _bars_day(
    day: str,
    hours: list[int],
    *,
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    closes: list[float] | None = None,
    base: float = 2000.0,
    spreads: float = 0.0,
) -> pd.DataFrame:
    rows = []
    for j, h in enumerate(hours):
        cl = closes[j] if closes is not None else base
        op = opens[j] if opens is not None else cl
        hi = highs[j] if highs is not None else max(op, cl) + 0.5
        lo = lows[j] if lows is not None else min(op, cl) - 0.5
        rows.append(
            {
                "time": pd.Timestamp(f"{day} {h:02d}:00:00", tz="UTC"),
                "open": op,
                "high": hi,
                "low": lo,
                "close": cl,
                "spread": spreads,
                "timeframe": "H1",
            }
        )
    return pd.DataFrame(rows)


def _warmup_days(n_days: int = 2, start: str = "2024-01-01") -> pd.DataFrame:
    """Quiet days: box forms, no pierce-reclaim in hunt."""
    frames = []
    t0 = pd.Timestamp(start, tz="UTC")
    for d in range(n_days):
        day = (t0 + pd.DateOffset(days=int(d))).strftime("%Y-%m-%d")
        hours = list(range(1, 14))  # include flat hour 13
        opens = [2000.0] * len(hours)
        highs = [2000.8] * len(hours)
        lows = [1999.2] * len(hours)
        closes = [2000.1] * len(hours)
        frames.append(
            _bars_day(day, hours, opens=opens, highs=highs, lows=lows, closes=closes)
        )
    return pd.concat(frames, ignore_index=True)


def _box_day(
    day: str,
    *,
    box_high: float = 2010.0,
    box_low: float = 1990.0,
    signal: str | None = None,
    signal_hour: int = 10,
    post_open: float | None = None,
    post_high: float | None = None,
    post_low: float | None = None,
    post_close: float | None = None,
    include_hour13: bool = True,
    spreads: float = 0.0,
    skip_box_hours: bool = False,
) -> pd.DataFrame:
    """Build one calendar day with completed Asia box and optional hunt signal.

    signal: 'long' pierce below box_low then close inside;
            'short' pierce above box_high then close inside;
            'pierce_no_reclaim' wick beyond without close inside;
            None = flat-while-unswept.
    """
    hours = list(range(1, 8))  # box
    if not skip_box_hours:
        mid = 0.5 * (box_high + box_low)
        # Quiet box bars spanning the extremes on first/last box hour
        opens = [mid] * 7
        highs = [mid + 1.0] * 7
        lows = [mid - 1.0] * 7
        closes = [mid] * 7
        highs[0] = box_high
        lows[0] = mid - 0.5
        lows[-1] = box_low
        highs[-1] = mid + 0.5
        box_df = _bars_day(
            day, hours, opens=opens, highs=highs, lows=lows, closes=closes, spreads=spreads
        )
    else:
        box_df = _bars_day(day, [], spreads=spreads)

    hunt_end = 13 if include_hour13 else 12
    hunt_hours = list(range(8, hunt_end + 1))
    mid = 0.5 * (box_high + box_low)
    n = len(hunt_hours)
    opens = [mid] * n
    highs = [mid + 0.5] * n
    lows = [mid - 0.5] * n
    closes = [mid] * n

    if signal is not None and signal_hour in hunt_hours:
        j = hunt_hours.index(signal_hour)
        if signal == "long":
            lows[j] = box_low - 2.0
            highs[j] = mid + 0.3
            closes[j] = box_low + 1.0  # back inside
            opens[j] = mid
        elif signal == "short":
            highs[j] = box_high + 2.0
            lows[j] = mid - 0.3
            closes[j] = box_high - 1.0
            opens[j] = mid
        elif signal == "pierce_no_reclaim":
            lows[j] = box_low - 2.0
            highs[j] = mid + 0.3
            closes[j] = box_low - 0.5  # closes still outside
            opens[j] = mid

        # Next bar (fill) path — default mild continuation inside box
        if j + 1 < n:
            fill_open = mid if post_open is None else post_open
            opens[j + 1] = fill_open
            highs[j + 1] = fill_open + 0.4 if post_high is None else post_high
            lows[j + 1] = fill_open - 0.4 if post_low is None else post_low
            closes[j + 1] = fill_open if post_close is None else post_close

    hunt_df = _bars_day(
        day,
        hunt_hours,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        spreads=spreads,
    )
    if skip_box_hours:
        return hunt_df
    return pd.concat([box_df, hunt_df], ignore_index=True)


def _run(df: pd.DataFrame, **kw):
    d = fam.prepare(df)
    log: list[dict] = []
    eq: list[float] = []
    m = fam.simulate(d, trade_log=log, equity_out=eq, **kw)
    return m, log, eq, d


# --- charter / plugin -----------------------------------------------------------------


def test_charter_v2_valid_v1_superseded_when_registered():
    assert validate_charter_file(CHARTER_V2) == []
    assert validate_charter_file(CHARTER_V1) == []
    assert hashlib.sha256(CHARTER_V2.read_bytes()).hexdigest() == V2_SHA
    assert hashlib.sha256(CHARTER_V1.read_bytes()).hexdigest() == V1_SHA
    ok2, why2 = is_charter_runnable(CHARTER_V2)
    assert ok2 is True, why2
    ok1, why1 = is_charter_runnable(CHARTER_V1)
    assert ok1 is False and "SUPERSEDED" in why1


def test_grid_cardinality_exactly_one():
    g = fam.build_grid()
    assert len(g) == 1
    assert g[0]["flat_hour"] == 13
    assert g[0]["box_hours"] == list(range(1, 8))
    assert g[0]["hunt_hours"] == list(range(8, 14))


def test_load_family_builtin():
    from xau_family_null_maxstat import load_family

    p = load_family("asia_box_london_sweep_fade_flat")
    assert p.name == "asia_box_london_sweep_fade_flat"
    assert p.kill_label == "KILL_ASIA_BOX_LONDON_SWEEP_FADE_FLAT"
    assert len(p.grid(max_n=10, seed=0)) == 1


# --- required fixtures -----------------------------------------------------------------


def test_same_bar_pierce_close_inside_long_accepted():
    warm = _warmup_days(2)
    day = _box_day("2024-01-03", signal="long", signal_hour=10)
    m, log, _, _ = _run(pd.concat([warm, day], ignore_index=True))
    assert len(log) >= 1
    t = log[0]
    assert t["direction"] == 1
    assert t["sl"] == pytest.approx(1990.0)
    assert t["tp"] == pytest.approx(2000.0)  # midline


def test_same_bar_pierce_close_inside_short_accepted():
    warm = _warmup_days(2)
    day = _box_day("2024-01-03", signal="short", signal_hour=10)
    m, log, _, _ = _run(pd.concat([warm, day], ignore_index=True))
    assert len(log) >= 1
    t = log[0]
    assert t["direction"] == -1
    assert t["sl"] == pytest.approx(2010.0)
    assert t["tp"] == pytest.approx(2000.0)


def test_pierce_without_close_inside_rejected():
    warm = _warmup_days(2)
    day = _box_day("2024-01-03", signal="pierce_no_reclaim", signal_hour=10)
    m, log, _, _ = _run(pd.concat([warm, day], ignore_index=True))
    assert log == []
    assert m.n_trades == 0


def test_flat_while_unswept_no_trade_in_hunt():
    warm = _warmup_days(2)
    day = _box_day("2024-01-03", signal=None)  # hunt bars inside box
    m, log, _, _ = _run(pd.concat([warm, day], ignore_index=True))
    assert log == []
    assert m.n_trades == 0


def test_box_incomplete_no_trade():
    warm = _warmup_days(2)
    # Hunt-only day: no box hours → undefined box → no trade
    day = _box_day("2024-01-03", signal="long", signal_hour=10, skip_box_hours=True)
    m, log, _, _ = _run(pd.concat([warm, day], ignore_index=True))
    assert log == []


def test_hour13_signal_fill_at_14_skipped():
    warm = _warmup_days(2)
    # Signal on hour 13; next open would be hour 14 — not in our bars / skip gate.
    # Build day with hours 1-13 only so fill bar does not exist → no entry.
    day = _box_day("2024-01-03", signal="long", signal_hour=13, include_hour13=True)
    m, log, _, d = _run(pd.concat([warm, day], ignore_index=True))
    # No hour-14 bar → pending never fills
    assert log == []
    assert m.n_trades == 0


def test_one_entry_per_day_second_event_ignored():
    warm = _warmup_days(2)
    # First long at 9, second would be at 11 — only first fills.
    day = _box_day("2024-01-03", signal="long", signal_hour=9)
    # Manually add another pierce at hour 11 after fill
    d = fam.prepare(pd.concat([warm, day], ignore_index=True))
    # Find hour 11 on signal day and force a second long-looking bar
    idx = [
        i
        for i, (h, day_id) in enumerate(zip(d["hour"], d["day_id"], strict=True))
        if day_id == "2024-01-03" and int(h) == 11
    ]
    assert idx
    i = idx[0]
    d.loc[i, "low"] = 1985.0
    d.loc[i, "close"] = 1992.0
    log: list[dict] = []
    fam.simulate(d, trade_log=log)
    # At most one entry that day
    assert sum(1 for t in log if t["entry_bar"] >= 0) <= 1
    assert len(log) == 1


def test_early_server_overlap_contrast():
    """Breakout-above-high ≠ fade-back-inside (relation fixture)."""
    warm = _warmup_days(2)
    # Close above box high without wick-reclaim fade → should NOT trade this family
    day = _box_day("2024-01-03", signal=None)
    d = fam.prepare(pd.concat([warm, day], ignore_index=True))
    idx = [
        i
        for i, (h, day_id) in enumerate(zip(d["hour"], d["day_id"], strict=True))
        if day_id == "2024-01-03" and int(h) == 10
    ][0]
    d.loc[idx, "high"] = 2015.0
    d.loc[idx, "close"] = 2012.0  # close above high — early_server style break
    d.loc[idx, "low"] = 2000.0
    log: list[dict] = []
    fam.simulate(d, trade_log=log)
    assert log == [], "continuation break above box high must not be a fade entry"


def test_entry_gap_open_beyond_sl_skipped():
    warm = _warmup_days(2)
    # Signal long; fill open gaps below box_low (beyond SL)
    day = _box_day(
        "2024-01-03",
        signal="long",
        signal_hour=10,
        post_open=1985.0,  # < box_low 1990
        post_high=1986.0,
        post_low=1984.0,
        post_close=1985.5,
    )
    m, log, _, _ = _run(pd.concat([warm, day], ignore_index=True))
    assert log == []
    assert m.n_trades == 0


def test_entry_gap_open_beyond_tp_skipped():
    warm = _warmup_days(2)
    # Signal long; fill open above midline TP
    day = _box_day(
        "2024-01-03",
        signal="long",
        signal_hour=10,
        post_open=2005.0,  # midline=2000
        post_high=2006.0,
        post_low=2004.0,
        post_close=2005.0,
    )
    m, log, _, _ = _run(pd.concat([warm, day], ignore_index=True))
    assert log == []


def test_entry_gap_degenerate_box_skipped():
    warm = _warmup_days(2)
    # Degenerate: box_high == box_low
    day = _box_day(
        "2024-01-03",
        box_high=2000.0,
        box_low=2000.0,
        signal="long",
        signal_hour=10,
    )
    # Force degenerate extremes on box bars
    d = fam.prepare(pd.concat([warm, day], ignore_index=True))
    for i, (h, day_id) in enumerate(zip(d["hour"], d["day_id"], strict=True)):
        if day_id == "2024-01-03" and int(h) in range(1, 8):
            d.loc[i, ["open", "high", "low", "close"]] = 2000.0
    # Hunt signal: pierce and close "inside" a zero-width box is ill-defined;
    # even if signal fires, gap policy must skip.
    idx = [
        i
        for i, (h, day_id) in enumerate(zip(d["hour"], d["day_id"], strict=True))
        if day_id == "2024-01-03" and int(h) == 10
    ][0]
    d.loc[idx, "low"] = 1999.0
    d.loc[idx, "close"] = 2000.1
    d.loc[idx, "high"] = 2000.2
    log: list[dict] = []
    fam.simulate(d, trade_log=log)
    assert log == []


def test_thin_n_below_min_is_screen_fail_not_waiver():
    """Accounting/docs fixture: soft_pass rejects n<20; charter pins thin-n SCREEN_FAIL."""
    ch = json.loads(CHARTER_V2.read_text())
    assert ch["gates"]["thin_n_is_screen_fail"] is True
    assert ch["rule"]["thin_n_policy"].startswith("if develop-eligible")
    # Module soft_pass mirrors n_trades_min
    class _M:
        n_trades = 5
        profit_factor = 2.0
        net_profit = 100.0
        max_drawdown_pct = 1.0
        win_rate = 60.0
        expectancy = 1.0
        avg_trade = 1.0

    # metrics_dict expects Metrics-like — use real simulate empty
    warm = _warmup_days(2)
    m, _, _, _ = _run(warm)
    assert m.n_trades < 20
    assert fam.soft_pass(m) is False


def test_two_trade_realized_balance_sizing():
    warm = _warmup_days(2)
    d1 = _box_day("2024-01-03", signal="long", signal_hour=9, spreads=0.0)
    d2 = _box_day("2024-01-04", signal="long", signal_hour=9, spreads=0.0)
    m, log, _, _ = _run(pd.concat([warm, d1, d2], ignore_index=True))
    assert len(log) == 2
    # Second trade sizes off realized balance after first exit
    assert log[1]["bal_at_entry"] == pytest.approx(log[0]["bal_after_exit"])


def test_entry_exit_equity_cost_timing():
    warm = _warmup_days(2)
    day = _box_day("2024-01-03", signal="long", signal_hour=9, spreads=10.0)
    m, log, eq, d = _run(pd.concat([warm, day], ignore_index=True))
    assert len(log) == 1
    t = log[0]
    # Cost measured at entry, deducted at exit only
    assert t["trade_cost"] > 0
    assert t["pnl"] == pytest.approx(t["gross"] - t["trade_cost"])
    # Balance at entry equals START before any booking
    assert t["bal_at_entry"] == pytest.approx(START_BALANCE)
    # Equity series length matches bars
    assert len(eq) == len(d)


def test_sl_before_tp_same_bar_priority():
    """Same-bar SL and TP both touchable → SL wins."""
    warm = _warmup_days(2)
    day = _box_day(
        "2024-01-03",
        signal="long",
        signal_hour=9,
        post_open=2000.0,  # midline = entry at mid; SL=1990 TP=2000 — entry==TP edge
        # Use entry inside, then fill bar spans both SL and TP
        post_high=2011.0,
        post_low=1989.0,
        post_close=2000.0,
    )
    # Adjust: entry open between SL and TP
    day = _box_day(
        "2024-01-03",
        signal="long",
        signal_hour=9,
        post_open=1995.0,
        post_high=2005.0,  # touches TP
        post_low=1988.0,  # touches SL
        post_close=1995.0,
    )
    m, log, _, _ = _run(pd.concat([warm, day], ignore_index=True))
    assert len(log) == 1
    assert log[0]["reason"] == "sl"
    assert log[0]["exit"] == pytest.approx(1990.0)
