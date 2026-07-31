#!/usr/bin/env bash
# mt5linux-arch.sh — Arch Linux counterpart of MetaQuotes' mt5linux.sh
# Official Ubuntu/Debian/Fedora guide:
#   https://www.metatrader5.com/en/terminal/help/start_advanced/install_linux
#
# Official one-liner (Ubuntu family only):
#   wget https://download.terminal.free/cdn/web/metaquotes.software.corp/mt5/mt5linux.sh
#   chmod +x mt5linux.sh && ./mt5linux.sh
#
# This script does the same steps for Arch Linux / Manjaro / EndeavourOS:
#   1) Install Wine (staging preferred, else wine) via pacman
#   2) Download mt5setup.exe + WebView2 bootstrapper
#   3) Create ~/.mt5 prefix, Windows 11 version
#   4) Install WebView2 (silent) then MetaTrader 5
#
# Run WITHOUT sudo for the whole script. When pacman needs privileges,
# it will prompt for your password once.
#
# Usage:
#   ./scripts/mt5linux-arch.sh
#   ./scripts/mt5linux-arch.sh --skip-webview   # skip WebView2 if it hangs
#   ./scripts/mt5linux-arch.sh --reinstall-mt5  # run installer even if terminal exists
set -euo pipefail

# --- mirrors official script URLs ---
URL_MT5="${URL_MT5:-https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe}"
URL_WEBVIEW="${URL_WEBVIEW:-https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/f2910a1e-e5a6-4f17-b52d-7faf525d17f8/MicrosoftEdgeWebview2Setup.exe}"

# Official uses WINE_VERSION=staging; on Arch we map that to wine-staging package.
WINE_PKG="${WINE_PKG:-wine-staging}"   # or: wine
WINEPREFIX="${WINEPREFIX:-$HOME/.mt5}"
WORKDIR="${WORKDIR:-$HOME/.cache/mt5-arch-install}"
export WINEPREFIX
export WINEARCH="${WINEARCH:-win64}"
export WINEDEBUG="${WINEDEBUG:--all}"

SKIP_WEBVIEW=0
REINSTALL_MT5=0
for arg in "$@"; do
  case "$arg" in
    --skip-webview) SKIP_WEBVIEW=1 ;;
    --reinstall-mt5) REINSTALL_MT5=1 ;;
    -h|--help)
      sed -n '2,30p' "$0"
      exit 0
      ;;
  esac
done

info() { echo "==> $*"; }
warn() { echo "warning: $*" >&2; }
die()  { echo "error: $*" >&2; exit 1; }

# --- detect Arch family ---
if [[ -f /etc/os-release ]]; then
  # shellcheck source=/dev/null
  . /etc/os-release
  info "OS: ${NAME:-?} ${VERSION_ID:-rolling}"
else
  die "cannot read /etc/os-release"
fi

case "${ID:-}:${ID_LIKE:-}" in
  arch:*|manjaro:*|*arch*|*archlinux*)
    ;;
  *)
    warn "This script targets Arch Linux. Detected: ${ID:-unknown}."
    warn "For Ubuntu/Debian/Fedora use the official script:"
    warn "  https://www.metatrader5.com/en/terminal/help/start_advanced/install_linux"
    ;;
esac

if [[ "$(id -u)" -eq 0 ]]; then
  die "Do not run as root. Run as your normal user (pacman will ask for sudo)."
fi

