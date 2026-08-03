#!/usr/bin/env bash
# Install top-level app menu + Desktop launchers for broker MT5 prefixes.
# Wine nested wine/Programs entries often have broken tiny icons; this installs
# proper PNGs and direct /portable launchers.
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
force_so = script_dir / "wine-net" / "force_src_bind.so"

BRANDS = {
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
}

apps = Path.home() / ".local/share/applications"
desktop_dir = Path.home() / "Desktop"
hicolor = Path.home() / ".local/share/icons/hicolor"
bin_dir = Path.home() / ".local/bin"
for d in (apps, desktop_dir, bin_dir):
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
    if force_so.is_file():
        preload = (
            f'export LD_PRELOAD="{force_so}${{LD_PRELOAD:+:$LD_PRELOAD}}"\n'
            'export MT5_FORCE_SRC_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | '
            "awk '{for(i=1;i<=NF;i++) if($i==\"src\"){print $(i+1); exit}}' || true)\"\n"
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
    for dest in (apps / b["desktop_name"], desktop_dir / b["desktop_name"]):
        dest.write_text(desktop)
        dest.chmod(0o755)
        subprocess.run(
            ["gio", "set", str(dest), "metadata::trusted", "true"],
            check=False,
            capture_output=True,
        )
    print(f"installed {key}: {b['desktop_name']} + mt5-{key}")

subprocess.run(
    ["gtk-update-icon-cache", "-f", "-t", str(hicolor)],
    check=False,
    capture_output=True,
)
subprocess.run(
    ["update-desktop-database", str(apps)], check=False, capture_output=True
)
print("done — search app launcher for: FP Markets MT5")
PY
