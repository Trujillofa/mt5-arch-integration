"""Force-login kill must stay prefix-scoped (never host-wide wineserver)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from mt5_arch.hypr_geometry import environ_wineprefix, list_terminal64_pids

REPO = Path(__file__).resolve().parents[1]
SCRIPT_13 = REPO / "scripts/13-force-login-bridge.sh"
LIB = REPO / "scripts/lib.sh"


def test_force_login_script_is_prefix_scoped() -> None:
    text = SCRIPT_13.read_text(encoding="utf-8")
    assert "WINEPREFIX=~/.mt5-vantage" in text
    assert "FP" in text
    assert "require_wineprefix" in text
    assert "kill_terminal64_processes" in text
    assert "kill_prefix_wineserver" in text
    body = "\n".join(
        ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")
    )
    assert "killall wineserver" not in body
    assert "pkill -f" not in body
    assert "keys = (" not in body
    assert '"wineserver")' not in body


def test_lib_wineserver_kill_is_env_prefixed() -> None:
    text = LIB.read_text(encoding="utf-8")
    assert 'env WINEPREFIX="$WINEPREFIX" wineserver -k' in text
    assert "killall wineserver" not in text


def _bash(snippet: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", "-c", snippet],
        cwd=REPO,
        capture_output=True,
        text=True,
        env=merged,
    )


def test_require_wineprefix_dies_when_empty() -> None:
    proc = _bash("source scripts/lib.sh; WINEPREFIX=; require_wineprefix")
    assert proc.returncode != 0
    assert "empty" in proc.stderr.lower()


def test_require_wineprefix_dies_when_missing(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-prefix"
    proc = _bash(f"source scripts/lib.sh; WINEPREFIX={missing}; require_wineprefix")
    assert proc.returncode != 0
    assert "not an existing prefix" in proc.stderr


def test_kill_prefix_wineserver_dies_before_bare_k() -> None:
    proc = _bash("source scripts/lib.sh; WINEPREFIX=; kill_prefix_wineserver")
    assert proc.returncode != 0
    assert "empty" in proc.stderr.lower()
    assert "wineserver -k" not in proc.stdout


def test_list_terminal64_pids_refuses_without_prefix(monkeypatch) -> None:
    monkeypatch.delenv("WINEPREFIX", raising=False)
    assert list_terminal64_pids() == []


def test_list_terminal64_pids_vantage_excludes_other_prefixes() -> None:
    """Dry enumerate: vantage list must not include FP/Exness/WSF terminals."""
    vantage = os.path.realpath(os.path.expanduser("~/.mt5-vantage"))
    others = {
        os.path.realpath(os.path.expanduser(p))
        for p in ("~/.mt5-fpmarkets", "~/.mt5-exness", "~/.mt5-wsf")
    }
    if not os.path.isdir(vantage):
        return
    for pid in list_terminal64_pids(wineprefix=vantage):
        env_path = Path(f"/proc/{pid}/environ")
        if not env_path.exists():
            continue
        wp = environ_wineprefix(env_path.read_bytes())
        assert wp == vantage
        assert wp not in others


def test_lib_list_terminal64_pids_dry_excludes_fp() -> None:
    """Dry bash helper: vantage pids are not FP wineserver/terminal pids."""
    vantage = Path.home() / ".mt5-vantage"
    fp = Path.home() / ".mt5-fpmarkets"
    if not vantage.is_dir():
        return
    proc = _bash(
        "source scripts/lib.sh; WINEPREFIX=~/.mt5-vantage; list_terminal64_pids",
    )
    assert proc.returncode == 0, proc.stderr
    pids = [int(x) for x in proc.stdout.split() if x.isdigit()]
    fp_resolved = os.path.realpath(fp) if fp.is_dir() else ""
    for pid in pids:
        env_path = Path(f"/proc/{pid}/environ")
        if not env_path.exists():
            continue
        wp = environ_wineprefix(env_path.read_bytes())
        assert wp != fp_resolved
