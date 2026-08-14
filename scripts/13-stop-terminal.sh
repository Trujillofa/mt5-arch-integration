#!/usr/bin/env bash
# Gracefully stop one broker's MetaTrader (scoped to WINEPREFIX).
#
# Use this when a terminal is unused but still burning Wine GDI (FP with many
# Fib charts was freezing while "idle"). Prefer stop over leaving a heavy
# profile running in the background.
#
#   WINEPREFIX=~/.mt5-fpmarkets ./scripts/13-stop-terminal.sh
#   MT5_STOP_ALL=1 ./scripts/13-stop-terminal.sh   # every broker (rare)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env

if [[ "${MT5_STOP_ALL:-0}" == "1" ]]; then
  stop_terminal_gracefully "${MT5_STOP_TIMEOUT:-40}"
else
  stop_terminal_gracefully "${MT5_STOP_TIMEOUT:-40}" "$WINEPREFIX"
fi
info "Stopped. Relaunch with: WINEPREFIX=$WINEPREFIX ./scripts/07-restart-terminal.sh"
