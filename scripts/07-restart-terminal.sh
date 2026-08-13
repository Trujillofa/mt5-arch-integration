#!/usr/bin/env bash
# Kill stuck MetaTrader terminal and relaunch onto the current Hyprland workspace.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env
require_cmd wine

# Clipboard bridge BEFORE unsetting WAYLAND (Wine/XWayland paste)
ensure_clipboard_bridge

# Prefer XWayland path under Hyprland (more reliable input for Wine)
if [[ -n "${DISPLAY:-}" ]]; then
  unset WAYLAND_DISPLAY || true
fi
export DISPLAY="${DISPLAY:-:0}"
export WINEDEBUG="${WINEDEBUG:--all}"
# Soften GPU paths that often paint black under Wine
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-d3d11=b;d3d12=b;dxgi=b}"

# Never use Wine virtual desktop here (breaks mouse with Hyprland)
wine reg delete 'HKEY_CURRENT_USER\Software\Wine\Explorer' /v Desktop /f >/dev/null 2>&1 || true

info "Stopping MetaTrader terminal processes..."
# Graceful WM_CLOSE first — signals alone lose all chart/indicator edits. See lib.sh.
#
# Scoped to this WINEPREFIX: this script relaunches exactly one terminal, and several
# brokers run side by side, so stopping all of them would leave the others dead.
# Set MT5_STOP_ALL=1 for the old behaviour of stopping every MetaTrader process.
if [[ "${MT5_STOP_ALL:-0}" == "1" ]]; then
  stop_terminal_gracefully "${MT5_STOP_TIMEOUT:-40}"
else
  stop_terminal_gracefully "${MT5_STOP_TIMEOUT:-40}" "$WINEPREFIX"
fi

term="$(find_terminal64)" || die "terminal64.exe not found. Run ./scripts/02-install-mt5.sh"
# If path is Windows-style in .env, resolve Linux path
if [[ "$term" == [Cc]:* ]] || [[ "$term" == *Program\ Files* && ! -f "$term" ]]; then
  term="$(find "$WINEPREFIX" -type f -name 'terminal64.exe' 2>/dev/null | head -n 1 || true)"
fi
[[ -n "$term" && -f "$term" ]] || die "could not resolve terminal64.exe under $WINEPREFIX"

# Launch, then confirm it survived — and retry if it did not.
#
# A terminal killed hard can take its wineserver down with it, and a launch that lands
# while that wineserver is still shutting down dies about a second later with
#   wine client error:0: recvmsg: Connection reset by peer
# Observed 2026-08-13 restarting Vantage out of a win32u deadlock: this script printed
# a healthy PID, the process was gone moments later, and the account was left with
# three open positions and no terminal at all until it was launched by hand.
#
# Checking liveness after a short settle catches that, and any other instant-exit,
# without guessing at the cause. Do NOT check $! — that is the wine loader, which
# exits normally; ask for a terminal64 in this prefix instead.
launched=0
for attempt in 1 2 3; do
  info "Starting: $term (attempt $attempt)"
  nohup wine "$term" /portable >>/tmp/mt5-terminal.log 2>&1 &
  echo $! >/tmp/mt5-terminal.pid
  sleep 5
  mapfile -t live_pids < <(mt5_terminal_pids "$WINEPREFIX")
  if [[ ${#live_pids[@]} -gt 0 ]]; then
    launched=1
    info "PID ${live_pids[0]}  log=/tmp/mt5-terminal.log"
    break
  fi
  warn "terminal exited immediately (see /tmp/mt5-terminal.log) — retrying in 5s"
  sleep 5
done
[[ "$launched" -eq 1 ]] || die "terminal failed to stay up after 3 attempts; check /tmp/mt5-terminal.log"

# Wait for main shell (not just Login), then move to active Hyprland workspace
if command -v hyprctl >/dev/null 2>&1; then
  info "Waiting for Hyprland main window..."
  MAIN_ADDR=""
  for _ in $(seq 1 40); do
    MAIN_ADDR="$(cd "$REPO_ROOT" && uv run python - <<'PY' 2>/dev/null || true
from mt5_arch.hypr_geometry import fetch_clients, select_main_terminal
m = select_main_terminal(fetch_clients())
print(m.address if m else "")
PY
)"
    if [[ -n "${MAIN_ADDR:-}" ]]; then
      cur="$(hyprctl activeworkspace -j 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || true)"
      if [[ -n "$cur" ]]; then
        hyprctl dispatch movetoworkspace "${cur},address:${MAIN_ADDR}" >/dev/null 2>&1 || true
      fi
      hyprctl dispatch focuswindow "address:${MAIN_ADDR}" >/dev/null 2>&1 || true
      info "Focused main terminal on workspace ${cur:-?} ($MAIN_ADDR)"
      break
    fi
    # Fallback: any terminal64 window (Login) — focus only, keep waiting for main
    mapfile -t addrs < <(hyprctl clients -j 2>/dev/null | python3 -c "
import sys, json
try:
    cs = json.load(sys.stdin)
except Exception:
    raise SystemExit(0)
for c in cs:
    if c.get('class') == 'terminal64.exe':
        print(c.get('address', ''))
" 2>/dev/null || true)
    if [[ ${#addrs[@]} -gt 0 && -n "${addrs[0]:-}" ]]; then
      hyprctl dispatch focuswindow "address:${addrs[0]}" >/dev/null 2>&1 || true
    fi
    sleep 0.4
  done
  if [[ -z "${MAIN_ADDR:-}" ]]; then
    warn "main window not ready yet (Login still open?); maximize may defer"
  fi
fi

FULLSCREEN=0
for arg in "$@"; do
  case "$arg" in
    --fullscreen|--maximize) FULLSCREEN=1 ;;
  esac
done

if [[ "$FULLSCREEN" -eq 1 ]]; then
  # Wait briefly more so title becomes main shell after auto-login
  sleep 1.5
  info "Applying maximize on active monitor..."
  export MT5_NO_AUTO_RECOVER="${MT5_NO_AUTO_RECOVER:-1}"
  "$SCRIPT_DIR/09-fullscreen-terminal.sh" --mode maximize || warn "fullscreen apply deferred (login dialog?)"
fi

info "Login to WSFmarkets-Server only. Keep charts as tabs (not undocked)."
info "Fullscreen later: ./scripts/09-fullscreen-terminal.sh"
info "Status: ./scripts/08-status.sh"
