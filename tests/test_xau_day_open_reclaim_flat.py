"""Synthetic fixture tests for day_open_reclaim_flat (v2 charter only).

No develop-screen / real-data evaluation. Offline only.
Required fixtures from charter execution_contract.required_fixtures:
  same_bar_undercut_reclaim_rejected
  prior_bar_undercut_reclaim_accepted
  two_trade_realized_balance_sizing
  entry_exit_equity_cost_timing
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

import xau_family_day_open_reclaim_flat as fam  # noqa: E402
from xau_charter_protocol import (  # noqa: E402
    is_charter_runnable,
    load_charter,
    null_spec_from_charter,
    validate_charter_file,
)
from xau_null_core import apply_null_method, null_invariants_ok  # noqa: E402

from backtest import CONTRACT_SIZE, START_BALANCE  # noqa: E402

CHARTER_V2 = ROOT / "results/xau_charters/2026-08-11_day_open_reclaim_flat_v2.json"
CHARTER_V1 = ROOT / "results/xau_charters/2026-08-11_day_open_reclaim_flat_v1.json"
V2_SHA = "961dd3d4794b66b444300716babe80476ce1b58c4b2ccf67eda4eafe04cc95ce"


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


def _concat_days(*frames: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(list(frames), ignore_index=True)


def _warmup_day(day: str = "2024-02-28") -> pd.DataFrame:
    """Quiet full session so warmup/ATR advance without reclaim entries."""
    hours = list(range(1, 23))
    # day_open ≈ 2000; keep lows above open so no undercut, closes near open
    opens = [2000.0] * len(hours)
    highs = [2000.5 + (i % 5) * 0.2 for i in range(len(hours))]
    lows = [1999.5 - (i % 3) * 0.1 for i in range(len(hours))]  # still > open-ish
    # Ensure no undercut of day_open=2000: lows must be >= 2000 for no undercut
    lows = [2000.0 + 0.1 for _ in hours]
    closes = [2000.2 + 0.05 * np.sin(i) for i in range(len(hours))]
    return _bars_day(
        day, hours, opens=opens, highs=highs, lows=lows, closes=closes, spreads=0.0
    )


def _reclaim_day(
    day: str,
    *,
    day_open: float = 2000.0,
    undercut_hour: int = 5,
    undercut_low: float = 1995.0,
    reclaim_hour: int = 10,
    reclaim_close: float = 2001.0,
    same_bar_undercut_reclaim: bool = False,
    include_hour16: bool = True,
    spreads: float = 0.0,
    post_reclaim_close: float | None = None,
) -> pd.DataFrame:
    """Build a same-day path with optional prior undercut + reclaim in 9–15."""
    hours = list(range(1, 16)) + ([16] if include_hour16 else [])
    n = len(hours)
    opens = [day_open if h == hours[0] else day_open + 0.1 for h in hours]
    # Default: no undercut, close below day_open (no reclaim)
    highs = [day_open + 0.5] * n
    lows = [day_open + 0.05] * n
    closes = [day_open - 0.2] * n

    if same_bar_undercut_reclaim:
        # Only the reclaim bar undercuts AND closes above — prior bars clean.
        # Later bars must NOT close above day_open (sticky undercut would then
        # allow a true prior-bar reclaim on a subsequent hour).
        j = hours.index(reclaim_hour)
        lows[j] = undercut_low
        highs[j] = reclaim_close + 0.5
        closes[j] = reclaim_close
        for h in range(reclaim_hour + 1, 16):
            if h in hours:
                jj = hours.index(h)
                highs[jj] = day_open - 0.05
                lows[jj] = day_open - 0.3
                closes[jj] = day_open - 0.1
        if include_hour16 and 16 in hours:
            jj = hours.index(16)
            highs[jj] = day_open - 0.05
            lows[jj] = day_open - 0.2
            closes[jj] = day_open - 0.1
    else:
        if undercut_hour in hours:
            j = hours.index(undercut_hour)
            lows[j] = undercut_low
            highs[j] = day_open - 0.1
            closes[j] = day_open - 0.5
        if reclaim_hour in hours:
            j = hours.index(reclaim_hour)
            lows[j] = day_open - 0.1  # not undercut needed if prior did
            highs[j] = reclaim_close + 0.5
            closes[j] = reclaim_close

        # Quiet path after reclaim → time-flat
        for h in range(reclaim_hour + 1, 16):
            if h in hours:
                j = hours.index(h)
                px = post_reclaim_close if post_reclaim_close is not None else reclaim_close
                highs[j] = px + 0.2
                lows[j] = px - 0.2
                closes[j] = px
        if include_hour16 and 16 in hours:
            j = hours.index(16)
            px = post_reclaim_close if post_reclaim_close is not None else reclaim_close
            highs[j] = px + 0.1
            lows[j] = px - 0.1
            closes[j] = px

    return _bars_day(
        day, hours, opens=opens, highs=highs, lows=lows, closes=closes, spreads=spreads
    )


# --- charter / plugin -----------------------------------------------------------------


def test_charter_v2_screen_fail_v1_superseded():
    assert validate_charter_file(CHARTER_V2) == []
    ok2, why2 = is_charter_runnable(CHARTER_V2)
    assert ok2 is False and "SCREEN_FAIL" in why2
    ok1, why1 = is_charter_runnable(CHARTER_V1)
    assert ok1 is False and "SUPERSEDED" in why1
    import hashlib

    assert hashlib.sha256(CHARTER_V2.read_bytes()).hexdigest() == V2_SHA


def test_grid_cardinality_exactly_one():
    g = fam.build_grid()
    assert len(g) == 1
    assert len(fam.grid(max_n=500, seed=0)) == 1
    assert g[0]["flat_hour"] == 16
    assert g[0]["sl_atr"] == 1.5
    assert g[0]["tp_atr"] == 2.0
    assert g[0]["entry_allowed_hours"] == list(range(9, 16))


def test_load_family_builtin():
    from xau_family_null_maxstat import load_family

    p = load_family("day_open_reclaim_flat")
    assert p.name == "day_open_reclaim_flat"
    assert p.kill_label == "KILL_DAY_OPEN_RECLAIM_FLAT"
    assert len(p.grid(max_n=10, seed=0)) == 1


def test_wilder_atr14_matches_ewm():
    hours = list(range(1, 23))
    highs = [2000.0 + (i + 1) * 0.5 for i in hours]
    lows = [2000.0 - (i % 4) * 0.8 for i in hours]
    closes = [2000.0 + 0.2 * i for i in hours]
    raw = _bars_day("2024-03-01", hours, highs=highs, lows=lows, closes=closes)
    d = fam.prepare(raw)
    h = d["high"].astype(float)
    lo = d["low"].astype(float)
    c = d["close"].astype(float)
    prev = c.shift(1)
    tr = pd.concat([(h - lo), (h - prev).abs(), (lo - prev).abs()], axis=1).max(axis=1)
    wilder = tr.ewm(alpha=1 / 14, adjust=False).mean()
    np.testing.assert_allclose(d["atr"].to_numpy(), wilder.to_numpy(), rtol=0, atol=1e-12)


# --- required fixtures ----------------------------------------------------------------


def test_same_bar_undercut_reclaim_rejected():
    """Bar that both undercuts and reclaims → no entry (undercut_seen_before_i false)."""
    signal = _reclaim_day(
        "2024-03-01",
        day_open=2000.0,
        reclaim_hour=10,
        reclaim_close=2001.0,
        undercut_low=1995.0,
        same_bar_undercut_reclaim=True,
        include_hour16=True,
        spreads=0.0,
    )
    raw = _concat_days(_warmup_day(), signal)
    d = fam.prepare(raw)
    d["atr"] = 50.0
    m = fam.simulate(d, spread_col=None, commission_per_lot=0.0, slippage_points=0.0)
    assert m.n_trades == 0


def test_prior_bar_undercut_reclaim_accepted():
    """Prior undercut + later reclaim close > day_open → exactly one trade."""
    signal = _reclaim_day(
        "2024-03-01",
        day_open=2000.0,
        undercut_hour=5,
        undercut_low=1995.0,
        reclaim_hour=10,
        reclaim_close=2001.0,
        same_bar_undercut_reclaim=False,
        include_hour16=True,
        spreads=0.0,
        post_reclaim_close=2001.0,
    )
    raw = _concat_days(_warmup_day(), signal)
    d = fam.prepare(raw)
    d["atr"] = 50.0
    m = fam.simulate(d, spread_col=None, commission_per_lot=0.0, slippage_points=0.0)
    assert m.n_trades == 1


def test_two_trade_realized_balance_sizing():
    """Trade2 lots sized from post-trade1 realized balance (lot-step crossing).

    ATR=8.4 → stop_dist=12.6: start-balance risk floors to 0.07 lots. Trade1
    hits TP (+2*ATR) so balance grows enough that trade2 floors to 0.08.
    An implementation that always sizes from START_BALANCE would keep 0.07.
    """
    atr = 8.4
    stop_dist = atr * fam.SL_ATR
    entry_px = 2001.0
    tp_px = entry_px + atr * fam.TP_ATR  # 2017.8

    d1 = _reclaim_day(
        "2024-03-01",
        day_open=2000.0,
        undercut_hour=4,
        undercut_low=1990.0,
        reclaim_hour=10,
        reclaim_close=entry_px,
        post_reclaim_close=entry_px,  # quiet until TP bar override
        include_hour16=True,
        spreads=0.0,
    )
    # Hour 11: hit TP (high >= tp); keep low above SL
    d1.loc[d1["time"].dt.hour == 11, "high"] = tp_px + 0.5
    d1.loc[d1["time"].dt.hour == 11, "low"] = entry_px - 1.0
    d1.loc[d1["time"].dt.hour == 11, "close"] = tp_px

    d2 = _reclaim_day(
        "2024-03-04",
        day_open=2000.0,
        undercut_hour=4,
        undercut_low=1990.0,
        reclaim_hour=10,
        reclaim_close=entry_px,
        post_reclaim_close=entry_px,
        include_hour16=True,
        spreads=0.0,
    )
    raw = _concat_days(_warmup_day(), d1, d2)
    d = fam.prepare(raw)
    d["atr"] = atr
    log: list[dict] = []
    m = fam.simulate(
        d,
        spread_col=None,
        commission_per_lot=0.0,
        slippage_points=0.0,
        trade_log=log,
    )
    assert m.n_trades == 2
    assert len(log) == 2
    assert log[0]["reason"] == "tp"

    risk1 = START_BALANCE * fam.RISK_PCT
    lots1 = float(np.floor((risk1 / (stop_dist * CONTRACT_SIZE)) * 100 + 1e-12) / 100.0)
    assert lots1 == pytest.approx(0.07)
    assert log[0]["lots"] == pytest.approx(0.07)
    assert log[0]["bal_at_entry"] == pytest.approx(START_BALANCE)

    bal_after_1 = log[0]["bal_after_exit"]
    assert bal_after_1 == pytest.approx(START_BALANCE + log[0]["pnl"])
    assert bal_after_1 > START_BALANCE

    risk2 = bal_after_1 * fam.RISK_PCT
    lots2 = float(np.floor((risk2 / (stop_dist * CONTRACT_SIZE)) * 100 + 1e-12) / 100.0)
    start_based_lots = lots1  # incorrect: always size from START_BALANCE
    assert lots2 == pytest.approx(0.08)
    assert log[1]["lots"] == pytest.approx(0.08)
    assert log[1]["bal_at_entry"] == pytest.approx(bal_after_1)
    assert log[1]["lots"] != pytest.approx(start_based_lots)
    assert log[1]["lots"] != log[0]["lots"]


def test_entry_exit_equity_cost_timing():
    """Cost measured at entry but not deducted from balance/equity until exit."""
    signal = _reclaim_day(
        "2024-03-01",
        day_open=2000.0,
        undercut_hour=5,
        undercut_low=1995.0,
        reclaim_hour=10,
        reclaim_close=2001.0,
        post_reclaim_close=2001.0,
        include_hour16=True,
        spreads=10.0,
    )
    raw = _concat_days(_warmup_day(), signal)
    d = fam.prepare(raw)
    d["atr"] = 10.0
    log: list[dict] = []
    eq: list[float] = []
    m = fam.simulate(
        d,
        spread_col="spread",
        point_size=0.01,
        commission_per_lot=0.0,
        slippage_points=0.0,
        trade_log=log,
        equity_out=eq,
    )
    assert m.n_trades == 1
    assert len(log) == 1
    t = log[0]
    stop_dist = 15.0
    risk_cash = START_BALANCE * 0.01
    lots = float(np.floor((risk_cash / (stop_dist * CONTRACT_SIZE)) * 100 + 1e-12) / 100.0)
    assert t["lots"] == pytest.approx(lots)
    trade_cost = 10.0 * 0.01 * CONTRACT_SIZE * lots
    assert t["trade_cost"] == pytest.approx(trade_cost)
    # Balance at entry fill equals start (cost not debited yet)
    assert t["bal_at_entry"] == pytest.approx(START_BALANCE)
    # Equity on entry bar: still start_balance (floating 0 at fill close)
    entry_i = int(t["entry_bar"])
    assert eq[entry_i] == pytest.approx(START_BALANCE)
    # Exit books gross - cost
    assert t["pnl"] == pytest.approx(t["gross"] - trade_cost)
    assert t["bal_after_exit"] == pytest.approx(START_BALANCE + t["pnl"])
    exit_i = int(t["exit_bar"])
    assert eq[exit_i] == pytest.approx(t["bal_after_exit"])


# --- additional contract checks -------------------------------------------------------


def test_no_trade_without_undercut():
    signal = _reclaim_day(
        "2024-03-01",
        day_open=2000.0,
        undercut_hour=5,
        undercut_low=2000.5,  # low never < day_open
        reclaim_hour=10,
        reclaim_close=2001.0,
        include_hour16=True,
    )
    # Force all lows >= day_open
    signal["low"] = 2000.05
    raw = _concat_days(_warmup_day(), signal)
    d = fam.prepare(raw)
    d["atr"] = 50.0
    m = fam.simulate(d, spread_col=None)
    assert m.n_trades == 0


def test_no_entry_without_hour16_bar():
    signal = _reclaim_day(
        "2024-03-01",
        undercut_hour=5,
        undercut_low=1995.0,
        reclaim_hour=10,
        reclaim_close=2001.0,
        include_hour16=False,
        spreads=0.0,
    )
    raw = _concat_days(_warmup_day(), signal)
    d = fam.prepare(raw)
    d["atr"] = 50.0
    m = fam.simulate(d, spread_col=None)
    assert m.n_trades == 0


def test_one_entry_per_day():
    """entered_day blocks re-entry even after TP exits and later reclaim signals.

    Without this guard, a second flat reclaim same day would open trade 2.
    """
    atr = 1.0
    entry_px = 2001.0
    tp_px = entry_px + atr * fam.TP_ATR  # 2003.0
    signal = _reclaim_day(
        "2024-03-01",
        undercut_hour=3,
        undercut_low=1990.0,
        reclaim_hour=9,
        reclaim_close=entry_px,
        post_reclaim_close=entry_px,
        include_hour16=True,
        spreads=0.0,
    )
    # Hour 10: take profit → flat again same day
    signal.loc[signal["time"].dt.hour == 10, "high"] = tp_px + 0.5
    signal.loc[signal["time"].dt.hour == 10, "low"] = entry_px - 0.2
    signal.loc[signal["time"].dt.hour == 10, "close"] = tp_px
    # Hours 11–13: eligible reclaim signals while flat (undercut already sticky)
    for h in (11, 12, 13):
        signal.loc[signal["time"].dt.hour == h, "close"] = 2002.0
        signal.loc[signal["time"].dt.hour == h, "high"] = 2003.0
        signal.loc[signal["time"].dt.hour == h, "low"] = 2000.5
    raw = _concat_days(_warmup_day(), signal)
    d = fam.prepare(raw)
    d["atr"] = atr
    log: list[dict] = []
    m = fam.simulate(d, spread_col=None, trade_log=log)
    assert m.n_trades == 1
    assert len(log) == 1
    assert log[0]["reason"] == "tp"
    # Would be 2+ trades if entered_day guard were removed


def test_no_entry_bar_exit_sl_before_tp():
    signal = _reclaim_day(
        "2024-03-01",
        undercut_hour=5,
        undercut_low=1995.0,
        reclaim_hour=11,
        reclaim_close=2001.0,
        include_hour16=True,
        spreads=0.0,
    )
    # Entry bar spans SL and TP if same-bar exit were allowed
    signal.loc[signal["time"].dt.hour == 11, "low"] = 1990.0
    signal.loc[signal["time"].dt.hour == 11, "high"] = 2020.0
    signal.loc[signal["time"].dt.hour == 12, "low"] = 1990.0
    signal.loc[signal["time"].dt.hour == 12, "high"] = 2020.0
    signal.loc[signal["time"].dt.hour == 12, "close"] = 2001.0
    raw = _concat_days(_warmup_day(), signal)
    d = fam.prepare(raw)
    entry_idx = int(np.where((d["day_id"] == "2024-03-01") & (d["hour"] == 11))[0][0])
    d.loc[d.index[entry_idx], "atr"] = 1.0
    d.loc[d.index[entry_idx + 1], "atr"] = 1.0
    m = fam.simulate(d, spread_col=None, commission_per_lot=0.0, slippage_points=0.0)
    assert m.n_trades == 1
    assert m.net_profit < 0
    stop_dist = 1.5
    risk_cash = START_BALANCE * 0.01
    raw_lots = risk_cash / (stop_dist * CONTRACT_SIZE)
    lots = min(float(np.floor(raw_lots * 100 + 1e-12) / 100.0), fam.MAX_LOTS)
    expected = -stop_dist * CONTRACT_SIZE * lots
    assert m.net_profit == pytest.approx(expected, rel=0, abs=1e-6)


def test_null_invariants_canonical_session_method():
    ch = load_charter(CHARTER_V2)
    ns = null_spec_from_charter(ch)
    assert ns["method"] == "within_day_ohlc_increment_rotate_v1"
    assert int(ns["base_seed"]) == 20260808
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


def test_sealed_fixture_resolves_entry_allowed_hours(monkeypatch):
    import xau_sealed_family_cycle as sealed

    ch = load_charter(CHARTER_V2)
    captured: dict = {}
    real_inv = null_invariants_ok

    def wrap_inv(raw, scr, **kwargs):
        captured.update(kwargs)
        return real_inv(raw, scr, **kwargs)

    import xau_null_core as nc

    monkeypatch.setattr(nc, "null_invariants_ok", wrap_inv)
    out = sealed._run_synthetic_fixture("day_open_reclaim_flat", ch)
    assert out.get("family_smoke") == "ok"
    assert captured.get("entry_hour") == 9
    assert captured.get("flat_hour") == 16
