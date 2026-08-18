"""Structure v3: FVG/sweep causality, lock, news skip, no holdout peek."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from us_index_session_autoresearch_v3 import (  # noqa: E402
    LOCK_PATH,
    SEARCH_ID,
    build_grid,
    div_signals,
    fvg_signals,
    sweep_signals,
)
from us_index_session_core import (  # noqa: E402
    fvg_at,
    pre_ny_liquidity_levels,
    wick_parts,
)

TZ_ET = ZoneInfo("America/New_York")


def test_lock_matches_runner():
    lock = json.loads(LOCK_PATH.read_text())
    assert lock["search_id"] == SEARCH_ID
    assert lock["holdout_start"] == "2026-06-01"
    assert lock["promote"] is False
    assert lock["families"]["macro_news_fix_api"]["status"] == "skipped"
    g = build_grid()
    assert len(g) == int(lock["n_configs_expected"])
    assert {r["family"] for r in g} == {
        "ny_cash_liquidity_sweep",
        "ny_cash_fvg_mitigation",
        "us100_us30_divergence",
    }


def test_wick_parts_and_fvg_no_lookahead():
    up, lo, rng = wick_parts(10.0, 12.0, 9.0, 10.5)
    assert abs(up - 1.5) < 1e-12
    assert abs(lo - 1.0) < 1e-12
    assert abs(rng - 3.0) < 1e-12
    high = np.array([10.0, 10.2, 12.0, 20.0])
    low = np.array([9.5, 9.8, 10.5, 11.0])
    # bar 2: low 10.5 > high[0] 10.0 → bullish FVG
    gap = fvg_at(high, low, 2)
    assert gap is not None and gap[0] == 1
    later = high.copy()
    later[3] = 30.0
    assert fvg_at(high, low, 2) == fvg_at(later, low, 2)


def test_pdh_is_prior_day_not_today():
    start = datetime(2026, 3, 16, 18, 0, tzinfo=TZ_ET)
    times = [start.astimezone(UTC) + timedelta(minutes=5 * i) for i in range(120)]
    high = np.full(120, 100.0)
    low = np.full(120, 99.0)
    high[2] = 120.0  # Mar 16 spike
    keys = np.array(
        [int(t.astimezone(TZ_ET).strftime("%Y%m%d")) for t in times], dtype=np.int32
    )
    _ah, _al, _lh, _ll, pdh, pdl = pre_ny_liquidity_levels(times, high, low, keys)
    # First day has no PDH
    assert not np.isfinite(pdh[0])
    # Second ET day must see 120, not later bars
    d1 = int(datetime(2026, 3, 17, tzinfo=TZ_ET).strftime("%Y%m%d"))
    i17 = next(i for i, k in enumerate(keys) if k == d1)
    assert abs(pdh[i17] - 120.0) < 1e-9
    assert abs(pdl[i17] - 99.0) < 1e-9


def test_sweep_needs_wick_rejection():
    n = 20
    mins = np.array([9 * 60 + 45 + 5 * i for i in range(n)], dtype=np.int32)
    keys = np.full(n, 20260316, dtype=np.int32)
    dow = np.zeros(n, dtype=np.int8)
    open_ = np.full(n, 100.0)
    close = np.full(n, 100.2)
    high = np.full(n, 100.4)
    low = np.full(n, 99.8)
    # Bar 1 sweeps 101 and closes inside with a large upper wick
    high[1] = 101.5
    close[1] = 100.4
    open_[1] = 100.3
    asia_h = np.full(n, 101.0)
    asia_l = np.full(n, 99.0)
    nan = np.full(n, np.nan)
    ready = np.ones(n, dtype=bool)
    sigs, _tgt = sweep_signals(
        open_,
        high,
        low,
        close,
        mins,
        keys,
        dow,
        asia_h,
        asia_l,
        nan,
        nan,
        nan,
        nan,
        nan,
        nan,
        ready,
        use_asia=True,
        use_london=False,
        use_pdh=False,
        use_or=False,
        wick_frac=0.25,
        entry_end_min=11 * 60,
        one_per_day=True,
        exit_tag="box_opposite",
    )
    assert int(sigs[1]) == -1
    # Same breach, tiny wick (close at the high)
    high2 = high.copy()
    close2 = close.copy()
    open2 = open_.copy()
    low2 = low.copy()
    high2[1] = 101.2
    close2[1] = 100.95
    open2[1] = 100.90
    low2[1] = 99.0
    blocked, _ = sweep_signals(
        open2,
        high2,
        low2,
        close2,
        mins,
        keys,
        dow,
        asia_h,
        asia_l,
        nan,
        nan,
        nan,
        nan,
        nan,
        nan,
        ready,
        use_asia=True,
        use_london=False,
        use_pdh=False,
        use_or=False,
        wick_frac=0.25,
        entry_end_min=11 * 60,
        one_per_day=True,
        exit_tag="box_opposite",
    )
    assert int(blocked[1]) == 0


def test_fvg_enters_on_later_ce_reject_not_birth_bar():
    n = 16
    mins = np.array([9 * 60 + 35 + 5 * i for i in range(n)], dtype=np.int32)
    keys = np.full(n, 20260316, dtype=np.int32)
    dow = np.zeros(n, dtype=np.int8)
    high = np.full(n, 10.2)
    low = np.full(n, 9.8)
    close = np.full(n, 10.0)
    atr = np.full(n, 1.0)
    # Birth at i=2: bullish FVG (low[2]=10.5 > high[0]=10.2) — wait need low[2]>high[0]
    high[0] = 10.0
    low[2] = 10.4
    high[2] = 10.8
    close[2] = 10.6
    # CE = 0.5*(10.4+10.0)=10.2. Later bar touches CE and closes up.
    low[5] = 10.15
    close[5] = 10.35
    high[5] = 10.4
    sigs, _ = fvg_signals(
        high,
        low,
        close,
        mins,
        keys,
        dow,
        atr,
        min_gap_atr=0.15,
        entry_end_min=12 * 60,
        one_per_day=True,
    )
    assert int(sigs[2]) == 0
    assert int(sigs[5]) == 1


def test_divergence_is_hh_vs_lh():
    n = 12
    mins = np.array([9 * 60 + 40 + 5 * i for i in range(n)], dtype=np.int32)
    keys = np.full(n, 20260316, dtype=np.int32)
    dow = np.zeros(n, dtype=np.int8)
    h100 = np.linspace(10, 12, n)
    l100 = h100 - 0.2
    h30 = np.linspace(10, 10.2, n)
    h30[-1] = 10.0  # last bar is not a new HH on US30
    l30 = h30 - 0.2
    # Force last-but-needed index: lookback 3, i=8
    h100[8] = 20.0
    h30[8] = 10.05
    sigs = div_signals(
        h100,
        l100,
        h30,
        l30,
        mins,
        keys,
        dow,
        lookback=3,
        entry_end_min=12 * 60,
        one_per_day=True,
    )
    assert int(sigs[8]) == -1
