"""Multi-broker profile discovery for mt5-arch-integration.

Broker-branded MT5 installers mainly pre-seed server lists and branding.
This module loads repo-local profile files under ``config/brokers/*.env`` so the
CLI and scripts can switch WINEPREFIX + login + server without hard-coding
broker names in Python.

It does **not** claim that one Wine binary can trade every broker worldwide —
see ``docs/MULTI-BROKER-MT5.md``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

_EXPORT_RE = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$"
)


def repo_root() -> Path:
    """Return repository root (parent of ``src/``)."""
    return Path(__file__).resolve().parents[2]


def brokers_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "config" / "brokers"


@dataclass(frozen=True)
class BrokerProfile:
    """One broker profile from ``config/brokers/<name>.env``."""

    name: str
    path: Path
    wineprefix: str
    login: str
    server: str
    backend: str = "file"
    bridge_max_age: str = "60"

    def as_exports(self) -> dict[str, str]:
        return {
            "MT5_BROKER": self.name,
            "BROKER": self.name,
            "WINEPREFIX": self.wineprefix,
            "MT5_LOGIN": self.login,
            "MT5_SERVER": self.server,
            "MT5_BACKEND": self.backend,
            "MT5_BRIDGE_MAX_AGE": self.bridge_max_age,
        }


def _unquote(val: str) -> str:
    val = val.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
        val = val[1:-1]
    # expand ${HOME} / $HOME (after quote strip)
    home = os.environ.get("HOME", str(Path.home()))
    val = val.replace("${HOME}", home).replace("$HOME", home)
    if val.startswith("~/"):
        val = str(Path.home() / val[2:])
    return val


def parse_broker_env_file(path: Path) -> dict[str, str]:
    """Parse a shell-style broker ``.env`` profile (KEY=value / export KEY=value)."""
    raw = path.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _EXPORT_RE.match(line)
        if not m:
            continue
        key, val = m.group(1), _unquote(m.group(2))
        if key == "MT5_PASSWORD":
            # never load passwords into profile objects
            continue
        out[key] = val
    return out


def load_broker_profile(name: str, root: Path | None = None) -> BrokerProfile:
    """Load ``config/brokers/<name>.env`` or raise ``FileNotFoundError`` / ``ValueError``."""
    path = brokers_dir(root) / f"{name}.env"
    if not path.is_file():
        raise FileNotFoundError(f"broker profile not found: {path}")
    data = parse_broker_env_file(path)
    missing = [k for k in ("WINEPREFIX", "MT5_LOGIN", "MT5_SERVER") if not data.get(k)]
    if missing:
        raise ValueError(f"broker profile {path} missing keys: {', '.join(missing)}")
    return BrokerProfile(
        name=name,
        path=path,
        wineprefix=data["WINEPREFIX"],
        login=data["MT5_LOGIN"],
        server=data["MT5_SERVER"],
        backend=data.get("MT5_BACKEND", "file"),
        bridge_max_age=data.get("MT5_BRIDGE_MAX_AGE", "60"),
    )


def list_broker_profiles(root: Path | None = None) -> list[BrokerProfile]:
    """Return all valid broker profiles under ``config/brokers/`` (sorted by name)."""
    d = brokers_dir(root)
    if not d.is_dir():
        return []
    profiles: list[BrokerProfile] = []
    for path in sorted(d.glob("*.env")):
        name = path.stem
        try:
            profiles.append(load_broker_profile(name, root=root))
        except (OSError, ValueError):
            continue
    return profiles
