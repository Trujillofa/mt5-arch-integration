"""CLI: keep hidden MT5 books out of X11's pointer-reachable coordinate space.

Every book is an XWayland client, so Wine routes input by X11 geometry and has
no notion of a Hyprland workspace. Hyprland leaves hidden-workspace windows
mapped at full size and tiles every window on a monitor to the same rect, so a
book you cannot see can be the topmost X11 window under your cursor and eat the
scroll or right-click meant for the book you are looking at.

This parks each hidden book below every monitor (floating, y >= PARK_Y) where
the pointer can never reach it, and restores it the moment its workspace comes
back on screen. Books stay mapped and fully alive throughout -- EAs, ticks and
the file bridge never notice.

    mt5-arch-park --status
    mt5-arch-park --once --dry-run
    mt5-arch-park --once
    mt5-arch-park --watch          # follow Hyprland workspace events
    mt5-arch-park --unpark-all     # undo; restore every book to tiled
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time

from mt5_arch.hypr_geometry import (
    PARK_STRIDE,
    PARK_X,
    PARK_Y,
    ParkPlan,
    apply_park_plans,
    fetch_clients,
    is_book_window,
    is_parked,
    plan_park,
    plan_unpark_all,
    visible_workspace_ids,
)

# Hyprland socket2 lines that can change which book is on screen.
WATCH_EVENTS = (
    "workspace>>",
    "focusedmon>>",
    "movewindow>>",
    "openwindow>>",
    "closewindow>>",
    "monitoradded>>",
    "monitorremoved>>",
)


def event_socket_path() -> str:
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    if not sig:
        raise RuntimeError("HYPRLAND_INSTANCE_SIGNATURE unset -- not inside Hyprland")
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return f"{runtime}/hypr/{sig}/.socket2.sock"


def state_path() -> str:
    """Addresses this tool parked, for the lifetime of the Hyprland session.

    Window addresses do not survive a reboot, and neither should this file --
    XDG_RUNTIME_DIR is cleared for us.
    """
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return f"{runtime}/mt5-arch-park.state.json"


def load_parked() -> set[str]:
    try:
        with open(state_path(), encoding="utf-8") as fh:
            return set(json.load(fh))
    except (OSError, ValueError):
        return set()


def save_parked(addresses: set[str]) -> None:
    try:
        with open(state_path(), "w", encoding="utf-8") as fh:
            json.dump(sorted(addresses), fh)
    except OSError:
        pass


def record_plans(plans: list[ParkPlan]) -> None:
    """Keep the parked set in step with what was just applied."""
    parked = load_parked()
    for plan in plans:
        if plan.action == "park":
            parked.add(plan.address)
        elif plan.action == "unpark":
            parked.discard(plan.address)
    save_parked(parked)


def current_plans(*, park_x: int, park_y: int, stride: int) -> list[ParkPlan]:
    return plan_park(
        fetch_clients(),
        visible_workspaces=visible_workspace_ids(),
        parked_addresses=tuple(load_parked()),
        park_x=park_x,
        park_y=park_y,
        stride=stride,
    )


def actionable(plans: list[ParkPlan]) -> list[ParkPlan]:
    return [p for p in plans if p.action != "keep"]


def run_once(args: argparse.Namespace) -> list[ParkPlan]:
    plans = current_plans(park_x=args.park_x, park_y=args.park_y, stride=args.stride)
    todo = actionable(plans)
    if todo:
        apply_park_plans(todo, dry_run=args.dry_run)
        if not args.dry_run:
            record_plans(todo)
    return plans


def print_status(args: argparse.Namespace) -> int:
    clients = fetch_clients()
    visible = visible_workspace_ids()
    books = [c for c in clients if is_book_window(c)]
    if args.json:
        print(
            json.dumps(
                {
                    "visible_workspaces": visible,
                    "books": [
                        {
                            "title": c.title,
                            "workspace": c.workspace_id,
                            "at": list(c.at),
                            "parked": is_parked(c, park_y=args.park_y),
                            "on_screen": c.workspace_id in set(visible),
                        }
                        for c in books
                    ],
                },
                indent=2,
            )
        )
        return 0
    print(f"visible workspaces: {sorted(set(visible))}")
    if not books:
        print("no MT5 books open")
        return 0
    for c in books:
        if is_parked(c, park_y=args.park_y):
            state = "parked"
        elif c.workspace_id in set(visible):
            state = "on-screen"
        else:
            state = "hidden"
        print(f"  ws={c.workspace_id:<3} at=({c.at[0]},{c.at[1]})  {state:<9}  {c.title[:52]}")
    overlapping = actionable(
        plan_park(clients, visible_workspaces=visible, park_y=args.park_y)
    )
    if overlapping:
        print(f"\n{len(overlapping)} hidden book(s) share a rectangle with an on-screen book.")
        print("Harmless while Hyprland keeps the visible book on top of the real X stacking")
        print("(it did in every test). Park manually only if input is actually misrouted:")
        print("  ./scripts/26-park-books.sh --once")
    return 0


def _plan_key(plans: list[ParkPlan]) -> tuple:
    return tuple(sorted((p.address, p.action, p.x, p.y) for p in plans))


def settled_plans(
    args: argparse.Namespace, *, settle: float = 0.12, tries: int = 4
) -> list[ParkPlan]:
    """Re-plan until two consecutive reads agree.

    Hyprland reports transient geometry and activeWorkspace mid-switch, so a
    naive read produces spurious park/unpark pairs. Acting on those churns
    Wine's float/tile state for nothing, and float churn is what wedges a book.
    """
    plans = current_plans(park_x=args.park_x, park_y=args.park_y, stride=args.stride)
    previous = _plan_key(plans)
    for _ in range(tries - 1):
        if not actionable(plans):
            return plans
        time.sleep(settle)
        plans = current_plans(park_x=args.park_x, park_y=args.park_y, stride=args.stride)
        current = _plan_key(plans)
        if current == previous:
            return plans
        previous = current
    return plans


def watch(args: argparse.Namespace) -> int:
    path = event_socket_path()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(path)
    print(f"watching {path}", file=sys.stderr, flush=True)
    initial = actionable(settled_plans(args))
    apply_park_plans(initial, dry_run=args.dry_run)
    if not args.dry_run:
        record_plans(initial)
    buf = b""
    with sock:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                return 0
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode("utf-8", "replace")
                if not text.startswith(WATCH_EVENTS):
                    continue
                todo = actionable(settled_plans(args))
                if not todo:
                    continue
                apply_park_plans(todo, dry_run=args.dry_run)
                if not args.dry_run:
                    record_plans(todo)
                for plan in todo:
                    print(
                        f"{plan.action}: ({plan.x},{plan.y}) {plan.title[:48]}",
                        file=sys.stderr,
                        flush=True,
                    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mt5-arch-park",
        description="Park hidden MT5 books outside pointer-reachable X11 coordinates",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true", help="report book state and exit")
    mode.add_argument("--once", action="store_true", help="apply once and exit")
    mode.add_argument("--watch", action="store_true", help="follow Hyprland events")
    mode.add_argument("--unpark-all", action="store_true", help="restore every book to tiled")
    p.add_argument("--dry-run", action="store_true", help="print plan, issue no hyprctl")
    p.add_argument("--json", action="store_true", help="machine-readable --status")
    p.add_argument("--park-x", type=int, default=PARK_X)
    p.add_argument("--park-y", type=int, default=PARK_Y)
    p.add_argument("--stride", type=int, default=PARK_STRIDE)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not any((args.status, args.once, args.watch, args.unpark_all)):
        args.status = True
    try:
        if args.status:
            return print_status(args)
        if args.unpark_all:
            clients = fetch_clients()
            tracked = load_parked()
            plans = plan_unpark_all(clients, park_y=args.park_y)
            seen = {p.address for p in plans}
            plans += [
                ParkPlan(c.address, c.title, "unpark")
                for c in clients
                if c.address in tracked and c.address not in seen
            ]
            save_parked(set())
            for lua in apply_park_plans(plans, dry_run=args.dry_run):
                print(lua)
            print(f"restored {len(plans)} book(s)")
            return 0
        if args.once:
            for plan in current_plans(
                park_x=args.park_x, park_y=args.park_y, stride=args.stride
            ):
                if plan.action != "keep":
                    print(f"{plan.action:<7} ({plan.x},{plan.y})  {plan.title[:52]}")
            if not args.dry_run:
                run_once(args)
            return 0
        if args.watch:
            return watch(args)
    except (RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
