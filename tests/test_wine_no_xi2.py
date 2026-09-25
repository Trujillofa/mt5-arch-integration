"""Checks for the no-XInput2 Wine preload that stops one click reaching every book.

Regression cover for 2026-09-24: each book runs its own wineserver, so each
believes it is the foreground window, and Wine 11 Staging fed XInput2 *raw*
button events (broadcast to every root-window listener) into all of them. One
right-click opened the chart menu in every running book -- even a click on a
non-Wine window -- and a scroll on one book moved another.
"""

from __future__ import annotations

import ctypes.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "scripts" / "wine-input" / "no_xi2.c"
SO = REPO / "scripts" / "wine-input" / "no_xi2.so"
LIB = REPO / "scripts" / "lib.sh"
LAUNCHERS = REPO / "scripts" / "17-install-desktop-launchers.sh"

PROBE = (
    "import ctypes, sys\n"
    "lib = ctypes.CDLL(None)\n"
    "lib.dlopen.restype = ctypes.c_void_p\n"
    "lib.dlopen.argtypes = [ctypes.c_char_p, ctypes.c_int]\n"
    "xi = lib.dlopen(b'libXi.so.6', 2)\n"
    "x11 = lib.dlopen(b'libX11.so.6', 2)\n"
    "print('xi=%s x11=%s' % (bool(xi), bool(x11)))\n"
)


def _build() -> None:
    subprocess.run(
        ["gcc", "-shared", "-fPIC", "-O2", "-o", str(SO), str(SRC), "-ldl"],
        check=True,
        cwd=REPO,
    )


def _probe(preload: bool) -> str:
    env = {"PATH": "/usr/bin:/bin"}
    if preload:
        env["LD_PRELOAD"] = str(SO)
    return subprocess.run(
        [sys.executable, "-c", PROBE], env=env, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_shim_only_interposes_dlopen() -> None:
    _build()
    out = subprocess.check_output(["nm", "-D", "--defined-only", str(SO)], text=True)
    exported = {line.split()[-1] for line in out.splitlines() if " T " in line}
    assert exported == {"dlopen"}


def test_shim_refuses_libxi_and_nothing_else() -> None:
    """The fix must deny XInput2 only; every other library still loads."""
    if not ctypes.util.find_library("Xi") or not ctypes.util.find_library("X11"):
        import pytest

        pytest.skip("libXi/libX11 not installed on this host")
    _build()
    assert _probe(preload=False) == "xi=True x11=True"
    assert _probe(preload=True) == "xi=False x11=True"


def test_every_interactive_launch_path_applies_the_shim() -> None:
    """A book started without the shim reintroduces the broadcast for everyone."""
    lib = LIB.read_text(encoding="utf-8")
    assert "export_no_xi2_preload()" in lib
    assert "MT5_WINE_XI2" in lib  # documented opt-out
    detached = lib[lib.index("start_terminal64_detached()") :]
    detached = detached[: detached.index("\n}\n")]
    assert detached.index("recycle_prefix_wineserver_if_idle") < detached.index("setsid -f wine")
    # Must come after the prefix-specific `unset LD_PRELOAD`, or it is wiped.
    assert detached.index("unset LD_PRELOAD") < detached.index("export_no_xi2_preload")
    launches = {
        "04-start-terminal.sh": 'exec wine "$term"',
        "07-restart-terminal.sh": 'nohup wine "$term" /portable',
        "13-force-login-bridge.sh": 'nohup wine "$term" /portable /config:auto_login.ini',
        # Headless tester/export runs share the desktop with live books too.
        "19-run-htf-fib-backtest.sh": 'timeout "$TIMEOUT_SEC" "${RUNNER[@]}" ./terminal64.exe',
        "24-run-grid-scalper-ruin.sh": 'timeout "$timeout_sec" wine ./terminal64.exe',
        "export-instruments-from-wine-mt5.sh": 'timeout "$TIMEOUT_S" wine ./terminal64.exe',
        "export-xau-from-wine-mt5.sh": "timeout 120 wine ./terminal64.exe",
    }
    for name, launch in launches.items():
        text = (REPO / "scripts" / name).read_text(encoding="utf-8")
        before = text[: text.index(launch)].rstrip().splitlines()[-1].strip()
        assert before == "export_no_xi2_preload", f"{name}: shim not applied right before launch"
    assert "no_xi2" in LAUNCHERS.read_text(encoding="utf-8")
    restart = (REPO / "scripts" / "07-restart-terminal.sh").read_text(encoding="utf-8")
    assert restart.index("kill_terminal64_processes") < restart.index("kill_prefix_wineserver")
    assert restart.index("kill_prefix_wineserver") < restart.index("export_no_xi2_preload")
    start = (REPO / "scripts" / "04-start-terminal.sh").read_text(encoding="utf-8")
    assert start.index("already running") < start.index("kill_prefix_wineserver")
    assert start.index("kill_prefix_wineserver") < start.index("start_terminal64_detached")
    launchers = LAUNCHERS.read_text(encoding="utf-8")
    assert launchers.index("recycle_prefix_wineserver_if_idle") < launchers.index(
        "exec wine ./terminal64.exe"
    )


def test_idle_wineserver_recycle_does_not_kill_a_live_book() -> None:
    """A launcher click on a running book must not wineserver -k."""
    script = r"""
source "$LIB" >/dev/null 2>&1
export WINEPREFIX="$PREFIX"
list_terminal64_pids() { echo 4242; }
kill_prefix_wineserver() { echo KILLED; }
recycle_prefix_wineserver_if_idle
list_terminal64_pids() { true; }
recycle_prefix_wineserver_if_idle
"""
    out = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=True,
        env={
            "LIB": str(LIB),
            "PREFIX": str(REPO),
            "PATH": "/usr/bin:/bin",
        },
    ).stdout
    assert out.strip() == "KILLED"


def test_preload_composes_with_existing_preload() -> None:
    """Vantage also runs force_src_bind.so; the shim must prepend, not replace."""
    out = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{LIB}" >/dev/null 2>&1; export LD_PRELOAD=/x/other.so; '
            'export_no_xi2_preload; export_no_xi2_preload; echo "$LD_PRELOAD"',
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert out == f"{SO}:/x/other.so"  # prepended once, idempotent


def test_opt_out_leaves_preload_untouched() -> None:
    out = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{LIB}" >/dev/null 2>&1; export MT5_WINE_XI2=1 LD_PRELOAD=/x/other.so; '
            'export_no_xi2_preload; echo "$LD_PRELOAD"',
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert out == "/x/other.so"
