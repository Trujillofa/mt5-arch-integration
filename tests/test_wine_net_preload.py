"""Structural + behavioral checks for Wine LAN source-bind helper."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "scripts" / "wine-net" / "force_src_bind.c"
SO = REPO / "scripts" / "wine-net" / "force_src_bind.so"
LIB = REPO / "scripts" / "lib.sh"
SCRIPT_13 = REPO / "scripts" / "13-force-login-bridge.sh"
SCRIPT_17 = REPO / "scripts" / "17-install-desktop-launchers.sh"


def _rebuild_so() -> None:
    subprocess.run(
        ["gcc", "-shared", "-fPIC", "-O2", "-o", str(SO), str(SRC), "-ldl"],
        check=True,
        cwd=REPO,
    )


def test_force_src_bind_source_exists() -> None:
    assert SRC.is_file()
    text = SRC.read_text(encoding="utf-8")
    assert "MT5_FORCE_SRC_IP" in text
    assert "connect(" in text
    assert "bind(" in text
    assert "is_dockerish" in text
    # 10/8, 172.16/12, 100.64/10 stay dockerish; 127/8 must not.
    assert "if (b[0] == 10) return 1;" in text
    assert "b[0] == 172" in text
    assert "b[0] == 100" in text
    assert "b[0] == 127" not in text


def test_force_src_bind_shared_object_exports_hooks() -> None:
    """Shipped .so must export connect/bind interceptors (build if missing)."""
    if not SO.is_file():
        _rebuild_so()
    assert SO.is_file()
    out = subprocess.check_output(["nm", "-D", str(SO)], text=True)
    assert " T connect\n" in out or " T connect" in out
    assert " T bind\n" in out or " T bind" in out


def test_preload_does_not_remap_loopback_listen() -> None:
    """Old helper rewrote 127/8 onto MT5_FORCE_SRC_IP; official MCP needs 127."""
    _rebuild_so()
    env = os.environ.copy()
    env["LD_PRELOAD"] = str(SO)
    env["MT5_FORCE_SRC_IP"] = "192.0.2.1"  # TEST-NET-1: not a local address
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import socket\n"
            "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "s.bind(('127.0.0.1', 0))\n"
            "host = s.getsockname()[0]\n"
            "s.close()\n"
            "assert host == '127.0.0.1', host\n",
        ],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_ops_scripts_rebuild_stale_preload() -> None:
    lib = LIB.read_text(encoding="utf-8")
    assert "ensure_force_src_bind_so()" in lib
    assert '"$src" -nt "$so"' in lib
    assert "ensure_force_src_bind_so" in SCRIPT_13.read_text(encoding="utf-8")
    text17 = SCRIPT_17.read_text(encoding="utf-8")
    assert "force_src_bind.c" in text17
    assert '"$SRC" -nt "$SO"' in text17
