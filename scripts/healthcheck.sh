#!/usr/bin/env bash
# Health check: terminal process, RPyC port, optional Python ping.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env

PORT="${MT5_RPYC_PORT:-18812}"
HOST="${MT5_RPYC_HOST:-localhost}"
status=0

info "Health check (host=$HOST port=$PORT prefix=$WINEPREFIX)"

# Terminal process
if pgrep -af 'terminal64\.exe' >/dev/null 2>&1; then
  info "OK: terminal64.exe process running"
else
  warn "terminal64.exe not running"
  status=1
fi

# mt5server process
if pgrep -af 'mt5server\.exe' >/dev/null 2>&1; then
  info "OK: mt5server.exe process running"
else
  warn "mt5server.exe not running"
  status=1
fi

# Port listening
if command -v ss >/dev/null 2>&1; then
  if ss -ltn "sport = :$PORT" 2>/dev/null | grep -q ":$PORT"; then
    info "OK: port $PORT is listening"
  else
    warn "port $PORT is not listening"
    status=1
  fi
elif command -v nc >/dev/null 2>&1; then
  if nc -z "$HOST" "$PORT" 2>/dev/null; then
    info "OK: can connect to $HOST:$PORT"
  else
    warn "cannot connect to $HOST:$PORT"
    status=1
  fi
else
  warn "ss/nc not available; skipped port check"
fi

# Optional Python ping
if [[ "${1:-}" == "--ping" ]] || [[ "${MT5_HEALTH_PING:-0}" == "1" ]]; then
  if command -v uv >/dev/null 2>&1; then
    if (cd "$REPO_ROOT" && uv run mt5-arch ping); then
      info "OK: mt5-arch ping succeeded"
    else
      warn "mt5-arch ping failed"
      status=1
    fi
  elif command -v mt5-arch >/dev/null 2>&1; then
    if mt5-arch ping; then
      info "OK: mt5-arch ping succeeded"
    else
      warn "mt5-arch ping failed"
      status=1
    fi
  else
    warn "mt5-arch not on PATH; skip Python ping (uv run from repo root)"
  fi
fi

if [[ "$status" -eq 0 ]]; then
  info "All checks passed."
else
  warn "One or more checks failed. See docs/TROUBLESHOOTING.md"
fi
exit "$status"
