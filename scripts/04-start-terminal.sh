#!/usr/bin/env bash
# Start MetaTrader 5 terminal under Wine (Hyprland-safe defaults).
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

# Prefer XWayland for Wine input
if [[ -n "${DISPLAY:-}" ]]; then
  unset WAYLAND_DISPLAY || true
fi
export DISPLAY="${DISPLAY:-:0}"
export WINEDEBUG="${WINEDEBUG:--all}"
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-d3d11=b;d3d12=b;dxgi=b}"

# Single instance: avoid zombie second terminals
if python3 -c "
import os, sys
for pid in os.listdir('/proc'):
    if not pid.isdigit():
        continue
    try:
        cmd = open(f'/proc/{pid}/cmdline', 'rb').read().replace(b'\\x00', b' ').decode()
    except OSError:
        continue
    if 'bash' in cmd:
        continue
    if 'terminal64.exe' in cmd:
        print(pid)
        sys.exit(0)
sys.exit(1)
" >/tmp/mt5-existing.pid 2>/dev/null; then
  warn "terminal64.exe already running (pid $(cat /tmp/mt5-existing.pid))."
  warn "Use ./scripts/07-restart-terminal.sh to kill and relaunch, or attach to the existing window."
  if command -v hyprctl >/dev/null 2>&1; then
    hyprctl clients -j 2>/dev/null | python3 -c "
import sys, json
for c in json.load(sys.stdin):
    if c.get('class') == 'terminal64.exe':
        print('  window:', c.get('title'), 'ws=', (c.get('workspace') or {}).get('id'))
" 2>/dev/null || true
  fi
  exit 0
fi

term="$(find_terminal64)" || die "terminal64.exe not found. Run ./scripts/02-install-mt5.sh"
if [[ ! -f "$term" ]]; then
  term="$(find "$WINEPREFIX" -type f -name 'terminal64.exe' 2>/dev/null | head -n 1 || true)"
fi
[[ -n "$term" && -f "$term" ]] || die "could not resolve terminal64.exe"

info "Starting MetaTrader 5: $term"
info "WINEPREFIX=$WINEPREFIX  DISPLAY=$DISPLAY"
info "Login: WSFmarkets-Server only. Charts: see docs/CHARTS-AND-STABILITY.md"
info "Bridge EA: keep Mt5ArchBridge on one chart."

DETACH=0
PORTABLE=1
for arg in "$@"; do
  case "$arg" in
    --detach) DETACH=1 ;;
    --no-portable) PORTABLE=0 ;;
    -h|--help)
      echo "Usage: $0 [--detach] [--no-portable]"
      exit 0
      ;;
  esac
done

ARGS=()
if [[ "$PORTABLE" -eq 1 ]]; then
  ARGS+=(/portable)
fi

if [[ "$DETACH" -eq 1 ]]; then
  nohup wine "$term" "${ARGS[@]}" >>/tmp/mt5-terminal.log 2>&1 &
  echo $! >/tmp/mt5-terminal.pid
  info "Detached PID $(cat /tmp/mt5-terminal.pid); log: /tmp/mt5-terminal.log"
  # Best-effort focus on Hyprland
  if command -v hyprctl >/dev/null 2>&1; then
    sleep 3
    cur="$(hyprctl activeworkspace -j 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || true)"
    hyprctl clients -j 2>/dev/null | python3 -c "
import sys, json, subprocess
cur = '''${cur}'''
for c in json.load(sys.stdin):
    if c.get('class') != 'terminal64.exe':
        continue
    a = c.get('address')
    if cur:
        subprocess.run(['hyprctl', 'dispatch', 'movetoworkspace', f'{cur},address:{a}'], capture_output=True)
    subprocess.run(['hyprctl', 'dispatch', 'focuswindow', f'address:{a}'], capture_output=True)
" 2>/dev/null || true
  fi
  exit 0
fi

exec wine "$term" "${ARGS[@]}"
