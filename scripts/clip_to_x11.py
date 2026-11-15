#!/usr/bin/env python3
"""Write text to X11 CLIPBOARD + PRIMARY as UTF8_STRING (what Wine expects)."""

from __future__ import annotations

import contextlib
import hashlib
import os
import subprocess
import sys
from pathlib import Path

STAMP_NAME = "mt5-clipboard-bridge.sha"


def stamp_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return Path(runtime) / STAMP_NAME


def payload_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_stamp() -> str | None:
    try:
        text = stamp_path().read_text(encoding="ascii")
    except (OSError, UnicodeError):
        return None
    text = text.strip()
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        return None
    return text


def write_stamp(digest: str) -> None:
    """Record the payload hash before any xclip claim.

    Xwayland echoes a new selection owner back to Wayland. The watcher must
    see this hash and leave the selection alone.
    """
    path = stamp_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, digest.encode("ascii") + b"\n")
        os.fsync(fd)
    except Exception:
        os.close(fd)
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    os.close(fd)
    os.replace(tmp, path)


def clear_stamp(digest: str) -> None:
    if read_stamp() != digest:
        return
    with contextlib.suppress(OSError):
        stamp_path().unlink()


def selection_bytes(selection: str) -> bytes | None:
    """Return the current selection, or None if it cannot be read.

    A failed read must not look like an empty selection: that would make an
    empty clipboard compare equal and skip a real update.
    """
    try:
        result = subprocess.run(
            ["xclip", "-selection", selection, "-o", "-t", "UTF8_STRING"],
            capture_output=True,
            timeout=1,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def set_selection(selection: str, data: bytes) -> bool:
    """Claim selection with data. Return False only when the claim failed.

    Already holding the same bytes is success and does not claim. A new xclip
    owner notifies Xwayland even when the bytes are unchanged.
    """
    if selection_bytes(selection) == data:
        return True
    result = subprocess.run(
        ["xclip", "-selection", selection, "-t", "UTF8_STRING", "-i"],
        input=data,
        check=False,
    )
    return result.returncode == 0


def sync_text(data: bytes) -> None:
    digest = payload_hash(data)
    # Echo of the text we just claimed. Do not touch xclip, even if the
    # current selection cannot be read or does not match byte for byte.
    if read_stamp() == digest:
        return
    write_stamp(digest)
    clipboard_held = set_selection("clipboard", data)
    set_selection("primary", data)
    if not clipboard_held:
        clear_stamp(digest)


def main() -> int:
    data = sys.stdin.buffer.read()
    if not data:
        return 0
    data = data.replace(b"\x00", b"")
    if not data:
        return 0
    # Skip image payloads that sometimes arrive as "text"
    if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff" or data[:4] == b"RIFF":
        return 0
    sync_text(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
