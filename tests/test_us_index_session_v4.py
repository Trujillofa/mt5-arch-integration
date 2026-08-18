"""v4 lock, proxies, regime gate, June buffer not in selection."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from us_index_session_autoresearch_v4 import (  # noqa: E402
    LOCK_PATH,
    SEARCH_ID,
    build_grid,
    split_v4,
)
from us_index_session_backtest import Trade  # noqa: E402
from us_index_session_core import (  # noqa: E402
    atr_expanding,
    prior_day_poc,
    proxy_cvd_series,
)


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
    assert lock["families"]["tick_proxy_cvd"]["true_cvd"] == "skipped — no aggressor ticks"
    assert len(build_grid()) == int(lock["n_configs_expected"])


def test_june_is_neither_develop_nor_holdout():
    trades = [
        _t("2026-05-31"),
        _t("2026-06-15"),
        _t("2026-07-02"),
    ]
    pre, post = split_v4(trades)
    assert [t.et_date for t in pre] == ["2026-05-31"]
    assert [t.et_date for t in post] == ["2026-07-02"]


def test_proxy_cvd_resets_each_et_day():
    keys = np.array([20260316, 20260316, 20260317], dtype=np.int32)
    open_ = np.array([10.0, 11.0, 10.0])
    close = np.array([11.0, 12.0, 9.0])
    vol = np.array([5.0, 3.0, 8.0])
    cvd = proxy_cvd_series(keys, open_, close, vol)
    assert cvd[0] == 5.0
    assert cvd[1] == 8.0
    assert cvd[2] == -8.0


def test_poc_is_prior_day():
    keys = np.array([20260316] * 4 + [20260317] * 3, dtype=np.int32)
    # Day 1 spends volume near 20
    high = np.array([21.0, 21.0, 12.0, 12.0, 30.0, 30.0, 30.0])
    low = np.array([19.0, 19.0, 10.0, 10.0, 29.0, 29.0, 29.0])
    vol = np.array([100.0, 100.0, 1.0, 1.0, 50.0, 50.0, 50.0])
    poc = prior_day_poc(keys, high, low, vol, bin_price=2.0, kind="volume")
    assert not np.isfinite(poc[0])
    assert np.isfinite(poc[4])
    assert 18.0 <= poc[4] <= 22.0


def test_atr_expanding_gate():
    fast = np.array([2.0, 1.0])
    slow = np.array([1.0, 2.0])
    m = atr_expanding(fast, slow, 1.0)
    assert bool(m[0]) is True
    assert bool(m[1]) is False
