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
    validate_charter,
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
    """Quiet full session so ATR/warmup advances without early-range break entries."""
    hours = list(range(1, 23))
    return _bars_day(
        day,
        hours,
        base=2000.0,
        highs=[2000.5] * len(hours),
        lows=[1999.5] * len(hours),
        closes=[2000.0] * len(hours),
        spreads=0.0,
    )


def test_charter_v2_runnable_v1_superseded():
    assert validate_charter(load_charter(CHARTER_V2)) == []
    ok2, _ = is_charter_runnable(CHARTER_V2)
    assert ok2 is True
    ok1, why1 = is_charter_runnable(CHARTER_V1)
    assert ok1 is False and "SUPERSEDED" in why1


def test_grid_cardinality_exactly_one():
    g = fam.build_grid()
    assert len(g) == 1
    assert len(fam.grid(max_n=500, seed=0)) == 1
    assert g[0]["flat_hour"] == 16
    assert g[0]["sl_atr"] == 1.5
    assert g[0]["tp_atr"] == 2.0


def test_wilder_atr14_matches_ewm_alpha():
    # Constant TR path: high-low = 2, flat close chain
    hours = list(range(1, 23))
    raw = _bars_day(
        "2024-03-01",
        hours,
        base=2000.0,
        highs=[2002.0] * len(hours),
        lows=[2000.0] * len(hours),
        closes=[2001.0] * len(hours),
    )
    d = fam.prepare(raw)
    h = d["high"].astype(float)
    lo = d["low"].astype(float)
    c = d["close"].astype(float)
    prev = c.shift(1)
    tr = pd.concat([(h - lo), (h - prev).abs(), (lo - prev).abs()], axis=1).max(axis=1)
    expected = tr.ewm(alpha=1 / 14, adjust=False).mean()
    np.testing.assert_allclose(d["atr"].to_numpy(), expected.to_numpy(), rtol=0, atol=1e-12)


def test_no_trade_without_early_block_bars():
    """Hours only 9–16: early_high never defined → zero trades."""
    raw = _bars_day(
        "2024-03-01",
        list(range(9, 17)),
        highs=[2010.0] * 8,
        lows=[1990.0] * 8,
        closes=[2005.0] * 8,
    )
    d = fam.prepare(raw)
    m = fam.simulate(d, spread_col="spread", commission_per_lot=0.0, slippage_points=0.0)
    assert m.n_trades == 0


def test_causal_early_high_and_daily_reset():
    """Day1: early high 2010; break only if close>2010. Day2 resets early high."""
    # Day1 early highs peak at 2010 on hour 5
    d1 = _bars_day(
        "2024-03-01",
        list(range(1, 17)),
        highs=[2001 + i * 0.1 if i < 8 else 2005 for i in range(16)],
        lows=[1990.0] * 16,
        closes=[2000.0] * 16,
    )
    # Force early block max high = 2010 at hour 4 (index 3)
    d1.loc[d1["time"].dt.hour == 4, "high"] = 2010.0
    # Hour 10 close barely fails: 2010.0 not >
    d1.loc[d1["time"].dt.hour == 10, "close"] = 2010.0
    d1.loc[d1["time"].dt.hour == 10, "high"] = 2010.5
    # Hour 11 strict break
    d1.loc[d1["time"].dt.hour == 11, "close"] = 2010.5
    d1.loc[d1["time"].dt.hour == 11, "high"] = 2011.0
    d1.loc[d1["time"].dt.hour == 11, "low"] = 2009.0

    # Day2: early high only 2005; hour 10 close 2004.9 no trade; hour 11 close 2006 break
    d2 = _bars_day(
        "2024-03-04",  # skip weekend
        list(range(1, 17)),
        highs=[2005.0] * 16,
        lows=[1995.0] * 16,
        closes=[2000.0] * 16,
    )
    d2.loc[d2["time"].dt.hour == 3, "high"] = 2005.0
    d2.loc[d2["time"].dt.hour == 10, "close"] = 2004.9
    d2.loc[d2["time"].dt.hour == 11, "close"] = 2006.0
    d2.loc[d2["time"].dt.hour == 11, "high"] = 2007.0
    d2.loc[d2["time"].dt.hour == 11, "low"] = 2000.0

    raw = _concat_days(d1, d2)
    d = fam.prepare(raw)
    m = fam.simulate(d)
    # At least one trade from day1 break; day2 also breaks → 2 trades if both hold
    assert m.n_trades >= 1

    # Strict equality does not enter on day1 hour 10
    only_eq = d1.copy()
    only_eq.loc[only_eq["time"].dt.hour == 11, "close"] = 2000.0  # remove later break
    only_eq.loc[only_eq["time"].dt.hour == 11, "high"] = 2001.0
    d_eq = fam.prepare(only_eq)
    m_eq = fam.simulate(d_eq)
    assert m_eq.n_trades == 0


