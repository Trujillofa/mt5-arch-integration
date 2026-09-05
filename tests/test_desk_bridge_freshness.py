"""Contract: Seven Desk Fetch must not call a stale file-bridge snapshot connected."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESK = ROOT / "apps" / "seven-desk" / "src"
HELPER = DESK / "lib" / "bridge-freshness.ts"
NEXT_CONFIG = DESK.parent / "next.config.ts"
CLIENT_DIR = DESK / "components"

PROBES = {
    "alphacapital": DESK / "lib" / "alphacapital" / "probe.ts",
    "fundednext": DESK / "lib" / "fundednext" / "probe.ts",
    "fundingpips": DESK / "lib" / "fundingpips" / "probe.ts",
    "fortraders": DESK / "lib" / "fortraders" / "probe.ts",
    "ftmo": DESK / "lib" / "ftmo" / "probe.ts",
    "neomaa": DESK / "lib" / "neomaa" / "probe.ts",
    "wsf": DESK / "lib" / "wsf" / "live-client.ts",
}

TYPES = {
    "alphacapital": DESK / "lib" / "alphacapital" / "types.ts",
    "fundednext": DESK / "lib" / "fundednext" / "types.ts",
    "fundingpips": DESK / "lib" / "fundingpips" / "types.ts",
    "fortraders": DESK / "lib" / "fortraders" / "types.ts",
    "ftmo": DESK / "lib" / "ftmo" / "types.ts",
    "neomaa": DESK / "lib" / "neomaa" / "types.ts",
    "wsf": DESK / "lib" / "wsf" / "types.ts",
}


def test_shared_helper_exists_and_defaults_match_file_bridge() -> None:
    helper = HELPER.read_text(encoding="utf-8")
    assert "export const DEFAULT_BRIDGE_MAX_AGE_SECONDS = 15" in helper
    assert "export function canReportConnected" in helper
    assert "export function inspectBridgeFreshness" in helper
    assert "export function deriveFileBridgeConnectionStatus" in helper
    assert "if (!freshness.heartbeatFresh) return false" in helper
    assert "if (freshness.terminalChecked && !freshness.terminalRunning) return false" in helper


def test_all_seven_probes_use_shared_helper() -> None:
    for name, path in PROBES.items():
        text = path.read_text(encoding="utf-8")
        assert '@/lib/bridge-freshness' in text, name
        assert "canReportConnected" in text or "deriveFileBridgeConnectionStatus" in text, name


def test_all_seven_status_unions_include_disconnected() -> None:
    for name, path in TYPES.items():
        text = path.read_text(encoding="utf-8")
        assert '| "disconnected"' in text, name


def test_stale_account_json_cannot_be_connected() -> None:
    helper = HELPER.read_text(encoding="utf-8")
    assert "if (!canReportConnected(input.freshness)) return \"disconnected\"" in helper
    assert "if (input.terminalConnected === false) return \"disconnected\"" in helper


def test_neomaa_weekend_is_disconnected_not_auth_failed() -> None:
    types = TYPES["neomaa"].read_text(encoding="utf-8")
    probe = PROBES["neomaa"].read_text(encoding="utf-8")
    ui = (DESK / "components" / "desk" / "neomaa-live-probe.tsx").read_text(encoding="utf-8")
    assert '| "disconnected"' in types
    assert "deriveFileBridgeConnectionStatus" in probe
    assert "Not an auth failure" in probe
    assert 'status: "disconnected"' in ui
    assert "trade server offline" in ui


def test_tailscale_origins_stay_on_next_config() -> None:
    text = NEXT_CONFIG.read_text(encoding="utf-8")
    assert '"*.ts.net"' in text
    assert '"100.95.218.24"' in text


def test_client_components_do_not_import_env() -> None:
    offenders: list[str] = []
    for path in CLIENT_DIR.rglob("*.tsx"):
        text = path.read_text(encoding="utf-8")
        if "/env" in text and "@/lib/" in text:
            for line in text.splitlines():
                if "from" in line and "/env" in line and "@/lib/" in line:
                    offenders.append(f"{path.relative_to(ROOT)}: {line.strip()}")
    assert offenders == []
