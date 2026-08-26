"""Synthetic fixture tests for multi_day_variance_expansion_flat (v1 charter).

No develop-screen / real-data evaluation. Offline only.
Required fixtures from charter execution_contract.required_fixtures.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import xau_family_multi_day_variance_expansion_flat as fam  # noqa: E402
from xau_charter_protocol import (  # noqa: E402
    is_charter_runnable,
    validate_charter_file,
)

from backtest import START_BALANCE  # noqa: E402

CHARTER = ROOT / "results/xau_charters/2026-08-20_multi_day_variance_expansion_flat_v1.json"
CHARTER_SHA = "36829e926f42c1f555d0a0d85941cdaf9c629937b4d65c08f63911e9f0b5faea"

WARM_START = "2024-01-01"
N_WARM = 21
QUIET_R = 0.0001
LARGE_RS = (0.02, -0.018, 0.022, -0.016)


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


def _day_str(start: str, offset: int) -> str:
    t0 = pd.Timestamp(start, tz="UTC")
    return (t0 + pd.DateOffset(days=int(offset))).strftime("%Y-%m-%d")


def _expansion_closes(*, last_r: float | None, n_warm: int = N_WARM) -> list[float]:
    """21 daily last closes: 15 quiet returns + 5 designed large |r|."""
    assert n_warm == 21
    closes = [2000.0]
    for _ in range(15):
        closes.append(closes[-1] * math.exp(QUIET_R))
    for r in LARGE_RS:
        closes.append(closes[-1] * math.exp(r))
    if last_r is None:
        closes.append(closes[-1])  # r_20 = 0 → C_{T-1} == C_{T-2}
    else:
        closes.append(closes[-1] * math.exp(float(last_r)))
    assert len(closes) == 21
    return closes


def _quiet_closes(n_warm: int = N_WARM) -> list[float]:
    closes = [2000.0]
    for _ in range(n_warm - 1):
        closes.append(closes[-1] * math.exp(QUIET_R))
    return closes


def _warmup_from_closes(
    closes: list[float],
    *,
    start: str = WARM_START,
    sl_dist: float = 10.0,
    zero_sl: bool = False,
    spreads: float = 0.0,
) -> pd.DataFrame:
    """One first-bar + hour-16 last-close per completed day."""
    frames = []
    n = len(closes)
    for i, c in enumerate(closes):
        day = _day_str(start, i)
        is_last = i == n - 1
        if zero_sl and is_last:
            o_first = float(c)
        elif is_last:
            o_first = float(c) - float(sl_dist)
        else:
            o_first = float(c)
        frames.append(
            _bars_day(
                day,
                [1, 16],
                opens=[o_first, float(c)],
                highs=[max(o_first, c) + 0.2, float(c) + 0.2],
                lows=[min(o_first, c) - 0.2, float(c) - 0.2],
                closes=[(o_first + c) / 2.0, float(c)],
                spreads=spreads,
            )
        )
    return pd.concat(frames, ignore_index=True)


def _trade_day(
    day: str,
    *,
    first_hour: int = 1,
    fill_hour: int | None = 2,
    extra_hours: list[int] | None = None,
    first_open: float = 2060.0,
    signal_close: float = 2060.0,
    fill_open: float = 2060.0,
    fill_high: float | None = None,
    fill_low: float | None = None,
    fill_close: float | None = None,
    last_close: float | None = None,
    include_hour16: bool = True,
    spreads: float = 0.0,
) -> pd.DataFrame:
    hours = [first_hour]
    if fill_hour is not None and fill_hour != first_hour:
        hours.append(fill_hour)
    if extra_hours:
        hours.extend(h for h in extra_hours if h not in hours)
    if include_hour16 and 16 not in hours:
        hours.append(16)
    hours = sorted(hours)

    n = len(hours)
    opens = [first_open] * n
    closes = [signal_close] * n
    highs = [max(first_open, signal_close) + 0.4] * n
    lows = [min(first_open, signal_close) - 0.4] * n

    if fill_hour is not None and fill_hour in hours:
        j = hours.index(fill_hour)
        fo = float(fill_open)
        opens[j] = fo
        closes[j] = fo if fill_close is None else float(fill_close)
        highs[j] = fo + 0.4 if fill_high is None else float(fill_high)
        lows[j] = fo - 0.4 if fill_low is None else float(fill_low)

    if include_hour16 and 16 in hours:
        j = hours.index(16)
        lc = signal_close if last_close is None else float(last_close)
        if fill_hour != 16:
            opens[j] = lc
            closes[j] = lc
            highs[j] = lc + 0.2
            lows[j] = lc - 0.2

    return _bars_day(
        day, hours, opens=opens, highs=highs, lows=lows, closes=closes, spreads=spreads
    )


def _run(df: pd.DataFrame, **kw):
    d = fam.prepare(df)
    log: list[dict] = []
    eq: list[float] = []
    m = fam.simulate(d, trade_log=log, equity_out=eq, **kw)
    return m, log, eq, d


def _expansion_frame(
    *,
    fade: str,
    sl_dist: float = 10.0,
    zero_sl: bool = False,
    trade_kwargs: dict | None = None,
    extra_days: list[pd.DataFrame] | None = None,
) -> pd.DataFrame:
    if fade == "up":
        closes = _expansion_closes(last_r=0.02)
    elif fade == "down":
        closes = _expansion_closes(last_r=-0.02)
    elif fade == "equal":
        closes = _expansion_closes(last_r=None)
    else:
        raise ValueError(fade)
    warm = _warmup_from_closes(closes, sl_dist=sl_dist, zero_sl=zero_sl)
    tday = _day_str(WARM_START, N_WARM)
    kw = dict(trade_kwargs or {})
    trade = _trade_day(tday, **kw)
    parts = [warm, trade]
    if extra_days:
        parts.extend(extra_days)
    return pd.concat(parts, ignore_index=True)


# --- charter / plugin -----------------------------------------------------------------


def test_charter_sha_and_screen_fail_closed():
    assert validate_charter_file(CHARTER) == []
    assert hashlib.sha256(CHARTER.read_bytes()).hexdigest() == CHARTER_SHA
    ok, why = is_charter_runnable(CHARTER)
    assert ok is False and "SCREEN_FAIL" in why


def test_grid_cardinality_exactly_one():
    g = fam.build_grid()
    assert len(g) == 1
    assert len(fam.grid(max_n=500, seed=0)) == 1
    assert g[0]["flat_hour"] == 16
    assert g[0]["short_n"] == 5
    assert g[0]["long_n"] == 20
    assert g[0]["expansion_ratio"] == 1.5
    assert g[0]["rr"] == 2
    assert "box_hours" not in g[0]
    assert "hunt_hours" not in g[0]


def test_load_family_builtin():
    from xau_family_null_maxstat import load_family

    p = load_family("multi_day_variance_expansion_flat")
    assert p.name == "multi_day_variance_expansion_flat"
    assert p.kill_label == "KILL_MULTI_DAY_VARIANCE_EXPANSION_FLAT"
    assert len(p.grid(max_n=10, seed=0)) == 1


# --- required fixtures -----------------------------------------------------------------


def test_expansion_true_fade_up_day_is_short():
    raw = _expansion_frame(fade="up")
    m, log, _, _ = _run(raw)
    assert m.n_trades == 1
    assert len(log) == 1
    assert log[0]["direction"] == -1


def test_expansion_true_fade_down_day_is_long():
    raw = _expansion_frame(fade="down")
    m, log, _, _ = _run(raw)
    assert m.n_trades == 1
    assert log[0]["direction"] == 1


def test_no_expansion_no_trade():
    warm = _warmup_from_closes(_quiet_closes(), sl_dist=10.0)
    trade = _trade_day(_day_str(WARM_START, N_WARM))
    m, log, _, _ = _run(pd.concat([warm, trade], ignore_index=True))
    assert log == []
    assert m.n_trades == 0


def test_equal_prior_closes_skip():
    raw = _expansion_frame(fade="equal")
    m, log, _, _ = _run(raw)
    assert log == []
    assert m.n_trades == 0


def test_zero_sl_distance_skip():
    raw = _expansion_frame(fade="up", zero_sl=True)
    m, log, _, _ = _run(raw)
    assert log == []
    assert m.n_trades == 0


def test_first_bar_only_second_signal_ignored():
    """Hour-3 would re-signal if first-bar-only / one-entry-per-day were dropped.

    First fill exits via TP so a later bar is flat again; still only one trade.
    """
    sl_dist = 10.0
    sig = 2060.0
    raw = _expansion_frame(
        fade="up",
        sl_dist=sl_dist,
        trade_kwargs={
            "first_hour": 1,
            "fill_hour": 2,
            "extra_hours": [3, 4],
            "signal_close": sig,
            "first_open": sig,
            "fill_open": sig,
            "fill_high": sig + sl_dist - 0.5,  # do not tag SL first
            "fill_low": sig - 2.0 * sl_dist - 0.5,  # TP
            "fill_close": sig - 2.0 * sl_dist,
        },
    )
    m, log, _, _ = _run(raw)
    assert m.n_trades == 1
    assert len(log) == 1
    assert log[0]["reason"] == "tp"


def test_hour16_fill_skipped():
    """First printed bar is hour 16 → next fill is missing or hour>16."""
    raw = _expansion_frame(
        fade="up",
        trade_kwargs={
            "first_hour": 16,
            "fill_hour": None,
            "include_hour16": True,
            "first_open": 2060.0,
            "signal_close": 2060.0,
            "last_close": 2060.0,
        },
    )
    m, log, _, _ = _run(raw)
    assert log == []
    assert m.n_trades == 0


def test_thin_n_below_40_is_screen_fail_not_waiver():
    ch = json.loads(CHARTER.read_text())
    assert ch["gates"]["thin_n_is_screen_fail"] is True
    assert ch["gates"]["soft"]["n_trades_min"] == 40
    warm = _warmup_from_closes(_quiet_closes())
    m, log, _, _ = _run(warm)
    assert m.n_trades < 40
    assert fam.soft_pass(m) is False
    raw = _expansion_frame(fade="up")
    m2, _, _, _ = _run(raw)
    assert m2.n_trades < 40
    assert fam.soft_pass(m2) is False


def test_two_trade_realized_balance_sizing():
    sl_dist = 12.6
    closes = _expansion_closes(last_r=0.02)
    c_tm1 = closes[-1]
    c_t = c_tm1 * math.exp(0.02)
    warm = _warmup_from_closes(closes, sl_dist=sl_dist)
    d1 = _day_str(WARM_START, N_WARM)
    d2 = _day_str(WARM_START, N_WARM + 1)
    sig1 = 2060.0
    day1 = _trade_day(
        d1,
        first_open=c_t - sl_dist,
        signal_close=sig1,
        fill_open=sig1,
        fill_high=sig1 + sl_dist - 0.5,
        fill_low=sig1 - 2.0 * sl_dist - 0.5,
        fill_close=sig1 - 2.0 * sl_dist,
        last_close=c_t,
    )
    sig2 = 2100.0
    day2 = _trade_day(
        d2,
        first_open=sig2,
        signal_close=sig2,
        fill_open=sig2,
        fill_high=sig2 + 0.3,
        fill_low=sig2 - 0.3,
        fill_close=sig2,
        last_close=sig2,
    )
    m, log, _, _ = _run(pd.concat([warm, day1, day2], ignore_index=True))
    assert m.n_trades == 2
    assert len(log) == 2
    assert log[1]["bal_at_entry"] == pytest.approx(log[0]["bal_after_exit"])


def test_entry_exit_equity_cost_timing():
    raw = _expansion_frame(
        fade="up",
        trade_kwargs={"spreads": 10.0, "signal_close": 2060.0, "fill_open": 2060.0},
    )
    m, log, eq, d = _run(raw)
    assert len(log) == 1
    t = log[0]
    assert t["trade_cost"] > 0
    assert t["pnl"] == pytest.approx(t["gross"] - t["trade_cost"])
    assert t["bal_at_entry"] == pytest.approx(START_BALANCE)
    assert len(eq) == len(d)


def test_entry_gap_open_beyond_sl_skipped():
    sl_dist = 10.0
    sig = 2060.0
    # fade-up → short; skip if fill open > signal_close + sl_dist
    raw = _expansion_frame(
        fade="up",
        sl_dist=sl_dist,
        trade_kwargs={
            "signal_close": sig,
            "fill_open": sig + sl_dist + 2.0,
            "fill_high": sig + sl_dist + 2.4,
            "fill_low": sig + sl_dist + 1.6,
            "fill_close": sig + sl_dist + 2.0,
        },
    )
    m, log, _, _ = _run(raw)
    assert log == []
    assert m.n_trades == 0


def test_entry_gap_open_beyond_tp_skipped():
    sl_dist = 10.0
    sig = 2060.0
    # fade-up → short; skip if fill open < signal_close - 2*sl_dist
    raw = _expansion_frame(
        fade="up",
        sl_dist=sl_dist,
        trade_kwargs={
            "signal_close": sig,
            "fill_open": sig - 2.0 * sl_dist - 2.0,
            "fill_high": sig - 2.0 * sl_dist - 1.6,
            "fill_low": sig - 2.0 * sl_dist - 2.4,
            "fill_close": sig - 2.0 * sl_dist - 2.0,
        },
    )
    m, log, _, _ = _run(raw)
    assert log == []
    assert m.n_trades == 0


def test_asia_box_candidate_not_implemented():
    assert fam.REJECTED_SISTER == "asia_box_london_sweep_fade_flat"
    assert not hasattr(fam, "BOX_HOURS")
    assert not hasattr(fam, "HUNT_HOURS")
    assert "box_hours" not in fam.build_grid()[0]
    src = Path(fam.__file__).read_text()
    assert "xau_family_asia_box" not in src
    assert "import xau_family_asia_box_london_sweep_fade_flat" not in src

    # Asia-box-looking day after quiet (no expansion) warmup must not trade.
    warm = _warmup_from_closes(_quiet_closes())
    day = _day_str(WARM_START, N_WARM)
    hours = list(range(1, 14)) + [16]
    mid = 2000.0
    box_low, box_high = 1990.0, 2010.0
    opens = [mid] * len(hours)
    highs = [mid + 0.8] * len(hours)
    lows = [mid - 0.8] * len(hours)
    closes = [mid] * len(hours)
    highs[0] = box_high
    lows[6] = box_low
    # Pierce-reclaim at hour 10 (asia-box hunt geometry)
    j = hours.index(10)
    lows[j] = box_low - 2.0
    closes[j] = box_low + 1.0
    opens[j] = mid
    asia_looking = _bars_day(day, hours, opens=opens, highs=highs, lows=lows, closes=closes)
    m, log, _, _ = _run(pd.concat([warm, asia_looking], ignore_index=True))
    assert log == []
    assert m.n_trades == 0
