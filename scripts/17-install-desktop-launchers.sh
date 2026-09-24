#!/usr/bin/env bash
# Install top-level app-menu launchers for broker MT5 prefixes.
# Wine nested wine/Programs entries often have broken tiny icons; this installs
# proper PNGs and direct /portable launchers, hides those Wine clones, and
# removes leftover ~/Desktop/*-mt5.desktop copies (Omarchy has no desktop icons).
#
# Usage: ./scripts/17-install-desktop-launchers.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

require_cmd python3
export REPO_SCRIPTS="$SCRIPT_DIR"

python3 - "$SCRIPT_DIR" <<'PY'
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Pillow required: uv run python -c 'import PIL' or pip install pillow"
    ) from exc

script_dir = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(script_dir))
from hide_wine_menu_shortcuts import hide_wine_programs, remove_desktop_mt5_copies

force_src = script_dir / "wine-net" / "force_src_bind.c"
force_so = script_dir / "wine-net" / "force_src_bind.so"
if force_src.is_file() and (
    not force_so.is_file() or force_src.stat().st_mtime > force_so.stat().st_mtime
):
    subprocess.run(
        ["gcc", "-shared", "-fPIC", "-O2", "-o", str(force_so), str(force_src), "-ldl"],
        check=True,
    )

BRANDS = {
    "exness": {
        "name": "Exness MT5",
        "comment": "Exness MetaTrader 5 (Wine)",
        "prefix": Path.home() / ".mt5-exness",
        "dir": Path.home()
        / ".mt5-exness/drive_c/Program Files/MetaTrader 5 EXNESS",
        "ico": Path.home()
        / ".mt5-exness/drive_c/Program Files/MetaTrader 5 EXNESS/Terminal.ico",
        "icon_name": "exness-mt5",
        "desktop_name": "exness-mt5.desktop",
    },
    "fpmarkets": {
        "name": "FP Markets MT5",
        "comment": "FP Markets SC MetaTrader 5 (Wine)",
        "prefix": Path.home() / ".mt5-fpmarkets",
        "dir": Path.home()
        / ".mt5-fpmarkets/drive_c/Program Files/FP Markets MT5 Terminal",
        "ico": Path.home()
        / ".mt5-fpmarkets/drive_c/Program Files/FP Markets MT5 Terminal/Terminal.ico",
        "icon_name": "fpmarkets-mt5",
        "desktop_name": "fpmarkets-mt5.desktop",
    },
    "vantage": {
        "name": "Vantage International MT5",
        "comment": "Vantage International MetaTrader 5 (Wine)",
        "prefix": Path.home() / ".mt5-vantage",
        "dir": Path.home()
        / ".mt5-vantage/drive_c/Program Files/Vantage International MT5",
        "ico": Path.home()
        / ".mt5-vantage/drive_c/Program Files/Vantage International MT5/Terminal.ico",
        "icon_name": "vantage-mt5",
        "desktop_name": "vantage-mt5.desktop",
    },
    "wsf": {
        "name": "WSFmarkets MT5",
        "comment": "WSFmarkets MetaTrader 5 (Wine)",
        "prefix": Path.home() / ".mt5-wsf",
        "dir": Path.home()
        / ".mt5-wsf/drive_c/Program Files/WSFmarkets MT5 Terminal",
        "ico": Path.home()
        / ".mt5-wsf/drive_c/Program Files/WSFmarkets MT5 Terminal/Terminal.ico",
        "icon_name": "wsf-mt5",
        "desktop_name": "wsf-mt5.desktop",
    },
    "fundednext": {
        "name": "FundedNext MT5",
        "comment": "FundedNext MetaTrader 5 (Wine)",
        "prefix": Path.home() / ".mt5-fundednext",
        "dir": Path.home()
        / ".mt5-fundednext/drive_c/Program Files/FundedNext MT5 Terminal",
        "ico": Path.home()
        / ".mt5-fundednext/drive_c/Program Files/FundedNext MT5 Terminal/Terminal.ico",
        "icon_name": "fundednext-mt5",
        "desktop_name": "fundednext-mt5.desktop",
    },
    "ftmo": {
        "name": "FTMO MT5",
        "comment": "FTMO Global Markets MetaTrader 5 (Wine)",
        "prefix": Path.home() / ".mt5-ftmo",
        "dir": Path.home()
        / ".mt5-ftmo/drive_c/Program Files/FTMO Global Markets MT5 Terminal",
        "ico": Path.home()
        / ".mt5-ftmo/drive_c/Program Files/FTMO Global Markets MT5 Terminal/Terminal.ico",
        "icon_name": "ftmo-mt5",
        "desktop_name": "ftmo-mt5.desktop",
    },
    "alphacapital": {
        "name": "Alpha Capital MT5",
        "comment": "ACG Markets / Alpha Capital MetaTrader 5 (Wine)",
        "prefix": Path.home() / ".mt5-alphacapital",
        "dir": Path.home()
        / ".mt5-alphacapital/drive_c/Program Files/ACG Markets MT5 Terminal",
        "ico": Path.home()
        / ".mt5-alphacapital/drive_c/Program Files/ACG Markets MT5 Terminal/Terminal.ico",
        "icon_name": "alphacapital-mt5",
        "desktop_name": "alphacapital-mt5.desktop",
    },
    "fundingpips": {
        "name": "FundingPips MT5",
        "comment": "FundingPips MetaTrader 5 (Wine)",
        "prefix": Path.home() / ".mt5-fundingpips",
        "dir": Path.home()
        / ".mt5-fundingpips/drive_c/Program Files/FundingPips 2 MT5 Terminal",
        "ico": Path.home()
        / ".mt5-fundingpips/drive_c/Program Files/FundingPips 2 MT5 Terminal/Terminal.ico",
        "icon_name": "fundingpips-mt5",
        "desktop_name": "fundingpips-mt5.desktop",
    },
    "neomaa": {
        "name": "Neomaa MT5",
        "comment": "Neomaaa MetaTrader 5 (Wine)",
        "prefix": Path.home() / ".mt5-neomaa",
        "dir": Path.home()
        / ".mt5-neomaa/drive_c/Program Files/Neomaaa MT5 Terminal",
        "ico": Path.home()
        / ".mt5-neomaa/drive_c/Program Files/Neomaaa MT5 Terminal/Terminal.ico",
        "icon_name": "neomaa-mt5",
        "desktop_name": "neomaa-mt5.desktop",
    },
    "fortraders": {
        "name": "Fortraders MT5",
        "comment": "FT Trading / Fortraders MetaTrader 5 (Wine)",
        "prefix": Path.home() / ".mt5-fortraders",
        "dir": Path.home()
        / ".mt5-fortraders/drive_c/Program Files/FT Trading MT5 Terminal",
        "ico": Path.home()
        / ".mt5-fortraders/drive_c/Program Files/FT Trading MT5 Terminal/Terminal.ico",
        "icon_name": "fortraders-mt5",
        "desktop_name": "fortraders-mt5.desktop",
    },
}

