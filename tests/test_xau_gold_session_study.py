"""Offline tests for the gold session study and its read-only MCP M1 fetcher.

Synthetic data only; no terminal, no MCP server.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_m1_official_mcp as fetch  # noqa: E402
import xau_gold_session_study as st  # noqa: E402


def _args(*extra: str):
    return st.build_parser().parse_args(["--csv", "unused", *extra])


def _minute_frame(start: str, end: str, seed: int = 0) -> pd.DataFrame:
    t = pd.date_range(start, end, freq="1min")
    t = t[t.dayofweek < 5]
    rng = np.random.default_rng(seed)
    p = 2600 + np.cumsum(rng.normal(0, 0.3, len(t)))
    c = p + rng.normal(0, 0.05, len(t))
    return pd.DataFrame({"server_time": pd.Series(t), "open": p,
                         "high": np.maximum(p, c) + 0.1, "low": np.minimum(p, c) - 0.1,
                         "close": c, "tickvol": 100, "spread": 20})


# ------------------------------------------------------------- trade engine
def _sim(side, entry, stop, target, bars, be=None):
    op, hi, lo, cl = (np.array(x, float) for x in zip(*bars, strict=True))
    return st.simulate(side, entry, stop, target, op, hi, lo, cl, np.zeros(len(op)), be)


def test_long_stop_gapped_through_fills_at_open():
    r, why, *_ = _sim(+1, 100.0, 99.0, 103.0, [(98.0, 98.5, 97.5, 98.2)])
    assert why == "stop"
    assert r == pytest.approx(-2.0)


def test_short_stop_gapped_through_fills_at_open():
    r, why, *_ = _sim(-1, 100.0, 101.0, 97.0, [(102.0, 102.5, 101.5, 102.2)])
    assert why == "stop"
    assert r == pytest.approx(-2.0)


def test_stop_checked_before_target_in_same_bar():
    r, why, *_ = _sim(+1, 100.0, 99.0, 102.0, [(100.0, 102.5, 98.5, 101.0)])
    assert (why, r) == ("stop", pytest.approx(-1.0))


def test_breakeven_moves_stop_after_trigger_bar():
    bars = [(100.0, 100.6, 99.8, 100.5), (100.4, 100.4, 99.9, 100.0)]
    r, why, *_ = _sim(+1, 100.0, 99.0, 103.0, bars, be=0.5)
    assert (why, r) == ("be", pytest.approx(0.0))


# --------------------------------------------------------------------- null
def test_null_paths_keep_drift_and_move_sizes():
    rng = np.random.default_rng(1)
    c = 100 + np.cumsum(rng.normal(0.01, 0.2, 300))
    mu = 0.01
    p = st.null_paths(100.0, c, 50, 30, rng, mu)
    real_dev = np.abs(np.diff(np.concatenate([[100.0], c])) - mu)
    null_dev = np.abs(np.diff(np.concatenate([np.zeros((50, 1)), p], axis=1), axis=1) - mu)
    assert np.allclose(null_dev, real_dev[None, :])


def test_null_block_flips_keep_consecutive_bars_together():
    rng = np.random.default_rng(2)
    c = 100 + np.cumsum(rng.normal(0, 0.2, 120))
    r = np.diff(np.concatenate([[100.0], c]))
    p = st.null_paths(100.0, c, 200, 30, rng)
    signs = np.diff(np.concatenate([np.zeros((200, 1)), p], axis=1), axis=1) / r
    same_as_next = np.isclose(signs[:, :-1], signs[:, 1:]).mean()
    assert same_as_next > 0.9  # only block edges (1 in 30) may change sign


def test_p_upper_is_never_zero():
    assert st.p_upper(10, np.zeros(99)) == pytest.approx(0.01)
    assert st.p_upper(0, np.zeros(99)) == pytest.approx(1.0)


def test_claim_needs_half_hour_edges():
    assert st.parse_claim("15:30-16:30@utc")[1] == [31, 32]
    with pytest.raises(SystemExit):
        st.parse_claim("15:10-16:30@utc")


def test_timing_p_values_not_extreme_on_random_walk():
    a = _args("--window", "all", "--n-null", "200")
    df = st.prepare(_minute_frame("2025-01-01", "2025-04-01"), a)
    days, stats = st.timing_study(df, a, np.random.default_rng(0))
    assert len(days) > 40
    _, rows = st.claim_test(stats, a.claim)
    assert rows[0]["p"] > 0.01
    assert st.best_window(stats, "utc", "all")[2] > 0.01


# ------------------------------------------------------------------- window
def test_develop_window_stops_before_holdout():
    df = _minute_frame("2025-12-22", "2026-01-10")
    dev = st.prepare(df, _args())
    hold = st.prepare(df, _args("--window", "holdout"))
    cut = st.holdout_start().tz_localize(None).normalize()
    dev_days = [d for d, _ in st.trading_days(dev, 700)]
    hold_days = [d for d, _ in st.trading_days(hold, 700)]
    assert dev_days and hold_days
    assert max(dev_days) < cut <= min(hold_days)


def test_zero_or_missing_spread_carries_last_known():
    df = _minute_frame("2025-03-03", "2025-03-04")
    df["spread"] = df["spread"].astype(float)
    df.loc[10, "spread"] = 0
    df.loc[11, "spread"] = np.nan
    out = st.prepare(df, _args("--window", "all"))
    assert (out["spread"] > 0).all()
    assert out["spread_filled"].sum() == 2


def test_server_tz_mismatch_warns(tmp_path, capsys):
    csv = tmp_path / "m1.csv"
    csv.write_text("")
    meta = {"server_utc_offset_h": 3.0, "fetched_at_utc": "2026-01-15T12:00:00+00:00"}
    Path(f"{csv}.meta.json").write_text(json.dumps(meta))
    st.check_server_tz(str(csv), "ny-close")  # January: NY-close is UTC+2
    assert "WARNING" in capsys.readouterr().out
    st.check_server_tz(str(csv), "fixed:+3")
    assert capsys.readouterr().out == ""


# ------------------------------------------------------------------ fetcher
def test_fetcher_refuses_trade_tools():
    client = fetch.McpReadOnlyClient(fetch.DEFAULT_URL, "t")
    for name in ("trade_send_market_order", "trade_close_single_position", "write_file"):
        with pytest.raises(PermissionError):
            client.call(name, {})


def test_fetcher_refuses_non_loopback_url():
    with pytest.raises(ValueError):
        fetch.McpReadOnlyClient("http://192.168.0.144:22346/mcp", "t")


def test_fetcher_writes_blank_for_missing_spread():
    bar = {"time": "2024.01.02 03:15:00", "open": 1, "high": 2, "low": 0.5,
           "close": 1.5, "tick_volume": 45}
    assert fetch.bar_line(bar).split("\t")[-1] == ""
    assert fetch.bar_line({**bar, "spread": 21}).split("\t")[-1] == "21"


def test_fetcher_parses_sse_and_offset():
    raw = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n\n'
    assert fetch.parse_rpc(raw)["id"] == 1
    info = {"utc_time": "2026-09-24T20:32:16Z",
            "trade_server_last_known_time": "2026-09-24T23:32:37"}
    assert fetch.server_offset_hours(info) == 3.0


def test_csv_round_trip_through_study_loader(tmp_path):
    bars = [{"time": f"2025.03.03 10:0{i}:00", "open": 1.0 + i, "high": 2.0 + i,
             "low": 0.5 + i, "close": 1.5 + i, "tick_volume": 10} for i in range(3)]
    bars[1]["spread"] = 20
    path = tmp_path / "m1.csv"
    path.write_text("\n".join([fetch.HEADER, *map(fetch.bar_line, bars)]) + "\n")
    df = st.load_csv(str(path), default_spread=30)
    assert list(df["close"]) == [1.5, 2.5, 3.5]
    assert df["spread"].isna().sum() == 2
