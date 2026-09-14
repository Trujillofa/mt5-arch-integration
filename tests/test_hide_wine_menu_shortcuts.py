"""Offline tests for Wine Start Menu hide + Desktop MT5 copy cleanup."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "hide_wine_menu_shortcuts.py"
SPEC = importlib.util.spec_from_file_location("hide_wine_menu_shortcuts", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
hide = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hide)

WINE_SHORTCUT = """[Desktop Entry]
Name=MetaEditor
Exec=env WINEPREFIX=/tmp wine MetaEditor.lnk
Type=Application
StartupNotify=true
Path=/tmp
Icon=metaeditor
StartupWMClass=metaeditor64.exe
"""

TERMINAL_SHORTCUT = """[Desktop Entry]
Name=FTMO
Exec=env WINEPREFIX=/tmp wine FTMO.lnk
Type=Application
Path=/tmp
"""


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_wine_label_known_and_unknown() -> None:
    assert hide.wine_label("WSFmarkets MT5 Terminal") == "WSF"
    assert hide.wine_label("MetaTrader 5") == "FTMO generic"
    assert hide.wine_label("Some Broker MT5 Terminal") == "Some Broker"


def test_hide_metaeditor_sets_nodisplay_and_broker_name(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "wine" / "Programs" / "WSFmarkets MT5 Terminal" / "MetaEditor.desktop",
        WINE_SHORTCUT,
    )
    assert hide.hide_wine_programs(tmp_path) == 1
    text = path.read_text()
    assert "Name=MetaEditor (WSF)\n" in text
    assert "NoDisplay=true\n" in text
    assert hide.hide_wine_programs(tmp_path) == 0


def test_hide_terminal_appends_wine_suffix(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "wine" / "Programs" / "FTMO Global Markets MT5 Terminal" / "FTMO.desktop",
        TERMINAL_SHORTCUT,
    )
    assert hide.hide_wine_programs(tmp_path) == 1
    text = path.read_text()
    assert "Name=FTMO (Wine)\n" in text
    assert "NoDisplay=true\n" in text
    assert hide.hide_wine_programs(tmp_path) == 0


def test_hide_missing_programs_dir_is_zero(tmp_path: Path) -> None:
    assert hide.hide_wine_programs(tmp_path) == 0


def test_remove_desktop_mt5_copies_only(tmp_path: Path) -> None:
    keep = tmp_path / "notes.txt"
    keep.write_text("keep")
    mt5 = tmp_path / "wsf-mt5.desktop"
    mt5.write_text("Name=WSF MT5")
    stray = tmp_path / "random-mt5.desktop"
    stray.write_text("Name=Stray")
    other = tmp_path / "steam.desktop"
    other.write_text("Name=Steam")
    named_dir = tmp_path / "vantage-mt5.desktop"
    named_dir.mkdir()
    removed = hide.remove_desktop_mt5_copies(tmp_path)
    assert [p.name for p in removed] == ["wsf-mt5.desktop"]
    assert keep.is_file()
    assert other.is_file()
    assert stray.is_file()
    assert named_dir.is_dir()
    assert not mt5.exists()


def test_desktop_allowlist_matches_script_17() -> None:
    text = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "17-install-desktop-launchers.sh"
    ).read_text(encoding="utf-8")
    names = set(re.findall(r'"desktop_name": "([^"]+)"', text))
    assert names == hide.SCRIPT17_DESKTOP_NAMES


def test_script_17_hides_wine_and_skips_desktop() -> None:
    text = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "17-install-desktop-launchers.sh"
    ).read_text(encoding="utf-8")
    assert "hide_wine_programs" in text
    assert "remove_desktop_mt5_copies" in text
    assert 'desktop_dir / b["desktop_name"]' not in text


def test_script_17_lists_live_book_brands() -> None:
    text = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "17-install-desktop-launchers.sh"
    ).read_text(encoding="utf-8")
    assert ".mt5-ftmo" in text
    assert "FTMO Global Markets" in text
    assert ".mt5-fundednext" in text
    assert ".mt5-alphacapital" in text
    assert ".mt5-fundingpips" in text
    assert ".mt5-neomaa" in text
    assert ".mt5-fortraders" in text
    assert "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS" in text
