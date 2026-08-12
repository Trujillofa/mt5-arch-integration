"""Adversarial fail-closed tests for multi-instrument Phase-0 integrity v6."""
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


def _challenge(run_id: str, symbols: list[str] | None = None) -> dict:
    return {
        "run_id": run_id,
        "symbols": list(symbols if symbols is not None else b.SYMBOLS),
        "timeframes": "H1",
        "months": 60,
        "holdout_start_server": "2026-01-01 00:00:00",
        "expect_login": 27496181,
        "expect_server": "VantageMarkets-Live 5",
        "issued_utc": "2026-08-11T20:00:00Z",
    }


def _valid_export_bundle(bridge: Path, run_id: str = "a" * 32) -> tuple[dict, dict]:
    symbols = list(b.SYMBOLS)
    files = {}
    for s in symbols:
        hist = bridge / f"history_{s}.csv"
        meta = bridge / f"symbol_meta_{s}.csv"
        _write_history(hist, _good_rows(s, n=12))
        _meta(meta, requested=s, resolved=s)
        st = hist.stat()
        files[f"history_{s}"] = {
            "path": str(hist),
            "sha256": b._sha256_file(hist),
            "bytes": st.st_size,
            "mtime_unix": int(st.st_mtime),
        }
        st2 = meta.stat()
        files[f"meta_{s}"] = {
            "path": str(meta),
            "sha256": b._sha256_file(meta),
            "bytes": st2.st_size,
            "mtime_unix": int(st2.st_mtime),
        }
    challenge = _challenge(run_id, symbols)
    (bridge / "export_challenge.json").write_text(
        json.dumps(challenge, separators=(",", ":")) + "\n"
    )
    export_run = {
        "run_id": run_id,
        "login": 27496181,
        "server": "VantageMarkets-Live 5",
        "export_started_utc": "2026-08-11T20:00:00Z",
        "export_finished_utc": "2026-08-11T20:01:00Z",
        "wine_exit_code": 3,
        "timeframes": "H1",
        "symbols": symbols,
        "files": files,
    }
    complete = {
        "ok": True,
        "run_id": run_id,
        "challenge_echo": json.dumps(challenge, separators=(",", ":")),
        "terminal_connected": True,
        "account_login": 27496181,
        "account_server": "VantageMarkets-Live 5",
        "symbols": [
            {
                "requested": s,
                "resolved": s,
                "bars": 12,
                "from": "2024.01.01 00:00",
                "to": "2024.01.01 11:00",
                "ok": True,
            }
            for s in symbols
        ],
    }
    return export_run, complete


def test_parse_history_is_naive_server_clock_not_utc(tmp_path: Path):
    p = tmp_path / "h.csv"
    _write_history(p, _good_rows())
    df = b._parse_history(p)
    assert df["time"].dt.tz is None


def test_bad_ohlc_hard_fail_does_not_publish(tmp_path: Path):
    bridge = tmp_path / "bridge"
    out = tmp_path / "out"
    bridge.mkdir()
    rows = _good_rows()
    rows[0]["high"] = 1.0
    _write_history(bridge / "history_EURUSD.csv", rows)
    _meta(bridge / "symbol_meta_EURUSD.csv")
    m, _ = b.build_symbol(
        "EURUSD",
        bridge_dir=bridge,
        costs={"login": 1, "server": "S"},
        export_run={"run_id": "a" * 32},
        holdout_start=b.DEVELOP_END_SERVER,
        out_dir=out,
        publish=True,
    )
    assert m.status == "FAIL"
    assert m.published is False
    assert not (out / "eurusd_h1.csv").exists()


def test_wrong_row_symbol_hard_fail(tmp_path: Path):
    bridge = tmp_path / "bridge"
    out = tmp_path / "out"
    bridge.mkdir()
    _write_history(bridge / "history_EURUSD.csv", _good_rows(symbol="GBPUSD"))
    _meta(bridge / "symbol_meta_EURUSD.csv", requested="EURUSD", resolved="EURUSD")
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
    assert any("ROW_SYMBOL" in e for e in m.hard_errors)


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
    assert any("H1_NOT_HOUR_ALIGNED" in e for e in m.hard_errors)


def test_export_run_rejects_wrong_run_id_and_missing_account(tmp_path: Path):
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    export_run, complete = _valid_export_bundle(bridge, run_id="b" * 32)
    complete["run_id"] = "c" * 32  # mismatch
    del complete["account_login"]
    errs = b.verify_export_run(
        export_run,
        {"login": 27496181, "server": "VantageMarkets-Live 5"},
        bridge_dir=bridge,
        export_complete=complete,
    )
    assert any("RUN_ID_MISMATCH" in e for e in errs)
    assert any("MQL_LOGIN_MISSING" in e for e in errs)


