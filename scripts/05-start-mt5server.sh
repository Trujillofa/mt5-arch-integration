#!/usr/bin/env bash
# Start mt5server.exe (RPyC bridge) under Wine.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env
require_cmd wine

PORT="${MT5_RPYC_PORT:-18812}"
HOST_BIND="${MT5_RPYC_BIND:-127.0.0.1}"
SERVER_EXE="$(mt5server_path)"

[[ -f "$SERVER_EXE" ]] || die "mt5server.exe missing. Run ./scripts/03-install-mt5server.sh"

if ! find_terminal64 >/dev/null 2>&1; then
  warn "terminal64.exe not found — start MT5 first if the bridge fails to attach"
fi

info "Starting mt5server on ${HOST_BIND}:${PORT}"
info "WINEPREFIX=$WINEPREFIX"
info "Server: $SERVER_EXE"

# mt5server accepts -p/--port; keep bound to localhost by default for safety
ARGS=(-p "$PORT")
# Some builds accept --host; ignore if unsupported
if [[ -n "${MT5_RPYC_BIND:-}" ]]; then
  ARGS+=(--host "$HOST_BIND")
fi

if [[ "${1:-}" == "--detach" ]]; then
  nohup wine "$SERVER_EXE" "${ARGS[@]}" >/tmp/mt5-rpyc.log 2>&1 &
  echo $! >/tmp/mt5-rpyc.pid
  info "Detached PID $(cat /tmp/mt5-rpyc.pid); log: /tmp/mt5-rpyc.log"
  exit 0
fi

exec wine "$SERVER_EXE" "${ARGS[@]}"
