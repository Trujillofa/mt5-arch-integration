#!/usr/bin/env bash
# Shared helpers for mt5-arch-integration scripts.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Load .env if present. Does not override variables already set in the environment
# (so WINEPREFIX=~/.mt5-staging ./scripts/13-force-login-bridge.sh works).
load_dotenv() {
  local env_file="${1:-$REPO_ROOT/.env}"
  if [[ -f "$env_file" ]]; then
    local line key val
    while IFS= read -r line || [[ -n "$line" ]]; do
      # strip CR, skip blanks/comments
      line="${line//$'\r'/}"
      line="${line#"${line%%[![:space:]]*}"}"
      [[ -z "$line" || "$line" =~ ^# ]] && continue
      # Broker profiles use `export KEY=value`; strip so the key is valid.
      if [[ "$line" == export[[:space:]]* ]]; then
        line="${line#export}"
        line="${line#"${line%%[![:space:]]*}"}"
      fi
      [[ "$line" != *=* ]] && continue
      key="${line%%=*}"
      val="${line#*=}"
      # trim key whitespace
      key="${key#"${key%%[![:space:]]*}"}"
      key="${key%"${key##*[![:space:]]}"}"
      [[ -z "$key" ]] && continue
      # strip optional surrounding quotes on value
      if [[ "$val" =~ ^\".*\"$ ]]; then val="${val:1:-1}"
      elif [[ "$val" =~ ^\'.*\'$ ]]; then val="${val:1:-1}"
      fi
      # skip if already set in environment
      if [[ -n "${!key+x}" ]]; then
        continue
      fi
      export "$key=$val"
    done <"$env_file"
  fi
}

# Charts stay on Wine builtin d3d11/dxgi (start scripts set WINEDLLOVERRIDES).
# Market / AI / reports use Edge WebView2, which paints blank on that stub.
# Software-render the WebView only — do not drop the d3d overrides globally.
# --disable-gpu fights ANGLE; swiftshader is the path that actually paints.
MT5_WEBVIEW2_BROWSER_ARGUMENTS_DEFAULT='--use-angle=swiftshader --enable-unsafe-swiftshader --no-sandbox'

export_wine_webview_env() {
  export WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS="${WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:-$MT5_WEBVIEW2_BROWSER_ARGUMENTS_DEFAULT}"
}

# Write HKCU\Control Panel\Desktop LogPixels (Wine user.reg). Prefix-wide.
# Uses DPI / MT5_LOG_PIXELS (96–192). Requires WINEPREFIX. No second DPI path.
apply_wine_logpixels() {
  local dpi="${1:-${DPI:-${MT5_LOG_PIXELS:-120}}}"
  [[ -n "${WINEPREFIX:-}" && -d "${WINEPREFIX}" ]] || die "WINEPREFIX missing for LogPixels"
  if ! [[ "$dpi" =~ ^[0-9]+$ ]] || (( dpi < 96 || dpi > 192 )); then
    die "LogPixels=$dpi out of range 96–192 (MT5_LOG_PIXELS)"
  fi
  wine reg add 'HKCU\Control Panel\Desktop' /v LogPixels /t REG_DWORD /d "$dpi" /f >/dev/null
}

ensure_wine_webview_reg() {
  export_wine_webview_env
  command -v wine >/dev/null 2>&1 || return 0
  [[ -n "${WINEPREFIX:-}" && -d "${WINEPREFIX}" ]] || return 0
  # Edge 151 paints nothing if Wine pins the child to XP (seen on this host).
  wine reg add 'HKCU\Software\Wine' /v Version /t REG_SZ /d win11 /f >/dev/null 2>&1 || true
  wine reg add 'HKCU\Software\Wine\AppDefaults\msedgewebview2.exe' \
    /v Version /t REG_SZ /d win11 /f >/dev/null 2>&1 || true
  wine reg add 'HKCU\Software\Wine\AppDefaults\msedge.exe' \
    /v Version /t REG_SZ /d win11 /f >/dev/null 2>&1 || true
  wine reg add 'HKCU\Environment' /v WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS \
    /t REG_SZ /d "${WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS}" /f >/dev/null 2>&1 || true
}

export_wine_env() {
  export WINEPREFIX="${WINEPREFIX:-$HOME/.mt5}"
  export WINEARCH="${WINEARCH:-win64}"
  # Reduce noise; keep GUI working
  export WINEDEBUG="${WINEDEBUG:--all}"
  export_wine_webview_env
}

# Rebuild force_src_bind.so when the .c is newer. Loopback listens must stay
# on 127.0.0.1 (official MCP); a stale .so remaps them onto the LAN NIC.
ensure_force_src_bind_so() {
  local src="$REPO_ROOT/scripts/wine-net/force_src_bind.c"
  local so="$REPO_ROOT/scripts/wine-net/force_src_bind.so"
  if [[ ! -f "$src" ]]; then
    return 0
  fi
  if [[ -f "$so" && ! "$src" -nt "$so" ]]; then
    return 0
  fi
  if ! command -v gcc >/dev/null 2>&1; then
    warn "gcc missing; cannot rebuild $so"
    return 0
  fi
  gcc -shared -fPIC -O2 -o "$so" "$src" -ldl
  info "rebuilt $so"
}

# Deny XInput2 to Wine books so one click cannot reach every book at once.
# Each prefix runs its own wineserver, so every book believes it is the
# foreground window, and Wine 11 Staging feeds XInput2 *raw* button events
# (broadcast to every root-window listener) into it. MT5 then acts on them:
# one right-click opened the chart menu in every running book (tested
# 2026-09-24, including a click on a non-Wine window). no_xi2.so refuses
# winex11's dlopen of libXi, which drops it back to core X11 events that the
# X server delivers to exactly one window. It must be in the environment when
# the prefix's session starts, since explorer.exe /desktop is the listener.
# Opt out with MT5_WINE_XI2=1.
ensure_no_xi2_so() {
  local src="$REPO_ROOT/scripts/wine-input/no_xi2.c"
  local so="$REPO_ROOT/scripts/wine-input/no_xi2.so"
  [[ -f "$src" ]] || return 0
  if [[ -f "$so" && ! "$src" -nt "$so" ]]; then
    return 0
  fi
  if ! command -v gcc >/dev/null 2>&1; then
    warn "gcc missing; cannot rebuild $so"
    return 0
  fi
  gcc -shared -fPIC -O2 -o "$so" "$src" -ldl
  info "rebuilt $so"
}

export_no_xi2_preload() {
  [[ "${MT5_WINE_XI2:-0}" == "1" ]] && return 0
  ensure_no_xi2_so
  local so="$REPO_ROOT/scripts/wine-input/no_xi2.so"
  [[ -f "$so" ]] || return 0
  case ":${LD_PRELOAD:-}:" in
    *":$so:"*) ;;
    *) export LD_PRELOAD="$so${LD_PRELOAD:+:$LD_PRELOAD}" ;;
  esac
}

# Ensure Wayland clipboard is visible to Wine/XWayland (Ctrl+V paste).
# Safe to call often; starts bridge if missing and does a one-shot sync.
ensure_clipboard_bridge() {
  local bridge="$REPO_ROOT/scripts/11-clipboard-bridge.sh"
  if [[ ! -x "$bridge" ]]; then
    return 0
  fi
  # Prefer not to fail start scripts if wl-paste/xclip missing
  if ! command -v wl-paste >/dev/null 2>&1 || ! command -v xclip >/dev/null 2>&1; then
    warn "clipboard bridge skipped (need wl-paste + xclip). Install: pacman -S wl-clipboard xclip"
    return 0
  fi
  # Keep WAYLAND_DISPLAY for the bridge (wine start scripts may unset it later)
  local saved_wl="${WAYLAND_DISPLAY:-}"
  if [[ -z "$saved_wl" ]]; then
    for sock in wayland-1 wayland-0; do
      if [[ -S "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/$sock" ]]; then
        saved_wl="$sock"
        break
      fi
    done
  fi
  DISPLAY="${DISPLAY:-:0}" WAYLAND_DISPLAY="$saved_wl" "$bridge" start >/dev/null 2>&1 || true
  DISPLAY="${DISPLAY:-:0}" WAYLAND_DISPLAY="$saved_wl" "$bridge" once >/dev/null 2>&1 || true
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "error: required command not found: $cmd" >&2
    return 1
  fi
}

info() { echo "==> $*"; }
warn() { echo "warning: $*" >&2; }
die()  { echo "error: $*" >&2; exit 1; }

branded_terminal64_dirnames() {
  # Brand install dirs first, generic MetaTrader 5 last (JSON SoT).
  python3 -c '
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
try:
    data = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    data = {}
branded, generic = [], []
for key, val in data.items():
    if not isinstance(val, str) or not val.strip():
        continue
    name = val.strip()
    if key.startswith("_"):
        if key == "_generic":
            generic.append(name)
        continue
    branded.append(name)
for name in branded + generic:
    print(name)
' "$REPO_ROOT/config/broker_install_dirs.json"
}

find_terminal64() {
  # Always honor the active WINEPREFIX. config/local.paths and MT5_TERMINAL_PATH
  # may hardcode ~/.mt5 from an older install — only use them if they live under
  # the current prefix (never source local.paths; that used to clobber WINEPREFIX).
  # Prefer the branded installer under this prefix; the generic MetaQuotes tree
  # often auths in the title bar only and then shows "not connected to internet".
  local prefix="${WINEPREFIX:-$HOME/.mt5}"
  local candidate found local_term name

  if [[ -f "$REPO_ROOT/config/broker_install_dirs.json" ]]; then
    while IFS= read -r name; do
      [[ -z "$name" ]] && continue
      candidate="$prefix/drive_c/Program Files/$name/terminal64.exe"
      if [[ -f "$candidate" ]]; then
        echo "$candidate"
        return 0
      fi
    done < <(branded_terminal64_dirnames)
  fi

  candidate="$prefix/drive_c/Program Files/MetaTrader 5/terminal64.exe"
  if [[ -f "$candidate" ]]; then
    echo "$candidate"
    return 0
  fi

  found="$(find "$prefix" -type f -name 'terminal64.exe' 2>/dev/null | head -n 1 || true)"
  if [[ -n "$found" ]]; then
    echo "$found"
    return 0
  fi

  if [[ -n "${MT5_TERMINAL_PATH:-}" && -f "$MT5_TERMINAL_PATH" ]]; then
    case "$MT5_TERMINAL_PATH" in
      "$prefix"/*)
        echo "$MT5_TERMINAL_PATH"
        return 0
        ;;
    esac
  fi

  if [[ -f "$REPO_ROOT/config/local.paths" ]]; then
    local_term="$(
      # shellcheck disable=SC1091
      MT5_TERMINAL_PATH=""
      source "$REPO_ROOT/config/local.paths" >/dev/null 2>&1 || true
      printf '%s' "${MT5_TERMINAL_PATH:-}"
    )"
    if [[ -n "$local_term" && -f "$local_term" ]]; then
      case "$local_term" in
        "$prefix"/*)
          echo "$local_term"
          return 0
          ;;
      esac
    fi
  fi

  return 1
}

write_local_paths() {
  local terminal_path="$1"
  local server_path="${2:-}"
  mkdir -p "$REPO_ROOT/config"
  cat >"$REPO_ROOT/config/local.paths" <<EOF
# Generated by install scripts — do not commit.
MT5_TERMINAL_PATH="$terminal_path"
MT5_SERVER_EXE="$server_path"
WINEPREFIX="${WINEPREFIX:-$HOME/.mt5}"
EOF
  info "Wrote $REPO_ROOT/config/local.paths"
}

default_mt5_setup_candidates() {
  cat <<EOF
${MT5_SETUP:-}
$HOME/storage/Downloads/mt5setup.exe
$HOME/Downloads/mt5setup.exe
/tmp/mt5setup.exe
EOF
}

find_mt5_setup() {
  local candidate
  while IFS= read -r candidate; do
    [[ -z "$candidate" ]] && continue
    if [[ -f "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done < <(default_mt5_setup_candidates)
  return 1
}

mt5server_dir() {
  echo "${WINEPREFIX:-$HOME/.mt5}/drive_c/mt5linux"
}

mt5server_path() {
  echo "$(mt5server_dir)/mt5server.exe"
}

# Hyprland 0.56+ evaluates `hyprctl dispatch` as Lua. Use `hyprctl eval`.
hypr_eval() {
  hyprctl eval "$1" >/dev/null 2>&1 || true
}

_hypr_safe_selector() {
  local sel="${1:-}"
  [[ -n "$sel" ]] || return 1
  case "$sel" in
    *\'*|*\\*)
      warn "refusing hypr selector with quotes: $sel"
      return 1
      ;;
  esac
  printf '%s' "$sel"
}

hypr_focus_window() {
  local sel
  sel="$(_hypr_safe_selector "${1:-}")" || return 0
  hypr_eval "hl.dispatch(hl.dsp.focus({ window = '${sel}' }))"
}

hypr_move_window_workspace() {
  local sel ws follow
  sel="$(_hypr_safe_selector "${1:-}")" || return 0
  ws="${2:-}"
  follow="${3:-true}"
  [[ -n "$ws" ]] || return 0
  case "$follow" in
    true|false) ;;
    *) follow=true ;;
  esac
  hypr_eval "hl.dispatch(hl.dsp.window.move({ window = '${sel}', workspace = ${ws}, follow = ${follow} }))"
}

# Survive agent/Cursor shell teardown. nohup from a short command still dies
# with the process group; setsid -f starts a new session.
start_terminal64_detached() {
  local term="$1"
  shift || true
  local dir log prefix_name
  [[ -n "$term" && -f "$term" ]] || return 1
  recycle_prefix_wineserver_if_idle
  dir="$(cd "$(dirname "$term")" && pwd)"
  prefix_name="$(basename "$(realpath "${WINEPREFIX:-$HOME/.mt5}")")"
  log="/tmp/mt5-${prefix_name}-terminal.log"
  (
    cd "$dir"
    unset WAYLAND_DISPLAY || true
    case "$(realpath "${WINEPREFIX:-}")" in
      *mt5-vantage*) ;;
      *) unset LD_PRELOAD || true ;;
    esac
    export_no_xi2_preload
    export DISPLAY="${DISPLAY:-:0}"
    export WINEPREFIX="${WINEPREFIX}"
    export WINEARCH="${WINEARCH:-win64}"
    export WINEDEBUG="${WINEDEBUG:--all}"
    export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-d3d11=b;d3d12=b;dxgi=b}"
    export_wine_webview_env
    setsid -f wine ./terminal64.exe "$@" </dev/null >>"$log" 2>&1
  )
  info "detached $prefix_name pid-session (log $log)"
}

# Workspace a book's windows belong on. MT5_WORKSPACE is the per-broker pin
# (set it in config/brokers/<broker>.env); MT5_BG_WORKSPACE is the shared
# parking workspace for the prop-firm tab group. Placing by Wine prefix is the
# only thing that works here -- every book shares class terminal64.exe, and a
# Hyprland title rule cannot place one, because a terminal maps as
# "MetaTrader 5" and only gains its broker name after login.
mt5_target_workspace() {
  echo "${MT5_WORKSPACE:-${MT5_BG_WORKSPACE:-11}}"
}

park_prefix_terminals_background() {
  local prefix="${1:-${WINEPREFIX:-}}"
  local ws="${2:-$(mt5_target_workspace)}"
  [[ -n "$prefix" ]] || return 0
  command -v hyprctl >/dev/null 2>&1 || return 0
  PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:$PYTHONPATH}" python3 -c '
import sys
from mt5_arch.hypr_geometry import park_prefix_terminals_silent
park_prefix_terminals_silent(sys.argv[1], int(sys.argv[2]))
' "$prefix" "$ws" >/dev/null 2>&1 || true
}

# --- prefix-scoped process control (PR #36 dialect) ---
# Prefix lives in /proc/<pid>/environ as WINEPREFIX=, not in argv.
# cmdline is usually `./terminal64.exe /portable` — never pkill -f "$WINEPREFIX".

require_wineprefix() {
  local raw="${1:-${WINEPREFIX:-}}"
  if [[ -z "$raw" ]]; then
    die "WINEPREFIX is empty; refusing host-wide wineserver/terminal kill"
  fi
  if [[ "$raw" == "~" ]]; then
    raw="$HOME"
  elif [[ "$raw" == "~/"* ]]; then
    raw="$HOME/${raw#~/}"
  fi
  local resolved
  resolved="$(readlink -f -- "$raw" 2>/dev/null || true)"
  if [[ -z "$resolved" || ! -d "$resolved" ]]; then
    die "WINEPREFIX is not an existing prefix directory: $raw"
  fi
  export WINEPREFIX="$resolved"
}

# Dry: print MetaTrader pids bound to $WINEPREFIX (no signals).
list_terminal64_pids() {
  require_wineprefix
  PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
from mt5_arch.hypr_geometry import list_terminal64_pids

for pid in list_terminal64_pids():
    print(pid)
PY
}

# SIGTERM/SIGKILL MetaTrader processes whose environ WINEPREFIX= matches.
kill_terminal64_processes() {
  require_wineprefix
  PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
from mt5_arch.hypr_geometry import kill_terminal64_processes

killed = kill_terminal64_processes()
for pid in killed:
    print(f"  kill {pid}")
print("  done")
PY
}

# Kill only this prefix's wineserver (fresh server so LD_PRELOAD applies).
# MUST be `env WINEPREFIX=... wineserver -k` after require_wineprefix.
kill_prefix_wineserver() {
  require_wineprefix
  if ! command -v wineserver >/dev/null 2>&1; then
    warn "wineserver not on PATH; skip prefix-scoped wineserver -k"
    return 0
  fi
  info "Stopping wineserver for WINEPREFIX=$WINEPREFIX only"
  env WINEPREFIX="$WINEPREFIX" wineserver -k || true
}

# New wine clients join the existing wineserver. explorer.exe, the XInput2
# listener, keeps the environment it was started with, so LD_PRELOAD on a
# later client does not deny libXi. Recycle only when this prefix has no
# terminal64 left: a cold start gets a new explorer, a live book is not bounced.
# 07 is an explicit restart and calls kill_prefix_wineserver itself.
recycle_prefix_wineserver_if_idle() {
  require_wineprefix
  local pids
  if ! pids="$(list_terminal64_pids)"; then
    warn "could not list terminal64 pids; not recycling wineserver"
    return 0
  fi
  if [[ -n "${pids//[$' \t\n\r']/}" ]]; then
    return 0
  fi
  kill_prefix_wineserver
}