def test_costs_file_required():
    errs = b.verify_costs_file(None)
    assert "MISSING_COSTS_FILE" in errs or "EMPTY_COSTS" in errs
    errs2 = b.verify_costs_file({})
    assert "EMPTY_COSTS" in errs2 or any("COSTS_" in e for e in errs2)


def test_costs_real_file_ok():
    costs = json.loads(b.COSTS_XAU.read_text())
    assert b.verify_costs_file(costs) == []


def test_verify_develop_mutation_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Develop CSV corruption must fail verify_committed_artifacts."""
    if not b.ARTIFACT_LOCK.is_file():
        pytest.skip("no artifact lock")
    lock = json.loads(b.ARTIFACT_LOCK.read_text())
    # Work on a copy of the lock pointing at temp mutated develop
    arts = lock["artifacts"]
    assert "EURUSD" in arts
    src_dev = ROOT / arts["EURUSD"]["develop_csv"]
    if not src_dev.is_file():
        pytest.skip("no develop csv")
    mutated = tmp_path / "eurusd_h1_develop.csv"
    mutated.write_text("corrupted\n")
    # Build a temp lock file
    lock2 = json.loads(json.dumps(lock))
    lock2["artifacts"]["EURUSD"]["develop_csv"] = str(mutated)
    # keep old sha so mismatch fires
    tlock = tmp_path / "lock.json"
    tlock.write_text(json.dumps(lock2))
    # Patch ROOT resolution: develop path is absolute so verify uses it
    errs = b.verify_committed_artifacts(tlock)
    assert any("develop_sha_mismatch" in e or "develop_row_count" in e for e in errs), errs


def test_verify_missing_symbol_detected(tmp_path: Path):
    if not b.ARTIFACT_LOCK.is_file():
        pytest.skip("no artifact lock")
    lock = json.loads(b.ARTIFACT_LOCK.read_text())
    lock["artifacts"].pop("EURUSD", None)
    tlock = tmp_path / "lock.json"
    tlock.write_text(json.dumps(lock))
    errs = b.verify_committed_artifacts(tlock)
    assert any("SYMBOL_SET_MISMATCH" in e or "missing_from_lock" in e for e in errs)


def test_repo_artifacts_not_touched_by_unit_tests(tmp_path: Path):
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


def test_committed_artifact_lock_full_and_develop():
    if not b.ARTIFACT_LOCK.is_file():
        pytest.skip("artifact lock not yet built")
    errs = b.verify_committed_artifacts()
    assert errs == [], errs
    data = json.loads(b.ARTIFACT_LOCK.read_text())
    assert set(data["artifacts"].keys()) == set(b.SYMBOLS)
    for _sym, ent in data["artifacts"].items():
        assert int(ent["n_rows_h1"]) >= 10_000
        assert int(ent["n_rows_h1_develop"]) >= 10_000
        assert ent.get("develop_csv_sha256")
        assert Path(ROOT / ent["develop_csv"]).is_file()


def test_common_window_ok():
    fx = pd.date_range("2024-01-01", periods=20, freq="h")
    xau = fx[::2]
    develops = {
        "EURUSD": pd.DataFrame({"time": fx}),
        "GBPUSD": pd.DataFrame({"time": fx}),
        "XAUUSD": pd.DataFrame({"time": xau}),
    }
    old = b.MIN_DEVELOP_BARS
    b.MIN_DEVELOP_BARS = 5
    try:
        assert b.common_window(develops)["status"] == "OK"
    finally:
        b.MIN_DEVELOP_BARS = old


def test_attested_path_diverges_from_canonical_consume(tmp_path: Path):
    """export_run.path may name a different file; consume path is always bridge_dir."""
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    export_run, complete = _valid_export_bundle(bridge)
    # Attacker points history_EURUSD path at a different valid CSV with different SHA
    other = tmp_path / "other_history_EURUSD.csv"
    _write_history(other, _good_rows("EURUSD", n=12, spread=99))
    ent = export_run["files"]["history_EURUSD"]
    ent["path"] = str(other)
    # Poison attestation to match the alt file (old verifier would accept this)
    ent["sha256"] = b._sha256_file(other)
    ent["bytes"] = other.stat().st_size
    ent["mtime_unix"] = int(other.stat().st_mtime)
    errs = b.verify_export_run(
        export_run,
        {"login": 27496181, "server": "VantageMarkets-Live 5"},
        bridge_dir=bridge,
        export_complete=complete,
    )
    assert any(
        "ATTESTED_PATH_DIVERGES" in e or "EXPORT_RUN_SHA_MISMATCH" in e for e in errs
    ), errs
    # Canonical bridge file is still what build_symbol would read
    assert (bridge / "history_EURUSD.csv").is_file()
    assert b._sha256_file(bridge / "history_EURUSD.csv") != b._sha256_file(other)


def test_challenge_echo_tamper_rejected(tmp_path: Path):
    """Presence-only echo must fail; exact field compare required."""
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    export_run, complete = _valid_export_bundle(bridge)
    complete["challenge_echo"] = "tampered-but-present"
    errs = b.verify_export_run(
        export_run,
        {"login": 27496181, "server": "VantageMarkets-Live 5"},
        bridge_dir=bridge,
        export_complete=complete,
    )
    assert any("CHALLENGE_ECHO_UNPARSEABLE" in e for e in errs), errs

    # Parseable but wrong run_id / symbols still fails
    export_run2, complete2 = _valid_export_bundle(bridge, run_id="b" * 32)
    bad = _challenge("b" * 32)
    bad["run_id"] = "c" * 32
    complete2["challenge_echo"] = json.dumps(bad)
    errs2 = b.verify_export_run(
        export_run2,
        {"login": 27496181, "server": "VantageMarkets-Live 5"},
        bridge_dir=bridge,
        export_complete=complete2,
    )
    assert any("CHALLENGE_ECHO_RUN_ID" in e for e in errs2), errs2




def _isolate_publish_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    (root / "results").mkdir(parents=True)
    monkeypatch.setattr(b, "ROOT", root)
    monkeypatch.setattr(b, "OUT_DIR", root / "results" / "instrument_data")
    monkeypatch.setattr(b, "MANIFEST_DIR", root / "results" / "instrument_data_manifests")
    monkeypatch.setattr(
        b, "REPORT_PATH", root / "results" / "multi_instrument_data_readiness.md"
    )
    monkeypatch.setattr(
        b,
        "FAIL_REPORT_PATH",
        root / "results" / "multi_instrument_data_readiness.FAIL.md",
    )
    monkeypatch.setattr(
        b,
        "ARTIFACT_LOCK",
        root / "results" / "instrument_data_manifests" / "committed_artifact_lock.json",
    )
    monkeypatch.setattr(b, "PACKAGE_ROOT", root / "results" / "instrument_data_packages")
    monkeypatch.setattr(
        b, "CURRENT_POINTER", root / "results" / "instrument_data_packages" / "CURRENT"
    )
    b.PACKAGE_ROOT.mkdir(parents=True)
    return root


def _make_pkg(pkg_id: str, marker: str) -> Path:
    b.validate_package_id(pkg_id)
    pkg = b.PACKAGE_ROOT / pkg_id
    data = pkg / "instrument_data"
    man = pkg / "instrument_data_manifests"
    data.mkdir(parents=True)
    man.mkdir(parents=True)
    arts = {}
    for s in b.SYMBOLS:
        full = data / f"{s.lower()}_h1.csv"
        dev = data / f"{s.lower()}_h1_develop.csv"
        full.write_text(f"{marker}-{s}-full\n")
        dev.write_text(f"{marker}-{s}-dev\n")
        (man / f"{s.lower()}_h1_manifest.json").write_text(
            json.dumps({"symbol": s, "m": marker})
        )
        arts[s] = {
            "research_csv": f"results/instrument_data/{s.lower()}_h1.csv",
            "research_csv_sha256": b._sha256_file(full),
            "n_rows_h1": 1,
            "n_rows_h1_develop": 1,
            "develop_csv": f"results/instrument_data/{s.lower()}_h1_develop.csv",
            "develop_csv_sha256": b._sha256_file(dev),
        }
    (man / "common_develop_window.json").write_text("{}\n")
    (man / "committed_artifact_lock.json").write_text(
        json.dumps(
            {
                "package_id": pkg_id,
                "export_run_id": pkg_id.split("-")[0] if "-" in pkg_id else None,
                "required_symbols": list(b.SYMBOLS),
                "artifacts": arts,
                "marker": marker,
            }
        )
        + "\n"
    )
    (pkg / "multi_instrument_data_readiness.md").write_text(f"# {marker}\n")
    return pkg


def _live_csv_texts() -> dict[str, str]:
    return {
        p.name: p.read_text()
        for p in b.OUT_DIR.iterdir()
        if p.is_file() or (p.is_symlink() and p.resolve().is_file())
    }


def test_live_roots_are_static_through_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Live roots always point at packages/CURRENT/...; only CURRENT moves."""
    _isolate_publish_roots(tmp_path, monkeypatch)
    old_id = "a" * 32 + "-" + "1" * 16
    new_id = "b" * 32 + "-" + "2" * 16
    _make_pkg(old_id, "OLD")
    b.install_package_to_live(b.PACKAGE_ROOT / old_id)

    assert b.OUT_DIR.is_symlink()
    assert str(b.OUT_DIR.readlink()) == "instrument_data_packages/CURRENT/instrument_data"
    assert str(b.MANIFEST_DIR.readlink()).endswith("CURRENT/instrument_data_manifests")
    assert str(b.REPORT_PATH.readlink()).endswith(
        "CURRENT/multi_instrument_data_readiness.md"
    )
    assert all(v.startswith("OLD-") for v in _live_csv_texts().values())

    _make_pkg(new_id, "NEW")
    b.publish_versioned_package(
        b.PACKAGE_ROOT / new_id, new_id, prevalidated=True
    )
    # Roots unchanged (still through CURRENT)
    assert str(b.OUT_DIR.readlink()) == "instrument_data_packages/CURRENT/instrument_data"
    assert b._read_current_package_id() == new_id
    assert all(v.startswith("NEW-") for v in _live_csv_texts().values())
    assert b.verify_live_matches_package(b.PACKAGE_ROOT / new_id) == []


