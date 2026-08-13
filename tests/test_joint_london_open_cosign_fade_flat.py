"""Synthetic fixtures for joint_london_open_cosign_fade_flat (v4 charter).

No develop-screen / real package evaluation. Offline only.
Required fixtures from charter execution_contract.required_fixtures:
  cosign_all_three_accept_entry_at_Tstar_plus_1_open
  reject_exit_using_Tstar_range
  cosign_fail_disagree_or_zero_return
  missing_intersection_or_missing_Tstar_plus_1_no_trade
  force_flat_last_bar_if_no_hour_16
  joint_gate_requires_all_three_symbol_soft
  lot_floor_step_min_max_and_fx_vs_xau_point_sizes
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import xau_family_joint_london_open_cosign_fade_flat as fam  # noqa: E402
from xau_charter_protocol import (  # noqa: E402
    is_charter_runnable,
    multi_instrument_single_frame_refuse_message,
    validate_charter_file,
)
from xau_family_null_maxstat import load_family  # noqa: E402

CHARTER_V4 = ROOT / "results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v4.json"
V4_SHA = "e29b26931b93443d7c903ddd034dfcabbeffde8761c41ad77b70e8292700b994"


# --- synthetic builders -------------------------------------------------------


def _bars(
    day: str,
    hours: list[int],
    *,
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    spreads: float = 0.0,
) -> pd.DataFrame:
    assert len(hours) == len(opens) == len(highs) == len(lows) == len(closes)
    rows = []
    for j, h in enumerate(hours):
        rows.append(
            {
                # Timezone-naive server_clock_as_stored (not UTC-labeled)
                "time": pd.Timestamp(f"{day} {h:02d}:00:00"),
                "open": opens[j],
                "high": highs[j],
                "low": lows[j],
                "close": closes[j],
                "spread": spreads,
                "timeframe": "H1",
            }
        )
    return pd.DataFrame(rows)


def _quiet_path(
    day: str,
    hours: list[int],
    *,
    base: float,
    drift: float = 0.0,
    bar_range: float = 0.5,
    spreads: float = 0.0,
) -> pd.DataFrame:
    """Near-flat bars around base; optional tiny drift per bar (for cosign)."""
    opens, highs, lows, closes = [], [], [], []
    px = base
    for _h in hours:
        o = px
        c = px + drift
        hi = max(o, c) + bar_range
        lo = min(o, c) - bar_range
        opens.append(o)
        highs.append(hi)
        lows.append(lo)
        closes.append(c)
        px = c
    return _bars(day, hours, opens=opens, highs=highs, lows=lows, closes=closes, spreads=spreads)


def _warmup_days(n_days: int = 3, start: str = "2024-01-02") -> dict[str, pd.DataFrame]:
    """Shared joint hours 1–20 for several days so ATR warmup passes."""
    bases = {"XAUUSD": 2000.0, "EURUSD": 1.1000, "GBPUSD": 1.2500}
    hours = list(range(1, 21))
    start_ts = pd.Timestamp(start)  # naive server calendar
    frames: dict[str, list[pd.DataFrame]] = {s: [] for s in fam.SYMBOLS}
    for d in range(n_days):
        day = (start_ts + pd.DateOffset(days=int(d))).strftime("%Y-%m-%d")
        for s, base in bases.items():
            frames[s].append(
                _quiet_path(day, hours, base=base, drift=0.0, bar_range=base * 0.0002)
            )
    return {s: pd.concat(frames[s], ignore_index=True) for s in fam.SYMBOLS}


def _signal_day_frames(
    day: str,
    *,
    cosign: str = "up",
    include_hour16: bool = True,
    t_star_hour: int = 7,
    xau_base: float = 2000.0,
    eur_base: float = 1.10,
    gbp_base: float = 1.25,
    spreads: float = 0.0,
    post_entry: str = "flat",
) -> dict[str, pd.DataFrame]:
    """Build one signal day with T* cosign and path after entry.

    cosign: 'up' | 'down' | 'disagree' | 'zero_xau'
    post_entry: 'flat' | 'sl_long' | 'tp_long' | 'sl_short' | 'tp_short'
    """
    hours = list(range(1, 16)) + ([16] if include_hour16 else [])
    # Default quiet small positive drift only on T* for cosign up
    out: dict[str, pd.DataFrame] = {}
    for s, base in (
        ("XAUUSD", xau_base),
        ("EURUSD", eur_base),
        ("GBPUSD", gbp_base),
    ):
        scale = base * 0.001 if s == "XAUUSD" else base * 0.0005
        opens, highs, lows, closes = [], [], [], []
        for h in hours:
            o = base
            c = base
            if h == t_star_hour:
                if cosign == "up":
                    c = base + scale
                elif cosign == "down":
                    c = base - scale
                elif cosign == "zero_xau" and s == "XAUUSD":
                    c = base  # zero return
                elif cosign == "zero_xau":
                    c = base + scale
                elif cosign == "disagree":
                    # XAU up, FX down
                    c = base + scale if s == "XAUUSD" else base - scale
                else:
                    c = base + scale
            elif h == t_star_hour + 1:
                # entry bar open = base; path depends on post_entry
                o = base
                c = base
            else:
                o = base
                c = base
            hi = max(o, c) + scale * 0.5
            lo = min(o, c) - scale * 0.5
            # After entry, shape SL/TP if requested (all symbols same structure)
            if h == t_star_hour + 1 and post_entry != "flat":
                # Entry fill is open=base; fade direction depends on cosign
                # For tests that need SL/TP we widen range
                if post_entry in ("sl_short", "tp_short"):
                    # short: SL above entry, TP below
                    if post_entry == "sl_short":
                        hi = base + abs(scale) * 50
                        lo = base - abs(scale) * 0.1
                        c = base + abs(scale)
                    else:
                        lo = base - abs(scale) * 50
                        hi = base + abs(scale) * 0.1
                        c = base - abs(scale)
                elif post_entry in ("sl_long", "tp_long"):
                    if post_entry == "sl_long":
                        lo = base - abs(scale) * 50
                        hi = base + abs(scale) * 0.1
                        c = base - abs(scale)
                    else:
                        hi = base + abs(scale) * 50
                        lo = base - abs(scale) * 0.1
                        c = base + abs(scale)
            opens.append(o)
            highs.append(hi)
            lows.append(lo)
            closes.append(c)
        out[s] = _bars(
            day, hours, opens=opens, highs=highs, lows=lows, closes=closes, spreads=spreads
        )
    return out


# Realistic ATR scales so risk-sized lots clear lot_min on all three books.
DEFAULT_ATR = {"XAUUSD": 10.0, "EURUSD": 0.0010, "GBPUSD": 0.0010}


def _merge_warmup_signal(
    signal: dict[str, pd.DataFrame],
    *,
    atr_force: dict[str, float] | None = None,
) -> dict[str, pd.DataFrame]:
    warm = _warmup_days(3)
    merged = {
        s: pd.concat([warm[s], signal[s]], ignore_index=True) for s in fam.SYMBOLS
    }
    aligned = fam.align_joint(merged)
    atr_map = DEFAULT_ATR if atr_force is None else atr_force
    for s in fam.SYMBOLS:
        aligned[s] = aligned[s].copy()
        aligned[s]["atr"] = float(atr_map[s])
    return aligned


# --- charter / refuse ---------------------------------------------------------


def test_charter_v4_runnable_and_sha():
    assert validate_charter_file(CHARTER_V4) == []
    ok, why = is_charter_runnable(CHARTER_V4)
    assert ok is True, why
    assert hashlib.sha256(CHARTER_V4.read_bytes()).hexdigest() == V4_SHA


def test_grid_cardinality_one():
    g = fam.build_grid()
    assert len(g) == 1
    assert fam.grid(max_n=100, seed=0) == g
    assert g[0]["coincident_hours"] == [7, 8, 9]
    assert g[0]["flat_hour"] == 16


def test_single_frame_simulate_refuses():
    with pytest.raises(RuntimeError, match="REFUSE_SINGLE_FRAME_SIMULATE"):
        fam.simulate(pd.DataFrame({"time": [], "open": [], "high": [], "low": [], "close": []}))


def test_single_frame_runners_still_refuse_charter():
    import json

    ch = json.loads(CHARTER_V4.read_text())
    msg = multi_instrument_single_frame_refuse_message(ch)
    assert msg is not None and "REFUSE_SINGLE_FRAME_RUNNER" in msg


def test_not_registered_as_null_maxstat_builtin():
    """Must not be a single-frame BUILTIN (dedicated multi-instrument harness only)."""
    from xau_family_null_maxstat import BUILTINS

    assert "joint_london_open_cosign_fade_flat" not in BUILTINS
    # Module may import via xau_family_* discovery, but single-frame simulate must refuse.
    plug = load_family("joint_london_open_cosign_fade_flat")
    with pytest.raises(RuntimeError, match="REFUSE_SINGLE_FRAME_SIMULATE"):
        plug.simulate(
            pd.DataFrame(
                {
                    "time": pd.to_datetime(["2024-01-01"], utc=True),
                    "open": [1.0],
                    "high": [1.0],
                    "low": [1.0],
                    "close": [1.0],
                }
            )
        )


# --- required fixtures --------------------------------------------------------


def test_cosign_all_three_accept_entry_at_tstar_plus_1_open():
    """Cosign up → fade short; three trades; entry at open of T*+1."""
    day = "2024-01-05"
    sig = _signal_day_frames(day, cosign="up", t_star_hour=7, include_hour16=True)
    aligned = _merge_warmup_signal(sig)
    log: list[dict] = []
    res = fam.simulate_joint(
        aligned,
        already_aligned=True,
        trade_log=log,
        commission_per_lot=0.0,
        slippage_points=0.0,
    )
    assert res.n_signals_cosign == 1
    assert res.n_signals_entered == 1
    assert res.joint.n_trades == 3
    assert len(log) == 3
    # All short
    assert all(t["pos"] == -1 for t in log)
    # Entry at open of T*+1: find entry bar
    ref = aligned["XAUUSD"]
    # T* hour 7 on signal day
    t_star_mask = (ref["day_id"] == day) & (ref["hour"] == 7)
    t_star_i = int(np.flatnonzero(t_star_mask.to_numpy())[0])
    entry_i = t_star_i + 1
    for t in log:
        assert t["entry_bar"] == entry_i
        assert t["entry"] == pytest.approx(float(aligned[t["symbol"]]["open"].iloc[entry_i]))
        # Entry must not be T* close
        assert t["entry"] != pytest.approx(
            float(aligned[t["symbol"]]["close"].iloc[t_star_i]), rel=0, abs=1e-12
        ) or float(aligned[t["symbol"]]["open"].iloc[entry_i]) == float(
            aligned[t["symbol"]]["close"].iloc[t_star_i]
        )


def test_reject_exit_using_tstar_range():
    """SL/TP from atr[T*]; never exit using T* high/low as entry geometry.

    Craft: T* has a huge high that would SL a wrong same-bar short, but entry is
    T*+1 open with quiet range → no SL from T* bar.
    """
    day = "2024-01-05"
    sig = _signal_day_frames(day, cosign="up", t_star_hour=7, include_hour16=True)
    # Blow out T* high on XAU only (would stop a short entered at T* close)
    for s in fam.SYMBOLS:
        m = sig[s]["time"].dt.hour == 7
        sig[s].loc[m, "high"] = float(sig[s].loc[m, "open"].iloc[0]) + 500.0
    aligned = _merge_warmup_signal(sig)
    log: list[dict] = []
    res = fam.simulate_joint(
        aligned,
        already_aligned=True,
        trade_log=log,
    )
    assert res.n_signals_entered == 1
    assert res.joint.n_trades == 3
    # No trade should have exit_bar == T*
    ref = aligned["XAUUSD"]
    t_star_i = int(
        np.flatnonzero(((ref["day_id"] == day) & (ref["hour"] == 7)).to_numpy())[0]
    )
    assert all(t["exit_bar"] != t_star_i for t in log)
    assert all(t["entry_bar"] == t_star_i + 1 for t in log)


def test_cosign_fail_disagree_or_zero_return():
    day = "2024-01-05"
    for cosign in ("disagree", "zero_xau"):
        sig = _signal_day_frames(day, cosign=cosign, t_star_hour=7)
        aligned = _merge_warmup_signal(sig)
        res = fam.simulate_joint(aligned, already_aligned=True)
        assert res.n_signals_cosign == 0, cosign
        assert res.n_signals_entered == 0, cosign
        assert res.joint.n_trades == 0, cosign


def test_missing_intersection_or_missing_tstar_plus_1_no_trade():
    # Missing intersection: EUR lacks the signal day entirely
    warm = _warmup_days(3)
    day = "2024-01-05"
    sig = _signal_day_frames(day, cosign="up")
    frames = {
        "XAUUSD": pd.concat([warm["XAUUSD"], sig["XAUUSD"]], ignore_index=True),
        "EURUSD": warm["EURUSD"].copy(),  # no signal day
        "GBPUSD": pd.concat([warm["GBPUSD"], sig["GBPUSD"]], ignore_index=True),
    }
    aligned = fam.align_joint(frames)
    for s in fam.SYMBOLS:
        aligned[s] = aligned[s].copy()
        aligned[s]["atr"] = DEFAULT_ATR[s]
    res = fam.simulate_joint(aligned, already_aligned=True)
    assert res.n_signals_entered == 0
    assert res.joint.n_trades == 0

    # Force T* at 9 as last bar of day (no T*+1).
    sig2 = _signal_day_frames(day, cosign="up", t_star_hour=9, include_hour16=False)
    for s in fam.SYMBOLS:
        # Drop coincident hours before 9 so T*=9, and drop any bar after 9
        sig2[s] = sig2[s].loc[
            ~sig2[s]["time"].dt.hour.isin([7, 8])
            & (sig2[s]["time"].dt.hour <= 9)
        ].reset_index(drop=True)
    aligned2 = _merge_warmup_signal(sig2)
    res2 = fam.simulate_joint(aligned2, already_aligned=True)
    # T*=9 is last bar of day → no T*+1 same day
    assert res2.n_signals_entered == 0
    assert res2.joint.n_trades == 0


def test_force_flat_last_bar_if_no_hour_16():
    day = "2024-01-05"
    sig = _signal_day_frames(
        day, cosign="up", t_star_hour=7, include_hour16=False, post_entry="flat"
    )
    aligned = _merge_warmup_signal(sig)
    log: list[dict] = []
    res = fam.simulate_joint(
        aligned, already_aligned=True, trade_log=log
    )
    assert res.n_signals_entered == 1
    assert res.joint.n_trades == 3
    assert all(t["reason"] == "day_end_flat" for t in log)
    # Exit on last bar of day
    ref = aligned["XAUUSD"]
    last_i = int(np.flatnonzero((ref["day_id"] == day).to_numpy())[-1])
    assert all(t["exit_bar"] == last_i for t in log)
    assert int(ref["hour"].iloc[last_i]) < 16


def test_joint_gate_requires_all_three_symbol_soft():
    """Binary gate fails if any symbol soft fails even if joint book looks fine."""
    # Synthetic metrics path: use empty/result with crafted Metrics
    from backtest import Metrics

    weak = Metrics(
        net_profit=100.0,
        win_rate=50.0,
        profit_factor=1.2,
        max_drawdown_pct=5.0,
        n_trades=5,  # < 20
        wins=3,
        losses=2,
    )
    strong = Metrics(
        net_profit=500.0,
        win_rate=55.0,
        profit_factor=1.3,
        max_drawdown_pct=5.0,
        n_trades=30,
        wins=18,
        losses=12,
    )
    joint = Metrics(
        net_profit=1100.0,
        win_rate=55.0,
        profit_factor=1.25,
        max_drawdown_pct=5.0,
        n_trades=90,
        wins=50,
        losses=40,
    )
    res = fam.JointResult(
        per_symbol={"XAUUSD": strong, "EURUSD": strong, "GBPUSD": weak},
        joint=joint,
    )
    assert fam.soft_pass_joint(joint) is True
    assert fam.soft_pass_per_symbol(strong) is True
    assert fam.soft_pass_per_symbol(weak) is False
    assert fam.joint_gate_success(res) is False
    assert fam.n_passers_binary(res) == 0

    res_ok = fam.JointResult(
        per_symbol={"XAUUSD": strong, "EURUSD": strong, "GBPUSD": strong},
        joint=joint,
    )
    assert fam.joint_gate_success(res_ok) is True
    assert fam.n_passers_binary(res_ok) == 1


def test_lot_floor_step_min_max_and_fx_vs_xau_point_sizes():
    """Sizing uses contract_size; never force min; FX vs XAU differ."""
    # Huge ATR → stop wide → lots floor below min → None (never force lot_min)
    assert (
        fam.size_lots(balance=10_000.0, atr_tstar=1000.0, contract_size=100.0) is None
    )
    # Normal XAU / FX ATR scales
    xau = fam.size_lots(balance=10_000.0, atr_tstar=10.0, contract_size=100.0)
    eur = fam.size_lots(balance=10_000.0, atr_tstar=0.0010, contract_size=100_000.0)
    assert xau is not None and eur is not None
    assert xau == pytest.approx(
        min(0.5, np.floor((100.0 / (1.5 * 10.0 * 100.0)) / 0.01) * 0.01)
    )
    # Cap at lot_max
    xau_max = fam.size_lots(
        balance=1_000_000.0, atr_tstar=0.01, contract_size=100.0, lot_max=0.5
    )
    eur_max = fam.size_lots(
        balance=1_000_000.0, atr_tstar=0.00001, contract_size=100_000.0, lot_max=0.5
    )
    assert xau_max == 0.5
    assert eur_max == 0.5

    assert fam.PER_SYMBOL_META["XAUUSD"]["point_size"] == 0.01
    assert fam.PER_SYMBOL_META["EURUSD"]["point_size"] == 1e-5
    assert fam.PER_SYMBOL_META["XAUUSD"]["contract_size"] == 100.0
    assert fam.PER_SYMBOL_META["EURUSD"]["contract_size"] == 100_000.0

    # Integration: partial basket skipped when one leg cannot size
    day = "2024-01-05"
    sig = _signal_day_frames(day, cosign="up", t_star_hour=7)
    # XAU ATR huge → lots < min; FX ATR normal
    aligned = _merge_warmup_signal(
        sig,
        atr_force={"XAUUSD": 1000.0, "EURUSD": 0.001, "GBPUSD": 0.001},
    )
    res = fam.simulate_joint(aligned, already_aligned=True)
    assert res.n_signals_cosign == 1
    assert res.n_signals_entered == 0
    assert res.n_signals_skipped_partial == 1
    assert res.joint.n_trades == 0


def test_align_joint_intersection_only():
    warm = _warmup_days(2)
    # Add extra hour only on XAU
    extra = _bars(
        "2024-01-10",
        [12],
        opens=[2000.0],
        highs=[2001.0],
        lows=[1999.0],
        closes=[2000.5],
    )
    frames = {
        "XAUUSD": pd.concat([warm["XAUUSD"], extra], ignore_index=True),
        "EURUSD": warm["EURUSD"],
        "GBPUSD": warm["GBPUSD"],
    }
    aligned = fam.align_joint(frames)
    n = len(aligned["XAUUSD"])
    assert n == len(aligned["EURUSD"]) == len(aligned["GBPUSD"])
    assert n == len(warm["EURUSD"])
    # Extra XAU-only bar dropped
    assert not ((aligned["XAUUSD"]["day_id"] == "2024-01-10").any())


# --- fail-closed / discriminating regressions (v4 re-review BLOCK) -------------


def test_costs_missing_spread_column_refuses():
    day = "2024-01-05"
    sig = _signal_day_frames(day, cosign="up")
    aligned = _merge_warmup_signal(sig)
    for s in fam.SYMBOLS:
        aligned[s] = aligned[s].drop(columns=["spread"])
    with pytest.raises(ValueError, match="spread|cost"):
        fam.simulate_joint(aligned, already_aligned=True)


def test_costs_nan_spread_refuses():
    day = "2024-01-05"
    sig = _signal_day_frames(day, cosign="up", spreads=5.0)
    aligned = _merge_warmup_signal(sig)
    for s in fam.SYMBOLS:
        aligned[s] = aligned[s].copy()
        aligned[s].loc[aligned[s].index[0], "spread"] = float("nan")
    with pytest.raises(ValueError, match="non-finite|spread"):
        fam.simulate_joint(aligned, already_aligned=True)


def test_costs_negative_spread_refuses():
    day = "2024-01-05"
    sig = _signal_day_frames(day, cosign="up", spreads=5.0)
    aligned = _merge_warmup_signal(sig)
    for s in fam.SYMBOLS:
        aligned[s] = aligned[s].copy()
        aligned[s]["spread"] = -5.0
    with pytest.raises(ValueError, match="negative"):
        fam.simulate_joint(aligned, already_aligned=True)


def test_costs_inf_spread_refuses():
    day = "2024-01-05"
    sig = _signal_day_frames(day, cosign="up", spreads=1.0)
    aligned = _merge_warmup_signal(sig)
    for s in fam.SYMBOLS:
        aligned[s] = aligned[s].copy()
        aligned[s]["spread"] = float("inf")
    with pytest.raises(ValueError, match="non-finite|Inf|inf"):
        fam.simulate_joint(aligned, already_aligned=True)


def test_already_aligned_shifted_eur_timestamps_refused():
    """Intersection calendar must not be bypassable via already_aligned=True."""
    day = "2024-01-05"
    sig = _signal_day_frames(day, cosign="up")
    aligned = _merge_warmup_signal(sig)
    bad = {s: aligned[s].copy() for s in fam.SYMBOLS}
    bad["EURUSD"]["time"] = bad["EURUSD"]["time"] + pd.Timedelta(1, unit="h")
    with pytest.raises(ValueError, match="timestamps|intersection"):
        fam.simulate_joint(bad, already_aligned=True)


def test_nan_entry_open_cancels_entire_basket():
    day = "2024-01-05"
    sig = _signal_day_frames(day, cosign="up", t_star_hour=7)
    aligned = _merge_warmup_signal(sig)
    ref = aligned["XAUUSD"]
    t_star_i = int(
        np.flatnonzero(((ref["day_id"] == day) & (ref["hour"] == 7)).to_numpy())[0]
    )
    entry_i = t_star_i + 1
    aligned["EURUSD"] = aligned["EURUSD"].copy()
    aligned["EURUSD"].loc[aligned["EURUSD"].index[entry_i], "open"] = float("nan")
    log: list[dict] = []
    res = fam.simulate_joint(aligned, already_aligned=True, trade_log=log)
    assert res.n_signals_cosign == 1
    assert res.n_signals_entered == 0
    assert res.n_signals_skipped_partial == 1
    assert res.joint.n_trades == 0
    assert log == []


def test_server_time_is_timezone_naive():
    day = "2024-01-05"
    sig = _signal_day_frames(day, cosign="up")
    for s in fam.SYMBOLS:
        assert getattr(sig[s]["time"].dtype, "tz", None) is None
    aligned = _merge_warmup_signal(sig)
    for s in fam.SYMBOLS:
        assert getattr(aligned[s]["time"].dtype, "tz", None) is None
    # UTC-labeled input must refuse
    utc = {s: aligned[s].copy() for s in fam.SYMBOLS}
    for s in fam.SYMBOLS:
        utc[s]["time"] = pd.to_datetime(utc[s]["time"], utc=True)
    with pytest.raises(ValueError, match="timezone-naive|server_clock"):
        fam.simulate_joint(utc, already_aligned=True)


def test_wilder_atr_not_sma():
    """prepare/align must use Wilder ewm, not SMA of TR."""
    # Two full days of H1 with expanding ranges so Wilder != SMA
    parts_xau = []
    parts_eur = []
    parts_gbp = []
    i_global = 0
    for day in ("2024-02-01", "2024-02-02"):
        hours = list(range(0, 24))
        opens = [2000.0 + i_global * 0.1 + j * 0.1 for j in range(len(hours))]
        highs = [o + 1.0 + ((i_global + j) % 7) for j, o in enumerate(opens)]
        lows = [o - 0.8 - ((i_global + j) % 5) * 0.2 for j, o in enumerate(opens)]
        closes = [o + 0.3 for o in opens]
        parts_xau.append(
            _bars(day, hours, opens=opens, highs=highs, lows=lows, closes=closes)
        )
        parts_eur.append(
            _bars(
                day,
                hours,
                opens=[1.1 + j * 1e-5 for j in range(24)],
                highs=[1.101 + j * 1e-5 for j in range(24)],
                lows=[1.099 + j * 1e-5 for j in range(24)],
                closes=[1.1005 + j * 1e-5 for j in range(24)],
            )
        )
        parts_gbp.append(
            _bars(
                day,
                hours,
                opens=[1.25 + j * 1e-5 for j in range(24)],
                highs=[1.251 + j * 1e-5 for j in range(24)],
                lows=[1.249 + j * 1e-5 for j in range(24)],
                closes=[1.2505 + j * 1e-5 for j in range(24)],
            )
        )
        i_global += 24
    raw = {
        "XAUUSD": pd.concat(parts_xau, ignore_index=True),
        "EURUSD": pd.concat(parts_eur, ignore_index=True),
        "GBPUSD": pd.concat(parts_gbp, ignore_index=True),
    }
    aligned = fam.align_joint(raw)
    d = aligned["XAUUSD"]
    wilder = fam._wilder_atr(d)
    sma = fam._sma_atr(d)
    mask = np.isfinite(wilder.to_numpy()) & np.isfinite(sma.to_numpy())
    assert mask.sum() > 10
    assert not np.allclose(wilder.to_numpy()[mask], sma.to_numpy()[mask], rtol=0, atol=1e-9)
    np.testing.assert_allclose(d["atr"].to_numpy(), wilder.to_numpy(), rtol=0, atol=1e-12)


def test_positive_spread_cost_arithmetic_and_timing():
    """Full RT spread cost measured at entry, deducted at exit (balance unchanged at fill)."""
    day = "2024-01-05"
    spread_pts = 20.0
    sig = _signal_day_frames(day, cosign="up", t_star_hour=7, spreads=spread_pts)
    aligned = _merge_warmup_signal(sig)
    log: list[dict] = []
    res = fam.simulate_joint(aligned, already_aligned=True, trade_log=log)
    assert res.n_signals_entered == 1
    assert len(log) == 3
    for t in log:
        s = t["symbol"]
        ps = fam.PER_SYMBOL_META[s]["point_size"]
        cs = fam.PER_SYMBOL_META[s]["contract_size"]
        expected = spread_pts * ps * cs * t["lots"]
        assert t["trade_cost"] == pytest.approx(expected, rel=0, abs=1e-9)
        # Cost deducted at exit: pnl = gross - cost
        assert t["pnl"] == pytest.approx(t["gross"] - t["trade_cost"], rel=0, abs=1e-9)
        # Balance at entry unchanged by cost booking
        assert t["bal_at_entry"] == pytest.approx(fam.START_BALANCE, rel=0, abs=1e-9)
        assert t["bal_after_exit"] == pytest.approx(
            t["bal_at_entry"] + t["pnl"], rel=0, abs=1e-9
        )


def test_sl_before_tp_when_both_touch():
    """On a bar that spans both SL and TP, short/long must take SL first."""
    day = "2024-01-05"
    # Cosign up → fade short; entry open = base; wide range hits both SL and TP
    sig = _signal_day_frames(day, cosign="up", t_star_hour=7, include_hour16=True)
    atr = DEFAULT_ATR
    aligned = _merge_warmup_signal(sig)
    ref = aligned["XAUUSD"]
    t_star_i = int(
        np.flatnonzero(((ref["day_id"] == day) & (ref["hour"] == 7)).to_numpy())[0]
    )
    entry_i = t_star_i + 1
    for s in fam.SYMBOLS:
        aligned[s] = aligned[s].copy()
        fill = float(aligned[s]["open"].iloc[entry_i])
        stop = 1.5 * atr[s]
        # Short SL = fill+stop, TP = fill-2*atr; make bar span both
        aligned[s].loc[aligned[s].index[entry_i], "high"] = fill + stop + 1.0
        aligned[s].loc[aligned[s].index[entry_i], "low"] = fill - 2.0 * atr[s] - 1.0
        aligned[s].loc[aligned[s].index[entry_i], "close"] = fill
    log: list[dict] = []
    res = fam.simulate_joint(aligned, already_aligned=True, trade_log=log)
    assert res.n_signals_entered == 1
    assert all(t["reason"] == "sl" for t in log)
    assert all(t["exit_bar"] == entry_i for t in log)


def test_joint_mtm_drawdown_uses_floating_equity():
    """Joint max DD must reflect adverse MTM while position open, not flat books only."""
    day = "2024-01-05"
    # Cosign down → fade long; then push all closes down hard before time flat
    sig = _signal_day_frames(day, cosign="down", t_star_hour=7, include_hour16=True)
    aligned = _merge_warmup_signal(sig)
    ref = aligned["XAUUSD"]
    t_star_i = int(
        np.flatnonzero(((ref["day_id"] == day) & (ref["hour"] == 7)).to_numpy())[0]
    )
    entry_i = t_star_i + 1
    # After entry, set intermediate bar deep underwater then recover at hour 16
    mid = entry_i + 2
    for s in fam.SYMBOLS:
        aligned[s] = aligned[s].copy()
        fill = float(aligned[s]["open"].iloc[entry_i])
        # Keep range quiet on entry so no SL/TP; then dump close on mid bar
        aligned[s].loc[aligned[s].index[entry_i], "high"] = fill + 1e-6
        aligned[s].loc[aligned[s].index[entry_i], "low"] = fill - 1e-6
        aligned[s].loc[aligned[s].index[entry_i], "close"] = fill
        crash = fill * 0.5 if s == "XAUUSD" else fill * 0.98
        aligned[s].loc[aligned[s].index[mid], "close"] = crash
        aligned[s].loc[aligned[s].index[mid], "high"] = fill
        aligned[s].loc[aligned[s].index[mid], "low"] = crash
    res = fam.simulate_joint(aligned, already_aligned=True)
    assert res.n_signals_entered == 1
    # Equity series must go below joint start at the crash bar
    assert min(res.joint_equity) < fam.JOINT_START_EQUITY - 1.0
    assert res.joint.max_drawdown_pct > 0.0


def test_two_cycle_realized_balance_compounding():
    """Second-day lots must size from post-trade-1 realized balance, not START_BALANCE."""
    atr_xau = 8.4
    # stop_dist = 12.6 → risk 100 / (12.6*100) = 0.07936 → floor 0.07
    # TP = 2*ATR → gross per lot large enough to lift lots next day
    day1 = "2024-01-05"
    day2 = "2024-01-08"
    sig1 = _signal_day_frames(day1, cosign="down", t_star_hour=7, include_hour16=True)
    sig2 = _signal_day_frames(day2, cosign="down", t_star_hour=7, include_hour16=True)
    warm = _warmup_days(3)
    frames = {
        s: pd.concat([warm[s], sig1[s], sig2[s]], ignore_index=True) for s in fam.SYMBOLS
    }
    aligned = fam.align_joint(frames)
    for s in fam.SYMBOLS:
        aligned[s] = aligned[s].copy()
        if s == "XAUUSD":
            aligned[s]["atr"] = atr_xau
        else:
            aligned[s]["atr"] = 0.0010
    # Force TP on hour 8 (entry) for day1 only — long fade hits high TP
    for day in (day1,):
        ref = aligned["XAUUSD"]
        t_star_i = int(
            np.flatnonzero(((ref["day_id"] == day) & (ref["hour"] == 7)).to_numpy())[0]
        )
        entry_i = t_star_i + 1
        for s in fam.SYMBOLS:
            fill = float(aligned[s]["open"].iloc[entry_i])
            atr_v = float(aligned[s]["atr"].iloc[t_star_i])
            tp = fill + 2.0 * atr_v
            aligned[s].loc[aligned[s].index[entry_i], "high"] = tp + atr_v
            aligned[s].loc[aligned[s].index[entry_i], "low"] = fill - 0.1 * atr_v
            aligned[s].loc[aligned[s].index[entry_i], "close"] = tp
    log: list[dict] = []
    res = fam.simulate_joint(aligned, already_aligned=True, trade_log=log)
    xau_trades = [t for t in log if t["symbol"] == "XAUUSD"]
    assert len(xau_trades) >= 2
    assert xau_trades[0]["reason"] == "tp"
    lots1 = xau_trades[0]["lots"]
    lots2 = xau_trades[1]["lots"]
    # After TP, balance grows → second day floors to a higher lot step
    assert lots1 == pytest.approx(0.07, abs=1e-9)
    assert lots2 > lots1
    assert res.n_signals_entered >= 2
