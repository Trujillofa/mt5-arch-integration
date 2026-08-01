"""Structural checks for Wine LAN source-bind helper (no live network required)."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "scripts" / "wine-net" / "force_src_bind.c"
SO = REPO / "scripts" / "wine-net" / "force_src_bind.so"


def test_force_src_bind_source_exists() -> None:
    assert SRC.is_file()
    text = SRC.read_text(encoding="utf-8")
    assert "MT5_FORCE_SRC_IP" in text
    assert "connect(" in text
    assert "bind(" in text
    assert "is_dockerish" in text


def test_force_src_bind_shared_object_exports_hooks() -> None:
    """Shipped .so must export connect/bind interceptors (build if missing)."""
    if not SO.is_file():
        subprocess.run(
            [
                "gcc",
                "-shared",
                "-fPIC",
                "-O2",
                "-o",
                str(SO),
                str(SRC),
                "-ldl",
            ],
            check=True,
            cwd=REPO,
        )
    assert SO.is_file()
    out = subprocess.check_output(["nm", "-D", str(SO)], text=True)
    # Dynamic symbols for LD_PRELOAD hooks
    assert " T connect\n" in out or " T connect" in out
    assert " T bind\n" in out or " T bind" in out
