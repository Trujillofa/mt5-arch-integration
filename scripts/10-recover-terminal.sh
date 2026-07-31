#!/usr/bin/env bash
# Recover MetaTrader when process is alive but window is gone (minimize/unmap bug),
# or when MT5 is not running. Then optional maximize on active monitor.
#
# Usage:
#   ./scripts/10-recover-terminal.sh
#   ./scripts/10-recover-terminal.sh --fullscreen
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env
require_cmd wine

# Prevent 09 → 10 → 07 → 09 → 10 infinite recover loops
DEPTH="${MT5_RECOVER_DEPTH:-0}"
if [[ "$DEPTH" -ge 2 ]]; then
  die "recover aborted: nested too deep (depth=$DEPTH). Check Hyprland/Wine manually."
fi
export MT5_RECOVER_DEPTH=$((DEPTH + 1))
# Tell 09 not to call us again while we restart
export MT5_NO_AUTO_RECOVER=1

FULLSCREEN=0
for arg in "$@"; do
  case "$arg" in
    --fullscreen|--maximize) FULLSCREEN=1 ;;
    -h|--help)
      echo "Usage: $0 [--fullscreen]"
      echo "  Kill ghost terminal64 (process without Hyprland window) and restart MT5."
      exit 0
      ;;
  esac
done

# Clipboard bridge BEFORE unsetting WAYLAND (Wine/XWayland paste)
ensure_clipboard_bridge

if [[ -n "${DISPLAY:-}" ]]; then
  unset WAYLAND_DISPLAY || true
fi
export DISPLAY="${DISPLAY:-:0}"
export WINEDEBUG="${WINEDEBUG:--all}"
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-d3d11=b;d3d12=b;dxgi=b}"
wine reg delete 'HKEY_CURRENT_USER\Software\Wine\Explorer' /v Desktop /f >/dev/null 2>&1 || true

cd "$REPO_ROOT"

# Detect ghost via shipped Python (true ghost = process + zero terminal64 clients)
STATUS_JSON="$(uv run python - <<'PY'
import json
from mt5_arch.hypr_geometry import (
    fetch_clients,
    is_ghost_terminal,
    list_terminal64_clients,
    select_main_terminal,
    terminal64_process_running,
)
proc = terminal64_process_running()
main = None
wins = []
try:
    clients = fetch_clients()
    wins = list_terminal64_clients(clients)
    main = select_main_terminal(clients)
except Exception as e:
    print(json.dumps({"process": proc, "ghost": proc, "main": None, "windows": 0, "error": str(e)}))
    raise SystemExit(0)
print(json.dumps({
    "process": proc,
    "ghost": is_ghost_terminal(process_running=proc, main_window=main, any_terminal_window=wins),
    "main_title": None if main is None else main.title,
    "windows": len(wins),
    "window_titles": [w.title for w in wins[:5]],
}))
PY
)" || STATUS_JSON='{"process":false,"ghost":false,"windows":0}'

info "state: $STATUS_JSON"

GHOST="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('ghost', False))" "$STATUS_JSON")"
PROC="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('process', False))" "$STATUS_JSON")"
MAIN="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('main_title') or '')" "$STATUS_JSON")"
WINS="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('windows', 0))" "$STATUS_JSON")"

# Only kill/restart on true ghost (process, zero windows). Login-only is not a ghost.
if [[ "$GHOST" == "True" ]]; then
  info "Ghost MT5 detected (process, no Hyprland window) — killing and restarting"
  "$SCRIPT_DIR/07-restart-terminal.sh" ${FULLSCREEN:+--fullscreen}
  exit 0
fi

if [[ "$PROC" != "True" ]]; then
  info "MT5 not running — starting"
  if [[ "$FULLSCREEN" -eq 1 ]]; then
    "$SCRIPT_DIR/04-start-terminal.sh" --detach --fullscreen
  else
    "$SCRIPT_DIR/04-start-terminal.sh" --detach
  fi
  exit 0
fi

if [[ -z "$MAIN" && "$WINS" != "0" ]]; then
  info "MT5 windows present ($WINS) but main shell not ready (Login?). Waiting..."
  for _ in $(seq 1 20); do
    sleep 0.5
    MAIN="$(uv run python - <<'PY'
from mt5_arch.hypr_geometry import fetch_clients, select_main_terminal
m = select_main_terminal(fetch_clients())
print(m.title if m else "")
PY
)" || MAIN=""
    if [[ -n "$MAIN" ]]; then
      break
    fi
  done
fi

if [[ -z "$MAIN" ]]; then
  warn "Still no main window after wait — restarting once"
  "$SCRIPT_DIR/07-restart-terminal.sh" ${FULLSCREEN:+--fullscreen}
  exit 0
fi

info "MT5 main window is visible: $MAIN"
if [[ "$FULLSCREEN" -eq 1 ]]; then
  # MT5_NO_AUTO_RECOVER prevents 09 from re-entering this script
  "$SCRIPT_DIR/09-fullscreen-terminal.sh" --mode maximize || true
fi
info "OK — recovery complete"
