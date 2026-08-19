"""BTC H1 pullback: lock, split, costs, no forming-bar / forming-H4 leak."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from btc_h1_trend_pullback_screen import (  # noqa: E402
    LOCK_PATH,
    SEARCH_ID,
    build_grid,
    load_lock,
)
from btc_trend_pullback_core import (  # noqa: E402
    FROZEN_CONTRACT,
    FROZEN_LOTS,
    FROZEN_POINT,
    FROZEN_SLIPPAGE_POINTS,
    HOLDOUT_START,
    completed_htf_index,
    frozen_cost_spec,
    htf_bias_strength,
    pullback_signals,
    refuse_mutated_btc_book,
    require_frozen_btc_book,
    split_btc,
)
from us_index_session_backtest import CostSpec, Trade, _round_trip_cost  # noqa: E402


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
        signal_time=f"{d}T12:00:00+00:00",
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
    assert lock["selection_end"] == "2026-01-01"
    assert lock["holdout_start"] == "2026-01-01"
    assert lock["promote"] is False
    assert lock["live_go"] is False
    assert lock["python_only"] is True
    assert lock["lots"] == FROZEN_LOTS
    assert lock["goal_daily_pct"] is None
    assert lock["goal_monthly_pct"] is None
    assert lock["costs"]["slippage_points"] == FROZEN_SLIPPAGE_POINTS
    assert lock["costs"]["lots"] == FROZEN_LOTS
    assert lock["costs"]["point_size"] == FROZEN_POINT
    assert lock["costs"]["contract_size"] == FROZEN_CONTRACT
    h1 = lock["data"]["files"]["H1"]
    h4 = lock["data"]["files"]["H4"]
    assert len(h1["sha256"]) == 64 and h1["sha256"] != "PENDING_EXPORT"
    assert len(h4["sha256"]) == 64 and h4["sha256"] != "PENDING_EXPORT"
    assert h1["bars"] == 29035
    assert h4["bars"] == 7260
    assert lock["causality"]["pivots"] == (
        "not used. Do not import htf_fib_core for this family. "
        "BtcTrendPullback is EMA/RSI/MACD reclaim, not Fib."
    )
    grid = build_grid()
    assert len(grid) == int(lock["n_configs_expected"])
    assert len(grid) == 16
    assert {r["family"] for r in grid} == {"h1_htf_ema_pullback"}
    assert all(r["flatten_weekend"] is True for r in grid)
    assert all(r["tp_rr"] == 2.0 for r in grid)
    refuse_mutated_btc_book(lock)


def test_holdout_split_is_utc_2026_01_01_not_us100_june():
    pre, post = split_btc(
        [_t("2025-12-31"), _t("2026-01-01"), _t("2026-06-15"), _t("2026-07-02")]
    )
    assert [t.signal_time[:10] for t in pre] == ["2025-12-31"]
    assert [t.signal_time[:10] for t in post] == [
        "2026-01-01",
        "2026-06-15",
        "2026-07-02",
    ]
    assert HOLDOUT_START.isoformat() == "2026-01-01"


def test_lock_tamper_promote():
    lock = json.loads(LOCK_PATH.read_text())
    lock["promote"] = True
    with pytest.raises(SystemExit, match="promote"):
        refuse_mutated_btc_book(lock)


def test_lock_tamper_slippage_us100_copy():
    lock = json.loads(LOCK_PATH.read_text())
    lock["costs"] = dict(lock["costs"])
    lock["costs"]["slippage_points"] = 10.0
    with pytest.raises(SystemExit, match="slippage"):
        refuse_mutated_btc_book(lock)
    with pytest.raises(SystemExit, match="frozen BTC book"):
        require_frozen_btc_book(CostSpec(lots=0.01, slippage_points=10.0))


def test_lock_tamper_lots_one():
    lock = json.loads(LOCK_PATH.read_text())
    lock["lots"] = 1.0
    with pytest.raises(SystemExit, match="lots"):
        refuse_mutated_btc_book(lock)
    with pytest.raises(SystemExit, match="frozen BTC book"):
        require_frozen_btc_book(CostSpec(lots=1.0, slippage_points=250.0))


def test_honest_lock_is_accepted():
    lock = load_lock()
    require_frozen_btc_book(frozen_cost_spec())
    assert lock["search_id"] == SEARCH_ID


def test_round_trip_uses_btc_book_not_us100():
    costs = frozen_cost_spec()
    rt = _round_trip_cost(1251.0, costs)
    assert rt == pytest.approx((1251.0 + 2.0 * 250.0) * 0.01 * 1.0 * 0.01)
    us100_copy = CostSpec(
        point_size=0.01,
        contract_size=1.0,
        lots=1.0,
        slippage_points=10.0,
        max_spread_points=200.0,
    )
    assert _round_trip_cost(1251.0, us100_copy) != pytest.approx(rt)


def test_forming_h4_is_not_joined():
    # Three H4: 00:00, 04:00, 08:00. H1 at 09:00 is still inside 08:00–12:00.
    h4_open = np.array(
        [
            datetime(2026, 3, 16, 0, 0, tzinfo=UTC).timestamp(),
            datetime(2026, 3, 16, 4, 0, tzinfo=UTC).timestamp(),
            datetime(2026, 3, 16, 8, 0, tzinfo=UTC).timestamp(),
        ]
    )
    h1_open = np.array(
        [
            datetime(2026, 3, 16, 9, 0, tzinfo=UTC).timestamp(),
            datetime(2026, 3, 16, 12, 0, tzinfo=UTC).timestamp(),
        ]
    )
    idx = completed_htf_index(h1_open, h4_open)
    assert int(idx[0]) == 1  # 04:00 H4 completed; 08:00 still forming
    assert int(idx[1]) == 2  # 08:00 H4 now complete
    h4_close = np.array([100.0, 100.0, 200.0])
    e50 = np.array([101.0, 101.0, 190.0])
    e200 = np.array([90.0, 90.0, 90.0])
    bias, _ = htf_bias_strength(idx, h4_close, e50, e200, min_strength=0.01)
    # 09:00 must not see the forming 200 close.
    assert int(bias[0]) == 1
    assert h4_close[int(idx[0])] == 100.0


def test_forming_last_h1_has_no_signal():
    n = 260
    t0 = datetime(2025, 6, 1, tzinfo=UTC)
    h1_times = [t0 + timedelta(hours=i) for i in range(n)]
    h1_ts = np.array([t.timestamp() for t in h1_times])
    close = 50_000.0 + np.linspace(0, 4_000, n)
    high = close + 80.0
    low = close - 80.0
    h4_n = n // 4
    h4_ts = np.array([t0.timestamp() + 14400 * i for i in range(h4_n)])
    h4_close = close[3::4][:h4_n]
    sigs = pullback_signals(
        close,
        high,
        low,
        h1_ts,
        h4_ts,
        h4_close,
        allow_continuation=True,
        allow_shorts=True,
        max_pullback_pct=0.015,
    )
    assert int(sigs[-1]) == 0


def test_shorts_off_never_emits_minus_one():
    n = 260
    t0 = datetime(2025, 6, 1, tzinfo=UTC)
    h1_ts = np.array([(t0 + timedelta(hours=i)).timestamp() for i in range(n)])
    close = 50_000.0 - np.linspace(0, 4_000, n)
    high = close + 80.0
    low = close - 80.0
    h4_n = n // 4
    h4_ts = np.array([t0.timestamp() + 14400 * i for i in range(h4_n)])
    h4_close = close[3::4][:h4_n]
    sigs = pullback_signals(
        close,
        high,
        low,
        h1_ts,
        h4_ts,
        h4_close,
        allow_continuation=True,
        allow_shorts=False,
        max_pullback_pct=0.015,
    )
    assert int(np.min(sigs)) >= 0


def test_core_does_not_import_htf_fib_or_mt5_arch():
    src = (ROOT / "scripts" / "btc_trend_pullback_core.py").read_text()
    assert "import htf_fib_core" not in src
    assert "from htf_fib_core" not in src
    assert "mt5_arch" not in src
    screen = (ROOT / "scripts" / "btc_h1_trend_pullback_screen.py").read_text()
    assert "mt5_arch" not in screen
    assert "argparse" in screen
