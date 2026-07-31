"""CLI: plan/apply full-screen placement for the main MetaTrader window."""

from __future__ import annotations

import argparse
import json
import sys

from mt5_arch.hypr_geometry import (
    apply_placement,
    placement_within_tolerance,
    plan_fullscreen,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mt5-arch-window",
        description="Maximize/fullscreen main MT5 terminal on active Hyprland monitor",
    )
    p.add_argument(
        "--mode",
        choices=("maximize", "fullscreen"),
        default="maximize",
        help="maximize (move+resize, preferred) or exclusive-style fullscreen",
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
    try:
        mon, placement, main = plan_fullscreen(
            mode=args.mode,
            monitor_name=args.monitor,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1

    payload = {
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
        "dry_run": args.dry_run,
        "virtual_desktop": False,
    }

    if main is None:
        payload["status"] = "no_main_window"
        payload["hint"] = (
            "Start MT5 (./scripts/04-start-terminal.sh --detach) then re-run. "
            "Charts must stay as tabs in the main window — not undocked."
        )
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"monitor: {mon.name} {mon.width}x{mon.height} @ ({mon.x},{mon.y})")
            print(f"target:  {placement.width}x{placement.height} mode={placement.mode}")
            print("main:    (not found — dry-run geometry still valid)")
            print(payload["hint"])
        # Planning geometry without MT5 is success (operator can start terminal next)
        return 0

    cmds = apply_placement(main, placement, dry_run=args.dry_run)
    payload["commands"] = cmds
    payload["status"] = "planned" if args.dry_run else "applied"

    if not args.dry_run:
        # re-fetch size if possible
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
                    again.size, placement, tol_px=64
                )
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
