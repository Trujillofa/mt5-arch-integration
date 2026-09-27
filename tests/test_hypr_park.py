"""Unit tests for off-screen parking of hidden MT5 books (no hyprctl required).

Regression cover for the XWayland crosstalk bug: every book on a monitor tiles
to the same X11 rectangle, and Hyprland keeps hidden-workspace XWayland windows
mapped there, so a book you cannot see can swallow the scroll or right-click
meant for the book you are looking at.
"""

from __future__ import annotations

import json

from mt5_arch.hypr_geometry import (
    PARK_STRIDE,
    PARK_X,
    PARK_Y,
    ClientRef,
    ParkPlan,
    apply_park_plans,
    is_book_window,
    is_parked,
    lua_for_park_plan,
    parse_clients_json,
    plan_park,
    plan_unpark_all,
    rects_overlap,
    visible_workspace_ids,
)


def book(
    *,
    address: str,
    title: str,
    workspace: int,
    at: tuple[int, int] = (12, 38),
    size: tuple[int, int] = (1896, 1030),
    floating: bool = False,
) -> ClientRef:
    return ClientRef(
        address=address,
        title=title,
        class_name="terminal64.exe",
        at=at,
        size=size,
        floating=floating,
        workspace_id=workspace,
    )


# Right-hand monitor: does not share a pixel with the left-hand books below.
VANTAGE = book(address="0xaaa", title="27496181 - VantageMarkets-Live 5", workspace=5,
               at=(1932, 38))
# Left-hand monitor. Every book tiled on one monitor lands on the same rect,
# which is the whole crosstalk precondition.
VANTAGE_LEFT = book(address="0xaaa", title="27496181 - VantageMarkets-Live 5", workspace=5)
FTMO = book(address="0xbbb", title="541163357 - FTMO-Server4", workspace=10)
WSF = book(address="0xccc", title="99 - WSF-Live", workspace=11)


def test_ghost_popup_is_not_a_book() -> None:
    """Wine's orphaned 195x40 empty-title surfaces must never be parked."""
    ghost = book(address="0xdead", title="", workspace=10, at=(1260, 692), size=(195, 40))
    assert not is_book_window(ghost)
    assert is_book_window(FTMO)


def test_small_titled_child_window_is_not_a_book() -> None:
    """A detached Navigator/tooltip has a title but is not the trading shell.

    Covers the size guard independently of the empty-title guard.
    """
    navigator = book(
        address="0xnav", title="Navigator", workspace=10, at=(100, 100), size=(195, 40)
    )
    assert not is_book_window(navigator)
    plans = plan_park([navigator, FTMO], visible_workspaces=[5])
    assert [p.address for p in plans] == ["0xbbb"]  # navigator excluded entirely


def test_non_terminal_windows_are_ignored() -> None:
    kitty = ClientRef(
        address="0xk", title="omarchy", class_name="kitty",
        at=(12, 38), size=(1896, 1030), floating=False, workspace_id=6,
    )
    assert not is_book_window(kitty)


def test_hidden_book_sharing_a_rect_is_parked() -> None:
    """The live case: two books on one monitor, one of them hidden."""
    plans = plan_park([VANTAGE_LEFT, FTMO], visible_workspaces=[5, 7])
    by_addr = {p.address: p for p in plans}
    assert by_addr["0xaaa"].action == "keep"  # on screen, already tiled
    assert by_addr["0xbbb"].action == "park"
    assert by_addr["0xbbb"].y >= PARK_Y


def test_hidden_book_on_its_own_monitor_is_left_alone() -> None:
    """No shared pixel means no crosstalk, so no float/tile churn.

    The live book would otherwise be churned on every workspace switch, and
    that churn is what wedges a Wine terminal.
    """
    plans = plan_park([VANTAGE, FTMO], visible_workspaces=[5, 7])
    assert {p.action for p in plans} == {"keep"}


def test_overlap_is_symmetric_and_strict() -> None:
    assert rects_overlap(VANTAGE_LEFT, FTMO)
    assert rects_overlap(FTMO, VANTAGE_LEFT)
    assert not rects_overlap(VANTAGE, FTMO)
    edge = book(address="0xe", title="edge", workspace=9, at=(1908, 38), size=(10, 10))
    assert not rects_overlap(FTMO, edge)  # FTMO spans x=12..1907 inclusive


