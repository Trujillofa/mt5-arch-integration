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

info "Stopping MetaTrader terminal processes in $WINEPREFIX only..."
python3 <<'PY'
import os, signal, time
from pathlib import Path

prefix = os.path.realpath(os.path.expanduser(os.environ.get("WINEPREFIX") or ""))
if not prefix:
    print("  refuse: WINEPREFIX unset (will not kill every terminal64.exe)")
    raise SystemExit(0)

keys = ("terminal64.exe", "MetaEditor64.exe", "metaeditor64.exe", "metatester64.exe")

def belongs(pid: str) -> bool:
    try:
        env = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        env = None
    wp = None
    if env:
        for part in env.split(b"\x00"):
            if part.startswith(b"WINEPREFIX="):
                raw = part.split(b"=", 1)[1].decode("utf-8", "replace")
                wp = os.path.realpath(os.path.expanduser(raw)) if raw else None
                break
    if wp is not None:
        return wp == prefix
    try:
        return prefix in Path(f"/proc/{pid}/maps").read_text(errors="replace")
    except OSError:
        return False

killed = []
for pid in list(os.listdir("/proc")):
    if not pid.isdigit():
        continue
    try:
        cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\x00", b" ").decode("utf-8", "replace")
    except OSError:
        continue
    if "bash" in cmd or "extglob" in cmd:
        continue
    if not any(k in cmd for k in keys):
        continue
    if not belongs(pid):
        continue
    print(f"  kill {pid}: {cmd[:90]}")
    try:
        os.kill(int(pid), signal.SIGTERM)
        killed.append(int(pid))
    except ProcessLookupError:
        pass
time.sleep(2)
for pid in killed:
    try:
        os.kill(pid, 0)
        os.kill(pid, signal.SIGKILL)
        print(f"  SIGKILL {pid}")
    except ProcessLookupError:
        pass
print("  done")
PY

term="$(find_terminal64)" || die "terminal64.exe not found. Run ./scripts/02-install-mt5.sh"
# If path is Windows-style in .env, resolve Linux path
if [[ "$term" == [Cc]:* ]] || [[ "$term" == *Program\ Files* && ! -f "$term" ]]; then
  term="$(find "$WINEPREFIX" -type f -name 'terminal64.exe' 2>/dev/null | head -n 1 || true)"
fi
[[ -n "$term" && -f "$term" ]] || die "could not resolve terminal64.exe under $WINEPREFIX"

info "Starting: $term"
nohup wine "$term" /portable >>/tmp/mt5-terminal.log 2>&1 &
echo $! >/tmp/mt5-terminal.pid
info "PID $(cat /tmp/mt5-terminal.pid)  log=/tmp/mt5-terminal.log"

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
        hypr_move_window_workspace "address:${MAIN_ADDR}" "$cur"
      fi
      hypr_focus_window "address:${MAIN_ADDR}"
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
      hypr_focus_window "address:${addrs[0]}"
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
