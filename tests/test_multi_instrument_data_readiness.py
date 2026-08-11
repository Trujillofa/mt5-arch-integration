"""Adversarial fail-closed tests for multi-instrument Phase-0 integrity v2."""
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
    assert df["time"].dt.tz is None


def test_spread_imputation_auditable():
    rows = _good_rows(n=4, spread=12)
    rows[1]["spread"] = 0
    rows[2]["spread"] = -1
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], format="%Y.%m.%d %H:%M")
    df["spread"] = pd.to_numeric(df["spread"])
    out, imp = b._apply_spread_imputation(df)
    assert int(out["spread_imputed"].sum()) == 2
    assert float(out.loc[1, "spread_raw_pts"]) == 0.0
    assert float(out.loc[1, "spread_effective_pts"]) == 12.0


def test_bad_ohlc_hard_fail_does_not_publish(tmp_path: Path):
    bridge = tmp_path / "bridge"
    out = tmp_path / "out"
    bridge.mkdir()
    out.mkdir()
    rows = _good_rows()
    rows[0]["high"] = 1.0
    _write_history(bridge / "history_EURUSD.csv", rows)
    _meta(bridge / "symbol_meta_EURUSD.csv")
    m, dev = b.build_symbol(
        "EURUSD",
        bridge_dir=bridge,
        costs={"login": 1, "server": "S", "broker": "V", "account_type": "STANDARD_STP"},
        export_run={"run_id": "a" * 32, "login": 1, "server": "S", "files": {}},
        holdout_start=b.DEVELOP_END_SERVER,
        out_dir=out,
        publish=True,
    )
    assert m.status == "FAIL"
    assert m.published is False
    assert not (out / "eurusd_h1.csv").exists()
    assert dev is None


def test_wrong_row_symbol_hard_fail(tmp_path: Path):
    bridge = tmp_path / "bridge"
    out = tmp_path / "out"
    bridge.mkdir()
    # File named EURUSD but rows are GBPUSD
    _write_history(bridge / "history_EURUSD.csv", _good_rows(symbol="GBPUSD"))
    _meta(bridge / "symbol_meta_EURUSD.csv", requested="EURUSD", resolved="EURUSD")
    m, _ = b.build_symbol(
        "EURUSD",
        bridge_dir=bridge,
        costs={},
        export_run={"run_id": "a" * 32, "login": 1, "server": "S"},
        holdout_start=b.DEVELOP_END_SERVER,
        out_dir=out,
        publish=True,
    )
    assert m.status == "FAIL"
    assert any("ROW_SYMBOL" in e for e in m.hard_errors)
    assert not (out / "eurusd_h1.csv").exists()


def test_half_hour_timestamps_fail(tmp_path: Path):
    bridge = tmp_path / "bridge"
    out = tmp_path / "out"
    bridge.mkdir()
    rows = _good_rows()
    for r in rows:
        r["time"] = r["time"].replace(":00", ":30")
    _write_history(bridge / "history_EURUSD.csv", rows)
    _meta(bridge / "symbol_meta_EURUSD.csv")
    m, _ = b.build_symbol(
        "EURUSD",
        bridge_dir=bridge,
        costs={},
        export_run={"run_id": "a" * 32},
        holdout_start=b.DEVELOP_END_SERVER,
        out_dir=out,
        publish=True,
    )
    assert m.status == "FAIL"
    assert any("H1_NOT_HOUR_ALIGNED" in e for e in m.hard_errors)


def test_missing_meta_is_hard_fail(tmp_path: Path):
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    _write_history(bridge / "history_EURUSD.csv", _good_rows())
    m, _ = b.build_symbol(
        "EURUSD",
        bridge_dir=bridge,
        costs={},
        export_run={"run_id": "a" * 32},
        holdout_start=b.DEVELOP_END_SERVER,
        out_dir=tmp_path / "out",
        publish=True,
    )
    assert m.status == "FAIL"
    assert any("MISSING_SYMBOL_META" in e for e in m.hard_errors)


def test_export_run_rejects_fake_hashes(tmp_path: Path):
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    # create real files
    p = bridge / "history_XAUUSD.csv"
    _write_history(p, _good_rows("XAUUSD"))
    _meta(bridge / "symbol_meta_XAUUSD.csv", requested="XAUUSD", resolved="XAUUSD")
    for s in ("EURUSD", "GBPUSD"):
        _write_history(bridge / f"history_{s}.csv", _good_rows(s))
        _meta(bridge / f"symbol_meta_{s}.csv", requested=s, resolved=s)

    fake = {
        "run_id": "",
        "login": 1,
        "server": "S",
        "export_started_utc": "not-a-date",
        "export_finished_utc": "also-bad",
        "wine_exit_code": 99,
        "timeframes": "M15",
        "symbols": ["FOO"],
        "files": {
            "history_XAUUSD": {
                "path": str(p),
                "sha256": "0" * 64,
                "bytes": 1,
                "mtime_unix": 0,
            }
        },
    }
    errs = b.verify_export_run(fake, {"login": 1, "server": "S"}, bridge_dir=bridge, export_complete=None)
    assert any("INVALID_RUN_ID" in e for e in errs)
    assert any("WINE_EXIT_NOT_ACCEPTED" in e for e in errs)
    assert any("EXPORT_RUN_SHA_MISMATCH" in e or "EXPORT_RUN_SIZE" in e for e in errs)
    assert any("MISSING_EXPORT_COMPLETE" in e for e in errs)


def test_common_window_requires_exact_relationships():
    fx_times = pd.date_range("2024-01-01", periods=20, freq="h")
    xau_times = fx_times[::2]
    develops = {
        "EURUSD": pd.DataFrame({"time": fx_times}),
        "GBPUSD": pd.DataFrame({"time": fx_times}),
        "XAUUSD": pd.DataFrame({"time": xau_times}),
    }
    old = b.MIN_DEVELOP_BARS
    b.MIN_DEVELOP_BARS = 5
    try:
        c = b.common_window(develops)
        assert c["status"] == "OK"
        assert c["intersection_equals_xau_count"] is True
    finally:
        b.MIN_DEVELOP_BARS = old


def test_repo_artifacts_not_touched_by_unit_tests(tmp_path: Path):
    """Regression: build_symbol must not write into repo OUT_DIR during tests."""
    eurusd = ROOT / "results/instrument_data/eurusd_h1.csv"
    before = eurusd.read_bytes() if eurusd.is_file() else None
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    rows = _good_rows()
    rows[0]["high"] = 0.5
    _write_history(bridge / "history_EURUSD.csv", rows)
    _meta(bridge / "symbol_meta_EURUSD.csv")
    b.build_symbol(
        "EURUSD",
        bridge_dir=bridge,
        costs={},
        export_run={"run_id": "a" * 32},
        holdout_start=b.DEVELOP_END_SERVER,
        out_dir=tmp_path / "isolated",
        publish=True,
    )
    after = eurusd.read_bytes() if eurusd.is_file() else None
    assert before == after


def test_committed_artifact_lock_verification():
    """Committed research CSVs must match lock sha/count (catches test pollution)."""
    lock = b.ARTIFACT_LOCK
    if not lock.is_file():
        pytest.skip("artifact lock not yet built")
    errs = b.verify_committed_artifacts(lock)
    assert errs == [], errs
    # Each artifact must be full-history size, not unit-test fixtures
    data = json.loads(lock.read_text())
    for sym, ent in data["artifacts"].items():
        assert int(ent["n_rows_h1"]) >= 10_000, (sym, ent["n_rows_h1"])

