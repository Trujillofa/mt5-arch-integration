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
    # Owning process; the only reliable way to tell one broker's terminal from
    # another's, since every prefix runs the same class and identical geometry.
    pid: int | None = None


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
                pid=int(row["pid"]) if str(row.get("pid", "")).lstrip("-").isdigit() else None,
            )
        )
    return out


def select_main_terminal(
    clients: Sequence[ClientRef],
    *,
    wineprefix: str | None = None,
) -> ClientRef | None:
    """Main MT5 shell, scoped to one Wine prefix when the pids allow it.

    Every broker runs the same ``terminal64.exe`` class at the same size, so the
    largest-area heuristic alone picks an arbitrary broker once two terminals are
    up — and window ops then act on the wrong live account. When any candidate
    carries a pid we filter to the prefix and return None if it has no window,
    which is what lets ghost detection see a per-broker ghost. Fixtures and older
    Hyprland report no pid; there we cannot distinguish, so the heuristic stands.
    """
    mains = [c for c in clients if is_main_terminal_client(c)]
    if not mains:
        return None
    if any(c.pid is not None for c in mains):
        prefix = wineprefix or os.environ.get("WINEPREFIX")
        if prefix:
            owned = set(list_terminal64_pids(wineprefix=prefix))
            mains = [c for c in mains if c.pid in owned]
            if not mains:
                return None
    # Prefer largest area (main shell vs small dialogs misclassified)
    return max(mains, key=lambda c: c.size[0] * c.size[1])


def list_terminal64_clients(
    clients: Sequence[ClientRef],
    *,
    wineprefix: str | None = None,
) -> list[ClientRef]:
    """All Hyprland clients with class terminal64.exe (main + Login + charts).

    Scoped to one prefix when the pids allow it — see ``select_main_terminal``.
    A ghost is "process alive, zero windows"; counting another broker's windows
    here is what hides one broker's ghost behind another broker's healthy shell.
    """
    out = [c for c in clients if c.class_name == "terminal64.exe"]
    if any(c.pid is not None for c in out):
        prefix = wineprefix or os.environ.get("WINEPREFIX")
        if prefix:
            owned = set(list_terminal64_pids(wineprefix=prefix))
            return [c for c in out if c.pid in owned]
    return out


def terminal64_process_running(*, wineprefix: str | None = None) -> bool:
    """True if a Wine MetaTrader terminal64.exe process exists.

    With a prefix (or WINEPREFIX set) this answers for that prefix only, so
    "is FP running?" is not satisfied by Vantage's terminal.
    """
    prefix = wineprefix or os.environ.get("WINEPREFIX")
    if prefix:
        return bool(list_terminal64_pids(wineprefix=prefix))
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


def park_windows_silent(
    addresses: Sequence[str],
    workspace: int,
    *,
    dry_run: bool = False,
) -> list[str]:
    """Move windows to ``workspace`` without following focus."""
    cmds: list[str] = []
    for addr in addresses:
        if not addr:
            continue
        sel = addr if str(addr).startswith("address:") else f"address:{addr}"
        lua = lua_move_window_workspace(sel, workspace, follow=False)
        cmds.append(lua)
        if not dry_run:
            hypr_eval(lua)
    return cmds


def park_prefix_terminals_silent(wineprefix: str, workspace: int) -> list[str]:
    """Park one Wine prefix's terminal64 windows without stealing the active workspace."""
    if not wineprefix:
        return []
    try:
        clients = fetch_clients()
    except (RuntimeError, json.JSONDecodeError, TypeError, OSError):
        return []
    owned = list_terminal64_clients(clients, wineprefix=wineprefix)
    if not owned:
        login = os.environ.get("MT5_LOGIN", "")
        if login:
            owned = [
                c
                for c in clients
                if c.class_name == "terminal64.exe" and login in (c.title or "")
            ]
    return park_windows_silent([c.address for c in owned], workspace)


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


def lua_set_floating(window: str) -> str:
    return (
        "hl.dispatch(hl.dsp.window.float({ "
        f"window = {_lua_quote(window)}, action = 'enable' }}))"
    )


# --- Off-screen parking -------------------------------------------------
#
# Wine works purely in X11 coordinates and knows nothing about Hyprland
# workspaces. Hyprland keeps XWayland windows on *hidden* workspaces mapped at
# their real geometry, and tiles every window on a monitor to the same rect, so
# two books on one monitor are literally the same rectangle to X11. The X
# server then routes pointer events there by geometry and stacking order, and
# the hidden book can be the topmost one -- that is the "scrolling Vantage
# moves FTMO" / "right-click opens two menus" failure.
#
# Hyprland ignores external X11 restack and iconify requests, so the only lever
# is geometry: float the hidden book and move it below every monitor. The
# pointer is confined to the monitor area (y < screen height), so a book parked
# at y = PARK_Y can never be under the cursor, while staying mapped and fully
# alive -- EAs, ticks and the file bridge are untouched.

PARK_X = 40
PARK_Y = 3000  # every monitor bottom edge is far above this
PARK_STRIDE = 200  # parked books get distinct rects too, never a shared one


