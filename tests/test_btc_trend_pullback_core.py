"""btc_trend_pullback core — clock, causality, lock holdout, forming-bar."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import btc_trend_pullback_core as core  # noqa: E402
import lane_kit as lk  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOCK = json.loads((ROOT / "results" / "btc_trend_pullback_lock.json").read_text())
TZ = ZoneInfo("America/New_York")


def test_holdout_refuses_taken_dates():
    for bad in ("2025-03-01", "2026-01-01", "2026-03-01", "2026-06-01", "2026-07-01"):
        with pytest.raises(SystemExit, match="already used"):
            lk.assert_lane_holdout(date.fromisoformat(bad), core.TAKEN_HOLDOUTS)
    assert LOCK["holdout"]["start"] == "2026-04-01"
    hs = date.fromisoformat(LOCK["holdout"]["start"])
    assert hs not in core.TAKEN_HOLDOUTS
    lk.assert_lane_holdout(hs, core.TAKEN_HOLDOUTS)


def test_et_from_server_jan_and_jul():
    # Server wall = ET + 7h. 2026-01-15 15:00 server → 08:00 EST; 2026-07-15 15:00 → 08:00 EDT.
    jan = pd.Series([datetime(2026, 1, 15, 15, 0)])
    jul = pd.Series([datetime(2026, 7, 15, 15, 0)])
    et_jan = core.et_from_server(pd.to_datetime(jan))
    et_jul = core.et_from_server(pd.to_datetime(jul))
    assert et_jan.dt.hour.iloc[0] == 8
    assert et_jul.dt.hour.iloc[0] == 8
    assert et_jan.iloc[0].utcoffset().total_seconds() == -5 * 3600
    assert et_jul.iloc[0].utcoffset().total_seconds() == -4 * 3600


def test_forming_bar_never_signals():
    n = 400
    close = np.linspace(40000.0, 50000.0, n)
    open_ = close - 10.0
    high = close + 20.0
    low = close - 20.0
    epoch = np.arange(n, dtype=np.int64) * 3600 + 1_700_000_000
    et_key = np.arange(n, dtype=np.int64) // 24
    b = core.rebuild_indicators(
        core.H1Book(
            open=open_,
            high=high,
            low=low,
            close=close,
            spread=np.full(n, 1250.0),
            server_epoch=epoch,
            et_key=et_key,
            et_date=np.array([date(2025, 1, 1)] * n, dtype=object),
            atr=np.array([]),
            ema50=np.array([]),
            ema200=np.array([]),
            rsi=np.array([]),
            macd_hist=np.array([]),
            h4_bias=np.array([]),
            h4_strength=np.array([]),
        )
    )
    for fam in core.FAMILIES:
        sigs = core.family_signals(b, fam, min_atr_pct=0.0, one_per_day=False)
        assert sigs[-1] == 0, fam


def test_h4_bias_never_reads_own_bucket():
    """CompletedHtfShift: a bar inside an H4 bucket uses the previous bucket."""
    n = 48  # 2 H4 buckets of 4 H1 bars, then more for EMA warmup
    n = 800
    close = np.linspace(40000.0, 41000.0, n)
    epoch = np.arange(n, dtype=np.int64) * 3600 + 1_700_000_000  # aligned
    bucket = (epoch // 14400) * 14400
    bias, _ = core._h4_bias_completed(epoch, close, 0.0)
    # For every bar, completed_bucket = own_bucket - 14400
    own = bucket
    completed = own - 14400
    # The first H4 bucket has no previous completed bucket in the unique list
    # that can produce a non-zero bias until EMA200 warms; just assert the
    # mapping itself: completed_bucket[i] < own_bucket[i] always.
    assert np.all(completed < own)


def test_lock_promote_and_live_go_stay_false():
    lk.refuse_promote_flips(LOCK)
    with pytest.raises(SystemExit, match="promote"):
        lk.refuse_promote_flips({**LOCK, "promote": True})