apps = Path.home() / ".local/share/applications"
hicolor = Path.home() / ".local/share/icons/hicolor"
bin_dir = Path.home() / ".local/bin"
for d in (apps, bin_dir):
    d.mkdir(parents=True, exist_ok=True)
sizes = [16, 24, 32, 48, 64, 128, 256]


def best_frame(ico_path: Path) -> Image.Image:
    im = Image.open(ico_path)
    best = None
    best_area = -1
    for i in range(getattr(im, "n_frames", 1)):
        try:
            im.seek(i)
        except EOFError:
            break
        frame = im.convert("RGBA")
        area = frame.size[0] * frame.size[1]
        if area > best_area:
            best_area = area
            best = frame.copy()
    if best is None:
        raise RuntimeError(f"no frames in {ico_path}")
    return best


for key, b in BRANDS.items():
    term = b["dir"] / "terminal64.exe"
    if not term.is_file():
        print(f"skip {key}: missing {term}")
        continue
    if not b["ico"].is_file():
        print(f"skip {key}: missing icon {b['ico']}")
        continue
    base = best_frame(b["ico"])
    for s in sizes:
        d = hicolor / f"{s}x{s}" / "apps"
        d.mkdir(parents=True, exist_ok=True)
        base.resize((s, s), Image.Resampling.LANCZOS).save(d / f"{b['icon_name']}.png")

    launcher = bin_dir / f"mt5-{key}"
    preload = ""
    if force_src.is_file() or force_so.is_file():
        preload = (
            f'SRC="{force_src}"\n'
            f'SO="{force_so}"\n'
            'if [[ -f "$SRC" ]] && { [[ ! -f "$SO" ]] || [[ "$SRC" -nt "$SO" ]]; }; then\n'
            '  if command -v gcc >/dev/null 2>&1; then\n'
            '    gcc -shared -fPIC -O2 -o "$SO" "$SRC" -ldl\n'
            "  fi\n"
            "fi\n"
            f'export LD_PRELOAD="{force_so}${{LD_PRELOAD:+:$LD_PRELOAD}}"\n'
            'export MT5_FORCE_SRC_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | '
            "awk '{for(i=1;i<=NF;i++) if($i==\"src\"){print $(i+1); exit}}' || true)\"\n"
        )
    # Deny XInput2 so one click cannot reach every book (see
    # scripts/wine-input/no_xi2.c and export_no_xi2_preload in lib.sh).
    noxi2_src = script_dir / "wine-input" / "no_xi2.c"
    noxi2_so = script_dir / "wine-input" / "no_xi2.so"
    if noxi2_src.is_file() or noxi2_so.is_file():
        preload += (
            f'NOXI2_SRC="{noxi2_src}"\n'
            f'NOXI2_SO="{noxi2_so}"\n'
            'if [[ "${MT5_WINE_XI2:-0}" != "1" ]]; then\n'
            '  if [[ -f "$NOXI2_SRC" ]] && { [[ ! -f "$NOXI2_SO" ]] || [[ "$NOXI2_SRC" -nt "$NOXI2_SO" ]]; }; then\n'
            '    command -v gcc >/dev/null 2>&1 && gcc -shared -fPIC -O2 -o "$NOXI2_SO" "$NOXI2_SRC" -ldl\n'
            "  fi\n"
            '  [[ -f "$NOXI2_SO" ]] && export LD_PRELOAD="$NOXI2_SO${LD_PRELOAD:+:$LD_PRELOAD}"\n'
            "fi\n"
        )
    launcher.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