def test_publish_rollback_restores_previous_via_current_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Failure after CURRENT flip rolls CURRENT back; live roots stay static."""
    _isolate_publish_roots(tmp_path, monkeypatch)
    old_id = "a" * 32 + "-" + "1" * 16
    new_id = "b" * 32 + "-" + "2" * 16
    _make_pkg(old_id, "OLD")
    b.install_package_to_live(b.PACKAGE_ROOT / old_id)
    old_live = _live_csv_texts()
    root_link = str(b.OUT_DIR.readlink())

    _make_pkg(new_id, "NEW")
    real_replace = Path.replace
    flipped = {"n": 0}

    def flaky_replace(self, target):  # type: ignore[no-untyped-def]
        # Fail the first time CURRENT.new is promoted (new package), allow rollback
        if self.name == ".CURRENT.new" and self.is_symlink():
            dest = str(self.readlink())
            if dest == new_id:
                flipped["n"] += 1
                if flipped["n"] == 1:
                    # Allow the write, then fail post-verify by poisoning after
                    pass
        return real_replace(self, target)

    # Instead of flaky CURRENT: poison post-switch verify
    monkeypatch.setattr(
        b,
        "verify_live_matches_package",
        lambda *_a, **_k: ["injected_live_verify_fail"],
    )
    with pytest.raises(RuntimeError, match="LIVE_VERIFY_FAIL"):
        b.publish_versioned_package(
            b.PACKAGE_ROOT / new_id, new_id, prevalidated=True
        )

    assert b._read_current_package_id() == old_id
    assert str(b.OUT_DIR.readlink()) == root_link
    assert _live_csv_texts() == old_live


def test_pre_switch_invalid_lock_never_becomes_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Broken lock must fail before CURRENT flip."""
    _isolate_publish_roots(tmp_path, monkeypatch)
    old_id = "a" * 32 + "-" + "1" * 16
    new_id = "b" * 32 + "-" + "2" * 16
    _make_pkg(old_id, "OLD")
    b.install_package_to_live(b.PACKAGE_ROOT / old_id)

    pkg = _make_pkg(new_id, "NEW")
    # Corrupt lock SHAs
    lock_path = pkg / "instrument_data_manifests" / "committed_artifact_lock.json"
    lock = json.loads(lock_path.read_text())
    for sym in lock["artifacts"]:
        lock["artifacts"][sym]["research_csv_sha256"] = "0" * 64
    lock_path.write_text(json.dumps(lock) + "\n")

    with pytest.raises(RuntimeError, match="PRE_SWITCH_VALIDATE_FAIL"):
        b.publish_versioned_package(pkg, new_id, prevalidated=False)

    assert b._read_current_package_id() == old_id
    assert all(v.startswith("OLD-") for v in _live_csv_texts().values())


