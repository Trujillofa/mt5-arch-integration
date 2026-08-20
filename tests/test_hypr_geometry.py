"""Unit tests for pure Hyprland geometry helpers (no hyprctl required)."""

from __future__ import annotations

import json

from mt5_arch.hypr_geometry import (
    ClientRef,
    Monitor,
    WindowPlacement,
    apply_placement,
    compute_maximize_placement,
    environ_wineprefix,
    is_main_terminal_client,
    lua_focus_window,
    lua_fullscreen_state,
    lua_move_window_workspace,
    lua_move_window_xy,
    parse_clients_json,
    parse_monitors_json,
    pick_active_monitor,
    pid_belongs_to_wineprefix,
    placement_within_tolerance,
    plan_fullscreen,
    select_main_terminal,
)

# Dual 1080p fixture matching this host layout (HDMI-A-2 @0,0 + HDMI-A-1 @1920,0)
DUAL_1080 = [
    Monitor(name="HDMI-A-2", width=1920, height=1080, x=0, y=0, scale=1.0, focused=True),
    Monitor(name="HDMI-A-1", width=1920, height=1080, x=1920, y=0, scale=1.0, focused=False),
]


def test_parse_monitors_dual_1080() -> None:
    raw = json.dumps(
        [
            {
                "name": "HDMI-A-2",
                "width": 1920,
                "height": 1080,
                "x": 0,
                "y": 0,
                "scale": 1.0,
                "focused": True,
            },
            {
                "name": "HDMI-A-1",
                "width": 1920,
                "height": 1080,
                "x": 1920,
                "y": 0,
                "scale": 1.0,
                "focused": False,
            },
        ]
    )
    mons = parse_monitors_json(raw)
    assert len(mons) == 2
    assert mons[0].name == "HDMI-A-2"
    assert mons[1].x == 1920


def test_pick_active_prefers_focused() -> None:
    m = pick_active_monitor(DUAL_1080)
    assert m.name == "HDMI-A-2"
    assert m.width == 1920


def test_pick_active_by_workspace_monitor() -> None:
    mons = [
        Monitor("HDMI-A-2", 1920, 1080, 0, 0, focused=False),
        Monitor("HDMI-A-1", 1920, 1080, 1920, 0, focused=False),
    ]
    m = pick_active_monitor(mons, active_workspace_monitor="HDMI-A-1")
    assert m.name == "HDMI-A-1"
    assert m.x == 1920


def test_pick_active_preferred_name() -> None:
    m = pick_active_monitor(DUAL_1080, preferred_name="HDMI-A-1")
    assert m.name == "HDMI-A-1"


def test_compute_maximize_left_monitor() -> None:
    mon = DUAL_1080[0]
    p = compute_maximize_placement(mon, mode="maximize")
    assert p.x == 0
    assert p.y == 0
    assert p.width == 1920
    assert p.height == 1080
    assert p.monitor == "HDMI-A-2"
    assert p.mode == "maximize"


def test_compute_maximize_right_monitor() -> None:
    mon = DUAL_1080[1]
    p = compute_maximize_placement(mon, mode="fullscreen")
    assert p.x == 1920
    assert p.y == 0
    assert p.width == 1920
    assert p.height == 1080
    assert p.mode == "fullscreen"


def test_compute_maximize_with_reserved_edges() -> None:
    mon = DUAL_1080[0]
    p = compute_maximize_placement(mon, reserved_top=40, reserved_bottom=0)
    assert p.y == 40
    assert p.height == 1040
    assert p.width == 1920


def test_is_main_terminal_client() -> None:
    assert is_main_terminal_client(
        ClientRef("0x1", "118248 - WSFmarkets-Server - Netting - EURUSD,H1", "terminal64.exe", (0, 0), (1600, 900), True)
    )
    assert not is_main_terminal_client(
        ClientRef("0x2", "Login", "terminal64.exe", (0, 0), (400, 300), True)
    )
    assert not is_main_terminal_client(
        ClientRef("0x3", "EURUSD, Euro vs US Dollar", "terminal64.exe", (0, 0), (900, 900), True)
    )
    assert not is_main_terminal_client(
        ClientRef("0x4", "Navigator", "terminal64.exe", (0, 0), (500, 500), True)
    )
    assert not is_main_terminal_client(
        ClientRef("0x5", "something", "kitty", (0, 0), (800, 600), False)
    )


