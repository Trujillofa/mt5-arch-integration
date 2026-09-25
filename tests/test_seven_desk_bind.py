"""Seven Desk listens on loopback and --foreground serves a production build.

The desk can place live orders. Binding every interface, or leaving `next dev`
as the unit command, is the failure these checks pin down.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "apps" / "seven-desk" / "package.json"
LAUNCHER = ROOT / "scripts" / "20-seven-desk.sh"


def test_package_scripts_bind_loopback_only() -> None:
    scripts = json.loads(PKG.read_text(encoding="utf-8"))["scripts"]
    for name, command in scripts.items():
        assert "0.0.0.0" not in command, name
    assert scripts["dev"] == "next dev --port 3847 --hostname 127.0.0.1"
    assert scripts["start"] == "next start --port 3847 --hostname 127.0.0.1"


def _bash_function(source: str, name: str) -> str:
    match = re.search(rf"^{name}\(\) \{{(.*?)^\}}", source, re.M | re.S)
    assert match is not None, f"missing function {name}"
    return match.group(1)


def test_foreground_builds_then_starts_on_loopback() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")
    assert 'URL="http://127.0.0.1:${PORT}/"' in source
    foreground = _bash_function(source, "run_foreground")
    assert "npm run build" in foreground
    assert "exec npm run start" in foreground
    assert "npm run dev" not in foreground
    dev = _bash_function(source, "run_dev")
    assert "exec npm run dev" in dev
    assert "npm run start" not in dev
    assert re.search(r"--foreground\)\s+run_foreground\b", source)
    assert re.search(r"--dev\)\s+run_dev\b", source)