def test_same_package_id_refuses_different_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _isolate_publish_roots(tmp_path, monkeypatch)
    pkg_id = "c" * 32 + "-" + "3" * 16
    first = _make_pkg(pkg_id, "FIRST")
    b.install_package_to_live(first)

    stage = tmp_path / "stage_collision"
    # different content, same forced id via finalize
    data = stage / "instrument_data"
    man = stage / "instrument_data_manifests"
    data.mkdir(parents=True)
    man.mkdir(parents=True)
    for s in b.SYMBOLS:
        (data / f"{s.lower()}_h1.csv").write_text("OTHER-full\n")
        (data / f"{s.lower()}_h1_develop.csv").write_text("OTHER-dev\n")
        (man / f"{s.lower()}_h1_manifest.json").write_text("{}")
    (man / "common_develop_window.json").write_text("{}\n")
    (man / "committed_artifact_lock.json").write_text("{}\n")
    (stage / "multi_instrument_data_readiness.md").write_text("# OTHER\n")

    with pytest.raises(RuntimeError, match="PACKAGE_ID_COLLISION"):
        b.finalize_package_dir(stage, pkg_id)

    assert (b.PACKAGE_ROOT / pkg_id / "instrument_data" / "eurusd_h1.csv").read_text().startswith(
        "FIRST-"
    )
    assert b._read_current_package_id() == pkg_id


