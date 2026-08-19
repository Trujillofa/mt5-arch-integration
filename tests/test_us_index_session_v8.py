"""v8 lock, H1/H4 causality, completed Daily SMA50, htf_fib_core pivots."""

from __future__ import annotations

import inspect
import json
import struct
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from us_index_session_autoresearch_v4 import split_v4  # noqa: E402
from us_index_session_autoresearch_v8 import (  # noqa: E402
    LOCK_PATH,
    SEARCH_ID,
    build_grid,
)
from us_index_session_backtest import (  # noqa: E402
    Trade,
    plausible_hc_step,
    read_mt5_hc,
    read_mt5_hc_m5,
)
from us_index_session_htf import (  # noqa: E402
    H4Impulse,
    bollinger,
    completed_daily_sma50_slope,
    donchian_prior,
    fib_pullback_signals,
    h4_impulses,
    keltner,
    squeeze_breakout_signals,
    squeezed,
)
import us_index_session_htf as htf  # noqa: E402

FP_H1 = Path.home() / (
    ".mt5-fpmarkets/drive_c/Program Files/FP Markets MT5 Terminal/"
    "Bases/FPMarketsSC-Live/history/US100/cache/H1.hc"
)
FP_H4 = FP_H1.with_name("H4.hc")


def _t(d: str, pnl: float = 1.0) -> Trade:
    return Trade(
        side=1,
        signal_i=0,
        fill_i=1,
        exit_i=2,
        entry=1,
        exit=2,
        reason="x",
        et_date=d,
        signal_time="",
        fill_time="",
        exit_time="",
        spread_pts=0,
        cost=0,
        pnl=pnl,
        mae=0,
        mfe=0,
    )


def test_lock_and_grid():
    lock = json.loads(LOCK_PATH.read_text())
    assert lock["search_id"] == SEARCH_ID
    assert lock["selection_end"] == "2026-06-01"
    assert lock["holdout_start"] == "2026-07-01"
    assert lock["promote"] is False
    assert lock["live_go"] is False
    assert lock["python_only"] is True
    assert lock["lots"] == 1.0
    assert lock["costs"]["slippage_points"] == 10.0
    assert lock["costs"]["max_spread_points"] == 200.0
    assert lock["causality"]["donchian_include_i"] is False
    assert lock["causality"]["daily_sma50_uses_forming"] is False
    assert "v4–v7 holdout" in lock["holdout_rule"] or "v4-v7 holdout" in lock["holdout_rule"]
    assert "not virgin" in lock["holdout_rule"]
    grid = build_grid()
    assert len(grid) == int(lock["n_configs_expected"])
    assert len(grid) == 32
    fams = {r["family"] for r in grid}
    assert fams == {"h1_volatility_squeeze_breakout", "h4_impulse_fib_pullback"}
    assert sum(1 for r in grid if r["family"] == "h1_volatility_squeeze_breakout") == 16
    assert sum(1 for r in grid if r["family"] == "h4_impulse_fib_pullback") == 16
    assert lock["grid_breakdown"]["h1_volatility_squeeze_breakout"] == 16
    assert lock["grid_breakdown"]["h4_impulse_fib_pullback"] == 16
    assert all(r.get("one_per_impulse") is True for r in grid if r["family"].startswith("h4"))


def test_june_is_neither_develop_nor_holdout():
    pre, post = split_v4([_t("2026-05-31"), _t("2026-06-15"), _t("2026-07-02")])
    assert [t.et_date for t in pre] == ["2026-05-31"]
    assert [t.et_date for t in post] == ["2026-07-02"]


def test_donchian_uses_i_minus_1():
    high = np.ones(30) * 100.0
    low = np.ones(30) * 90.0
    high[25] = 150.0
    dh, dl = donchian_prior(high, low, 20)
    assert dh[25] == 100.0
    assert dl[25] == 90.0
    assert dh[26] == 150.0


def test_squeeze_uses_completed_h1_and_prior_donchian():
    n = 48
    close = np.full(n, 100.0)
    high = close + 1.0
    low = close - 1.0
    # Forming last bar must not be required for a mid-series release.
    close[40] = 130.0
    high[40] = 131.0
    low[40] = 129.0
    # Same-bar spike that must not be the Donchian break level if close stays in.
    high[41] = 200.0
    close[41] = 100.5
    low[41] = 99.5
    bb_u, bb_l = bollinger(close, 20, 2.0)
    kc_u, kc_l = keltner(close, high, low, 20, 1.5)
    sq = squeezed(bb_u, bb_l, kc_u, kc_l)
    assert bool(sq[39])
    assert bool(sq[39]) and not bool(sq[40])
    mins = np.full(n, 10 * 60, dtype=np.int32)
    keys = np.full(n, 20260316, dtype=np.int32)
    dow = np.zeros(n, dtype=np.int8)
    slope = np.ones(n, dtype=np.int8)
    sigs = squeeze_breakout_signals(
        close, high, low, mins, keys, dow, slope, bb_k=2.0, kc_atr_mult=1.5, one_per_day=False
    )
    # Release + close 130 > prior Donchian 101.
    assert int(sigs[40]) == 1
    # close 100.5 does not break prior Donchian even though high[41]=200.
    assert int(sigs[41]) == 0
    # Forming last bar excluded.
    assert int(sigs[-1]) == 0


