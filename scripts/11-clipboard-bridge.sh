#!/usr/bin/env bash
# Bridge Wayland clipboard ↔ X11 so Wine/XWayland MetaTrader can paste (Ctrl+V).
#
# Hyprland + Omarchy apps copy into the Wayland clipboard (wl-copy). MT5 runs as
# XWayland and only sees the X11 CLIPBOARD/PRIMARY selections. Without a bridge,
# Ctrl+V / Shift+Insert in MT5 paste nothing.
#
# Usage:
#   ./scripts/11-clipboard-bridge.sh start|stop|status|sync|once
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

PIDFILE="${MT5_CLIP_BRIDGE_PID:-/tmp/mt5-clipboard-bridge.pid}"
LOGFILE="${MT5_CLIP_BRIDGE_LOG:-/tmp/mt5-clipboard-bridge.log}"
WORKER_TAG="mt5-clipboard-bridge-worker"

need_tools() {
  require_cmd wl-paste
  require_cmd wl-copy
  require_cmd xclip
}

# One-shot: push current Wayland text into X11 CLIPBOARD + PRIMARY
sync_wl_to_x11() {
  local content
  content="$(wl-paste --type text --no-newline 2>/dev/null || wl-paste --no-newline 2>/dev/null || true)"
  if [[ -z "${content}" ]]; then
    return 0
  fi
  printf '%s' "$content" | xclip -selection clipboard -i
  printf '%s' "$content" | xclip -selection primary -i
}

is_running() {
  # Prefer pidfile; fall back to pgrep on worker tag
  if [[ -f "$PIDFILE" ]]; then
    local pid
    pid="$(cat "$PIDFILE" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  pgrep -f "$WORKER_TAG" >/dev/null 2>&1
}

cmd_status() {
  need_tools
  if is_running; then
    local pid
    pid="$(cat "$PIDFILE" 2>/dev/null || pgrep -f "$WORKER_TAG" | head -1 || true)"
    info "clipboard bridge running pid=${pid:-?} log=$LOGFILE"
    echo "  wayland: $(wl-paste --no-newline 2>/dev/null | head -c 60 | tr '\n' ' ')"
    echo "  x11clip: $(xclip -selection clipboard -o 2>/dev/null | head -c 60 | tr '\n' ' ')"
    return 0
  fi
  info "clipboard bridge not running"
  return 1
}

cmd_stop() {
  if [[ -f "$PIDFILE" ]]; then
    local pid
    pid="$(cat "$PIDFILE" 2>/dev/null || true)"
    if [[ -n "$pid" ]]; then
      kill "$pid" 2>/dev/null || true
      # children of watcher
      pkill -P "$pid" 2>/dev/null || true
      sleep 0.2
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PIDFILE"
  fi
  pkill -f "$WORKER_TAG" 2>/dev/null || true
  pkill -f 'wl-paste --type text --watch' 2>/dev/null || true
  info "clipboard bridge stopped"
}

run_worker() {
  # Invoked as background process. argv0 tagged for pgrep.
  echo "[$(date -Iseconds)] bridge start DISPLAY=${DISPLAY:-} WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-}"

  # On every Wayland clipboard change, mirror into X11 CLIPBOARD + PRIMARY.
  # wl-paste --watch passes clipboard data on stdin to the command.
  exec -a "$WORKER_TAG" wl-paste --type text --watch bash -c '
    data=$(cat)
    [ -z "$data" ] && exit 0
    printf %s "$data" | xclip -selection clipboard -i
    printf %s "$data" | xclip -selection primary -i
  '
}

cmd_start() {
  need_tools
  # Bridge needs BOTH sockets. Never unset WAYLAND_DISPLAY for this process.
  export DISPLAY="${DISPLAY:-:0}"
  if [[ -z "${WAYLAND_DISPLAY:-}" ]]; then
    for sock in wayland-1 wayland-0; do
      if [[ -S "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/$sock" ]]; then
        export WAYLAND_DISPLAY="$sock"
        break
      fi
    done
  fi
  [[ -n "${WAYLAND_DISPLAY:-}" ]] || die "WAYLAND_DISPLAY not set and no wayland socket found"

  if is_running; then
    info "clipboard bridge already running"
    sync_wl_to_x11 || true
    return 0
  fi

  sync_wl_to_x11 || true

  # Export env for the background worker
  nohup env DISPLAY="$DISPLAY" WAYLAND_DISPLAY="$WAYLAND_DISPLAY" \
    bash "$SCRIPT_DIR/11-clipboard-bridge.sh" --worker \
    >>"$LOGFILE" 2>&1 &
  echo $! >"$PIDFILE"
  sleep 0.4
  if is_running; then
    info "clipboard bridge started pid=$(cat "$PIDFILE") (log: $LOGFILE)"
    info "In MT5 use Ctrl+V, Shift+Insert, or Super+V (Omarchy → Shift+Insert)"
  else
    warn "bridge failed to stay up — see $LOGFILE"
    tail -20 "$LOGFILE" 2>/dev/null || true
    return 1
  fi
}

cmd_once() {
  need_tools
  export DISPLAY="${DISPLAY:-:0}"
  sync_wl_to_x11
  info "synced Wayland → X11 clipboard"
  local preview
  preview="$(xclip -selection clipboard -o 2>/dev/null | head -c 80 | tr '\n' ' ')"
  echo "  x11: ${preview}"
}

case "${1:-start}" in
  --worker) run_worker ;;
  start) cmd_start ;;
  stop) cmd_stop ;;
  status) cmd_status ;;
  sync|once) cmd_once ;;
  -h|--help)
    sed -n '2,12p' "$0"
    echo "Commands: start | stop | status | sync|once"
    ;;
  *) die "unknown arg: $1 (use start|stop|status|once)" ;;
esac
