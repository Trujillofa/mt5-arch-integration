"""Synthetic fixture tests for early_server_range_break_flat (v2 charter only).

No develop-screen / real-data evaluation. Offline only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import xau_family_early_server_range_break_flat as fam  # noqa: E402
from xau_charter_protocol import (  # noqa: E402
    is_charter_runnable,
    load_charter,
    null_spec_from_charter,
)
from xau_null_core import apply_null_method, null_invariants_ok  # noqa: E402

from backtest import CONTRACT_SIZE, START_BALANCE  # noqa: E402

CHARTER_V2 = (
    ROOT / "results/xau_charters/2026-08-10_early_server_range_break_flat_v2.json"
)
CHARTER_V1 = (
    ROOT / "results/xau_charters/2026-08-10_early_server_range_break_flat_v1.json"
)


def _bars_day(
    day: str,
    hours: list[int],
    *,
    base: float = 2000.0,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    closes: list[float] | None = None,
    spreads: float = 20.0,
) -> pd.DataFrame:
    rows = []
    for j, h in enumerate(hours):
        hi = highs[j] if highs is not None else base + 1.0
        lo = lows[j] if lows is not None else base - 1.0
        cl = closes[j] if closes is not None else base
        op = cl
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


def _concat_days(*frames: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(list(frames), ignore_index=True)


def _warmup_day(day: str = "2024-02-28") -> pd.DataFrame:
    """Quiet full session (hours 1–22) so warmup/ATR advance without break entries."""
    hours = list(range(1, 23))
    # Non-constant TR so ATR is not degenerate across estimators
    highs = [2000.0 + 0.5 + (i % 5) * 0.3 for i in range(len(hours))]
    lows = [2000.0 - 0.5 - (i % 3) * 0.2 for i in range(len(hours))]
    closes = [2000.0 + 0.1 * np.sin(i) for i in range(len(hours))]
    return _bars_day(
        day,
        hours,
        highs=highs,
        lows=lows,
        closes=closes,
        spreads=0.0,
    )


def _signal_day_with_flat(
    day: str,
    *,
    early_high: float = 2005.0,
    break_hour: int = 10,
    break_close: float = 2006.0,
    include_hour16: bool = True,
    spreads: float = 0.0,
) -> pd.DataFrame:
    """Build hours 1..15 (+ optional 16) with causal early block + one break."""
    hours = list(range(1, 16)) + ([16] if include_hour16 else [])
    n = len(hours)
    highs = [early_high if h <= 8 else break_close + 0.5 for h in hours]
    lows = [early_high - 10.0] * n
    closes = [early_high - 1.0] * n
    df = _bars_day(day, hours, highs=highs, lows=lows, closes=closes, spreads=spreads)
    df.loc[df["time"].dt.hour == break_hour, "close"] = break_close
    df.loc[df["time"].dt.hour == break_hour, "high"] = break_close + 1.0
    df.loc[df["time"].dt.hour == break_hour, "low"] = break_close - 1.0
    return df


def test_charter_v2_screen_fail_v1_superseded():
    from xau_charter_protocol import validate_charter_file

    assert validate_charter_file(CHARTER_V2) == []
    ok2, why2 = is_charter_runnable(CHARTER_V2)
    assert ok2 is False and "SCREEN_FAIL" in why2
    ok1, why1 = is_charter_runnable(CHARTER_V1)
    assert ok1 is False and "SUPERSEDED" in why1


def test_grid_cardinality_exactly_one():
    g = fam.build_grid()
    assert len(g) == 1
    assert len(fam.grid(max_n=500, seed=0)) == 1
    assert g[0]["flat_hour"] == 16
    assert g[0]["sl_atr"] == 1.5
    assert g[0]["tp_atr"] == 2.0


def test_wilder_atr14_differs_from_sma_on_nonconstant_tr():
    """Non-constant TR: Wilder ewm α=1/14 ≠ SMA of TR (proves estimator choice)."""
    hours = list(range(1, 23))
    # Expanding then contracting ranges
    highs = [2000.0 + (i + 1) * 0.5 for i in hours]
    lows = [2000.0 - (i % 4) * 0.8 for i in hours]
    closes = [2000.0 + 0.2 * i for i in hours]
    raw = _bars_day(
        "2024-03-01",
        hours,
        highs=highs,
        lows=lows,
        closes=closes,
    )
    d = fam.prepare(raw)
    h = d["high"].astype(float)
    lo = d["low"].astype(float)
    c = d["close"].astype(float)
    prev = c.shift(1)
    tr = pd.concat([(h - lo), (h - prev).abs(), (lo - prev).abs()], axis=1).max(axis=1)
    wilder = tr.ewm(alpha=1 / 14, adjust=False).mean()
    sma = tr.rolling(14, min_periods=1).mean()
    np.testing.assert_allclose(d["atr"].to_numpy(), wilder.to_numpy(), rtol=0, atol=1e-12)
    # Not identical to SMA over the full path
    assert not np.allclose(wilder.to_numpy()[14:], sma.to_numpy()[14:], rtol=0, atol=1e-9)


def test_no_trade_without_early_block_bars():
    """Hours only 9–16 after warmup: early_high never defined → zero trades."""
    signal = _bars_day(
        "2024-03-01",
        list(range(9, 17)),
        highs=[2010.0] * 8,
        lows=[1990.0] * 8,
        closes=[2005.0] * 8,
    )
    raw = _concat_days(_warmup_day(), signal)
    assert len(raw) >= fam.WARMUP + 8
    d = fam.prepare(raw)
    m = fam.simulate(d, spread_col="spread", commission_per_lot=0.0, slippage_points=0.0)
    assert m.n_trades == 0


def test_strict_equality_close_not_break_with_warmup():
    """close == early_high is not a break (needs close > early_high)."""
    signal = _signal_day_with_flat(
        "2024-03-01",
        early_high=2010.0,
        break_hour=11,
        break_close=2010.0,  # equal, not greater
        include_hour16=True,
    )
    raw = _concat_days(_warmup_day(), signal)
    assert len(raw) >= fam.WARMUP + 16
    d = fam.prepare(raw)
    m = fam.simulate(d)
    assert m.n_trades == 0


def test_causal_early_high_and_daily_reset_two_trades():
    """Day1 and Day2 each break their own early high → exactly 2 trades."""
    d1 = _signal_day_with_flat(
        "2024-03-01",
        early_high=2010.0,
        break_hour=11,
        break_close=2010.5,
        include_hour16=True,
        spreads=0.0,
    )
    # Quiet path after entry to time-flat (wide ATR forced later)
    for h in range(12, 16):
        d1.loc[d1["time"].dt.hour == h, ["high", "low", "close"]] = [
            2010.6,
            2010.4,
            2010.5,
        ]
    d1.loc[d1["time"].dt.hour == 16, "close"] = 2010.5

    d2 = _signal_day_with_flat(
        "2024-03-04",
        early_high=2005.0,
        break_hour=11,
        break_close=2006.0,
        include_hour16=True,
        spreads=0.0,
    )
    for h in range(12, 16):
        d2.loc[d2["time"].dt.hour == h, ["high", "low", "close"]] = [
            2006.1,
            2005.9,
            2006.0,
        ]
    d2.loc[d2["time"].dt.hour == 16, "close"] = 2006.0

    # Day that would break if early high leaked from day1 (early high would be 2010)
    # but day2 early is 2005 — hour 10 close 2005.5 would NOT break day1's 2010
    d2.loc[d2["time"].dt.hour == 10, "close"] = 2005.5
    d2.loc[d2["time"].dt.hour == 10, "high"] = 2005.6

    raw = _concat_days(_warmup_day(), d1, d2)
    d = fam.prepare(raw)
    d["atr"] = 50.0  # no SL/TP on quiet path
    m = fam.simulate(d, spread_col=None, commission_per_lot=0.0, slippage_points=0.0)
    assert m.n_trades == 2


def test_no_entry_without_hour16_bar_fail_closed_overnight():
    """Entry day ending at hour 15 must not open; cannot hit next-day SL overnight."""
    # Day ends at 15 (no hour 16) with a break signal
    entry_day = _signal_day_with_flat(
        "2024-03-01",
        early_high=2005.0,
        break_hour=11,
        break_close=2006.0,
        include_hour16=False,
        spreads=0.0,
    )
    # Next day hour 1 would hit a deep SL if overnight were allowed
    next_day = _bars_day(
        "2024-03-04",
        [1, 2, 16],
        highs=[2006.0, 2006.0, 2006.0],
        lows=[1900.0, 1990.0, 1990.0],  # hour 1 low 1900
        closes=[2000.0, 2000.0, 2000.0],
        spreads=0.0,
    )
    raw = _concat_days(_warmup_day(), entry_day, next_day)
    d = fam.prepare(raw)
    d["atr"] = 1.0
    m = fam.simulate(d, spread_col=None, commission_per_lot=0.0, slippage_points=0.0)
    assert m.n_trades == 0
    assert m.net_profit == 0.0


def test_one_entry_per_day_and_hours_window():
    signal = _signal_day_with_flat(
        "2024-03-01",
        early_high=2005.0,
        break_hour=9,
        break_close=2006.0,
        include_hour16=True,
    )
    # Additional later breaks same day must not add trades
    for h in (10, 11, 12):
        signal.loc[signal["time"].dt.hour == h, "close"] = 2007.0
        signal.loc[signal["time"].dt.hour == h, "high"] = 2008.0
    raw = _concat_days(_warmup_day(), signal)
    d = fam.prepare(raw)
    d["atr"] = 50.0
    m = fam.simulate(d, spread_col=None, commission_per_lot=0.0, slippage_points=0.0)
    assert m.n_trades == 1


def test_no_entry_bar_exit_sl_before_tp():
    """Entry bar spans SL and TP levels; exit only on next bar; SL before TP."""
    signal = _signal_day_with_flat(
        "2024-03-01",
        early_high=2000.5,
        break_hour=11,
        break_close=2001.0,
        include_hour16=True,
        spreads=0.0,
    )
    # Entry bar itself would touch both SL and TP if exits were allowed same bar
    signal.loc[signal["time"].dt.hour == 11, "low"] = 1990.0
    signal.loc[signal["time"].dt.hour == 11, "high"] = 2020.0
    # Next bar (12): SL and TP both touchable — SL must win
    signal.loc[signal["time"].dt.hour == 12, "low"] = 1990.0
    signal.loc[signal["time"].dt.hour == 12, "high"] = 2020.0
    signal.loc[signal["time"].dt.hour == 12, "close"] = 2001.0

    raw = _concat_days(_warmup_day(), signal)
    d = fam.prepare(raw)
    entry_idx = int(np.where((d["day_id"] == "2024-03-01") & (d["hour"] == 11))[0][0])
    d.loc[d.index[entry_idx], "atr"] = 1.0  # SL = entry-1.5, TP = entry+2.0
    # Keep atr defined on next bar
    d.loc[d.index[entry_idx + 1], "atr"] = 1.0

    m = fam.simulate(d, commission_per_lot=0.0, slippage_points=0.0, spread_col=None)
    assert m.n_trades == 1
    # SL first → negative; entry bar spanning SL/TP must not flatten same bar
    # (next-bar SL still books one trade).
    assert m.net_profit < 0
    stop_dist = 1.5
    risk_cash = START_BALANCE * 0.01
    raw_lots = risk_cash / (stop_dist * CONTRACT_SIZE)
    lots = min(float(np.floor(raw_lots * 100 + 1e-12) / 100.0), fam.MAX_LOTS)
    expected = -stop_dist * CONTRACT_SIZE * lots
    assert m.net_profit == pytest.approx(expected, rel=0, abs=1e-6)


def test_time_flat_at_hour_16_close():
    signal = _signal_day_with_flat(
        "2024-03-01",
        early_high=2005.0,
        break_hour=10,
        break_close=2006.0,
        include_hour16=True,
        spreads=0.0,
    )
    for h in range(11, 16):
        signal.loc[signal["time"].dt.hour == h, ["high", "low", "close"]] = [
            2006.5,
            2005.5,
            2006.0,
        ]
    signal.loc[signal["time"].dt.hour == 16, "close"] = 2006.2
    signal.loc[signal["time"].dt.hour == 16, "high"] = 2006.5
    signal.loc[signal["time"].dt.hour == 16, "low"] = 2005.8

    raw = _concat_days(_warmup_day(), signal)
    d = fam.prepare(raw)
    d["atr"] = 50.0
    m = fam.simulate(d, spread_col=None, commission_per_lot=0.0, slippage_points=0.0)
    assert m.n_trades == 1
    assert m.net_profit > 0


def test_lot_floor_and_round_trip_cost():
    signal = _signal_day_with_flat(
        "2024-03-01",
        early_high=2005.0,
        break_hour=10,
        break_close=2006.0,
        include_hour16=True,
        spreads=10.0,
    )
    for h in range(11, 16):
        signal.loc[signal["time"].dt.hour == h, ["high", "low", "close"]] = [
            2006.1,
            2005.9,
            2006.0,
        ]
    signal.loc[signal["time"].dt.hour == 16, "close"] = 2006.0
    signal.loc[signal["time"].dt.hour == 16, "high"] = 2006.1
    signal.loc[signal["time"].dt.hour == 16, "low"] = 2005.9

    raw = _concat_days(_warmup_day(), signal)
    d = fam.prepare(raw)
    d["atr"] = 10.0  # stop_dist = 15
    m = fam.simulate(
        d,
        spread_col="spread",
        point_size=0.01,
        commission_per_lot=0.0,
        slippage_points=0.0,
    )
    stop_dist = 10.0 * 1.5
    risk_cash = START_BALANCE * 0.01
    raw_lots = risk_cash / (stop_dist * CONTRACT_SIZE)
    lots = float(np.floor(raw_lots * 100 + 1e-12) / 100.0)
    assert lots == 0.06
    trade_cost = 10.0 * 0.01 * CONTRACT_SIZE * lots
    assert m.n_trades == 1
    assert m.net_profit == pytest.approx(-trade_cost, rel=0, abs=1e-6)


def test_null_invariants_canonical_session_method():
    ch = load_charter(CHARTER_V2)
    ns = null_spec_from_charter(ch)
    assert ns["method"] == "within_day_ohlc_increment_rotate_v1"
    frames = []
    for day in ("2024-03-01", "2024-03-04", "2024-03-05", "2024-03-06"):
        frames.append(
            _bars_day(
                day,
                list(range(1, 23)),
                base=2000.0 + hash(day) % 10,
            )
        )
    raw = _concat_days(*frames)
    rng = np.random.default_rng(0)
    scr = apply_null_method(
        raw, rng, method="within_day_ohlc_increment_rotate_v1", block_days=1
    )
    inv = null_invariants_ok(
        raw,
        scr,
        method="within_day_ohlc_increment_rotate_v1",
        entry_hour=9,
        flat_hour=16,
    )
    assert inv.get("protocol_session_valid") is not False
    assert inv["within_day_path_continuous"]
    assert inv["time_unchanged"]
    # With entry_hour set, path-association invariants must be evaluated
    assert "entry_hour_closes_moved" in inv
    assert "session_path_association_broken" in inv


def test_sealed_fixture_resolves_entry_allowed_hours_server(monkeypatch):
    """Helper must pass entry_hour=9 and flat_hour=16 into null_invariants_ok."""
    import xau_sealed_family_cycle as sealed

    ch = load_charter(CHARTER_V2)
    captured: dict = {}

    real_inv = null_invariants_ok

    def wrap_inv(raw, scr, **kwargs):
        captured.update(kwargs)
        return real_inv(raw, scr, **kwargs)

    monkeypatch.setattr(sealed, "null_spec_from_charter", sealed.null_spec_from_charter)
    # Patch where used: inside function imports from xau_null_core — patch module attr
    import xau_null_core as nc

    monkeypatch.setattr(nc, "null_invariants_ok", wrap_inv)

    out = sealed._run_synthetic_fixture("early_server_range_break_flat", ch)
    assert out.get("family_smoke") == "ok"
    assert captured.get("entry_hour") == 9
    assert captured.get("flat_hour") == 16


def test_load_family_builtin():
    from xau_family_null_maxstat import load_family

    p = load_family("early_server_range_break_flat")
    assert p.name == "early_server_range_break_flat"
    assert p.kill_label == "KILL_EARLY_SERVER_RANGE_BREAK_FLAT"
    assert len(p.grid(max_n=10, seed=0)) == 1
