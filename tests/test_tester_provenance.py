"""Offline Strategy Tester provenance: schema, registry floor, no live tester."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from mt5_arch.tester_provenance import (
    ProvenanceError,
    build_provenance,
    record_tester_run,
    sha256_file,
    verify_provenance,
)

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "20-run-htf-fib-backtest-provenance.sh"
RUNNER = ROOT / "scripts" / "19-run-htf-fib-backtest.sh"
VERIFY = ROOT / "scripts" / "verify_tester_provenance.py"
MODULE = ROOT / "src" / "mt5_arch" / "tester_provenance.py"
OFFLINE = ROOT / "tests" / "fixtures" / "tester_provenance" / "offline_ok"


def _clone(tmp_path: Path) -> tuple[Path, dict]:
    raw = json.loads(OFFLINE.joinpath("provenance.json").read_text(encoding="utf-8"))
    dest = tmp_path / "provenance.json"
    dest.write_text(json.dumps(raw), encoding="utf-8")
    return dest, raw


def test_offline_synthetic_fixture():
    report = verify_provenance(OFFLINE)
    assert report["ok"] is True
    assert report["broker"] == "vantage"
    assert report["source"] == "synthetic"
    assert report["login"] == 84000001


def test_platform_layer_does_not_import_research():
    imports = [
        line
        for line in MODULE.read_text(encoding="utf-8").splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]
    joined = "\n".join(imports)
    assert "xau_" not in joined
    assert "backtest" not in joined
    assert "from mt5_arch.symbol_registry import" in joined
    assert "OrderSend" not in MODULE.read_text(encoding="utf-8")


def test_wrapper_calls_19_and_keeps_secrets_out():
    text = WRAPPER.read_text(encoding="utf-8")
    assert "19-run-htf-fib-backtest.sh" in text
    assert "provenance.json" in text
    assert "MT5_BROKER" in text
    assert "InpBroker" in text
    assert "KILL_EXISTING" in text
    assert "SKIP_TESTER" in text
    assert "OrderSend" not in text
    assert RUNNER.is_file()
    # Password may be named only as a forbidden write; never interpolated into JSON.
    assert "MT5_PASSWORD" in text
    assert "Does not write MT5_PASSWORD" in text


def test_wrapper_refuses_empty_broker():
    env = os.environ.copy()
    env["MT5_BROKER"] = ""
    env["BROKER"] = ""
    env["InpBroker"] = ""
    env["SKIP_TESTER"] = "1"
    proc = subprocess.run(
        [str(WRAPPER), "XAUUSD", "H1", "2024.01.01", "2025.01.01"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "MT5_BROKER" in (proc.stderr + proc.stdout)


def test_wrapper_refuses_unresolved_symbol():
    env = os.environ.copy()
    env["MT5_BROKER"] = "wsf"
    env["BROKER"] = "wsf"
    env["SKIP_TESTER"] = "1"
    proc = subprocess.run(
        [str(WRAPPER), "XAUUSD", "H1", "2024.01.01", "2025.01.01"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    combined = proc.stderr + proc.stdout
    assert "no mapping" in combined or "unresolved" in combined.lower() or "XAUUSD" in combined


def test_missing_hash_refuses(tmp_path: Path):
    dest, raw = _clone(tmp_path)
    del raw["hashes"]["ex5"]
    dest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProvenanceError, match="missing hash ex5"):
        verify_provenance(dest)


def test_login_zero_refuses(tmp_path: Path):
    dest, raw = _clone(tmp_path)
    raw["account"]["login"] = 0
    dest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProvenanceError, match="Login=0"):
        verify_provenance(dest)


def test_empty_broker_refuses(tmp_path: Path):
    dest, raw = _clone(tmp_path)
    raw["broker"] = ""
    dest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProvenanceError, match="empty broker"):
        verify_provenance(dest)


def test_unresolved_symbol_refuses(tmp_path: Path):
    dest, raw = _clone(tmp_path)
    raw["symbol"]["requested"] = "GOLD"
    raw["symbol"]["canonical"] = "GOLD"
    raw["symbol"]["broker_symbol"] = "GOLD"
    dest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProvenanceError, match="unresolved symbol"):
        verify_provenance(dest)


def test_mql5_export_missing_report_refuses(tmp_path: Path):
    dest, raw = _clone(tmp_path)
    raw["source"] = "mql5_export"
    raw["report_path"] = str(tmp_path / "missing_report.htm")
    dest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProvenanceError, match="report path does not exist"):
        verify_provenance(dest)


def test_secret_key_refuses(tmp_path: Path):
    dest, raw = _clone(tmp_path)
    raw["account"]["password"] = "nope"
    dest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProvenanceError, match="secret key"):
        verify_provenance(dest)


def test_build_and_verify_round_trip(tmp_path: Path):
    blobs = {
        "ini": b"[Tester]\r\nModel=1\r\n",
        "set": b"\xff\xfe" + "InpLots=0.01\r\n".encode("utf-16-le"),
        "mql5_expert": b"// expert\n",
        "mql5_include": b"// include\n",
        "ex5": b"EX5\x00",
    }
    paths = {}
    for name, data in blobs.items():
        p = tmp_path / name
        p.write_bytes(data)
        paths[name] = p
    report = tmp_path / "report.htm"
    report.write_text("<html>synthetic</html>\n", encoding="utf-8")
    out = tmp_path / "provenance.json"
    result = record_tester_run(
        out,
        source="mql5_export",
        broker="vantage",
        requested="XAUUSD",
        login=84000001,
        server="Synthetic-Demo",
        period="H1",
        model=1,
        from_date="2024.01.01",
        to_date="2025.01.01",
        report_path=report,
        ini_path=paths["ini"],
        set_path=paths["set"],
        mql5_expert_path=paths["mql5_expert"],
        mql5_include_path=paths["mql5_include"],
        ex5_path=paths["ex5"],
        history={
            "found": True,
            "path": str(tmp_path / "history"),
            "n_files": 1,
            "listing_sha256": "f" * 64,
            "note": "test",
        },
    )
    assert result["ok"] is True
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert "password" not in json.dumps(loaded).lower()
    assert loaded["hashes"]["ini"] == sha256_file(paths["ini"])
    assert loaded["symbol"]["broker_symbol"] == "XAUUSD"


def test_build_refuses_unmapped_broker_symbol():
    with pytest.raises(Exception, match="no mapping"):
        build_provenance(
            source="synthetic",
            broker="wsf",
            requested="XAUUSD",
            login=1,
            server="x",
            period="H1",
            model=1,
            from_date="2024.01.01",
            to_date="2025.01.01",
            report_path="report.htm",
            hashes=dict.fromkeys(("ini", "set", "mql5_expert", "mql5_include", "ex5"), "a" * 64),
        )


def test_verify_cli_default_fixture():
    proc = subprocess.run(
        ["python3", str(VERIFY)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "PASSED" in proc.stdout