@dataclass(frozen=True, slots=True)
class ParkPlan:
    """One book's desired parking state."""

    address: str
    title: str
    action: str  # "park" | "unpark" | "keep"
    x: int = 0
    y: int = 0


def is_book_window(client: ClientRef, *, min_size: int = 200) -> bool:
    """A real MT5 shell window, not a Wine popup/tooltip/dialog leftover.

    Reuses the main-terminal filter so Login (which hyprland.lua floats on
    purpose), Navigator, Toolbox and undocked charts are all excluded -- parking
    those would fight a deliberate window rule. The size floor additionally
    drops the orphaned 195x40 surfaces Wine leaves behind, which are already
    harmless and would only churn Wine.
    """
    return (
        is_main_terminal_client(client)
        and client.size[0] >= min_size
        and client.size[1] >= min_size
    )


def is_parked(client: ClientRef, *, park_y: int = PARK_Y) -> bool:
    return client.floating and client.at[1] >= park_y


def rects_overlap(a: ClientRef, b: ClientRef) -> bool:
    """True when two windows share any X11 pixel -- the crosstalk precondition."""
    ax, ay = a.at
    aw, ah = a.size
    bx, by = b.at
    bw, bh = b.size
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def plan_park(
    clients: Sequence[ClientRef],
    *,
    visible_workspaces: Sequence[int],
    parked_addresses: Sequence[str] = (),
    park_x: int = PARK_X,
    park_y: int = PARK_Y,
    stride: int = PARK_STRIDE,
) -> list[ParkPlan]:
    """Park hidden books that would steal a visible book's input; restore the rest.

    Pure: takes parsed clients plus the workspace ids currently displayed on
    some monitor, and returns one plan per book.

    Only a hidden book whose rectangle *overlaps a book that is on screen* can
    steal input -- that needs both of them on one monitor. A hidden book alone
    on its monitor is harmless, and parking it would float/tile-churn Wine for
    nothing; that churn is what wedges a terminal, and the live book would take
    it on every workspace switch. So such a book plans as "keep".

    A parked book's rectangle is off-screen and therefore overlaps nothing, so
    it stays parked until its own workspace comes back on screen. That
    hysteresis is deliberate: it stops a book flapping as other workspaces move.

    "keep" means already correct -- callers must skip those.
    """
    visible = {int(w) for w in visible_workspaces}
    known_parked = set(parked_addresses)
    books = [c for c in clients if is_book_window(c)]
    books.sort(key=lambda c: (c.workspace_id if c.workspace_id is not None else -1, c.address))
    on_screen = [c for c in books if c.workspace_id in visible]

    plans: list[ParkPlan] = []
    slot = 0
    for client in books:
        # Geometry alone is not enough: moving a parked book to another
        # workspace makes Hyprland clamp it back into view, so it is still
        # floating but no longer sits at the park coordinates. Without the
        # caller's record of what it parked, such a book would be left floating
        # for good instead of returning to the tiled layout.
        parked = is_parked(client, park_y=park_y) or client.address in known_parked
        if client.workspace_id in visible:
            plans.append(
                ParkPlan(client.address, client.title, "unpark" if parked else "keep")
            )
            continue
        conflicts = any(
            other.address != client.address and rects_overlap(client, other)
            for other in on_screen
        )
        if not conflicts:
            plans.append(ParkPlan(client.address, client.title, "keep"))
            continue
        target_y = park_y + slot * stride
        slot += 1
        action = "keep" if parked and client.at == (park_x, target_y) else "park"
        plans.append(ParkPlan(client.address, client.title, action, park_x, target_y))
    return plans


def plan_unpark_all(clients: Sequence[ClientRef], *, park_y: int = PARK_Y) -> list[ParkPlan]:
    """Restore every parked book to tiled. The undo for plan_park."""
    return [
        ParkPlan(c.address, c.title, "unpark")
        for c in clients
        if is_book_window(c) and is_parked(c, park_y=park_y)
    ]


def lua_for_park_plan(plan: ParkPlan) -> list[str]:
    """Lua statements realising one plan. Empty for "keep"."""
    sel = plan.address if plan.address.startswith("address:") else f"address:{plan.address}"
    if plan.action == "park":
        return [lua_set_floating(sel), lua_move_window_xy(sel, plan.x, plan.y)]
    if plan.action == "unpark":
        return [lua_set_tiled(sel)]
    return []


def apply_park_plans(plans: Sequence[ParkPlan], *, dry_run: bool = False) -> list[str]:
    """Execute plans via hyprctl eval. Returns the Lua actually issued."""
    issued: list[str] = []
    for plan in plans:
        for lua in lua_for_park_plan(plan):
            issued.append(lua)
            if not dry_run:
                hypr_eval(lua)
    return issued


def visible_workspace_ids(monitors_payload: Any = None) -> list[int]:
    """Workspace ids currently displayed on some monitor."""
    data = monitors_payload if monitors_payload is not None else _hyprctl_json(["monitors"])
    out: list[int] = []
    for row in data:
        if row.get("disabled"):
            continue
        ws = row.get("activeWorkspace") or {}
        if isinstance(ws, dict) and "id" in ws:
            out.append(int(ws["id"]))
    return out


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
