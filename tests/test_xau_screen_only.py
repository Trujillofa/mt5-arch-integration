"""E2E: --screen-only never burns nulls even with positive primary passers."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

CHARTER_V2 = (
    ROOT / "results/xau_charters/2026-08-10_early_server_range_break_flat_v2.json"
)


def _synthetic_h1(n_days: int = 5) -> pd.DataFrame:
    rows = []
    px = 2000.0
    for d in range(n_days):
        day = f"2024-03-{1 + d:02d}"
        for h in range(1, 23):
            px += 0.1
            rows.append(
                {
                    "time": pd.Timestamp(f"{day} {h:02d}:00:00", tz="UTC"),
                    "open": px,
                    "high": px + 1.0,
                    "low": px - 1.0,
                    "close": px,
                    "spread": 10.0,
                    "timeframe": "H1",
                    "symbol": "XAUUSD",
                }
            )
    return pd.DataFrame(rows)


def test_screen_only_requires_strict_charter():
    import xau_family_null_maxstat as harness

    with pytest.raises(SystemExit, match="strict-charter"):
        harness.main(
            [
                "--family",
                "early_server_range_break_flat",
                "--charter",
                str(CHARTER_V2),
                "--screen-only",
            ]
        )


def test_screen_only_positive_passers_never_calls_null_trial(
    tmp_path: Path, monkeypatch
):
    """Positive passers under --screen-only must not invoke _null_trial or seal null."""
    import xau_charter_protocol as chp
    import xau_family_null_maxstat as harness

    out = tmp_path / "screen_only_out"
    out.mkdir()
    null_calls: list[int] = []

    def boom_null(*_a, **_k):
        null_calls.append(1)
        raise AssertionError("_null_trial must not run under --screen-only")

    monkeypatch.setattr(harness, "_null_trial", boom_null)
    monkeypatch.setattr(harness, "load_h1", _synthetic_h1)
    monkeypatch.setattr(
        harness,
        "develop_only",
        lambda raw, cutoff: raw,  # use all synthetic bars
    )
    monkeypatch.setattr(chp, "assert_clean_dispositional_tree", lambda: {"clean": True})
    monkeypatch.setattr(
        chp,
        "assert_charter_path_for_sealed",
        lambda p: {"path": str(p), "matches_head": True},
    )
    # harness imports assert_* into its namespace at module load
    monkeypatch.setattr(
        harness, "assert_clean_dispositional_tree", lambda: {"clean": True}
    )
    monkeypatch.setattr(
        harness,
        "assert_charter_path_for_sealed",
        lambda p: {"path": str(p), "matches_head": True},
    )
    # build_provenance also calls assert_clean_dispositional_tree via protocol module

    def fake_score_grid(*_a, **_k):
        return {
            "n_configs": 1,
            "min_trades_gate": 20,
            "elapsed_s": 0.01,
            "best_by_pf": {
                "index": 0,
                "params": {},
                "profit_factor": 1.5,
                "net_profit": 100.0,
                "win_rate": 60.0,
                "max_drawdown_pct": 5.0,
                "n_trades": 30,
                "expectancy": 3.0,
                "passes_classic": True,
                "passes_soft": True,
            },
            "best_by_pf_min_trades": {
                "index": 0,
                "params": {},
                "profit_factor": 1.5,
                "net_profit": 100.0,
                "win_rate": 60.0,
                "max_drawdown_pct": 5.0,
                "n_trades": 30,
                "expectancy": 3.0,
                "passes_classic": True,
                "passes_soft": True,
            },
            "best_soft_passer": {
                "index": 0,
                "params": {},
                "profit_factor": 1.5,
                "net_profit": 100.0,
                "win_rate": 60.0,
                "max_drawdown_pct": 5.0,
                "n_trades": 30,
                "expectancy": 3.0,
                "passes_classic": True,
                "passes_soft": True,
            },
            "n_passers_classic": 2,
            "n_passers_soft": 5,
            "n_with_min_trades": 1,
            "pf": {
                "max_raw": 1.5,
                "max_min_trades": 1.5,
                "p50": 1.2,
                "p90": 1.4,
                "p99": 1.5,
                "mean": 1.2,
            },
            "net_profit": {
                "max_raw": 100.0,
                "max_min_trades": 100.0,
                "p50": 50.0,
                "mean": 50.0,
            },
            "top20_by_pf_min_trades": [],
            "max_pf": 1.5,
            "max_net": 100.0,
            "max_pf_raw": 1.5,
        }

    monkeypatch.setattr(harness, "score_grid", fake_score_grid)
    # If ProcessPoolExecutor were used, fail loudly
    monkeypatch.setattr(
        harness,
        "ProcessPoolExecutor",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("ProcessPoolExecutor must not start under --screen-only")
        ),
    )

    rc = harness.main(
        [
            "--family",
            "early_server_range_break_flat",
            "--charter",
            str(CHARTER_V2),
            "--strict-charter",
            "--screen-only",
            "--out-dir",
            str(out),
            "--workers",
            "1",
            "--n-null",
            "999",  # should be ignored for execution
        ]
    )
    assert rc == 0
    # boom_null would have raised; also assert no accidental recording
    assert null_calls == []

    report = json.loads((out / "null_maxstat.json").read_text())
    assert report["verdict"]["disposition"] == "SCREEN_PASS_PENDING_NULL_REVIEW"
    assert report["verdict"]["screen_status"] == "PASSERS_GE_1_PENDING_NULL_REVIEW"
    assert report["screen"]["screen_only"] is True
    assert report["real"]["n_passers"] == 5
    assert report["null"]["n_null_planned"] == 999
    assert report["null"]["n_null_executed"] == 0
    assert report["null"]["n_trials"] == 0
    assert report["null"]["trials"] == []
    assert report["null"]["skipped_reason"] == "SCREEN_ONLY"
    assert report["null"]["p_max_pf"] is None
    assert report["null"]["p_max_pf_status"] == "not_evaluated"
    acct = report["attempt_accounting"]
    assert acct["attempt_type"] == "SCREEN_ONLY"
    assert acct["family_screen_attempt"] is True
    assert acct["sealed_null_attempt"] is False
    assert acct["n_null_executed"] == 0
    assert acct["null_trials_executed"] == 0
    assert acct["r1_style_null_burned"] is False
    assert acct.get("r1_burned") is False
    assert report["provenance"]["n_null"] == 0
    assert report["provenance"]["n_null_executed"] == 0
    assert report["provenance"]["n_null_planned"] == 999
    assert report["provenance"].get("sealed_null_attempt") is False


def test_screen_only_zero_passers_still_screen_fail(tmp_path: Path, monkeypatch):
    import xau_charter_protocol as chp
    import xau_family_null_maxstat as harness

    out = tmp_path / "screen_zero"
    out.mkdir()
    null_calls: list[int] = []

    def boom_null(*_a, **_k):
        null_calls.append(1)
        raise AssertionError("_null_trial must not run")

    monkeypatch.setattr(harness, "_null_trial", boom_null)
    monkeypatch.setattr(harness, "load_h1", _synthetic_h1)
    monkeypatch.setattr(harness, "develop_only", lambda raw, cutoff: raw)
    monkeypatch.setattr(
        harness, "assert_clean_dispositional_tree", lambda: {"clean": True}
    )
    monkeypatch.setattr(
        harness,
        "assert_charter_path_for_sealed",
        lambda p: {"path": str(p), "matches_head": True},
    )
    # build_provenance(require_clean_tree=True) calls protocol assert directly
    monkeypatch.setattr(chp, "assert_clean_dispositional_tree", lambda: {"clean": True})

    def fake_score_grid(*_a, **_k):
        base = {
            "index": 0,
            "params": {},
            "profit_factor": 0.8,
            "net_profit": -10.0,
            "win_rate": 40.0,
            "max_drawdown_pct": 20.0,
            "n_trades": 30,
            "expectancy": -1.0,
            "passes_classic": False,
            "passes_soft": False,
        }
        return {
            "n_configs": 1,
            "min_trades_gate": 20,
            "elapsed_s": 0.01,
            "best_by_pf": base,
            "best_by_pf_min_trades": base,
            "best_soft_passer": None,
            "n_passers_classic": 0,
            "n_passers_soft": 0,
            "n_with_min_trades": 1,
            "pf": {
                "max_raw": 0.8,
                "max_min_trades": 0.8,
                "p50": 0.8,
                "p90": 0.8,
                "p99": 0.8,
                "mean": 0.8,
            },
            "net_profit": {
                "max_raw": -10.0,
                "max_min_trades": -10.0,
                "p50": -10.0,
                "mean": -10.0,
            },
            "top20_by_pf_min_trades": [],
            "max_pf": 0.8,
            "max_net": -10.0,
            "max_pf_raw": 0.8,
        }

    monkeypatch.setattr(harness, "score_grid", fake_score_grid)

    rc = harness.main(
        [
            "--family",
            "early_server_range_break_flat",
            "--charter",
            str(CHARTER_V2),
            "--strict-charter",
            "--screen-only",
            "--out-dir",
            str(out),
            "--workers",
            "1",
        ]
    )
    assert rc == 0
    assert null_calls == []
    report = json.loads((out / "null_maxstat.json").read_text())
    assert report["verdict"]["disposition"] == "SCREEN_FAIL"
    assert report["null"]["n_null_planned"] == 999
    assert report["null"]["n_null_executed"] == 0
    assert report["attempt_accounting"]["sealed_null_attempt"] is False
    assert report["attempt_accounting"]["r1_style_null_burned"] is False
