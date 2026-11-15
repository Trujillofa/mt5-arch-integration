"""An echo of our own X11 claim must not claim the selection again."""

from __future__ import annotations

import importlib.util
import io
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "clip_to_x11.py"
BRIDGE = Path(__file__).resolve().parents[1] / "scripts" / "11-clipboard-bridge.sh"
SPEC = importlib.util.spec_from_file_location("clip_to_x11", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
clip = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(clip)


class Board:
    def __init__(self) -> None:
        self.selections: dict[str, bytes | None] = {"clipboard": None, "primary": None}
        self.claims: list[tuple[str, bytes | None]] = []
        self.reads: list[str] = []

    def run(self, args, input=None, capture_output=False, timeout=None, check=False):
        sel = args[args.index("-selection") + 1]
        if "-o" in args:
            self.reads.append(sel)
            data = self.selections[sel]
            if data is None:
                return subprocess.CompletedProcess(args, 1, b"", b"fail")
            return subprocess.CompletedProcess(args, 0, data, b"")
        self.claims.append((sel, input))
        if input is None:
            return subprocess.CompletedProcess(args, 1, b"", b"")
        self.selections[sel] = input
        return subprocess.CompletedProcess(args, 0, b"", b"")


def _bind(monkeypatch, tmp_path: Path) -> Board:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    board = Board()
    monkeypatch.setattr(clip.subprocess, "run", board.run)
    return board


def _stdin(data: bytes):
    return type("Stdin", (), {"buffer": io.BytesIO(data)})()


def test_first_sync_claims_both_and_stamps(tmp_path: Path, monkeypatch) -> None:
    board = _bind(monkeypatch, tmp_path)
    clip.sync_text(b"hello")
    assert board.claims == [("clipboard", b"hello"), ("primary", b"hello")]
    assert clip.read_stamp() == clip.payload_hash(b"hello")
    assert clip.stamp_path().stat().st_mode & 0o777 == 0o600


def test_same_text_again_does_not_claim(tmp_path: Path, monkeypatch) -> None:
    board = _bind(monkeypatch, tmp_path)
    clip.sync_text(b"hello")
    claims = list(board.claims)
    reads = list(board.reads)
    clip.sync_text(b"hello")
    assert board.claims == claims
    assert board.reads == reads


def test_stamp_match_skips_when_read_would_fail(tmp_path: Path, monkeypatch) -> None:
    board = _bind(monkeypatch, tmp_path)
    clip.write_stamp(clip.payload_hash(b"hello"))
    clip.sync_text(b"hello")
    assert board.claims == []
    assert board.reads == []


def test_stamp_match_skips_when_selection_bytes_differ(tmp_path: Path, monkeypatch) -> None:
    board = _bind(monkeypatch, tmp_path)
    board.selections = {"clipboard": b"other", "primary": b"other"}
    clip.write_stamp(clip.payload_hash(b"hello"))
    clip.sync_text(b"hello")
    assert board.claims == []
    assert board.reads == []


def test_equal_bytes_do_not_claim(tmp_path: Path, monkeypatch) -> None:
    board = _bind(monkeypatch, tmp_path)
    board.selections = {"clipboard": b"hello", "primary": b"hello"}
    clip.sync_text(b"hello")
    assert board.claims == []
    assert board.reads == ["clipboard", "primary"]
    assert clip.read_stamp() == clip.payload_hash(b"hello")


def test_different_text_claims_and_updates_stamp(tmp_path: Path, monkeypatch) -> None:
    board = _bind(monkeypatch, tmp_path)
    clip.sync_text(b"hello")
    clip.sync_text(b"world")
    assert ("clipboard", b"world") in board.claims
    assert ("primary", b"world") in board.claims
    assert clip.read_stamp() == clip.payload_hash(b"world")


def test_failed_clipboard_claim_clears_stamp(tmp_path: Path, monkeypatch) -> None:
    board = _bind(monkeypatch, tmp_path)

    def run(args, input=None, capture_output=False, timeout=None, check=False):
        sel = args[args.index("-selection") + 1]
        if "-i" in args and sel == "clipboard":
            return subprocess.CompletedProcess(args, 1, b"", b"fail")
        return board.run(args, input=input, capture_output=capture_output, timeout=timeout, check=check)

    monkeypatch.setattr(clip.subprocess, "run", run)
    clip.sync_text(b"hello")
    assert clip.read_stamp() is None


def test_image_and_empty_do_not_stamp(tmp_path: Path, monkeypatch) -> None:
    board = _bind(monkeypatch, tmp_path)
    monkeypatch.setattr(clip.sys, "stdin", _stdin(b""))
    assert clip.main() == 0
    monkeypatch.setattr(clip.sys, "stdin", _stdin(b"\x89PNG\r\n\x1a\nxxxx"))
    assert clip.main() == 0
    assert board.claims == []
    assert not clip.stamp_path().exists()


def test_apply_exits_before_xclip_when_stamp_matches(tmp_path: Path) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "xclip.log"
    fake = bindir / "xclip"
    fake.write_text(f"#!/bin/sh\necho \"$@\" >> {log}\nexit 1\n")
    fake.chmod(0o755)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    stamp = runtime / "mt5-clipboard-bridge.sha"
    stamp.write_text(clip.payload_hash(b"hello") + "\n")
    os.chmod(stamp, 0o600)
    env = os.environ.copy()
    env["XDG_RUNTIME_DIR"] = str(runtime)
    env["PATH"] = f"{bindir}{os.pathsep}{env.get('PATH', '')}"
    result = subprocess.run(
        ["bash", str(BRIDGE), "--apply"],
        input=b"hello",
        capture_output=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not log.exists()
