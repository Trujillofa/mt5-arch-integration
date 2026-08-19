"""v5 lock, cash-open gap vs prior cash close, completed HTF, US30 isolation."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from us_index_session_autoresearch_v4 import split_v4  # noqa: E402
from us_index_session_autoresearch_v5 import (  # noqa: E402
    LOCK_PATH,
    SEARCH_ID,
    build_grid,
    gap_fade_signals,
    us30_cosign_signals,
)
from us_index_session_backtest import Trade  # noqa: E402
from us_index_session_core import (  # noqa: E402
    cash_adr_series,
    cash_open_gap_pct,
    completed_daily_donch_state,
    completed_h4_ema_bias,
    prior_cash_close_series,
)

ET = ZoneInfo("America/New_York")


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
    assert lock["costs"]["slippage_points"] == 10.0
    assert "exog_london_fx_cosign_xau_follow_flat hours {7,8,9}" in str(lock["not_copied"])
    assert len(build_grid()) == int(lock["n_configs_expected"])
    fams = {r["family"] for r in build_grid()}
    assert fams == {
        "ny_cash_gap_fade_adr",
        "htf_lock_orb",
        "exog_us30_ny_cash_cosign_us100_follow",
    }


def test_june_is_neither_develop_nor_holdout():
    pre, post = split_v4([_t("2026-05-31"), _t("2026-06-15"), _t("2026-07-02")])
    assert [t.et_date for t in pre] == ["2026-05-31"]
    assert [t.et_date for t in post] == ["2026-07-02"]


def test_gap_uses_prior_cash_close_not_overnight_print():
    # Day1 cash close 100; overnight last print 150; day2 09:30 open 100.6.
    times = []
    mins = []
    keys = []
    open_ = []
    close = []
    high = []
    low = []
    d1 = datetime(2026, 3, 16, 9, 30, tzinfo=ET)
    # 09:30 and 15:55 cash bars + 16:05 post + next 09:25 overnight + 09:30
    stamps = [
        (d1, 100.0, 100.0),
        (d1 + timedelta(hours=6, minutes=25), 100.0, 100.0),
        (d1 + timedelta(hours=6, minutes=35), 150.0, 150.0),
        (d1 + timedelta(days=1, minutes=-5), 150.0, 150.0),
        (d1 + timedelta(days=1), 100.6, 100.6),
    ]
    for ts, o, c in stamps:
        utc = ts.astimezone(UTC)
        times.append(utc)
        et = ts
        mins.append(et.hour * 60 + et.minute)
        keys.append(et.year * 10000 + et.month * 100 + et.day)
        open_.append(o)
        close.append(c)
        high.append(max(o, c) + 0.1)
        low.append(min(o, c) - 0.1)
    mins_a = np.array(mins, dtype=np.int32)
    keys_a = np.array(keys, dtype=np.int32)
    prior = prior_cash_close_series(mins_a, keys_a, np.array(close, float))
    assert prior[-1] == 100.0
    gap = cash_open_gap_pct(mins_a, keys_a, np.array(open_, float), prior)
    assert abs(gap[-1] - 0.006) < 1e-9


def test_adr_excludes_today():
    # Two cash days: ranges 10 then 20. Third day ADR(1) must be 20, not today.
    keys = np.array([20260316] * 2 + [20260317] * 2 + [20260318] * 2, dtype=np.int32)
    mins = np.array([9 * 60 + 30, 12 * 60, 9 * 60 + 30, 12 * 60, 9 * 60 + 30, 12 * 60])
    high = np.array([110.0, 110.0, 130.0, 130.0, 200.0, 200.0])
    low = np.array([100.0, 100.0, 110.0, 110.0, 100.0, 100.0])
    adr = cash_adr_series(mins, keys, high, low, n=1)
    assert np.isnan(adr[0])
    assert adr[2] == 10.0
    assert adr[4] == 20.0


def test_h4_bias_ignores_forming_bucket():
    # One completed 4h bucket of rising closes, then first bar of the next bucket.
    t0 = datetime(2026, 3, 16, 0, 0, tzinfo=UTC)
    times = [t0 + timedelta(minutes=5 * i) for i in range(48 + 1)]
    close = np.linspace(100.0, 120.0, 48)
    close = np.append(close, 90.0)
    # warmup: tile the rising 4h many times so EMA200 exists
    times_w = []
    close_w = []
    for k in range(220):
        base = t0 + timedelta(hours=4 * k)
        for i in range(48):
            times_w.append(base + timedelta(minutes=5 * i))
            close_w.append(100.0 + k * 0.1 + i * 0.01)
    times_w.append(t0 + timedelta(hours=4 * 220))
    close_w.append(50.0)
    bias = completed_h4_ema_bias(times_w, np.array(close_w, float), fast=5, slow=20)
    # Last bar is the first print of a new bucket; bias must come from prior H4, not 50.
    assert bias[-1] == 1
    assert int(bias[10]) == 0


def test_donch_uses_completed_days_only():
    # 20 flat days then a breakout day; current day reads that completed breakout.
    keys = []
    high = []
    low = []
    close = []
    for i in range(20):
        d = 20260301 + i
        keys.extend([d, d])
        high.extend([100.0, 100.0])
        low.extend([90.0, 90.0])
        close.extend([99.0, 99.0])
    keys.extend([20260321, 20260321, 20260322, 20260322])
    high.extend([120.0, 120.0, 121.0, 121.0])
    low.extend([90.0, 90.0, 90.0, 90.0])
    close.extend([119.0, 119.0, 118.0, 118.0])
    st = completed_daily_donch_state(
        np.array(keys, np.int32),
        np.array(high, float),
        np.array(low, float),
        np.array(close, float),
        n=20,
    )
    assert st[0] == 0
    assert st[-1] == 1


def test_us30_predicate_ignores_us100_bar():
    mins = np.array([9 * 60 + 45, 9 * 60 + 50], dtype=np.int32)
    keys = np.array([20260316, 20260316], dtype=np.int32)
    dow = np.array([0, 0], dtype=np.int8)
    # US30 down, dummy US100 would be up if someone cheated
    sigs = us30_cosign_signals(
        np.array([100.0, 100.0]),
        np.array([99.0, 99.0]),
        np.array([1.0, 1.0]),
        mins,
        keys,
        dow,
        min_atr_k=0.0,
        one_per_day=True,
    )
    assert sigs[0] == -1
    assert sigs[1] == 0


def test_gap_fade_stamps_first_cash_bar_only():
    mins = np.array([9 * 60 + 25, 9 * 60 + 30, 9 * 60 + 35], dtype=np.int32)
    keys = np.array([20260316] * 3, dtype=np.int32)
    dow = np.array([0, 0, 0], dtype=np.int8)
    gap = np.array([np.nan, 0.006, 0.006])
    adr = np.array([1.0, 1.0, 1.0])
    prior = np.array([np.nan, 100.0, 100.0])
    close = np.array([100.0, 100.6, 100.7])
    sigs = gap_fade_signals(
        close,
        mins,
        keys,
        dow,
        gap,
        adr,
        prior,
        gap_min=0.005,
        gap_max=0.01,
        adr_k=0.4,
        entry="next_0930",
        one_per_day=True,
    )
    assert sigs[0] == 0
    assert sigs[1] == -1
    assert sigs[2] == 0
