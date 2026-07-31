#!/usr/bin/env bash
# Check Arch Linux dependencies for MetaTrader 5 under Wine.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env

missing=()
recommended=()

check_required() {
  local cmd="$1"
  if command -v "$cmd" >/dev/null 2>&1; then
    info "found $cmd: $(command -v "$cmd")"
  else
    missing+=("$cmd")
  fi
}

check_pkg_hint() {
  local pkg="$1"
  if pacman -Q "$pkg" &>/dev/null; then
    info "package installed: $pkg"
  else
    recommended+=("$pkg")
  fi
}

info "Checking required commands..."
check_required wine
check_required winetricks
check_required curl
check_required find

if command -v wine >/dev/null 2>&1; then
  info "wine version: $(wine --version 2>/dev/null || echo unknown)"
fi

info "Checking recommended Arch packages..."
for pkg in wine winetricks lib32-gnutls lib32-libxcomposite ttf-liberation noto-fonts; do
  check_pkg_hint "$pkg"
done

if [[ ${#missing[@]} -gt 0 ]]; then
  echo
  die "missing required tools: ${missing[*]}
Install with:
  sudo pacman -S --needed wine winetricks curl"
fi

if [[ ${#recommended[@]} -gt 0 ]]; then
  echo
  warn "recommended packages not installed: ${recommended[*]}"
  echo "  sudo pacman -S --needed ${recommended[*]}"
fi

if [[ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
  warn "No DISPLAY or WAYLAND_DISPLAY set. MT5 GUI install/start needs a graphical session."
  warn "On Hyprland/Omarchy, run these scripts from a terminal inside the desktop session."
else
  info "display: DISPLAY=${DISPLAY:-unset} WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-unset}"
fi

if [[ -d "${WINEPREFIX}" ]]; then
  info "WINEPREFIX exists: $WINEPREFIX"
  if find_terminal64 >/dev/null 2>&1; then
    info "terminal64.exe: $(find_terminal64)"
  else
    warn "terminal64.exe not found under $WINEPREFIX — run ./scripts/02-install-mt5.sh"
  fi
else
  warn "WINEPREFIX missing: $WINEPREFIX — run ./scripts/01-create-prefix.sh"
fi

if [[ -f "$(mt5server_path)" ]]; then
  info "mt5server.exe: $(mt5server_path)"
else
  warn "mt5server.exe not found — run ./scripts/03-install-mt5server.sh"
fi

echo
info "Dependency check complete."
