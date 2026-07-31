"""CLI: plan/apply full-screen placement for the main MetaTrader window."""

from __future__ import annotations

import argparse
import json
import sys

from mt5_arch.hypr_geometry import (
    apply_placement,
    is_ghost_terminal,
    placement_within_tolerance,
    plan_fullscreen,
    terminal64_process_running,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mt5-arch-window",
        description="Maximize main MT5 terminal on active Hyprland monitor",
    )
    p.add_argument(
        "--mode",
        choices=("maximize", "fullscreen"),
        default="maximize",
        help="maximize (tiled fill, preferred) or fullscreen-1 after tile",
    )
    p.add_argument("--monitor", default=None, help="Hyprland monitor name (e.g. HDMI-A-2)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan only; do not call hyprctl dispatch",
    )
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    proc = terminal64_process_running()
    try:
        mon, placement, main = plan_fullscreen(
            mode=args.mode,
            monitor_name=args.monitor,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1

    ghost = is_ghost_terminal(process_running=proc, main_window=main)

    payload: dict = {
        "monitor": {
            "name": mon.name,
            "width": mon.width,
            "height": mon.height,
            "x": mon.x,
            "y": mon.y,
            "scale": mon.scale,
            "focused": mon.focused,
        },
        "placement": {
            "mode": placement.mode,
            "x": placement.x,
            "y": placement.y,
            "width": placement.width,
            "height": placement.height,
        },
        "main_window": None
        if main is None
        else {
            "address": main.address,
            "title": main.title,
            "at": list(main.at),
            "size": list(main.size),
            "floating": main.floating,
        },
        "process_running": proc,
        "ghost_process": ghost,
        "dry_run": args.dry_run,
        "virtual_desktop": False,
    }

    if main is None:
        if ghost:
            payload["status"] = "ghost_process"
            payload["hint"] = (
                "MT5 process is running but the window is unmapped (Hyprland/Wine bug). "
                "Run: ./scripts/10-recover-terminal.sh"
            )
            code = 3
        else:
            payload["status"] = "no_main_window"
            payload["hint"] = (
                "Start MT5: ./scripts/04-start-terminal.sh --detach "
                "then re-run fullscreen. Charts as tabs only — not undocked."
            )
            code = 0 if args.dry_run else 2
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"monitor: {mon.name} {mon.width}x{mon.height} @ ({mon.x},{mon.y})")
            print(f"target:  {placement.width}x{placement.height} mode={placement.mode}")
            if ghost:
                print("main:    GHOST process (no Hyprland window)")
            else:
                print("main:    (not found)")
            print(payload["hint"])
        return code

    cmds = apply_placement(main, placement, dry_run=args.dry_run)
    payload["commands"] = cmds
    payload["status"] = "planned" if args.dry_run else "applied"

    if not args.dry_run:
        try:
            from mt5_arch.hypr_geometry import fetch_clients, select_main_terminal

            again = select_main_terminal(fetch_clients())
            if again is not None:
                payload["main_window_after"] = {
                    "title": again.title,
                    "at": list(again.at),
                    "size": list(again.size),
                }
                payload["within_tolerance"] = placement_within_tolerance(
                    again.size, placement, tol_px=96
                )
            elif terminal64_process_running():
                payload["status"] = "unmapped_after_apply"
                payload["hint"] = "Window vanished after resize; run ./scripts/10-recover-terminal.sh"
        except Exception:  # noqa: BLE001
            pass

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"monitor: {mon.name} {mon.width}x{mon.height} @ ({mon.x},{mon.y})")
        print(
            f"target:  {placement.width}x{placement.height} "
            f"at ({placement.x},{placement.y}) mode={placement.mode}"
        )
        print(f"main:    {main.title!r}")
        print(f"size:    {main.size[0]}x{main.size[1]}")
        print("virtual_desktop: no")
        if args.dry_run:
            print("commands:")
            for c in cmds:
                print(f"  hyprctl dispatch {c}")
        else:
            print(f"status:  {payload['status']}")
            if "within_tolerance" in payload:
                print(f"fit:     {payload['within_tolerance']}")
            if payload.get("status") == "unmapped_after_apply":
                print(payload.get("hint", ""))
    if payload.get("status") == "unmapped_after_apply":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
