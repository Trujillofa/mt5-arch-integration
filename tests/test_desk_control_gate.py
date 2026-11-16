"""Contract: the coordinator inhibit switch gates entries only.

Static checks — MQL5 is compiled at deploy time (MetaEditor F7), not in CI.
The switch is coordinator-owned: the EA reads control.json and never writes it.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "mql5" / "Include" / "DeskControl.mqh"
BRIDGE = ROOT / "mql5" / "Include" / "DeskOrderBridge.mqh"
EA = ROOT / "mql5" / "Mt5ArchBridge.mq5"


def test_control_include_is_read_only() -> None:
    text = CONTROL.read_text(encoding="utf-8")
    assert "control.json" in text
    assert "inhibited" in text
    assert "FILE_COMMON" in text
    assert "FileIsExist" in text
    assert "FileReadString" in text
    for forbidden in ("FileWrite", "OrderSend", "OrderClose", "CTrade"):
        assert forbidden not in text, forbidden


def test_missing_file_allows_but_bad_file_fails_closed() -> None:
    text = CONTROL.read_text(encoding="utf-8")
    # missing → not inhibited
    assert "if(!g_desk_ctl_present)" in text
    assert "if(!g_desk_ctl_inhibited)" in text
    # unreadable / malformed → inhibited
    assert "control.json unreadable" in text
    assert "control.json malformed" in text
    assert text.count("g_desk_ctl_inhibited = true;") >= 2


def test_bridge_includes_gate_and_gates_only_entries() -> None:
    text = BRIDGE.read_text(encoding="utf-8")
    assert "#include <DeskControl.mqh>" in text
    assert "if(want_open && DeskControlEntriesBlocked(control_reason))" in text
    assert 'DeskOrdFail("control"' in text

    gate = text.index("DeskControlEntriesBlocked(control_reason)")
    close = text.index("if(want_close && !want_open)")
    cancel = text.index("if(want_cancel)")
    modify = text.index("if(want_modify)")
    assert gate < close
    assert gate < cancel
    assert gate < modify


def test_ea_reads_control_at_startup() -> None:
    text = EA.read_text(encoding="utf-8")
    assert "DeskControlLogOnInit();" in text
    init_start = text.index("int OnInit()")
    init_end = text.index("void OnDeinit", init_start)
    assert "DeskControlLogOnInit();" in text[init_start:init_end]
