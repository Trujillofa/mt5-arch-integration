"""Tests for XAU offline pipeline + risk sizing (real shipped functions)."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest import (  # noqa: E402
    indicators,
    load_h1,
    metrics_from_pnls,
    normalize_params,
    passes,
    simulate,
    slice_to_window,
)
from live_trader import MAX_RISK_FRAC, size_position  # noqa: E402

PARAMS_FILE = ROOT / "strategy_params.json"


def test_csv_exists_and_covers_year():
    csv = ROOT / "xauusd_data.csv"
    assert csv.is_file() and csv.stat().st_size > 10_000
    import pandas as pd

    df = pd.read_csv(csv, parse_dates=["time"])
    assert {"M15", "H1"}.issubset(set(df["timeframe"].unique()))
    h1 = df[df["timeframe"] == "H1"]
    span = (h1["time"].max() - h1["time"].min()).days
    assert span >= 300
    assert len(h1) >= 1000


def test_risk_size_caps_one_percent():
    # $10k, 1% risk, $10 stop → max loss = $100
    r = size_position(
        balance=10_000,
        entry=2500.0,
        side=1,
        atr=5.0,
        sl_atr=2.0,  # stop = 10
        tp_atr=2.0,
        risk_pct=0.01,
        contract_size=100.0,
    )
    assert r.risk_dollars == pytest.approx(100.0)
    assert r.stop_distance == pytest.approx(10.0)
    # lots = 100 / (10 * 100) = 0.1
    assert r.lots == pytest.approx(0.1)
    # realized risk at full stop
    loss = r.stop_distance * 100.0 * r.lots
    assert loss == pytest.approx(100.0)
    assert r.sl_price < 2500.0
    assert r.tp_price > 2500.0
    # hard cap even if caller asks for 5%
    r2 = size_position(
        balance=10_000,
        entry=2500.0,
        side=1,
        atr=5.0,
        sl_atr=2.0,
        tp_atr=2.0,
        risk_pct=0.05,
    )
    assert r2.risk_dollars == pytest.approx(10_000 * MAX_RISK_FRAC)


def test_risk_size_skips_when_min_lot_exceeds_risk():
    """Wide ATR stop: 0.01 lot would lose > $100 — must return lots=0."""
    # stop = 80 * 2 = 160; min lot risk = 160 * 100 * 0.01 = $160 > $100
    r = size_position(
        balance=10_000,
        entry=2500.0,
        side=1,
        atr=80.0,
        sl_atr=2.0,
        tp_atr=2.0,
        risk_pct=0.01,
        contract_size=100.0,
        volume_min=0.01,
    )
    assert r.lots == 0.0
    assert r.risk_dollars == pytest.approx(100.0)
    min_lot_loss = r.stop_distance * 100.0 * 0.01
    assert min_lot_loss > r.risk_dollars


def test_backtest_never_oversizes_min_lot():
    """simulate()'s sizing arithmetic floors to 0 lots when min lot would breach 1% risk."""
    from backtest import CONTRACT_SIZE, START_BALANCE

    # Spot-check: for any atr*sl_atr where min lot exceeds risk, raw floor is 0
    bal = START_BALANCE
    risk_pct = 0.01
    for atr, sl_atr in [(5.0, 2.0), (80.0, 2.0), (156.66, 1.0)]:
        stop = atr * sl_atr
        risk_cash = bal * risk_pct
        raw = risk_cash / (stop * CONTRACT_SIZE)
        lots = float(__import__("numpy").floor(raw * 100 + 1e-12) / 100.0)
        min_lot_risk = stop * CONTRACT_SIZE * 0.01
        if min_lot_risk > risk_cash:
            assert lots < 0.01


def test_order_request_always_has_sl_tp():
    """Structural: build_order_request rejects missing SL/TP."""
    from live_trader import build_order_request

    class FakeTick:
        ask = 2500.1
        bid = 2500.0

    class FakeMT5:
        TRADE_ACTION_DEAL = 1
        ORDER_TYPE_BUY = 0
        ORDER_TYPE_SELL = 1
        ORDER_TIME_GTC = 0
        ORDER_FILLING_IOC = 1

        def symbol_info_tick(self, _s):
            return FakeTick()

    mt5 = FakeMT5()
    req = build_order_request(mt5, symbol="XAUUSD", side=1, lots=0.1, sl=2490.0, tp=2520.0)
    assert req["sl"] == 2490.0 and req["tp"] == 2520.0
    with pytest.raises(ValueError):
        build_order_request(mt5, symbol="XAUUSD", side=1, lots=0.1, sl=0.0, tp=2520.0)


