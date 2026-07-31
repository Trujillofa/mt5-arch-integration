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

if [[ -n "${DISPLAY:-}" ]]; then
  unset WAYLAND_DISPLAY || true
fi
export DISPLAY="${DISPLAY:-:0}"
export WINEDEBUG="${WINEDEBUG:--all}"
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-d3d11=b;d3d12=b;dxgi=b}"
wine reg delete 'HKEY_CURRENT_USER\Software\Wine\Explorer' /v Desktop /f >/dev/null 2>&1 || true

cd "$REPO_ROOT"

# Detect ghost via shipped Python
STATUS_JSON="$(uv run python - <<'PY'
import json
from mt5_arch.hypr_geometry import (
    fetch_clients,
    is_ghost_terminal,
    select_main_terminal,
    terminal64_process_running,
)
proc = terminal64_process_running()
main = None
try:
    main = select_main_terminal(fetch_clients())
except Exception as e:
    print(json.dumps({"process": proc, "main": None, "error": str(e)}))
    raise SystemExit(0)
print(json.dumps({
    "process": proc,
    "ghost": is_ghost_terminal(process_running=proc, main_window=main),
    "main_title": None if main is None else main.title,
}))
PY
)" || STATUS_JSON='{"process":false,"ghost":false}'

info "state: $STATUS_JSON"

GHOST="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('ghost', False))" "$STATUS_JSON")"
PROC="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('process', False))" "$STATUS_JSON")"
MAIN="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('main_title') or '')" "$STATUS_JSON")"

if [[ "$GHOST" == "True" ]] || [[ "$PROC" == "True" && -z "$MAIN" ]]; then
  info "Ghost or unmapped MT5 detected — killing process and restarting"
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

info "MT5 main window is visible: $MAIN"
if [[ "$FULLSCREEN" -eq 1 ]]; then
  "$SCRIPT_DIR/09-fullscreen-terminal.sh" --mode maximize || true
fi
info "OK — no recovery needed"