def test_daily_sma50_ignores_forming_daily():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    daily_times = [start + timedelta(days=i) for i in range(60)]
    daily_close = np.full(60, 100.0)
    daily_close[59] = 200.0
    # H1 during the last Daily (still forming).
    h1 = [daily_times[59] + timedelta(hours=12)]
    slope = completed_daily_sma50_slope(h1, daily_times, daily_close)
    assert int(slope[0]) == 0
    # After that Daily completes, the spike is visible and slope turns up.
    h1_after = [daily_times[59] + timedelta(days=1)]
    slope_after = completed_daily_sma50_slope(h1_after, daily_times, daily_close)
    assert int(slope_after[0]) == 1


def test_pivots_imported_from_htf_fib_core():
    src = inspect.getsource(htf)
    assert "from htf_fib_core import" in src
    assert "confirmed_pivots" in src
    assert "confirmed_pivots_with_centers" in src
    assert "walk_swing_and_fibs" in src
    body = inspect.getsource(h4_impulses)
    assert "confirmed_pivots_with_centers" in body
    assert "walk_swing_and_fibs" in body


def test_no_fib_signal_before_h4_confirm_close():
    n = 12
    t0 = datetime(2026, 3, 16, 8, 0, tzinfo=UTC)
    times = [t0 + timedelta(hours=i) for i in range(n)]
    close = np.full(n, 100.0)
    high = close + 1.0
    low = close - 1.0
    # Pocket 90–95. Close enters at i=6.
    close[6] = 92.0
    low[6] = 91.0
    high[6] = 93.0
    mins = np.array([t.hour * 60 + t.minute for t in times], dtype=np.int32)
    dow = np.zeros(n, dtype=np.int8)
    # Confirm close = close of H1[6] → first eligible bar is 6.
    confirm = times[6].timestamp() + 3600.0
    early = H4Impulse(
        direction=1,
        origin=80.0,
        extreme=110.0,
        confirm_i=0,
        confirm_close_ts=confirm,
        origin_center=0,
        extreme_center=1,
        atr=5.0,
        fib_lo=90.0,
        fib_hi=95.0,
        sl=77.5,
        tp=110.0,
    )
    sigs, sl, tp = fib_pullback_signals(
        close, high, low, times, mins, dow, [early], entry="close_in_zone"
    )
    assert int(np.max(np.abs(sigs[:6]))) == 0
    assert int(sigs[6]) == 1
    assert sl[6] == 77.5
    assert tp[6] == 110.0


def _write_hc(path: Path, step: int, n: int, t0: int = 1_700_000_000) -> None:
    header = bytes(432)
    times = b"".join(struct.pack("<q", t0 + i * step) for i in range(n))

    def pref_f8(arr: np.ndarray) -> bytes:
        return struct.pack("<i", n) + np.asarray(arr, dtype="<f8").tobytes()

    def pref_u8(arr: np.ndarray) -> bytes:
        return struct.pack("<i", n) + np.asarray(arr, dtype="<u8").tobytes()

    def pref_i32(arr: np.ndarray) -> bytes:
        return struct.pack("<i", n) + np.asarray(arr, dtype="<i4").tobytes()

    o = np.full(n, 100.0)
    blob = (
        header
        + times
        + pref_f8(o)
        + pref_f8(o + 1.0)
        + pref_f8(o - 1.0)
        + pref_f8(o)
        + pref_u8(np.ones(n, dtype=np.uint64))
        + pref_i32(np.zeros(n, dtype=np.int32))
    )
    path.write_bytes(blob)


def test_hc_reader_accepts_h1_and_h4(tmp_path: Path):
    assert plausible_hc_step(3600, max_step=3600)
    assert plausible_hc_step(14400, max_step=86400)
    assert not plausible_hc_step(14400, max_step=3600)
    assert plausible_hc_step(86400, max_step=86400)
    h1p = tmp_path / "H1.hc"
    h4p = tmp_path / "H4.hc"
    _write_hc(h1p, 3600, 120)
    _write_hc(h4p, 14400, 120)
    h1 = read_mt5_hc(h1p)
    h4 = read_mt5_hc(h4p)
    assert len(h1) == 120
    assert len(h4) == 120
    assert int(h1["server_epoch"].iloc[1] - h1["server_epoch"].iloc[0]) == 3600
    assert int(h4["server_epoch"].iloc[1] - h4["server_epoch"].iloc[0]) == 14400
    with pytest.raises(ValueError, match="no HTF time table"):
        read_mt5_hc_m5(h4p)


@pytest.mark.skipif(not FP_H1.is_file() or not FP_H4.is_file(), reason="FP US100 hc not on disk")
def test_hc_reader_real_fp_h1_h4():
    h1 = read_mt5_hc(FP_H1)
    h4 = read_mt5_hc(FP_H4)
    assert len(h1) >= 1000
    assert len(h4) >= 200
    assert int(np.median(np.diff(h1["server_epoch"].to_numpy()))) == 3600
    assert int(np.median(np.diff(h4["server_epoch"].to_numpy()))) == 14400