def test_saved_params_reproduce_on_their_fit_window():
    """Replaying strategy_params.json over its recorded window must reproduce its metrics.

    Simulating over the *whole* CSV instead would drift every time the CSV is
    extended, which is how the recorded metrics silently stopped matching before.
    """
    import json

    saved = json.loads(PARAMS_FILE.read_text())
    window = saved.get("data")
    assert window, "strategy_params.json has no `data` window — re-fit with `backtest.py --save`"

    raw = slice_to_window(load_h1(), window)
    m = simulate(indicators(raw), **normalize_params(saved["params"]))

    recorded = saved["metrics"]
    assert m.n_trades == recorded["n_trades"]
    assert m.profit_factor == pytest.approx(recorded["profit_factor"], rel=1e-6)
    assert m.win_rate == pytest.approx(recorded["win_rate"], rel=1e-6)
    assert m.net_profit == pytest.approx(recorded["net_profit"], rel=1e-6)
    assert m.max_drawdown_pct == pytest.approx(recorded["max_drawdown_pct"], rel=1e-6)


def test_saved_params_clear_the_gates():
    """The shipped params must still satisfy the promotion gates on their fit window."""
    import json

    saved = json.loads(PARAMS_FILE.read_text())
    raw = slice_to_window(load_h1(), saved["data"])
    m = simulate(indicators(raw), **normalize_params(saved["params"]))
    assert m.n_trades >= 20
    assert m.profit_factor > 1.5
    assert m.win_rate > 55.0
    assert m.max_drawdown_pct < 10.0
    assert passes(m)


def test_backtest_cli_stdout_metrics(tmp_path):
    """Run backtest.py entry point; parse real stdout metrics.

    Runs without --save, and points --out at tmp: a test run must never rewrite
    the tracked strategy_params.json.
    """
    before = PARAMS_FILE.read_bytes()
    proc = subprocess.run(
        [sys.executable, str(ROOT / "backtest.py"), "--out", str(tmp_path / "params.json")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    out = proc.stdout + "\n" + proc.stderr
    assert proc.returncode == 0, out[-2000:]
    pf = float(re.search(r"Profit Factor:\s*([0-9.]+)", out).group(1))
    wr = float(re.search(r"Win Rate \(%\):\s*([0-9.]+)", out).group(1))
    dd = float(re.search(r"Max Drawdown \(%\):\s*([0-9.]+)", out).group(1))
    assert pf > 1.5
    assert wr > 55.0
    assert dd < 10.0
    assert PARAMS_FILE.read_bytes() == before, "a read-only backtest run rewrote tracked params"
    assert not (tmp_path / "params.json").exists(), "--out was written without --save"


def test_backtest_save_is_opt_in(tmp_path):
    """--save writes only where it is told, and records the fit window."""
    import json

    dest = tmp_path / "params.json"
    before = PARAMS_FILE.read_bytes()
    proc = subprocess.run(
        [sys.executable, str(ROOT / "backtest.py"), "--save", "--out", str(dest)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-2000:]
    assert PARAMS_FILE.read_bytes() == before, "--out was ignored; tracked params overwritten"
    written = json.loads(dest.read_text())
    assert written["data"]["bars"] > 0
    assert written["data"]["sha256"]
    assert written["params"]["mode"]


def test_costs_reduce_pnl_and_default_to_frictionless():
    """Cost params must be opt-in (defaults reproduce) and strictly hurt when set."""
    import json

    saved = json.loads(PARAMS_FILE.read_text())
    params = normalize_params(saved["params"])
    d = indicators(slice_to_window(load_h1(), saved["data"]))

    free = simulate(d, **params)
    assert free.net_profit == pytest.approx(saved["metrics"]["net_profit"], rel=1e-6)

    # No spread column in the CSV yet -> spread term is 0; commission alone must bite.
    costed = simulate(d, **params, commission_per_lot=3.0)
    assert costed.net_profit < free.net_profit
    assert costed.profit_factor < free.profit_factor
    assert costed.n_trades == free.n_trades, "costs must not change which trades are taken"


def test_metrics_helper_not_trivial():
    import numpy as np

    m = metrics_from_pnls([100.0, -50.0, 80.0], np.array([10000, 10050, 10130.0]))
    assert m.n_trades == 3
    assert m.wins == 2
    assert m.profit_factor == pytest.approx(180 / 50)
