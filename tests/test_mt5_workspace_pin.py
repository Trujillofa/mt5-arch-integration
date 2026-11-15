"""Per-broker workspace pinning must come from the Wine prefix, not a title rule.

Every book shares XWayland class ``terminal64.exe`` and a terminal maps as
"MetaTrader 5" and only gains its broker name after login, so a Hyprland
title rule cannot place one. Placement is by prefix via
``park_prefix_terminals_background``, and the workspace it targets is
``MT5_WORKSPACE`` (per broker) falling back to ``MT5_BG_WORKSPACE``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "scripts/lib.sh"
START_04 = REPO / "scripts/04-start-terminal.sh"
START_21 = REPO / "scripts/21-start-broker-background.sh"
ALIGN_25 = REPO / "scripts/25-align-xwayland-monitors.sh"
VANTAGE_ENV = REPO / "config/brokers/vantage.env"


def _bash(snippet: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", snippet],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), **(env or {})},
        check=False,
    )


def _workspace(env: dict[str, str] | None = None) -> str:
    proc = _bash("source scripts/lib.sh; mt5_target_workspace", env=env)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_defaults_to_the_shared_parking_workspace() -> None:
    assert _workspace() == "11"


def test_bg_workspace_overrides_the_default() -> None:
    assert _workspace({"MT5_BG_WORKSPACE": "9"}) == "9"


def test_per_broker_pin_wins_over_the_shared_one() -> None:
    assert _workspace({"MT5_WORKSPACE": "5", "MT5_BG_WORKSPACE": "11"}) == "5"


def test_vantage_env_pins_a_workspace_off_the_prop_firm_group() -> None:
    proc = _bash(
        "source scripts/lib.sh; set -a; source config/brokers/vantage.env; set +a; "
        "mt5_target_workspace"
    )
    assert proc.returncode == 0, proc.stderr
    pinned = proc.stdout.strip()
    assert pinned.isdigit()
    # The point of the pin: live Vantage must not land in the prop-firm tab group.
    assert pinned != "11"


def test_start_scripts_resolve_the_workspace_through_the_helper() -> None:
    for script in (START_04, START_21):
        text = script.read_text(encoding="utf-8")
        assert "mt5_target_workspace" in text, f"{script.name} hardcodes its workspace"


def test_broker_loop_unsets_the_pin_between_brokers() -> None:
    # 21 sources one broker profile per iteration; a leftover MT5_WORKSPACE
    # would park the next book on the previous broker's workspace.
    text = START_21.read_text(encoding="utf-8")
    unset_lines = [ln for ln in text.splitlines() if ln.strip().startswith("unset ")]
    assert any("MT5_WORKSPACE" in ln for ln in unset_lines), unset_lines


def test_vantage_stays_excluded_from_the_background_helper() -> None:
    # Live book: 21 must keep refusing the Vantage prefix outright.
    assert "mt5-vantage" in START_21.read_text(encoding="utf-8")


def test_xwayland_alignment_script_never_re_enables_via_hl_monitor() -> None:
    # `hl.monitor` re-enable reports ok and leaves the output dark. Reload is
    # the only safe way back, because it re-applies monitors.lua where every
    # monitor is enabled.
    text = ALIGN_25.read_text(encoding="utf-8")
    body = "\n".join(
        ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")
    )
    assert "hyprctl reload" in body
    assert "disabled = true" in body
    # The only hl.monitor call in the body is the disable.
    hl_monitor_calls = [ln for ln in body.splitlines() if "hl.monitor(" in ln]
    assert hl_monitor_calls, "expected the disable call"
    for call in hl_monitor_calls:
        assert "disabled = true" in call, f"non-disable hl.monitor call: {call.strip()}"


def test_alignment_guard_is_not_prefix_scoped() -> None:
    """The guard must answer "is any book open", not "is this broker running".

    ``list_terminal64_pids()`` returns [] without a WINEPREFIX by design, so
    using it here silently disabled the guard once -- it found zero books with
    seven open.
    """
    text = ALIGN_25.read_text(encoding="utf-8")
    body = "\n".join(
        ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")
    )
    assert "list_terminal64_pids" not in body
    # It asks Hyprland for mapped windows instead.
    assert "hyprctl clients" in body
    assert "terminal64.exe" in body


def test_alignment_guard_refuses_by_default_and_has_a_force_escape() -> None:
    text = ALIGN_25.read_text(encoding="utf-8")
    assert "--force" in text
    assert "FORCE" in text
    # Refusal must be a hard stop, not a warning that falls through.
    assert "refusing to churn monitors under open books" in text


def test_alignment_script_is_executable_and_parses() -> None:
    assert ALIGN_25.stat().st_mode & 0o111, "25-align-xwayland-monitors.sh is not executable"
    proc = subprocess.run(
        ["bash", "-n", str(ALIGN_25)], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr
