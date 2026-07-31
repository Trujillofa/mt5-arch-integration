#!/usr/bin/env bash
# Install MetaTrader 5 into the Wine prefix.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env
require_cmd wine
require_cmd curl

if [[ ! -d "$WINEPREFIX/drive_c" ]]; then
  die "Wine prefix not initialized. Run ./scripts/01-create-prefix.sh first."
fi

if find_terminal64 >/dev/null 2>&1; then
  term="$(find_terminal64)"
  info "MetaTrader 5 already installed: $term"
  write_local_paths "$term" "$(mt5server_path 2>/dev/null || true)"
  info "Re-run installer with --force to install again."
  if [[ "${1:-}" != "--force" ]]; then
    exit 0
  fi
fi

SETUP=""
if SETUP="$(find_mt5_setup)"; then
  info "Using local installer: $SETUP"
else
  SETUP="/tmp/mt5setup.exe"
  info "Downloading official MetaTrader 5 installer to $SETUP"
  # Official MetaQuotes download redirect
  curl -fsSL -o "$SETUP" "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe" \
    || die "download failed; place mt5setup.exe somewhere and set MT5_SETUP="
fi

[[ -f "$SETUP" ]] || die "installer not found: $SETUP"

if [[ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
  die "No graphical display. Run this script from a desktop session so the installer GUI can open."
fi

info "Launching installer under Wine..."
info "Follow the GUI, then log into your broker account and enable Algo Trading."
wine "$SETUP" || warn "Installer exited non-zero (common if you closed the window)."

# Wait briefly for files to settle
sleep 2

if term="$(find_terminal64)"; then
  info "Found terminal: $term"
  write_local_paths "$term" "$(mt5server_path 2>/dev/null || true)"
  info "Next steps:"
  echo "  1. ./scripts/04-start-terminal.sh   # log in, enable Algo Trading"
  echo "  2. ./scripts/03-install-mt5server.sh"
  echo "  3. ./scripts/05-start-mt5server.sh"
else
  die "terminal64.exe not found after install. Check the installer completed successfully."
fi
