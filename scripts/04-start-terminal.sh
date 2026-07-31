#!/usr/bin/env bash
# Start MetaTrader 5 terminal under Wine.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env
require_cmd wine

if [[ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
  die "No graphical display. Start from a desktop session (Hyprland/Omarchy terminal)."
fi

term="$(find_terminal64)" || die "terminal64.exe not found. Run ./scripts/02-install-mt5.sh"

info "Starting MetaTrader 5: $term"
info "WINEPREFIX=$WINEPREFIX"
info "Remember: log in to the broker and enable Algo Trading (toolbar button)."

# Background friendly: pass --detach to return immediately
if [[ "${1:-}" == "--detach" ]]; then
  nohup wine "$term" >/tmp/mt5-terminal.log 2>&1 &
  echo $! >/tmp/mt5-terminal.pid
  info "Detached PID $(cat /tmp/mt5-terminal.pid); log: /tmp/mt5-terminal.log"
  exit 0
fi

exec wine "$term"