def test_select_main_prefers_largest() -> None:
    clients = parse_clients_json(
        [
            {
                "address": "0xa",
                "title": "118248 - WSFmarkets-Server - Netting",
                "class": "terminal64.exe",
                "at": [10, 10],
                "size": [800, 600],
                "floating": True,
                "workspace": {"id": 2},
            },
            {
                "address": "0xb",
                "title": "118248 - WSFmarkets-Server - Netting - EURUSD,H1",
                "class": "terminal64.exe",
                "at": [0, 0],
                "size": [1920, 1080],
                "floating": True,
                "workspace": {"id": 2},
            },
            {
                "address": "0xc",
                "title": "EURUSD, Euro vs US Dollar",
                "class": "terminal64.exe",
                "at": [100, 100],
                "size": [900, 900],
                "floating": True,
                "workspace": {"id": 2},
            },
        ]
    )
    main = select_main_terminal(clients)
    assert main is not None
    assert main.address == "0xb"
    assert main.size == (1920, 1080)


def test_is_ghost_terminal() -> None:
    from mt5_arch.hypr_geometry import is_ghost_terminal

    main = ClientRef(
        "0x1",
        "118248 - WSFmarkets-Server - Netting",
        "terminal64.exe",
        (0, 0),
        (1920, 1080),
        False,
    )
    login = ClientRef("0x2", "Login", "terminal64.exe", (0, 0), (400, 300), True)
    # Backward-compat: no window list + no main ⇒ ghost
    assert is_ghost_terminal(process_running=True, main_window=None) is True
    assert is_ghost_terminal(process_running=False, main_window=None) is False
    assert is_ghost_terminal(process_running=True, main_window=main) is False
    assert is_ghost_terminal(process_running=False, main_window=main) is False
    # True ghost: process + zero windows
    assert (
        is_ghost_terminal(process_running=True, main_window=None, any_terminal_window=[])
        is True
    )
    # Login-only is NOT a ghost (avoids recover kill-loop during startup)
    assert (
        is_ghost_terminal(
            process_running=True, main_window=None, any_terminal_window=[login]
        )
        is False
    )
    assert (
        is_ghost_terminal(
            process_running=True, main_window=None, any_terminal_window=True
        )
        is False
    )


def test_list_terminal64_clients() -> None:
    from mt5_arch.hypr_geometry import list_terminal64_clients

    clients = [
        ClientRef("0xa", "Login", "terminal64.exe", (0, 0), (400, 300), True),
        ClientRef("0xb", "kitty", "kitty", (0, 0), (800, 600), False),
        ClientRef(
            "0xc",
            "118248 - WSFmarkets-Server - Netting",
            "terminal64.exe",
            (0, 0),
            (1900, 1000),
            False,
        ),
    ]
    terms = list_terminal64_clients(clients)
    assert len(terms) == 2
    assert {t.address for t in terms} == {"0xa", "0xc"}


def test_is_main_accepts_bracket_title() -> None:
    assert is_main_terminal_client(
        ClientRef(
            "0x1",
            "118248 - WSFmarkets-Server - Netting - [USDJPY,H1]",
            "terminal64.exe",
            (0, 0),
            (1900, 1000),
            True,
        )
    )


def test_placement_within_tolerance() -> None:
    mon = DUAL_1080[0]
    p = compute_maximize_placement(mon)
    assert placement_within_tolerance((1920, 1080), p, tol_px=0)
    assert placement_within_tolerance((1900, 1060), p, tol_px=48)
    assert not placement_within_tolerance((800, 600), p, tol_px=48)


def test_plan_fullscreen_dual_fixture_no_io() -> None:
    mon, placement, main = plan_fullscreen(
        mode="maximize",
        monitors=DUAL_1080,
        clients=[],
        active_workspace_monitor="HDMI-A-2",
    )
    assert mon.name == "HDMI-A-2"
    assert placement.width == 1920
    assert placement.height == 1080
    assert main is None