def test_missing_previous_package_aborts_before_live_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _isolate_publish_roots(tmp_path, monkeypatch)
    b.OUT_DIR.mkdir(parents=True)
    b.MANIFEST_DIR.mkdir(parents=True)
    for s in b.SYMBOLS:
        (b.OUT_DIR / f"{s.lower()}_h1.csv").write_text(f"LEGACY-{s}\n")
        (b.OUT_DIR / f"{s.lower()}_h1_develop.csv").write_text(f"LEGACY-{s}-d\n")
    b.REPORT_PATH.write_text("# LEGACY\n")

    # Dangling CURRENT with valid format
    dangling = "d" * 32 + "-" + "e" * 16
    b.CURRENT_POINTER.write_text(dangling + "\n")

    with pytest.raises(RuntimeError, match="CURRENT_PACKAGE_MISSING"):
        b.resolve_current_package_dir()

    new_id = "f" * 32 + "-" + "9" * 16
    new_pkg = _make_pkg(new_id, "NEW")
    with pytest.raises(RuntimeError, match="CURRENT_PACKAGE_MISSING"):
        b.publish_versioned_package(new_pkg, new_id, prevalidated=True)

    assert (b.OUT_DIR / "eurusd_h1.csv").read_text().startswith("LEGACY-")


def test_current_text_path_escape_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _isolate_publish_roots(tmp_path, monkeypatch)
    b.CURRENT_POINTER.write_text("../outside\n")
    with pytest.raises(RuntimeError, match="CURRENT_TEXT_ESCAPE|CURRENT_INVALID"):
        b._read_current_package_id()
    b.CURRENT_POINTER.write_text("not-a-valid-id\n")
    with pytest.raises(RuntimeError, match="CURRENT_INVALID"):
        b._read_current_package_id()


def test_fail_evidence_does_not_clobber_package_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _isolate_publish_roots(tmp_path, monkeypatch)
    old_id = "a" * 32 + "-" + "1" * 16
    b.install_package_to_live(_make_pkg(old_id, "OLD"))
    before = b.REPORT_PATH.read_text()
    b.write_fail_evidence([], {"status": "FAIL"}, "FAIL_DATA", ["boom"])
    assert b.FAIL_REPORT_PATH.is_file()
    assert "FAIL_DATA" in b.FAIL_REPORT_PATH.read_text()
    assert b.REPORT_PATH.read_text() == before
    assert before.startswith("# OLD")


def test_content_package_id_stable_for_same_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _isolate_publish_roots(tmp_path, monkeypatch)
    # content_package_id excludes nothing special for lock presence
    run = "a" * 32
    # Build under temp then move naming not required
    pkg = tmp_path / "pkg"
    data = pkg / "instrument_data"
    man = pkg / "instrument_data_manifests"
    data.mkdir(parents=True)
    man.mkdir(parents=True)
    for s in b.SYMBOLS:
        (data / f"{s.lower()}_h1.csv").write_text("SAME\n")
        (data / f"{s.lower()}_h1_develop.csv").write_text("SAME\n")
        (man / f"{s.lower()}_h1_manifest.json").write_text("{}")
    (man / "common_develop_window.json").write_text("{}")
    (pkg / "multi_instrument_data_readiness.md").write_text("# x\n")
    id1 = b.content_package_id(pkg, run)
    id2 = b.content_package_id(pkg, run)
    assert id1 == id2
    assert id1.startswith(run + "-")
    (data / "eurusd_h1.csv").write_text("mutated\n")
    assert b.content_package_id(pkg, run) != id1
