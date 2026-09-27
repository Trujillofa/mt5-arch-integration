"""Fast check that the null max-stat baseline replay resolves ``_SAVED``.

Does not load the H1 tape and does not run the search grid or any null trial.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import xau_null_maxstat as null_maxstat  # noqa: E402

from backtest import Metrics  # noqa: E402

PARAMS_FILE = ROOT / "strategy_params.json"


def test_replay_shipped_baseline_resolves_saved(monkeypatch):
    saved = json.loads(PARAMS_FILE.read_text())
    assert null_maxstat._SAVED["params"] == saved["params"]
    assert "_SAVED" in inspect.getsource(null_maxstat.replay_shipped_baseline)
    assert "replay_shipped_baseline" in inspect.getsource(null_maxstat.main)

    sentinel = json.loads(json.dumps(saved))
    sentinel["params"] = dict(saved["params"])
    sentinel["params"]["rsi_buy"] = 31.0
    monkeypatch.setattr(null_maxstat, "_SAVED", sentinel)

    captured: dict = {}

    def fake_simulate(_d, **kw):
        captured.update(kw)
        return Metrics(
            net_profit=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            max_drawdown_pct=0.0,
            n_trades=0,
            wins=0,
            losses=0,
        )

    monkeypatch.setattr(null_maxstat, "simulate", fake_simulate)
    out = null_maxstat.replay_shipped_baseline(None)
    assert captured["rsi_buy"] == 31.0
    assert captured["hours"] == tuple(saved["params"]["hours"])
    assert out["params"]["rsi_buy"] == 31.0
    assert out["params"]["hours"] == list(saved["params"]["hours"])
    assert out["n_trades"] == 0
    assert out["passes"] is False