def test_parked_books_get_distinct_rectangles() -> None:
    """Two parked books sharing one rect would reintroduce the very bug."""
    plans = plan_park([VANTAGE_LEFT, FTMO, WSF], visible_workspaces=[5])
    parked = [p for p in plans if p.action == "park"]
    assert len(parked) == 2
    assert parked[0].y != parked[1].y
    assert abs(parked[0].y - parked[1].y) == PARK_STRIDE


def test_park_target_is_below_every_monitor() -> None:
    """Pointer y is bounded by screen height; PARK_Y must sit far beyond it."""
    plans = plan_park([VANTAGE_LEFT, FTMO], visible_workspaces=[5])
    parked = [p for p in plans if p.action == "park"]
    assert parked[0].y > 1080 * 2


def test_book_returning_to_screen_is_unparked() -> None:
    parked_ftmo = book(
        address="0xbbb", title="541163357 - FTMO-Server4", workspace=10,
        at=(PARK_X, PARK_Y), floating=True,
    )
    plans = plan_park([parked_ftmo], visible_workspaces=[10])
    assert plans[0].action == "unpark"


def test_already_parked_book_is_kept_not_rechurned() -> None:
    """Float/tile churn is what wedges Wine -- a correct book must be a no-op."""
    parked_ftmo = book(
        address="0xbbb", title="541163357 - FTMO-Server4", workspace=10,
        at=(PARK_X, PARK_Y), floating=True,
    )
    plans = plan_park([VANTAGE_LEFT, parked_ftmo], visible_workspaces=[5])
    ftmo_plan = next(p for p in plans if p.address == "0xbbb")
    assert ftmo_plan.action == "keep"
    assert lua_for_park_plan(ftmo_plan) == []


def test_is_parked_requires_both_floating_and_offscreen() -> None:
    assert not is_parked(FTMO)
    assert not is_parked(book(address="0x1", title="t", workspace=9, floating=True))
    assert is_parked(
        book(address="0x2", title="t", workspace=9, at=(PARK_X, PARK_Y), floating=True)
    )


def test_unpark_all_restores_only_parked_books() -> None:
    parked = book(
        address="0xbbb", title="541163357 - FTMO-Server4", workspace=10,
        at=(PARK_X, PARK_Y), floating=True,
    )
    plans = plan_unpark_all([VANTAGE, parked])
    assert [p.address for p in plans] == ["0xbbb"]
    assert plans[0].action == "unpark"


def test_lua_for_park_floats_then_moves() -> None:
    lua = lua_for_park_plan(ParkPlan("0xbbb", "FTMO", "park", 40, 3000))
    assert len(lua) == 2
    assert "action = 'enable'" in lua[0]
    assert "x = 40" in lua[1] and "y = 3000" in lua[1]
    assert "address:0xbbb" in lua[0]


def test_lua_for_unpark_sets_tiled() -> None:
    lua = lua_for_park_plan(ParkPlan("0xbbb", "FTMO", "unpark"))
    assert len(lua) == 1
    assert "action = 'disable'" in lua[0]


