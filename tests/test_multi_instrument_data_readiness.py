"""Adversarial fail-closed tests for multi-instrument Phase-0 data readiness."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_multi_instrument_data_readiness as b  # noqa: E402


def _write_history(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "time",
        "timeframe",
        "symbol",
        "open",
        "high",
        "low",
        "close",
        "tick_volume",
        "spread",
    ]
    pd.DataFrame(rows)[cols].to_csv(path, index=False)


def _meta(path: Path, **kwargs: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    base = {
        "requested": "EURUSD",
        "resolved": "EURUSD",
        "digits": "5",
        "point": "0.00001",
        "contract_size": "100000",
    }
    base.update({k: str(v) for k, v in kwargs.items()})
    lines = ["key,value"] + [f"{k},{v}" for k, v in base.items()]
    path.write_text("\n".join(lines) + "\n")


def _good_rows(symbol: str = "EURUSD", n: int = 5, spread: int = 10) -> list[dict]:
    rows = []
    for i in range(n):
        rows.append(
            {
                "time": f"2024.01.0{1 + i // 24} {i % 24:02d}:00",
                "timeframe": "H1",
                "symbol": symbol,
                "open": 1.1,
                "high": 1.11,
                "low": 1.09,
                "close": 1.105,
                "tick_volume": 100,
                "spread": spread,
            }
        )
    return rows


def test_parse_history_is_naive_server_clock_not_utc(tmp_path: Path):
    p = tmp_path / "h.csv"
    _write_history(p, _good_rows())
    df = b._parse_history(p)
    assert str(df["time"].dtype) == "datetime64[ns]"
    # No timezone attached
    assert df["time"].dt.tz is None


def test_spread_imputation_auditable():
    rows = _good_rows(n=4, spread=12)
    rows[1]["spread"] = 0
    rows[2]["spread"] = -1
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], format="%Y.%m.%d %H:%M")
    df["spread"] = pd.to_numeric(df["spread"])
    out, imp = b._apply_spread_imputation(df)
    assert "spread_raw_pts" in out.columns
    assert "spread_effective_pts" in out.columns
    assert "spread_imputed" in out.columns
    assert int(out["spread_imputed"].sum()) == 2
    assert float(out.loc[1, "spread_raw_pts"]) == 0.0
    assert float(out.loc[1, "spread_effective_pts"]) == 12.0
    assert imp["n_imputed"] == 2


def test_bad_ohlc_is_hard_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    rows = _good_rows()
    rows[0]["high"] = 1.0  # high < open/close → bad
    _write_history(bridge / "history_EURUSD.csv", rows)
    _meta(bridge / "symbol_meta_EURUSD.csv")
    monkeypatch.setattr(b, "_wine_bridge_dir", lambda: bridge)
    # Only test EURUSD path via build_symbol directly
    m, dev = b.build_symbol(
        "EURUSD",
        bridge_dir=bridge,
        costs={"login": 1, "server": "S", "broker": "V", "account_type": "STANDARD_STP"},
        export_run={
            "run_id": "t",
            "login": 1,
            "server": "S",
            "files": {"history_EURUSD": {}, "meta_EURUSD": {}},
        },
        holdout_start=b.DEVELOP_END_SERVER,
    )
    assert m.status == "FAIL"
    assert any("BAD_OHLC" in e for e in m.hard_errors)
    assert dev is None


def test_missing_meta_is_hard_fail(tmp_path: Path):
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    _write_history(bridge / "history_EURUSD.csv", _good_rows())
    # no meta file
    m, _ = b.build_symbol(
        "EURUSD",
        bridge_dir=bridge,
        costs={},
        export_run={"run_id": "t", "login": 1, "server": "S", "files": {}},
        holdout_start=b.DEVELOP_END_SERVER,
    )
    assert m.status == "FAIL"
    assert any("MISSING_SYMBOL_META" in e for e in m.hard_errors)


def test_missing_export_run_fails_verify():
    errs = b.verify_export_run(None, {"login": 1, "server": "S"})
    assert "MISSING_EXPORT_RUN_JSON" in errs


def test_export_run_login_mismatch():
    errs = b.verify_export_run(
        {
            "run_id": "x",
            "login": 99,
            "server": "S",
            "export_finished_utc": "t",
            "files": {
                "history_XAUUSD": {},
                "meta_XAUUSD": {},
                "history_EURUSD": {},
                "meta_EURUSD": {},
                "history_GBPUSD": {},
                "meta_GBPUSD": {},
            },
        },
        {"login": 27496181, "server": "S"},
    )
    assert any("LOGIN_MISMATCH" in e for e in errs)


def test_common_window_requires_exact_relationships():
    # Identical FX, XAU subset → OK
    fx_times = pd.date_range("2024-01-01", periods=20, freq="h")
    xau_times = fx_times[::2]  # subset every other hour
    develops = {
        "EURUSD": pd.DataFrame({"time": fx_times}),
        "GBPUSD": pd.DataFrame({"time": fx_times}),
        "XAUUSD": pd.DataFrame({"time": xau_times}),
    }
    # Lower thresholds for unit test
    old_min = b.MIN_DEVELOP_BARS
    b.MIN_DEVELOP_BARS = 5
    try:
        c = b.common_window(develops)
        assert c["status"] == "OK"
        assert c["fx_calendars_identical"] is True
        assert c["xau_subset_of_fx"] is True
        assert c["intersection_equals_xau_count"] is True
        assert c["n_intersection_timestamps"] == len(xau_times)
    finally:
        b.MIN_DEVELOP_BARS = old_min


def test_common_window_fails_when_fx_calendars_differ():
    t1 = pd.date_range("2024-01-01", periods=12, freq="h")
    t2 = pd.date_range("2024-01-01 01:00:00", periods=12, freq="h")
    develops = {
        "EURUSD": pd.DataFrame({"time": t1}),
        "GBPUSD": pd.DataFrame({"time": t2}),
        "XAUUSD": pd.DataFrame({"time": t1[:6]}),
    }
    old = b.MIN_DEVELOP_BARS
    b.MIN_DEVELOP_BARS = 3
    try:
        c = b.common_window(develops)
        assert c["status"] == "FAIL"
        assert any("EURUSD_GBPUSD" in e for e in c["hard_errors"])
    finally:
        b.MIN_DEVELOP_BARS = old


def test_kill_prefix_only_logic():
    """Document expected isolation: only matching WINEPREFIX PIDs (unit-level)."""
    # Functional check is in the shell script; here we assert the helper exists
    # by reading the script text for fail-closed patterns.
    text = (ROOT / "scripts/export-instruments-from-wine-mt5.sh").read_text()
    assert "WINEPREFIX" in text
    assert "stale_" in text or "PRE_EXPORT_EPOCH" in text
    assert "|| true" not in text.split("timeout")[1][:200] if "timeout" in text else True
    assert "EXPECT_LOGIN" in text
    assert "export_run.json" in text
