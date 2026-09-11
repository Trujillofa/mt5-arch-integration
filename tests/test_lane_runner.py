"""lane_runner tests — uncommitted lock, cardinality drift, jsonl idempotency.

Uses tmp_path git repos. Does **not** run the 192-config BTP screen.

Run with plain python3 (host numpy/pandas), never uv run:
    python3 -m pytest tests/test_lane_runner.py -q
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import lane_kit as lk  # noqa: E402
import lane_runner as lr  # noqa: E402

_STUB_NAME = "fixture_lane_stub"
_DATA = b"book-bytes\n"


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    _git(repo, "config", "commit.gpgsign", "false")
    return repo


def _lock(data_sha: str, *, expected: int = 2, sl_atr: list | None = None) -> dict:
    """1 family x len(sl_atr) x 1 tp = product; default 2 configs."""
    return {
        "search_id": "fixture_lane_develop_v1",
        "promote": False,
        "live_go": False,
        "runner": _STUB_NAME,
        "book": {
            "point_size": 0.01,
            "contract_size": 1.0,
            "lots": 1.0,
            "balance_usd": 10000,
        },
        "costs": {
            "commission_per_lot": 0.0,
            "slippage_points": 10.0,
            "max_spread_points": 100.0,
        },
        "data": {"path": "book.csv", "sha256": data_sha},
        "holdout": {"start": "2026-09-01"},
        "families": {"search": ["fam_a"]},
        "grid": {
            "sl_atr": sl_atr if sl_atr is not None else [1.0, 1.5],
            "tp_r": [1.0],
            "max_configs": 16,
            "expected_configs": expected,
        },
    }


def _write_lock(repo: Path, lock: dict, *, name: str = "lock.json") -> Path:
    p = repo / name
    p.write_text(json.dumps(lock, indent=2) + "\n")
    return p


def _write_book(repo: Path, blob: bytes = _DATA) -> str:
    p = repo / "book.csv"
    p.write_bytes(blob)
    return hashlib.sha256(blob).hexdigest()


def _commit(repo: Path, *paths: str, msg: str = "lock") -> str:
    _git(repo, "add", "--", *paths)
    _git(repo, "commit", "-m", msg)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _install_stub(monkeypatch, *, disposition: str = "SCREEN_FAIL", n_eligible: int = 0):
    mod = types.ModuleType(_STUB_NAME)

    def run_screen(lock):
        return {
            "search_id": lock["search_id"],
            "disposition": disposition,
            "n_eligible": n_eligible,
            "promote": False,
            "null": {"frac_null_ge_real": 1.0},
        }

    mod.run_screen = run_screen  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, _STUB_NAME, mod)
    return mod


def test_uncommitted_lock_refuse(tmp_path: Path):
    repo = _init_repo(tmp_path)
    (repo / "README").write_text("seed\n")
    _commit(repo, "README", msg="seed")
    sha = _write_book(repo)
    lock_path = _write_lock(repo, _lock(sha))

    with pytest.raises(SystemExit, match="not committed"):
        lr.require_committed_lock(lock_path, repo)

    _commit(repo, "lock.json")
    lr.require_committed_lock(lock_path, repo)

    lock_path.write_text(lock_path.read_text() + "\n")
    with pytest.raises(SystemExit, match="dirty vs HEAD"):
        lr.require_committed_lock(lock_path, repo)


def test_cardinality_drift_refuse(tmp_path: Path):
    repo = _init_repo(tmp_path)
    sha = _write_book(repo)
    # product is 1 family * 2 sl * 1 tp = 2, but lock claims 99
    lock_path = _write_lock(repo, _lock(sha, expected=99))
    _commit(repo, "lock.json")

    lock = json.loads(lock_path.read_text())
    with pytest.raises(SystemExit, match="cardinality"):
        lr.validate_lane_lock(lock, repo=repo, lock_path=lock_path)

    with pytest.raises(SystemExit, match="cardinality"):
        lr.run_lane(lock_path, tmp_path / "out")


def test_jsonl_append_and_idempotency(tmp_path: Path, monkeypatch):
    _install_stub(monkeypatch, disposition="SCREEN_FAIL", n_eligible=0)
    repo = _init_repo(tmp_path)
    sha = _write_book(repo)
    lock_path = _write_lock(repo, _lock(sha, expected=2))
    commit = _commit(repo, "lock.json")
    out = tmp_path / "out"
    ledger = repo / "results" / "lane_verdicts.jsonl"

    rc = lr.main(["--lock", str(lock_path), "--out", str(out), "--ledger", str(ledger)])
    assert rc == 0
    assert ledger.is_file()
    lines = [ln for ln in ledger.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["search_id"] == "fixture_lane_develop_v1"
    assert row["disposition"] == "SCREEN_FAIL"
    assert row["lock_sha256"] == lk.sha256_file(lock_path)
    assert row["data_sha256"] == sha
    assert row["code_commit"] == commit
    assert row["n_eligible"] == 0
    assert row["frac_null_ge_real"] == pytest.approx(1.0)
    assert row["promote"] is False

    stamped = json.loads((out / "fixture_lane_develop_v1.json").read_text())
    assert stamped["digests"]["lock_sha256"] == row["lock_sha256"]
    assert stamped["digests"]["data_sha256"] == sha
    assert stamped["digests"]["code_commit"] == commit
    assert stamped["promote"] is False

    history = ledger.read_text()
    rc2 = lr.main(["--lock", str(lock_path), "--out", str(out), "--ledger", str(ledger)])
    assert rc2 == 0
    assert ledger.read_text() == history  # never rewrite, never duplicate-append

    # append_verdict itself is idempotent on the same key
    assert lr.append_verdict(ledger, row) is False
    assert ledger.read_text() == history
