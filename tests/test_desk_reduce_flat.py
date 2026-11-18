"""Contract: coordinator flat/reduce actor in DeskOrderBridge.

Static checks only — MQL5 is compiled at deploy time (MetaEditor F7).
The actor closes by explicit ticket and is never gated by control.json.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "mql5" / "Include" / "DeskOrderBridge.mqh"


def _source() -> str:
    return BRIDGE.read_text(encoding="utf-8")


def test_actions_flat_and_reduce_are_accepted() -> None:
    text = _source()
    assert 'const bool want_flat = (g_desk_action == "flat");' in text
    assert 'const bool want_reduce = (g_desk_action == "reduce");' in text
    assert "flat, or reduce" in text


def test_actor_requires_explicit_ticket() -> None:
    text = _source()
    assert "flat/reduce require an explicit position ticket" in text
    assert "if(g_desk_ticket == 0)" in text


def test_flat_is_idempotent_on_a_closed_ticket() -> None:
    text = _source()
    assert "bool DeskOrdPositionEverExisted(const ulong ticket)" in text
    assert "HistorySelectByPosition((long)ticket)" in text
    assert "HistoryDealsTotal() > 0" in text
    assert '"already_flat"' in text
    assert "idempotent flat" in text


def test_reduce_refuses_to_exceed_position_volume() -> None:
    text = _source()
    assert "reduce exceeds position volume — refusing" in text
    assert "close_vol > vol_before + 1e-8" in text


def test_actor_refuses_unconfigured_symbol_and_account() -> None:
    text = _source()
    assert "is not the configured" in text
    # account/confirm checks run before the actor in DeskOrdProcessRequest
    login_check = text.index("login != g_desk_expect_login")
    actor = text.index("if(want_flat || want_reduce)")
    assert login_check < actor


def test_actor_reports_resulting_position_state() -> None:
    text = _source()
    for field in (
        "volume_before",
        "volume_closed",
        "volume_after",
        "stage",
        "retcode",
        "balance_after",
    ):
        assert field in text, field
    assert "PositionSelectByTicket(g_desk_ticket)" in text
    assert "vol_after = PositionGetDouble(POSITION_VOLUME)" in text


def test_flat_and_reduce_are_not_control_gated() -> None:
    text = _source()
    start = text.index("if(want_flat || want_reduce)")
    end = text.index("if(want_close && !want_open)", start)
    block = text[start:end]
    assert "DeskControlEntriesBlocked" not in block
    assert "DeskControl" not in block


def test_existing_close_path_is_unchanged_for_scratch() -> None:
    text = _source()
    actor = text.index("if(want_flat || want_reduce)")
    close = text.index("if(want_close && !want_open)", actor)
    assert actor < close
