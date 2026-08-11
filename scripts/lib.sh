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
      [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
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

export_wine_env() {
  export WINEPREFIX="${WINEPREFIX:-$HOME/.mt5}"
  export WINEARCH="${WINEARCH:-win64}"
  # Reduce noise; keep GUI working
  export WINEDEBUG="${WINEDEBUG:--all}"
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

mt5_terminal_pids() {
  local pid cmd
  for pid in /proc/[0-9]*; do
    pid="${pid#/proc/}"
    # Group the redirect so a process exiting mid-scan cannot print a bash error.
    cmd="$( { tr '\0' ' ' <"/proc/$pid/cmdline"; } 2>/dev/null || true)"
    [[ -z "$cmd" ]] && continue
    case "$cmd" in
      *bash*|*extglob*) continue ;;
    esac
    case "$cmd" in
      *terminal64.exe*|*MetaEditor64.exe*|*metaeditor64.exe*|*metatester64.exe*)
        echo "$pid" ;;
    esac
  done
}

# Stop MT5 the way Windows expects, so it runs its own shutdown path.
#
# MT5 only flushes chart state — indicators, objects, templates, timeframe, the
# MQL5/Profiles/Charts/<profile>/*.chr files — when the app closes itself. A POSIX
# SIGTERM to terminal64.exe under Wine does not become a WM_CLOSE, so the app never
# reaches that code: every chart edit made during the session is silently discarded.
# (Observed 2026-08-11: *.chr frozen at Aug 8 10:52 across several later sessions.)
#
# So: ask each window to close, give MT5 time to write, and only then escalate.
stop_terminal_gracefully() {
  local timeout="${1:-40}" pids wins w waited closed=0
  export DISPLAY="${DISPLAY:-:0}"

  mapfile -t pids < <(mt5_terminal_pids)
  if [[ ${#pids[@]} -eq 0 ]]; then
    info "No MetaTrader process running."
    return 0
  fi

  # Ask the compositor to close the window. Measured 2026-08-11 on Hyprland 0.56 +
  # XWayland, in order of what actually reaches MT5:
  #   hyprctl dispatch closewindow  -> MT5 exits in ~3s and writes every *.chr   WORKS
  #   xdotool windowquit            -> sends WM_DELETE_WINDOW; MT5 ignores it    NO-OP
  #   xdotool windowclose           -> destroys the X window, no WM_CLOSE at all LOSES DATA
  # The window advertises WM_DELETE_WINDOW in WM_PROTOCOLS, so the xdotool path looks
  # correct and silently is not — do not "simplify" back to it.
  if command -v hyprctl >/dev/null 2>&1; then
    mapfile -t wins < <(hyprctl clients -j 2>/dev/null | python3 -c "
import json, sys
try:
    for c in json.load(sys.stdin):
        if c.get('class') == 'terminal64.exe':
            print(c['address'])
except Exception:
    pass
" || true)
    for w in "${wins[@]}"; do
      [[ -z "$w" ]] && continue
      hyprctl dispatch closewindow "address:$w" >/dev/null 2>&1 && closed=1
    done
  fi

  if [[ "$closed" -eq 0 ]] && command -v xdotool >/dev/null 2>&1; then
    warn "hyprctl close unavailable — falling back to xdotool windowquit (unreliable for MT5)"
    mapfile -t wins < <(xdotool search --class '^terminal64\.exe$' 2>/dev/null || true)
    for w in "${wins[@]}"; do
      [[ -z "$w" ]] && continue
      xdotool windowquit "$w" 2>/dev/null && closed=1
    done
  fi

  # A ghost (process alive, zero windows) has nothing to ask and nothing to save;
  # waiting the full timeout would only slow 10-recover-terminal.sh down.
  if [[ "$closed" -eq 0 ]]; then
    warn "No MetaTrader window to close — terminating directly"
    timeout=0
  else
    info "Asked MetaTrader to close (WM_CLOSE); waiting up to ${timeout}s for it to save charts..."
  fi

  for ((waited = 0; waited < timeout; waited++)); do
    mapfile -t pids < <(mt5_terminal_pids)
    if [[ ${#pids[@]} -eq 0 ]]; then
      info "MetaTrader exited cleanly (charts saved)."
      return 0
    fi
    sleep 1
  done

  warn "MetaTrader still running after ${timeout}s — escalating (chart edits may be lost)"
  mapfile -t pids < <(mt5_terminal_pids)
  for w in "${pids[@]}"; do kill -TERM "$w" 2>/dev/null || true; done
  sleep 3
  mapfile -t pids < <(mt5_terminal_pids)
  for w in "${pids[@]}"; do
    kill -0 "$w" 2>/dev/null && { warn "SIGKILL $w"; kill -KILL "$w" 2>/dev/null || true; }
  done
  return 0
}

find_terminal64() {
  # Always honor the active WINEPREFIX. config/local.paths and MT5_TERMINAL_PATH
  # may hardcode ~/.mt5 from an older install — only use them if they live under
  # the current prefix (never source local.paths; that used to clobber WINEPREFIX).
  local prefix="${WINEPREFIX:-$HOME/.mt5}"
  local candidate found local_term

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
