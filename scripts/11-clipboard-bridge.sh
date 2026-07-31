#!/usr/bin/env bash
# Bridge Wayland clipboard → X11 so Wine/XWayland MetaTrader can paste.
#
# Critical details:
# - Only sync *text* (screenshots/PNG must not wipe/replace X11 text incorrectly)
# - Offer UTF8_STRING (Wine prefers this)
# - Keep WAYLAND_DISPLAY set for the watcher; Wine itself uses DISPLAY=:0
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
CLIP_PY="$SCRIPT_DIR/clip_to_x11.py"

need_tools() {
  require_cmd wl-paste
  require_cmd wl-copy
  require_cmd xclip
}

resolve_wayland() {
  export DISPLAY="${DISPLAY:-:0}"
  if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
    return 0
  fi
  for sock in wayland-1 wayland-0; do
    if [[ -S "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/$sock" ]]; then
      export WAYLAND_DISPLAY="$sock"
      return 0
    fi
  done
  return 1
}

# One-shot: Wayland *text* → X11
sync_wl_to_x11() {
  local content
  content="$(wl-paste --type text --no-newline 2>/dev/null || true)"
  if [[ -z "${content}" ]]; then
    return 1
  fi
  # Reject accidental binary
  if [[ "$content" == $'\x89PNG'* ]]; then
    return 1
  fi
  if [[ -f "$CLIP_PY" ]]; then
    printf '%s' "$content" | python3 "$CLIP_PY" || true
  fi
  printf '%s' "$content" | xclip -selection clipboard -t UTF8_STRING -i
  printf '%s' "$content" | xclip -selection primary -t UTF8_STRING -i
  return 0
}

is_running() {
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
  resolve_wayland || true
  if is_running; then
    local pid
    pid="$(cat "$PIDFILE" 2>/dev/null || pgrep -f "$WORKER_TAG" | head -1 || true)"
    info "clipboard bridge running pid=${pid:-?} log=$LOGFILE"
  else
    info "clipboard bridge not running"
  fi
  local wl x11
  wl="$(wl-paste --type text --no-newline 2>/dev/null | head -c 80 | tr '\n' ' ' || true)"
  x11="$(xclip -selection clipboard -o -t UTF8_STRING 2>/dev/null | head -c 80 | tr '\n' ' ' || true)"
  if [[ -z "$x11" ]]; then
    x11="$(xclip -selection clipboard -o 2>/dev/null | head -c 80 | tr '\n' ' ' || true)"
  fi
  echo "  wayland_text: ${wl:-<empty or image>}"
  echo "  x11_utf8:     ${x11:-<empty>}"
  if [[ -n "$wl" && -n "$x11" && "$wl" == "$x11" ]]; then
    echo "  match: yes"
  else
    echo "  match: no  (copy text again, then: $0 once)"
  fi
  is_running
}

cmd_stop() {
  if [[ -f "$PIDFILE" ]]; then
    local pid
    pid="$(cat "$PIDFILE" 2>/dev/null || true)"
    if [[ -n "$pid" ]]; then
      kill "$pid" 2>/dev/null || true
      pkill -P "$pid" 2>/dev/null || true
      sleep 0.2
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PIDFILE"
  fi
  pkill -f "$WORKER_TAG" 2>/dev/null || true
  # only our watchers, not system ones that only echo
  pkill -f 'mt5-clipboard-bridge' 2>/dev/null || true
  info "clipboard bridge stopped"
}

run_worker() {
  echo "[$(date -Iseconds)] bridge start DISPLAY=${DISPLAY:-} WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-}"
  # Only watch text MIME — screenshots won't fire empty overwrites
  exec -a "$WORKER_TAG" wl-paste --type text --watch bash -c '
    data=$(cat)
    [ -z "$data" ] && exit 0
    case "$data" in
      $'\''\x89PNG'\''*) exit 0 ;;
    esac
    printf %s "$data" | xclip -selection clipboard -t UTF8_STRING -i
    printf %s "$data" | xclip -selection primary -t UTF8_STRING -i
    if [ -f "'"$CLIP_PY"'" ]; then
      printf %s "$data" | python3 "'"$CLIP_PY"'" 2>/dev/null || true
    fi
  '
}

cmd_start() {
  need_tools
  resolve_wayland || die "WAYLAND_DISPLAY not set and no wayland socket found"

  if is_running; then
    info "clipboard bridge already running"
    sync_wl_to_x11 || true
    return 0
  fi

  sync_wl_to_x11 || true

  nohup env DISPLAY="$DISPLAY" WAYLAND_DISPLAY="$WAYLAND_DISPLAY" \
    bash "$SCRIPT_DIR/11-clipboard-bridge.sh" --worker \
    >>"$LOGFILE" 2>&1 &
  echo $! >"$PIDFILE"
  sleep 0.4
  if is_running; then
    info "clipboard bridge started pid=$(cat "$PIDFILE") (log: $LOGFILE)"
  else
    warn "bridge failed to stay up — see $LOGFILE"
    tail -20 "$LOGFILE" 2>/dev/null || true
    return 1
  fi
}

cmd_once() {
  need_tools
  resolve_wayland || true
  if sync_wl_to_x11; then
    info "synced Wayland text → X11 UTF8_STRING"
    local preview
    preview="$(xclip -selection clipboard -o -t UTF8_STRING 2>/dev/null | head -c 80 | tr '\n' ' ')"
    echo "  x11: ${preview}"
  else
    warn "no Wayland *text* to sync (clipboard may be a screenshot/image)"
    warn "copy text (Ctrl+C) from browser/terminal, then re-run: $0 once"
    return 1
  fi
}

case "${1:-start}" in
  --worker) run_worker ;;
  start) cmd_start ;;
  stop) cmd_stop ;;
  status) cmd_status || true ;;
  sync|once) cmd_once ;;
  -h|--help)
    sed -n '2,14p' "$0"
    echo "Commands: start | stop | status | once"
    echo "Hard paste into MT5: ./scripts/12-paste-into-mt5.sh [--type]"
    ;;
  *) die "unknown arg: $1 (use start|stop|status|once)" ;;
esac
