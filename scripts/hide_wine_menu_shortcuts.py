"""Hide Wine Start Menu .desktop clones; drop unused ~/Desktop MT5 copies."""

from __future__ import annotations

from pathlib import Path

FOLDER_LABELS = {
    "WSFmarkets MT5 Terminal": "WSF",
    "MetaTrader 5 EXNESS": "Exness",
    "MetaTrader 5": "FTMO generic",
    "FT Trading MT5 Terminal": "Fortraders",
    "FTMO Global Markets MT5 Terminal": "FTMO",
    "FundingPips 2 MT5 Terminal": "FundingPips",
    "ACG Markets MT5 Terminal": "Alpha Capital",
    "Neomaaa MT5 Terminal": "Neomaa",
    "FundedNext MT5 Terminal": "FundedNext",
}

_STRIP_SUFFIXES = (" MT5 Terminal", " Terminal")

# Keep in sync with scripts/17-install-desktop-launchers.sh BRANDS desktop_name.
SCRIPT17_DESKTOP_NAMES = frozenset(
    {
        "exness-mt5.desktop",
        "fpmarkets-mt5.desktop",
        "vantage-mt5.desktop",
        "wsf-mt5.desktop",
    }
)


def wine_label(folder_name: str) -> str:
    if folder_name in FOLDER_LABELS:
        return FOLDER_LABELS[folder_name]
    label = folder_name
    for suffix in _STRIP_SUFFIXES:
        if label.endswith(suffix):
            return label[: -len(suffix)]
    return label


def _current_name(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("Name="):
            return line[5:]
    return ""


def _display_name(path: Path, text: str) -> tuple[str, str]:
    folder = wine_label(path.parent.name)
    stem = path.stem
    if stem == "MetaEditor":
        return f"MetaEditor ({folder})", f"Wine Start Menu MetaEditor for {folder}"
    if stem == "Uninstall":
        return f"Uninstall ({folder})", f"Wine Start Menu uninstall for {folder}"
    current = _current_name(text) or stem
    name = current if current.endswith(" (Wine)") else f"{current} (Wine)"
    return name, f"Wine Start Menu shortcut for {folder}; use branded mt5-* launcher"


def patch_desktop(text: str, *, name: str, comment: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    seen_name = seen_comment = seen_nodisplay = False
    in_entry = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_entry and stripped != "[Desktop Entry]":
                if not seen_comment:
                    out.append(f"Comment={comment}")
                    seen_comment = True
                if not seen_nodisplay:
                    out.append("NoDisplay=true")
                    seen_nodisplay = True
            in_entry = stripped == "[Desktop Entry]"
            out.append(line)
            continue
        if not in_entry:
            out.append(line)
            continue
        if line.startswith("Name="):
            out.append(f"Name={name}")
            seen_name = True
        elif line.startswith("Comment="):
            out.append(f"Comment={comment}")
            seen_comment = True
        elif line.startswith("NoDisplay="):
            out.append("NoDisplay=true")
            seen_nodisplay = True
        else:
            out.append(line)
    if not seen_name:
        out.append(f"Name={name}")
    if not seen_comment:
        out.append(f"Comment={comment}")
    if not seen_nodisplay:
        out.append("NoDisplay=true")
    return "\n".join(out) + "\n"


def hide_desktop_file(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8", errors="replace")
    name, comment = _display_name(path, raw)
    patched = patch_desktop(raw, name=name, comment=comment)
    if patched == raw:
        return False
    path.write_text(patched, encoding="utf-8")
    return True


def hide_wine_programs(apps_dir: Path) -> int:
    root = apps_dir / "wine" / "Programs"
    if not root.is_dir():
        return 0
    changed = 0
    for path in sorted(root.rglob("*.desktop")):
        if hide_desktop_file(path):
            changed += 1
    return changed


def remove_desktop_mt5_copies(desktop_dir: Path) -> list[Path]:
    if not desktop_dir.is_dir():
        return []
    removed: list[Path] = []
    for name in sorted(SCRIPT17_DESKTOP_NAMES):
        path = desktop_dir / name
        if path.is_file():
            path.unlink()
            removed.append(path)
    return removed
