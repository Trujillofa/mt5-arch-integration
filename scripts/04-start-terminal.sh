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

# Clipboard bridge BEFORE unsetting WAYLAND (Wine needs X11 clip; Linux apps use Wayland)
ensure_clipboard_bridge

# Prefer XWayland for Wine input
if [[ -n "${DISPLAY:-}" ]]; then
  unset WAYLAND_DISPLAY || true
fi
export DISPLAY="${DISPLAY:-:0}"
export WINEDEBUG="${WINEDEBUG:--all}"
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-d3d11=b;d3d12=b;dxgi=b}"
# Never enable Wine virtual desktop (breaks mouse under Hyprland)
wine reg delete 'HKEY_CURRENT_USER\Software\Wine\Explorer' /v Desktop /f >/dev/null 2>&1 || true

# Single instance: avoid zombie second terminals; recover ghosts automatically
if python3 <<'PY' >/tmp/mt5-existing.pid 2>/dev/null
import os, sys
from pathlib import Path
prefix = os.path.realpath(os.path.expanduser(os.environ.get("WINEPREFIX") or ""))
if not prefix:
    sys.exit(1)
for pid in os.listdir("/proc"):
    if not pid.isdigit():
        continue
    try:
        cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\x00", b" ").decode()
    except OSError:
        continue
    if "bash" in cmd:
        continue
    if "terminal64.exe" not in cmd:
        continue
    wp = None
    try:
        env = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        env = None
    if env:
        for part in env.split(b"\x00"):
            if part.startswith(b"WINEPREFIX="):
                raw = part.split(b"=", 1)[1].decode("utf-8", "replace")
                wp = os.path.realpath(os.path.expanduser(raw)) if raw else None
                break
    if wp is None:
        try:
            wp = prefix if prefix in Path(f"/proc/{pid}/maps").read_text(errors="replace") else None
        except OSError:
            wp = None
    if wp == prefix:
        print(pid)
        sys.exit(0)
sys.exit(1)
PY
then
  EXISTING_PID="$(cat /tmp/mt5-existing.pid)"
  # Count Hyprland terminal64 windows (0 ⇒ ghost process)
  WIN_COUNT=0
  if command -v hyprctl >/dev/null 2>&1; then
    WIN_COUNT="$(hyprctl clients -j 2>/dev/null | python3 -c "
import sys, json
try:
    cs = json.load(sys.stdin)
except Exception:
    print(0); raise SystemExit(0)
print(sum(1 for c in cs if c.get('class') == 'terminal64.exe'))
" 2>/dev/null || echo 0)"
  fi
  if [[ "${WIN_COUNT:-0}" -eq 0 ]]; then
    warn "terminal64.exe pid $EXISTING_PID is a GHOST (no Hyprland window) — recovering"
    exec "$SCRIPT_DIR/10-recover-terminal.sh" "$@"
  fi
  warn "terminal64.exe already running (pid $EXISTING_PID, windows=$WIN_COUNT)."
  warn "Use ./scripts/07-restart-terminal.sh to kill and relaunch, or attach to the existing window."
  if command -v hyprctl >/dev/null 2>&1; then
    hyprctl clients -j 2>/dev/null | python3 -c "
import sys, json
for c in json.load(sys.stdin):
    if c.get('class') == 'terminal64.exe':
        print('  window:', c.get('title'), 'ws=', (c.get('workspace') or {}).get('id'))
" 2>/dev/null || true
  fi
  # Still apply fullscreen if requested on the live window
  for arg in "$@"; do
    case "$arg" in
      --fullscreen|--maximize)
        "$SCRIPT_DIR/09-fullscreen-terminal.sh" --mode maximize || true
        ;;
    esac
  done
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
FULLSCREEN=0
for arg in "$@"; do
  case "$arg" in
    --detach) DETACH=1 ;;
    --no-portable) PORTABLE=0 ;;
    --fullscreen|--maximize) FULLSCREEN=1 ;;
    -h|--help)
      echo "Usage: $0 [--detach] [--no-portable] [--fullscreen]"
      echo "  --fullscreen  after start, maximize main MT5 on active monitor"
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
    if not a:
        continue
    sel = f'address:{a}'
    if cur:
        lua = (
            'hl.dispatch(hl.dsp.window.move({ window = \'' + sel + '\', workspace = '
            + cur + ', follow = true }))'
        )
        subprocess.run(['hyprctl', 'eval', lua], capture_output=True)
    subprocess.run(
        ['hyprctl', 'eval', 'hl.dispatch(hl.dsp.focus({ window = \'' + sel + '\' }))'],
        capture_output=True,
    )
" 2>/dev/null || true
  fi
  if [[ "$FULLSCREEN" -eq 1 ]]; then
    sleep 2
    info "Applying maximize on active monitor..."
    "$SCRIPT_DIR/09-fullscreen-terminal.sh" --mode maximize || warn "fullscreen apply deferred (login dialog?)"
  fi
  exit 0
fi

if [[ "$FULLSCREEN" -eq 1 ]]; then
  warn "--fullscreen requires --detach (will apply after background start)"
fi
exec wine "$term" "${ARGS[@]}"
