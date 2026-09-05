"""Contract: Neomaa Fetch must not call a writing-but-offline bridge auth_failed."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TYPES = ROOT / "apps" / "seven-desk" / "src" / "lib" / "neomaa" / "types.ts"
PROBE = ROOT / "apps" / "seven-desk" / "src" / "lib" / "neomaa" / "probe.ts"
UI = ROOT / "apps" / "seven-desk" / "src" / "components" / "desk" / "neomaa-live-probe.tsx"
RUNNER = ROOT / "apps" / "seven-desk" / "src" / "lib" / "live-order" / "runner.ts"


def test_neomaa_identity_and_magic_unchanged() -> None:
    types = TYPES.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    assert 'NEOMAA_EXPECTED_LOGIN = "7745107"' in types
    assert 'NEOMAA_EXPECTED_SERVER = "Neomaaa-Live"' in types
    assert 'NEOMAA_LIVE_CONFIRM = "NEOMAA-7745107"' in types
    assert "magic: 20263852" in runner


def test_neomaa_probe_has_disconnected_status() -> None:
    types = TYPES.read_text(encoding="utf-8")
    probe = PROBE.read_text(encoding="utf-8")
    ui = UI.read_text(encoding="utf-8")
    assert '| "disconnected"' in types
    assert "deriveFileBridgeConnectionStatus" in probe
    assert "Not an auth failure" in probe
    assert "trade server offline" in ui
    assert 'status: "disconnected"' in ui
