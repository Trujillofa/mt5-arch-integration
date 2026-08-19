"""BTC H1 range-vol breakout: lock, split, costs, causality, no EMA/H4."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from btc_h1_range_vol_breakout_screen import (  # noqa: E402
    LOCK_PATH,
    SEARCH_ID,
    build_grid,
    load_lock,
    score_row,
)
from btc_range_vol_breakout_core import (  # noqa: E402
    FROZEN_CONTRACT,
    FROZEN_LOTS,
    FROZEN_POINT,
    FROZEN_SLIPPAGE_POINTS,
    HOLDOUT_START,
    breakout_signals,
    frozen_cost_spec,
    range_known_at_prior_bars,
    refuse_mutated_btc_book,
    require_frozen_btc_book,
    split_btc,
    true_range,
)
from us_index_session_backtest import CostSpec, Trade, _round_trip_cost  # noqa: E402
from us_index_session_htf import donchian_prior  # noqa: E402


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
    assert lock["search_id"] != "btc_h1_trend_pullback_v1"
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
    fam = lock["families"]["h1_range_vol_breakout"]
    assert fam["use_ema"] is False
    assert fam["use_h4"] is False
    assert fam["allow_shorts"] is True
    assert fam["close_through"] is True
    h1 = lock["data"]["files"]["H1"]
    assert len(h1["sha256"]) == 64 and h1["sha256"] != "PENDING_EXPORT"
    assert h1["bars"] == 29035
    assert "H4" not in lock["data"]["files"]
    assert lock["causality"]["ema"] == "OFF. This is the sealed v1 failure mode."
    grid = build_grid()
    assert len(grid) == int(lock["n_configs_expected"])
    assert len(grid) == 16
    assert {r["family"] for r in grid} == {"h1_range_vol_breakout"}
    assert all(r["flatten_weekend"] is True for r in grid)
    assert all(r["allow_shorts"] is True for r in grid)
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
    assert HOLDOUT_START == date(2026, 1, 1)


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


def test_lock_tamper_ema_or_h4_on():
    lock = json.loads(LOCK_PATH.read_text())
    lock["families"] = json.loads(json.dumps(lock["families"]))
    lock["families"]["h1_range_vol_breakout"]["use_ema"] = True
    with pytest.raises(SystemExit, match="use_ema"):
        refuse_mutated_btc_book(lock)
    lock = json.loads(LOCK_PATH.read_text())
    lock["families"] = json.loads(json.dumps(lock["families"]))
    lock["families"]["h1_range_vol_breakout"]["use_h4"] = True
    with pytest.raises(SystemExit, match="use_h4"):
        refuse_mutated_btc_book(lock)


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


def test_score_row_ignores_holdout_keys():
    develop_pass = {
        "trades": 50,
        "net_pnl": 20.0,
        "profit_factor": 1.4,
        "expectancy": 0.4,
    }
    develop_fail = {
        "trades": 10,
        "net_pnl": -5.0,
        "profit_factor": 0.5,
        "expectancy": -0.5,
    }
    assert score_row(develop_pass) > 0
    assert score_row(develop_fail) == -1e9
    bloated = dict(develop_fail)
    bloated["holdout_pf"] = 9.9
    bloated["holdout_net"] = 1_000.0
    assert score_row(bloated) == -1e9


def test_range_excludes_bar_i():
    high = np.array([10.0, 11.0, 12.0, 13.0, 99.0])
    low = np.array([9.0, 8.0, 7.0, 6.0, 1.0])
    rh, rl = donchian_prior(high, low, n=3)
    known_h, known_l = range_known_at_prior_bars(high, low, 4, 3)
    assert known_h == pytest.approx(13.0)
    assert known_l == pytest.approx(6.0)
    assert float(rh[4]) == pytest.approx(13.0)
    assert float(rl[4]) == pytest.approx(6.0)
    assert known_h != 99.0
    assert known_l != 1.0


def _compressed_then_break(*, close_through: bool, short: bool = False) -> np.ndarray:
    """Wide history → quiet squeeze → one expansion bar. Last bar stays quiet."""
    n = 120
    px = np.full(n, 50_000.0)
    high = px + 80.0
    low = px - 80.0
    # Elevated vol so ATR50 stays high.
    high[:55] = px[:55] + 400.0
    low[:55] = px[:55] - 400.0
    # Quiet compression window (ATR14 decays).
    high[55:110] = px[55:110] + 20.0
    low[55:110] = px[55:110] - 20.0
    i = 110
    prior_h, prior_l = range_known_at_prior_bars(high, low, i, 20)
    if short:
        if close_through:
            px[i] = prior_l - 30.0
        else:
            px[i] = (prior_h + prior_l) / 2.0
        high[i] = max(px[i], prior_l) + 5.0
        low[i] = min(px[i], prior_l - 80.0)
    else:
        if close_through:
            px[i] = prior_h + 30.0
        else:
            px[i] = (prior_h + prior_l) / 2.0
        high[i] = max(px[i], prior_h + 80.0)
        low[i] = min(px[i], prior_h) - 5.0
    return px, high, low, i


def test_wick_through_without_close_does_not_signal():
    close, high, low, i = _compressed_then_break(close_through=False)
    prior_h, _ = range_known_at_prior_bars(high, low, i, 20)
    assert float(high[i]) > prior_h
    assert float(close[i]) <= prior_h
    sigs = breakout_signals(
        close, high, low, range_n=20, squeeze_max=0.90, expand_min=1.25
    )
    assert int(sigs[i]) == 0


def test_close_through_after_squeeze_expands():
    close, high, low, i = _compressed_then_break(close_through=True)
    prior_h, _ = range_known_at_prior_bars(high, low, i, 20)
    assert float(close[i]) > prior_h
    atr14 = __import__("us_index_session_core", fromlist=["wilder_atr"]).wilder_atr(
        high, low, close, 14
    )
    atr50 = __import__("us_index_session_core", fromlist=["wilder_atr"]).wilder_atr(
        high, low, close, 50
    )
    tr = true_range(high, low, close)
    assert float(atr14[i - 1]) / float(atr50[i - 1]) <= 0.90
    assert float(tr[i]) / float(atr14[i - 1]) >= 1.25
    sigs = breakout_signals(
        close, high, low, range_n=20, squeeze_max=0.90, expand_min=1.25
    )
    assert int(sigs[i]) == 1
    assert int(sigs[-1]) == 0


def test_short_close_through_fires_when_allowed():
    close, high, low, i = _compressed_then_break(close_through=True, short=True)
    sigs = breakout_signals(
        close, high, low, range_n=20, squeeze_max=0.90, expand_min=1.25
    )
    assert int(sigs[i]) == -1
    blocked = breakout_signals(
        close,
        high,
        low,
        range_n=20,
        squeeze_max=0.90,
        expand_min=1.25,
        allow_shorts=False,
    )
    assert int(blocked[i]) == 0


def test_squeeze_uses_prior_atr_not_bar_i():
    close, high, low, i = _compressed_then_break(close_through=True)
    atr14 = __import__("us_index_session_core", fromlist=["wilder_atr"]).wilder_atr(
        high, low, close, 14
    )
    atr50 = __import__("us_index_session_core", fromlist=["wilder_atr"]).wilder_atr(
        high, low, close, 50
    )
    ratio_prev = float(atr14[i - 1]) / float(atr50[i - 1])
    ratio_now = float(atr14[i]) / float(atr50[i])
    assert ratio_prev <= 0.90
    # Bar i is the expansion — ATR[i] is not the squeeze baseline.
    sigs = breakout_signals(
        close, high, low, range_n=20, squeeze_max=0.90, expand_min=1.25
    )
    assert int(sigs[i]) == 1
    assert ratio_now != pytest.approx(ratio_prev)


def test_forming_last_h1_has_no_signal():
    close, high, low, i = _compressed_then_break(close_through=True)
    # Copy the breakout onto the last bar; exclude_forming must still zero it.
    close[-1] = close[i]
    high[-1] = high[i]
    low[-1] = low[i]
    sigs = breakout_signals(
        close, high, low, range_n=20, squeeze_max=0.90, expand_min=1.25
    )
    assert int(sigs[-1]) == 0


def test_core_does_not_import_ema_htf_fib_or_mt5_arch():
    src = (ROOT / "scripts" / "btc_range_vol_breakout_core.py").read_text()
    assert "ema_series" not in src
    assert "rsi_series" not in src
    assert "macd_series" not in src
    assert "htf_bias" not in src
    assert "import htf_fib_core" not in src
    assert "from htf_fib_core" not in src
    assert "mt5_arch" not in src
    screen = (ROOT / "scripts" / "btc_h1_range_vol_breakout_screen.py").read_text()
    assert "mt5_arch" not in screen
    assert "ema_series" not in screen
    assert "argparse" in screen