def test_one_entry_per_day_and_hours_window():
    signal = _bars_day(
        "2024-03-01",
        list(range(1, 17)),
        highs=[2005.0] * 16,
        lows=[1995.0] * 16,
        closes=[2000.0] * 16,
    )
    # Early high 2005 from hours 1-8
    signal.loc[signal["time"].dt.hour.isin(range(1, 9)), "high"] = 2005.0
    # Multiple break closes in entry window
    for h in (9, 10, 11, 12):
        signal.loc[signal["time"].dt.hour == h, "close"] = 2006.0
        signal.loc[signal["time"].dt.hour == h, "high"] = 2007.0
        signal.loc[signal["time"].dt.hour == h, "low"] = 2000.0
    raw = _concat_days(_warmup_day(), signal)
    d = fam.prepare(raw)
    m = fam.simulate(d)
    assert m.n_trades == 1


def test_no_entry_bar_exit_sl_before_tp_before_flat():
    """Enter hour 11; next bar hits both SL and TP levels → SL wins."""
    hours = list(range(1, 17))
    signal = _bars_day(
        "2024-03-01",
        hours,
        base=2000.0,
        highs=[2002.0] * len(hours),
        lows=[1998.0] * len(hours),
        closes=[2000.0] * len(hours),
        spreads=0.0,
    )
    # Early high 2000.5
    signal.loc[signal["time"].dt.hour.isin(range(1, 9)), "high"] = 2000.5
    # Entry at hour 11
    signal.loc[signal["time"].dt.hour == 11, "close"] = 2001.0
    signal.loc[signal["time"].dt.hour == 11, "high"] = 2001.5
    signal.loc[signal["time"].dt.hour == 11, "low"] = 2000.0
    raw = _concat_days(_warmup_day(), signal)
    d = fam.prepare(raw)
    # Force atr at entry bar so SL/TP known
    entry_idx = int(np.where((d["day_id"] == "2024-03-01") & (d["hour"] == 11))[0][0])
    d.loc[d.index[entry_idx], "atr"] = 1.0  # SL=entry-1.5, TP=entry+2.0
    # Next bar OHLC spans both SL and TP
    nxt = entry_idx + 1
    entry_px = float(d.loc[d.index[entry_idx], "close"])
    d.loc[d.index[nxt], "low"] = entry_px - 3.0  # through SL
    d.loc[d.index[nxt], "high"] = entry_px + 3.0  # through TP
    d.loc[d.index[nxt], "close"] = entry_px
    d.loc[d.index[nxt], "hour"] = 12

    m = fam.simulate(d, commission_per_lot=0.0, slippage_points=0.0, spread_col=None)
    assert m.n_trades == 1
    # SL first: pnl negative ~ -1.5 * CONTRACT * lots
    assert m.net_profit < 0