def test_apply_park_plans_dry_run_issues_no_hyprctl(monkeypatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(
        "mt5_arch.hypr_geometry.hypr_eval", lambda lua: called.append(lua)
    )
    issued = apply_park_plans([ParkPlan("0xb", "FTMO", "park", 40, 3000)], dry_run=True)
    assert len(issued) == 2
    assert called == []


def test_visible_workspace_ids_skips_disabled_monitors() -> None:
    payload = [
        {"name": "HDMI-A-2", "activeWorkspace": {"id": 7}, "disabled": False},
        {"name": "HDMI-A-1", "activeWorkspace": {"id": 5}, "disabled": False},
        {"name": "HDMI-A-3", "activeWorkspace": {"id": 3}, "disabled": True},
    ]
    assert sorted(visible_workspace_ids(payload)) == [5, 7]


def test_real_hyprctl_payload_round_trips() -> None:
    """Shape taken from this host: FTMO hidden on ws10 while ws7 is displayed."""
    raw = json.dumps(
        [
            {
                "address": "0xbbb", "title": "541163357 - FTMO-Server4", "class": "terminal64.exe",
                "at": [12, 38], "size": [1896, 1030], "floating": False,
                "workspace": {"id": 10}, "pid": 210793,
            },
            {
                "address": "0xdead", "title": "", "class": "terminal64.exe",
                "at": [1260, 692], "size": [195, 40], "floating": False,
                "workspace": {"id": 10}, "pid": 210793,
            },
        ]
    )
    clients = parse_clients_json(raw) + [VANTAGE_LEFT]
    plans = plan_park(clients, visible_workspaces=[7, 5])
    assert len(plans) == 2  # the ghost popup is excluded
    ftmo_plan = next(p for p in plans if p.address == "0xbbb")
    assert ftmo_plan.action == "park"


def test_settled_plans_ignores_a_transient_read(monkeypatch) -> None:
    """A mid-switch Hyprland read must not trigger float/tile churn.

    Hyprland briefly reports the old activeWorkspace while the client's
    workspace has already moved; acting on that produces a spurious
    park/unpark pair, and float churn is what wedges Wine.
    """
    import argparse

    from mt5_arch import park_ops

    transient = [ParkPlan("0xbbb", "FTMO", "unpark")]
    stable = [ParkPlan("0xbbb", "FTMO", "park", 40, 3000)]
    reads = [transient, stable, stable]
    monkeypatch.setattr(park_ops, "current_plans", lambda **kw: reads.pop(0))
    monkeypatch.setattr(park_ops.time, "sleep", lambda _s: None)

    args = argparse.Namespace(park_x=40, park_y=3000, stride=200)
    got = park_ops.settled_plans(args)
    assert [p.action for p in got] == ["park"]
    assert reads == []  # took all three reads: first disagreed, next two agreed


def test_settled_plans_returns_immediately_when_nothing_to_do(monkeypatch) -> None:
    import argparse

    from mt5_arch import park_ops

    calls = {"n": 0}

    def one_read(**_kw):
        calls["n"] += 1
        return [ParkPlan("0xaaa", "Vantage", "keep")]

    monkeypatch.setattr(park_ops, "current_plans", one_read)
    args = argparse.Namespace(park_x=40, park_y=3000, stride=200)
    assert park_ops.settled_plans(args) == [ParkPlan("0xaaa", "Vantage", "keep")]
    assert calls["n"] == 1  # no settle delay when the layout is already correct


def test_login_dialog_is_never_parked() -> None:
    """hyprland.lua floats the Login window on purpose; parking it fights that."""
    login = book(address="0xlog", title="Login", workspace=10, size=(600, 400))
    assert not is_book_window(login)


def test_undocked_chart_is_not_a_book() -> None:
    chart = book(
        address="0xch", title="EURUSD, Euro vs US Dollar", workspace=10, size=(900, 700)
    )
    assert not is_book_window(chart)


def test_clamped_parked_book_is_still_unparked_via_tracked_address() -> None:
    """Moving a parked book to another workspace makes Hyprland clamp it back
    on screen, so it is floating but no longer at the park coordinates. Without
    the tracked address it would be left floating for good.
    """
    clamped = book(
        address="0xbbb", title="541163357 - FTMO-Server4", workspace=10,
        at=(2, 48), floating=True,
    )
    # Geometry alone: not recognised as parked -> would wrongly plan "keep".
    assert not is_parked(clamped)
    assert plan_park([clamped], visible_workspaces=[10])[0].action == "keep"
    # With the caller's record it is restored.
    plans = plan_park([clamped], visible_workspaces=[10], parked_addresses=["0xbbb"])
    assert plans[0].action == "unpark"


def test_tracked_address_does_not_unpark_a_hidden_book() -> None:
    clamped = book(
        address="0xbbb", title="541163357 - FTMO-Server4", workspace=10,
        at=(2, 48), floating=True,
    )
    plans = plan_park([clamped], visible_workspaces=[5], parked_addresses=["0xbbb"])
    assert plans[0].action == "keep"