if [[ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
  die "No graphical session (DISPLAY/WAYLAND_DISPLAY empty). Run from a desktop terminal."
fi

# Prefer XWayland for Wine under Hyprland (same as our hardened start scripts)
if [[ -n "${DISPLAY:-}" ]]; then
  unset WAYLAND_DISPLAY || true
fi
export DISPLAY="${DISPLAY:-:0}"

mkdir -p "$WORKDIR"
cd "$WORKDIR"

# --- packages (Arch equivalent of winehq-staging + mono) ---
info "Installing packages with pacman (sudo may prompt)..."
need_pkgs=()
for p in "$WINE_PKG" winetricks curl cabextract; do
  if ! pacman -Q "$p" &>/dev/null; then
    need_pkgs+=("$p")
  fi
done
# Multilib helpers often needed for Wine
for p in lib32-gnutls lib32-libxcomposite ttf-liberation; do
  if ! pacman -Q "$p" &>/dev/null; then
    need_pkgs+=("$p")
  fi
done

if [[ ${#need_pkgs[@]} -gt 0 ]]; then
  info "Will install: ${need_pkgs[*]}"
  if ! pacman -Si "$WINE_PKG" &>/dev/null; then
    if [[ "$WINE_PKG" == "wine-staging" ]] && pacman -Si wine &>/dev/null; then
      warn "wine-staging not available; falling back to wine"
      WINE_PKG=wine
      need_pkgs=("${need_pkgs[@]/wine-staging}")
      need_pkgs+=(wine)
    else
      die "package $WINE_PKG not found. Enable multilib if needed: /etc/pacman.conf"
    fi
  fi
  sudo pacman -Syu --needed --noconfirm "${need_pkgs[@]}"
else
  info "Required packages already installed."
fi

if ! command -v wine >/dev/null; then
  die "wine not on PATH after install"
fi
info "Wine: $(wine --version)"

# Wine Mono / Gecko: winetricks if missing (official script installs wine-mono on Fedora)
info "Ensuring Wine Mono/Gecko (winetricks)..."
winetricks -q -f dotnet48 2>/dev/null || true
# lighter: just corefonts + mono if user prefers speed
# Official path uses WebView2 instead of fighting every dependency.

# --- downloads (same as official) ---
info "Downloading MetaTrader 5 installer..."
curl -fL --retry 3 -o mt5setup.exe "$URL_MT5"
info "Downloading WebView2 Runtime bootstrapper..."
curl -fL --retry 3 -o webview2.exe "$URL_WEBVIEW" || {
  warn "WebView2 download failed; continuing without it (--skip-webview)"
  SKIP_WEBVIEW=1
}

# --- prefix + Windows 11 (official: winecfg -v=win11) ---
info "Preparing Wine prefix: $WINEPREFIX (Windows 11)"
mkdir -p "$WINEPREFIX"
# Non-interactive Windows version
if command -v winecfg >/dev/null; then
  winecfg -v=win11 || wine winecfg -v=win11 || true
fi
# Also set via registry for reliability
wine reg add 'HKEY_LOCAL_MACHINE\Software\Microsoft\Windows NT\CurrentVersion' \
  /v ProductName /t REG_SZ /d 'Windows 11' /f >/dev/null 2>&1 || true
# X11 driver tweaks for Hyprland (not in official script; Arch desktop reality)
wine reg add 'HKEY_CURRENT_USER\Software\Wine\X11 Driver' /v GrabFullscreen /t REG_SZ /d N /f >/dev/null 2>&1 || true
wine reg add 'HKEY_CURRENT_USER\Software\Wine\X11 Driver' /v UseTakeFocus /t REG_SZ /d N /f >/dev/null 2>&1 || true
wine reg add 'HKEY_CURRENT_USER\Software\Wine\X11 Driver' /v Managed /t REG_SZ /d Y /f >/dev/null 2>&1 || true
# No virtual desktop (breaks mouse under Hyprland)
wine reg delete 'HKEY_CURRENT_USER\Software\Wine\Explorer' /v Desktop /f >/dev/null 2>&1 || true

# --- WebView2 (official: wine webview2.exe /silent /install) ---
if [[ "$SKIP_WEBVIEW" -eq 0 ]]; then
  info "Installing WebView2 Runtime (may take several minutes)..."
  # /silent /install matches official script
  wine webview2.exe /silent /install || warn "WebView2 install returned non-zero (often OK)"
else
  warn "Skipping WebView2 (Market/AI panes may stay black)"
fi

# --- MetaTrader 5 ---
TERM_EXE="$WINEPREFIX/drive_c/Program Files/MetaTrader 5/terminal64.exe"
if [[ -f "$TERM_EXE" && "$REINSTALL_MT5" -eq 0 ]]; then
  info "MetaTrader 5 already installed at:"
  info "  $TERM_EXE"
  info "Re-run with --reinstall-mt5 to launch the installer again."
else
  info "Launching MetaTrader 5 installer (GUI)..."
  info "Complete the installer wizard, then log into your broker."
  wine mt5setup.exe || warn "Installer exited non-zero"
fi

# --- post checks ---
if [[ -f "$TERM_EXE" ]]; then
  info "SUCCESS: terminal found"
  ls -lh "$TERM_EXE"
else
  # search
  found="$(find "$WINEPREFIX" -name 'terminal64.exe' 2>/dev/null | head -n 1 || true)"
  if [[ -n "$found" ]]; then
    info "SUCCESS: terminal at $found"
  else
    die "terminal64.exe not found. Re-run installer: $0 --reinstall-mt5"
  fi
fi

cat <<EOF

========================================================================
  MetaTrader 5 on Arch — install finished (official-style flow)
========================================================================

  Data directory (same as MetaQuotes docs):
    $WINEPREFIX/drive_c/Program Files/MetaTrader 5

  Start the platform:
    WINEPREFIX=$WINEPREFIX wine "\$WINEPREFIX/drive_c/Program Files/MetaTrader 5/terminal64.exe" /portable

  Or from this repo:
    cd ~/Projects/trading/mt5-arch-integration
    ./scripts/04-start-terminal.sh --detach
    ./scripts/07-restart-terminal.sh   # if frozen / invisible

  Linux Python data bridge (optional, this repo):
    ./scripts/06-install-file-bridge.sh
    # attach Mt5ArchBridge EA, Algo Trading green
    uv run mt5-arch account

  Official note: reboot can help after first Wine install.
  Keep Wine and the OS updated:
    sudo pacman -Syu

  Ubuntu reference:
    https://www.metatrader5.com/en/terminal/help/start_advanced/install_linux

  Arch extras (Hyprland charts, recovery):
    docs/INSTALL-LINUX-ARCH.md
    docs/CHARTS-AND-STABILITY.md
========================================================================
EOF