def test_time_flat_at_hour_16_close():
    hours = list(range(1, 17))
    signal = _bars_day(
        "2024-03-01",
        hours,
        highs=[2005.0] * len(hours),
        lows=[1995.0] * len(hours),
        closes=[2000.0] * len(hours),
        spreads=0.0,
    )
    signal.loc[signal["time"].dt.hour.isin(range(1, 9)), "high"] = 2005.0
    signal.loc[signal["time"].dt.hour == 10, "close"] = 2006.0
    signal.loc[signal["time"].dt.hour == 10, "high"] = 2007.0
    signal.loc[signal["time"].dt.hour == 10, "low"] = 2004.0
    # Quiet path after entry (no SL/TP); flat at 16
    for h in range(11, 16):
        signal.loc[signal["time"].dt.hour == h, "high"] = 2006.5
        signal.loc[signal["time"].dt.hour == h, "low"] = 2005.5
        signal.loc[signal["time"].dt.hour == h, "close"] = 2006.0
    signal.loc[signal["time"].dt.hour == 16, "close"] = 2006.2
    signal.loc[signal["time"].dt.hour == 16, "high"] = 2006.5
    signal.loc[signal["time"].dt.hour == 16, "low"] = 2005.8

    raw = _concat_days(_warmup_day(), signal)
    d = fam.prepare(raw)
    # Large ATR so SL/TP not hit by quiet path
    d["atr"] = 50.0
    m = fam.simulate(d, spread_col=None, commission_per_lot=0.0, slippage_points=0.0)
    assert m.n_trades == 1
    # Exit at 16 close 2006.2 vs entry 2006.0 → small positive before lots
    assert m.net_profit > 0


def test_lot_floor_and_round_trip_cost():
    hours = list(range(1, 17))
    signal = _bars_day(
        "2024-03-01",
        hours,
        highs=[2005.0] * len(hours),
        lows=[1995.0] * len(hours),
        closes=[2000.0] * len(hours),
        spreads=10.0,
    )
    signal.loc[signal["time"].dt.hour.isin(range(1, 9)), "high"] = 2005.0
    signal.loc[signal["time"].dt.hour == 10, "close"] = 2006.0
    signal.loc[signal["time"].dt.hour == 10, "high"] = 2007.0
    signal.loc[signal["time"].dt.hour == 10, "low"] = 2004.0
    # Immediate next-bar time path to flat with flat close = entry (zero gross)
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
    # risk_cash=100, stop_dist=15, raw=100/(15*100)=0.0666..., floor to 0.06
    stop_dist = 10.0 * 1.5
    risk_cash = START_BALANCE * 0.01
    raw_lots = risk_cash / (stop_dist * CONTRACT_SIZE)
    lots = float(np.floor(raw_lots * 100 + 1e-12) / 100.0)
    assert lots == 0.06
    trade_cost = (10.0 + 0.0) * 0.01 * CONTRACT_SIZE * lots  # spread only
    # Gross pnl ~ 0 if exit at entry; net ≈ -trade_cost
    assert m.n_trades == 1
    assert m.net_profit == pytest.approx(-trade_cost, rel=0, abs=1e-6)


def test_null_invariants_canonical_session_method():
    ch = load_charter(CHARTER_V2)
    ns = null_spec_from_charter(ch)
    assert ns["method"] == "within_day_ohlc_increment_rotate_v1"
    # multi-day synthetic for rotate
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
        entry_hour=10,
        flat_hour=16,
    )
    assert inv.get("protocol_session_valid") is not False
    assert inv["within_day_path_continuous"]
    assert inv["time_unchanged"]


def test_sealed_fixture_smoke_via_cycle_helper():
    """Synthetic fixture path used by sealed cycle must succeed for this family."""
    import xau_sealed_family_cycle as sealed

    ch = load_charter(CHARTER_V2)
    out = sealed._run_synthetic_fixture("early_server_range_break_flat", ch)
    assert out.get("family_smoke") == "ok"
    assert out.get("null_method") == "within_day_ohlc_increment_rotate_v1"


def test_load_family_builtin():
    from xau_family_null_maxstat import load_family

    p = load_family("early_server_range_break_flat")
    assert p.name == "early_server_range_break_flat"
    assert p.kill_label == "KILL_EARLY_SERVER_RANGE_BREAK_FLAT"
    assert len(p.grid(max_n=10, seed=0)) == 1