export WINEPREFIX="{b['prefix']}"
export WINEARCH=win64
export DISPLAY="${{DISPLAY:-:0}}"
unset WAYLAND_DISPLAY || true
export WINEDEBUG="${{WINEDEBUG:--all}}"
export WINEDLLOVERRIDES="${{WINEDLLOVERRIDES:-d3d11=b;d3d12=b;dxgi=b}}"
export WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS="${{WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:---use-angle=swiftshader --enable-unsafe-swiftshader --no-sandbox}}"
{preload}cd "{b['dir']}"
exec wine ./terminal64.exe /portable "$@"
"""
    )
    launcher.chmod(0o755)

    desktop = f"""[Desktop Entry]
Type=Application
Version=1.0
Name={b['name']}
GenericName=MetaTrader 5
Comment={b['comment']}
Exec={launcher} %U
Path={b['dir']}
Icon={b['icon_name']}
Terminal=false
Categories=Office;Finance;
Keywords=mt5;metatrader;forex;{key};
StartupNotify=true
StartupWMClass=terminal64.exe
"""
    dest = apps / b["desktop_name"]
    dest.write_text(desktop)
    dest.chmod(0o755)
    subprocess.run(
        ["gio", "set", str(dest), "metadata::trusted", "true"],
        check=False,
        capture_output=True,
    )
    print(f"installed {key}: {b['desktop_name']} + mt5-{key}")

hid = hide_wine_programs(apps)
print(f"hid {hid} Wine Start Menu shortcut(s)")
removed = remove_desktop_mt5_copies(Path.home() / "Desktop")
for path in removed:
    print(f"removed Desktop copy {path.name}")

subprocess.run(
    ["gtk-update-icon-cache", "-f", "-t", str(hicolor)],
    check=False,
    capture_output=True,
)
subprocess.run(
    ["update-desktop-database", str(apps)], check=False, capture_output=True
)
print(
    "done — search app launcher for: Exness MT5 | FP Markets MT5 | Vantage | "
    "WSFmarkets | FundedNext MT5 | FTMO MT5 | Alpha Capital MT5 | "
    "FundingPips MT5 | Neomaa MT5 | Fortraders MT5"
)
PY
