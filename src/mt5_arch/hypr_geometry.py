"""Hyprland monitor geometry helpers for full-screen / maximize MT5 windows.

Pure functions are unit-tested without hyprctl. I/O wrappers call hyprctl when present.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Monitor:
    name: str
    width: int
    height: int
    x: int = 0
    y: int = 0
    scale: float = 1.0
    focused: bool = False


@dataclass(frozen=True, slots=True)
class WindowPlacement:
    """Target placement for the main MT5 terminal window."""

    x: int
    y: int
    width: int
    height: int
    monitor: str
    mode: str  # "maximize" | "fullscreen"


@dataclass(frozen=True, slots=True)
class ClientRef:
    address: str
    title: str
    class_name: str
    at: tuple[int, int]
    size: tuple[int, int]
    floating: bool
    workspace_id: int | None = None


# Titles that are NOT the main trading terminal.
_CHILD_TITLE_RE = re.compile(
    r"(?i)^(login|navigator|toolbox|market watch|options|"
    r".*euro vs.*|.*,\s*euro vs.*|.*,\s*us dollar vs.*|"
    r".*vs us dol.*|.*vs yen.*|.*vs swiss.*)$"
)


def parse_monitors_json(payload: str | bytes | list[dict[str, Any]]) -> list[Monitor]:
    """Parse `hyprctl monitors -j` output into Monitor list."""
    data = json.loads(payload) if isinstance(payload, (str, bytes)) else payload
    out: list[Monitor] = []
    for row in data:
        out.append(
            Monitor(
                name=str(row.get("name", "")),
                width=int(row.get("width", 0)),
                height=int(row.get("height", 0)),
                x=int(row.get("x", 0)),
                y=int(row.get("y", 0)),
                scale=float(row.get("scale", 1.0) or 1.0),
                focused=bool(row.get("focused", False)),
            )
        )
    return out


def pick_active_monitor(
    monitors: Sequence[Monitor],
    *,
    preferred_name: str | None = None,
    active_workspace_monitor: str | None = None,
) -> Monitor:
    """Pick the monitor to fill.

    Priority: preferred_name → focused → active_workspace_monitor → first by x.
    """
    if not monitors:
        raise ValueError("no monitors")
    if preferred_name:
        for m in monitors:
            if m.name == preferred_name:
                return m
    for m in monitors:
        if m.focused:
            return m
    if active_workspace_monitor:
        for m in monitors:
            if m.name == active_workspace_monitor:
                return m
    return sorted(monitors, key=lambda m: (m.x, m.y))[0]


def compute_maximize_placement(
    monitor: Monitor,
    *,
    mode: str = "maximize",
    reserved_top: int = 0,
    reserved_bottom: int = 0,
    reserved_left: int = 0,
    reserved_right: int = 0,
) -> WindowPlacement:
    """Compute pixel placement filling the monitor (usable area after reserved edges).

    reserved_* allow accounting for bars; default 0 fills the full monitor rect
    (Hyprland exclusive/fullscreen or floating maximize).
    """
    if mode not in {"maximize", "fullscreen"}:
        raise ValueError(f"unknown mode {mode!r}")
    # hyprctl monitors -j width/height are layout pixels (already scale-aware).
    w = monitor.width
    h = monitor.height
    x = monitor.x + reserved_left
    y = monitor.y + reserved_top
    width = max(1, w - reserved_left - reserved_right)
    height = max(1, h - reserved_top - reserved_bottom)
    return WindowPlacement(
        x=x,
        y=y,
        width=width,
        height=height,
        monitor=monitor.name,
        mode=mode,
    )


def is_main_terminal_client(client: ClientRef | dict[str, Any]) -> bool:
    """True for main MT5 shell; false for Login/Navigator/undocked charts."""
    if isinstance(client, dict):
        class_name = str(client.get("class", "") or "")
        title = str(client.get("title", "") or "")
    else:
        class_name = client.class_name
        title = client.title
    if class_name != "terminal64.exe":
        return False
    if not title.strip():
        return False
    if title.strip().lower() == "login":
        return False
    if _CHILD_TITLE_RE.match(title.strip()):
        return False
    # Undocked chart windows look like "EURUSD, Euro vs US Dollar"
    if re.search(r",\s*.+\s+vs\s+", title, re.I):
        return False
    # Main window typically has broker/server or account netting
    if re.search(r"(?i)(wsfmarkets|netting|metatrader\s*5\s*$|metaquotes-demo)", title):
        return True
    # Fallback: account id prefix "118248 - ..." without "vs"
    return bool(re.match(r"^\d+\s*-\s*", title) and " vs " not in title.lower())


def parse_clients_json(payload: str | bytes | list[dict[str, Any]]) -> list[ClientRef]:
    data = json.loads(payload) if isinstance(payload, (str, bytes)) else payload
    out: list[ClientRef] = []
    for row in data:
        at = row.get("at") or [0, 0]
        size = row.get("size") or [0, 0]
        ws = row.get("workspace") or {}
        out.append(
            ClientRef(
                address=str(row.get("address", "")),
                title=str(row.get("title", "") or ""),
                class_name=str(row.get("class", "") or ""),
                at=(int(at[0]), int(at[1])),
                size=(int(size[0]), int(size[1])),
                floating=bool(row.get("floating", False)),
                workspace_id=int(ws["id"]) if isinstance(ws, dict) and "id" in ws else None,
            )
        )
    return out


def select_main_terminal(clients: Sequence[ClientRef]) -> ClientRef | None:
    mains = [c for c in clients if is_main_terminal_client(c)]
    if not mains:
        return None
    # Prefer largest area (main shell vs small dialogs misclassified)
    return max(mains, key=lambda c: c.size[0] * c.size[1])


def list_terminal64_clients(clients: Sequence[ClientRef]) -> list[ClientRef]:
    """All Hyprland clients with class terminal64.exe (main + Login + charts)."""
    return [c for c in clients if c.class_name == "terminal64.exe"]


def terminal64_process_running() -> bool:
    """True if a Wine MetaTrader terminal64.exe process exists."""
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                cmd = fh.read().replace(b"\x00", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if "bash" in cmd or "extglob" in cmd:
            continue
        if "terminal64.exe" in cmd:
            return True
    return False


def is_ghost_terminal(
    *,
    process_running: bool,
    main_window: ClientRef | None = None,
    any_terminal_window: bool | Sequence[ClientRef] | None = None,
) -> bool:
    """True only when process is alive and Hyprland has zero terminal64 windows.

    Login / undocked charts / partial titles still count as visible windows —
    those are *not* ghosts (killing them causes recover loops during startup).
    """
    if not process_running:
        return False
    if main_window is not None:
        return False
    if any_terminal_window is None:
        # Backward-compatible: treat missing window list as "unknown → not main"
        # only counts as ghost when caller passes any_terminal_window explicitly.
        return True
    if isinstance(any_terminal_window, bool):
        return not any_terminal_window
    return len(list_terminal64_clients(any_terminal_window)) == 0


def _lua_quote(value: str) -> str:
    """Single-quote a string for Hyprland 0.56 ``hyprctl eval`` Lua."""
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def lua_focus_window(window: str) -> str:
    return f"hl.dispatch(hl.dsp.focus({{ window = {_lua_quote(window)} }}))"


def lua_move_window_workspace(window: str, workspace: int, *, follow: bool = True) -> str:
    follow_lit = "true" if follow else "false"
    return (
        "hl.dispatch(hl.dsp.window.move({ "
        f"window = {_lua_quote(window)}, workspace = {int(workspace)}, "
        f"follow = {follow_lit} }}))"
    )


def lua_move_window_monitor(window: str, monitor: str, *, follow: bool = False) -> str:
    follow_lit = "true" if follow else "false"
    return (
        "hl.dispatch(hl.dsp.window.move({ "
        f"window = {_lua_quote(window)}, monitor = {_lua_quote(monitor)}, "
        f"follow = {follow_lit} }}))"
    )


def lua_move_window_xy(window: str, x: int, y: int) -> str:
    return (
        "hl.dispatch(hl.dsp.window.move({ "
        f"window = {_lua_quote(window)}, x = {int(x)}, y = {int(y)} }}))"
    )


def lua_set_tiled(window: str) -> str:
    return (
        "hl.dispatch(hl.dsp.window.float({ "
        f"window = {_lua_quote(window)}, action = 'disable' }}))"
    )


def lua_fullscreen_state(window: str, *, internal: int, client: int) -> str:
    return (
        "hl.dispatch(hl.dsp.window.fullscreen_state({ "
        f"window = {_lua_quote(window)}, internal = {int(internal)}, "
        f"client = {int(client)}, action = 'set' }}))"
    )


def hypr_eval(lua: str) -> subprocess.CompletedProcess[str]:
    """Run ``hyprctl eval`` (Hyprland 0.56+). Legacy ``dispatch NAME args`` is Lua now."""
    return subprocess.run(
        ["hyprctl", "eval", lua],
        check=False,
        capture_output=True,
        text=True,
    )


def environ_wineprefix(environ_bytes: bytes) -> str | None:
    """Return realpath of WINEPREFIX from a /proc/pid/environ blob, or None."""
    for part in environ_bytes.split(b"\x00"):
        if part.startswith(b"WINEPREFIX="):
            raw = part.split(b"=", 1)[1].decode("utf-8", "replace")
            if not raw:
                return None
            return os.path.realpath(os.path.expanduser(raw))
    return None


def pid_belongs_to_wineprefix(
    *,
    wineprefix: str,
    environ_bytes: bytes | None = None,
    maps_text: str | None = None,
) -> bool:
    """True when a process is bound to ``wineprefix`` (environ first, then maps)."""
    target = os.path.realpath(os.path.expanduser(wineprefix))
    if environ_bytes is not None:
        wp = environ_wineprefix(environ_bytes)
        if wp is not None:
            return wp == target
    if maps_text:
        return target in maps_text
    return False


def list_terminal64_pids(*, wineprefix: str | None = None) -> list[int]:
    """MetaTrader pids bound to ``wineprefix`` via /proc environ (not argv).

    Cmdline is usually ``./terminal64.exe /portable``; the prefix lives in
    ``WINEPREFIX=``. Empty prefix returns [] so callers never scan the host.
    """
    prefix = wineprefix or os.environ.get("WINEPREFIX")
    if not prefix:
        return []
    target = os.path.realpath(os.path.expanduser(prefix))
    keys = ("terminal64.exe", "MetaEditor64.exe", "metaeditor64.exe", "metatester64.exe")
    found: list[int] = []
    for pid_s in list(os.listdir("/proc")):
        if not pid_s.isdigit():
            continue
        try:
            with open(f"/proc/{pid_s}/cmdline", "rb") as fh:
                cmd = fh.read().replace(b"\x00", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if "bash" in cmd or "extglob" in cmd:
            continue
        if not any(k in cmd for k in keys) and "webview-exe-name=terminal64" not in cmd:
            continue
        env: bytes | None
        maps: str | None = None
        try:
            env = Path(f"/proc/{pid_s}/environ").read_bytes()
        except OSError:
            env = None
        if env is None or environ_wineprefix(env) is None:
            try:
                maps = Path(f"/proc/{pid_s}/maps").read_text(errors="replace")
            except OSError:
                maps = None
        if not pid_belongs_to_wineprefix(
            wineprefix=target, environ_bytes=env, maps_text=maps
        ):
            continue
        found.append(int(pid_s))
    return found


def kill_terminal64_processes(*, wineprefix: str | None = None) -> list[int]:
    """SIGTERM then SIGKILL MetaTrader processes in one Wine prefix.

    Refuses a host-wide kill when no prefix is given so FP/Exness stay up.
    """
    import signal
    import time

    killed: list[int] = []
    for pid in list_terminal64_pids(wineprefix=wineprefix):
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except ProcessLookupError:
            pass
    time.sleep(1.5)
    for pid in killed:
        try:
            os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return killed


def placement_within_tolerance(
    actual_size: tuple[int, int],
    expected: WindowPlacement,
    *,
    tol_px: int = 48,
) -> bool:
    """True if actual W×H is within tol of expected (taskbars / borders)."""
    aw, ah = actual_size
    return abs(aw - expected.width) <= tol_px and abs(ah - expected.height) <= tol_px


def _hyprctl_json(args: list[str]) -> Any:
    proc = subprocess.run(
        ["hyprctl", *args, "-j"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"hyprctl {' '.join(args)} failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def fetch_monitors() -> list[Monitor]:
    return parse_monitors_json(_hyprctl_json(["monitors"]))


def fetch_clients() -> list[ClientRef]:
    return parse_clients_json(_hyprctl_json(["clients"]))


def fetch_active_workspace_monitor() -> str | None:
    try:
        data = _hyprctl_json(["activeworkspace"])
        return str(data.get("monitor") or "") or None
    except (RuntimeError, json.JSONDecodeError, TypeError):
        return None


def patch_mt5_terminal_ini(
    placement: WindowPlacement,
    *,
    wineprefix: str | None = None,
) -> str | None:
    """Write [Window] geometry into portable MT5 terminal.ini so Wine keeps size.

    Returns path written, or None if missing.
    """
    prefix = Path(wineprefix or os.environ.get("WINEPREFIX", Path.home() / ".mt5")).expanduser()
    ini = prefix / "drive_c" / "Program Files" / "MetaTrader 5" / "Config" / "terminal.ini"
    if not ini.is_file():
        return None
    raw = ini.read_bytes()
    try:
        text = raw.decode("utf-16-le")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="ignore")
    bom = text.startswith("\ufeff")
    if bom:
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Relative coords on that monitor: Wine uses client-ish window rect
    left, top = 0, 0
    right, bottom = placement.width, placement.height
    replacements = {
        "Fullscreen": "0",
        "FullscreenView": "0",
        "Type": "1",
        "Left": str(left),
        "Top": str(top),
        "Right": str(right),
        "Bottom": str(bottom),
    }
    lines = text.split("\n")
    out: list[str] = []
    in_window = False
    seen_keys: set[str] = set()
    for line in lines:
        if line.strip() == "[Window]":
            in_window = True
            out.append(line)
            continue
        if in_window and line.startswith("["):
            # flush any missing keys before next section
            for k, v in replacements.items():
                if k not in seen_keys:
                    out.append(f"{k}={v}")
            in_window = False
            out.append(line)
            continue
        if in_window and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in replacements:
                out.append(f"{key}={replacements[key]}")
                seen_keys.add(key)
                continue
        out.append(line)
    if in_window:
        for k, v in replacements.items():
            if k not in seen_keys:
                out.append(f"{k}={v}")
    new_text = "\ufeff" + "\n".join(out).replace("\n", "\r\n")
    ini.write_bytes(new_text.encode("utf-16-le"))
    return str(ini)


def apply_placement(
    client: ClientRef,
    placement: WindowPlacement,
    *,
    dry_run: bool = False,
    wineprefix: str | None = None,
    patch_ini: bool = True,
) -> list[str]:
    """Dispatch Hyprland commands to maximize/fullscreen the client.

    Uses absolute ``fullscreen_state`` (not toggle) so re-runs stay stable.
    - maximize → internal=1 client=1 (fills monitor minus gaps; Wine-safe)
    - fullscreen → internal=2 client=2 (exclusive; can unmap after chart clicks)

    Hyprland 0.56 evaluates ``hyprctl dispatch`` as Lua. Call ``hyprctl eval``
    with ``hl.dispatch(hl.dsp.*)`` tables (address selectors stay per-window).
    """
    sel = f"address:{client.address}"
    internal = 2 if placement.mode == "fullscreen" else 1
    steps = [
        lua_focus_window(sel),
        lua_move_window_monitor(sel, placement.monitor),
        lua_set_tiled(sel),
        lua_fullscreen_state(sel, internal=internal, client=internal),
    ]

    cmds = list(steps)
    if patch_ini:
        cmds.append(f"# patch terminal.ini -> {placement.width}x{placement.height}")
    if dry_run:
        return cmds
    if patch_ini:
        patch_mt5_terminal_ini(placement, wineprefix=wineprefix)
    for lua in steps:
        hypr_eval(lua)
    # Second pass: only re-assert absolute fullscreenstate.
    # Re-running settiled/movewindow here clears maximize (fs → 0).
    import time

    time.sleep(0.35)
    hypr_eval(lua_focus_window(sel))
    hypr_eval(lua_fullscreen_state(sel, internal=internal, client=internal))
    time.sleep(0.2)
    hypr_eval(lua_fullscreen_state(sel, internal=internal, client=internal))
    return cmds


def plan_fullscreen(
    *,
    mode: str = "maximize",
    monitor_name: str | None = None,
    monitors: Sequence[Monitor] | None = None,
    clients: Sequence[ClientRef] | None = None,
    active_workspace_monitor: str | None = None,
) -> tuple[Monitor, WindowPlacement, ClientRef | None]:
    """Compute placement and optional main client (None if no MT5)."""
    mons = list(monitors) if monitors is not None else fetch_monitors()
    mon = pick_active_monitor(
        mons,
        preferred_name=monitor_name,
        active_workspace_monitor=active_workspace_monitor
        if active_workspace_monitor is not None
        else fetch_active_workspace_monitor(),
    )
    placement = compute_maximize_placement(mon, mode=mode)
    main: ClientRef | None = None
    if clients is not None:
        main = select_main_terminal(clients)
    else:
        try:
            main = select_main_terminal(fetch_clients())
        except RuntimeError:
            main = None
    return mon, placement, main
