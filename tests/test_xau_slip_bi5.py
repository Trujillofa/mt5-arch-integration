"""bi5 unpack + fill-vs-quote slip sign. No network."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from xau_slip_bi5 import (  # noqa: E402
    DealFill,
    dukascopy_tick_utc_from_raw_url,
    merge_asof_slip,
    pack_bi5_records,
    slip_points,
    unpack_bi5,
)


def test_unpack_keeps_bid_ask():
    url = "https://www.dukascopy.com/datafeed/XAUUSD/2026/07/18/13h_ticks.bi5"
    # 100 ms into the hour; ask 4668.110, bid 4668.100 (point 1000)
    payload = pack_bi5_records([(100, 4_668_110, 4_668_100, 1.5, 1.2)])
    rows = unpack_bi5(payload, url)
    assert len(rows) == 1
    assert rows[0]["ask"] == 4668.110
    assert rows[0]["bid"] == 4668.100
    assert rows[0]["time"] == datetime(2026, 8, 18, 13, 0, 0, 100_000, tzinfo=UTC)


def test_url_month_is_zero_based():
    url = "https://www.dukascopy.com/datafeed/XAUUSD/2026/00/01/00h_ticks.bi5"
    t = dukascopy_tick_utc_from_raw_url(url, 0)
    assert t == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


def test_buy_fill_above_ask_is_positive_slip():
    # buy paid 2 points above ask
    assert slip_points("buy", 4668.13, bid=4668.10, ask=4668.11) == pytest.approx(2.0)


def test_sell_fill_below_bid_is_positive_slip():
    assert slip_points("sell", 4668.08, bid=4668.10, ask=4668.11) == pytest.approx(2.0)


def test_merge_asof_backward_ignores_future_tick():
    t0 = datetime(2026, 8, 24, 14, 26, 8, tzinfo=UTC)
    ticks = pd.DataFrame(
        [
            {"time": t0 - timedelta(seconds=1), "bid": 4668.10, "ask": 4668.11},
            {"time": t0 + timedelta(seconds=5), "bid": 4670.00, "ask": 4670.50},
        ]
    )
    deals = [
        DealFill(
            broker="fpmarkets",
            symbol="XAUUSD.r",
            side="buy",
            entry="in",
            fill=4668.13,
            utc=t0,
            deal_id=1,
            volume=0.01,
        )
    ]
    m = merge_asof_slip(ticks, deals, max_age_sec=2.0)
    assert len(m) == 1
    assert bool(m.iloc[0]["usable"]) is True
    assert float(m.iloc[0]["slip_points"]) == pytest.approx(2.0)
    assert float(m.iloc[0]["ask"]) == 4668.11


def test_stale_tick_not_usable():
    t0 = datetime(2026, 8, 24, 14, 26, 8, tzinfo=UTC)
    ticks = pd.DataFrame(
        [{"time": t0 - timedelta(seconds=30), "bid": 4668.10, "ask": 4668.11}]
    )
    deals = [
        DealFill(
            broker="vantage",
            symbol="XAUUSD",
            side="sell",
            entry="out",
            fill=4668.08,
            utc=t0,
            deal_id=2,
            volume=0.1,
        )
    ]
    m = merge_asof_slip(ticks, deals, max_age_sec=2.0)
    assert bool(m.iloc[0]["usable"]) is False