def test_patch_mt5_terminal_ini_window_geometry(tmp_path) -> None:
    from mt5_arch.hypr_geometry import WindowPlacement, patch_mt5_terminal_ini

    # Minimal portable tree
    cfg = (
        tmp_path
        / "drive_c"
        / "Program Files"
        / "MetaTrader 5"
        / "Config"
    )
    cfg.mkdir(parents=True)
    ini = cfg / "terminal.ini"
    content = "\ufeff[Window]\r\nFullscreen=0\r\nType=1\r\nLeft=45\r\nTop=-6\r\nRight=1645\r\nBottom=894\r\n"
    ini.write_bytes(content.encode("utf-16-le"))
    placement = WindowPlacement(0, 0, 1920, 1080, "HDMI-A-2", "maximize")
    path = patch_mt5_terminal_ini(placement, wineprefix=str(tmp_path))
    assert path == str(ini)
    text = ini.read_bytes().decode("utf-16-le")
    assert "Right=1920" in text
    assert "Bottom=1080" in text
    assert "Left=0" in text


def test_plan_fullscreen_right_monitor_with_client() -> None:
    clients = [
        ClientRef(
            "0xmt5",
            "118248 - WSFmarkets-Server - Netting - GBPUSD,H1",
            "terminal64.exe",
            (50, 50),
            (1600, 900),
            True,
            7,
        )
    ]
    mon, placement, main = plan_fullscreen(
        mode="maximize",
        monitor_name="HDMI-A-1",
        monitors=DUAL_1080,
        clients=clients,
        active_workspace_monitor="HDMI-A-2",
    )
    assert mon.name == "HDMI-A-1"
    assert placement.x == 1920
    assert placement.width == 1920
    assert main is not None
    assert main.address == "0xmt5"


def test_lua_dispatch_builders() -> None:
    focus = lua_focus_window("address:0xabc")
    assert focus == "hl.dispatch(hl.dsp.focus({ window = 'address:0xabc' }))"
    move = lua_move_window_workspace("class:terminal64.exe", 1, follow=True)
    assert "hl.dispatch(hl.dsp.window.move({" in move
    assert "window = 'class:terminal64.exe'" in move
    assert "workspace = 1" in move
    assert "follow = true" in move
    xy = lua_move_window_xy("class:terminal64.exe", 1940, 40)
    assert "x = 1940" in xy
    assert "y = 40" in xy
    fs = lua_fullscreen_state("address:0xabc", internal=1, client=1)
    assert "fullscreen_state" in fs
    assert "internal = 1" in fs
    assert "action = 'set'" in fs


def test_lua_quote_escapes_quotes() -> None:
    quoted = lua_focus_window("title:O'Brien")
    assert "title:O\\'Brien" in quoted


def test_apply_placement_dry_run_uses_lua_eval() -> None:
    client = ClientRef(
        "0xabc",
        "118248 - WSFmarkets-Server - Netting",
        "terminal64.exe",
        (0, 0),
        (1920, 1080),
        False,
    )
    placement = WindowPlacement(0, 0, 1920, 1080, "HDMI-A-2", "maximize")
    cmds = apply_placement(client, placement, dry_run=True, patch_ini=False)
    joined = "\n".join(cmds)
    assert "hl.dispatch(hl.dsp.focus({ window = 'address:0xabc' }))" in cmds
    assert "hl.dsp.window.fullscreen_state" in joined
    assert "focuswindow" not in joined
    assert "hyprctl dispatch" not in joined


def test_environ_wineprefix_and_pid_scope() -> None:
    blob = b"USER=x\x00WINEPREFIX=/home/yderf/.mt5-vantage\x00PATH=/usr/bin\x00"
    assert environ_wineprefix(blob).endswith(".mt5-vantage")
    assert pid_belongs_to_wineprefix(
        wineprefix="/home/yderf/.mt5-vantage",
        environ_bytes=blob,
    )
    assert not pid_belongs_to_wineprefix(
        wineprefix="/home/yderf/.mt5-fpmarkets",
        environ_bytes=blob,
    )
    assert pid_belongs_to_wineprefix(
        wineprefix="/home/yderf/.mt5-fpmarkets",
        maps_text="/home/yderf/.mt5-fpmarkets/drive_c/windows/system32/ntdll.dll",
    )
    assert not pid_belongs_to_wineprefix(
        wineprefix="/home/yderf/.mt5-vantage",
        environ_bytes=b"USER=x\x00",
        maps_text="/usr/lib/wine/ntdll.so",
    )


def test_kill_terminal64_refuses_without_prefix(monkeypatch) -> None:
    from mt5_arch.hypr_geometry import kill_terminal64_processes

    monkeypatch.delenv("WINEPREFIX", raising=False)
    assert kill_terminal64_processes() == []

