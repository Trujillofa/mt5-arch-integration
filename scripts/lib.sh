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

# PIDs of MetaTrader processes. With an argument, only those whose WINEPREFIX matches
# it — several brokers run side by side (Vantage, Exness, FP Markets, WSF) and an
# unfiltered stop takes down all of them to restart one.
#
# Match on the command line, not /proc/<pid>/comm: Wine names the main thread "main",
# so a comm-based scan finds nothing and silently reports MT5 as not running.
mt5_terminal_pids() {
  local want="${1:-}" pid cmd pfx
  for pid in /proc/[0-9]*; do
    pid="${pid#/proc/}"
    # Group the redirect so a process exiting mid-scan cannot print a bash error.
    cmd="$( { tr '\0' ' ' <"/proc/$pid/cmdline"; } 2>/dev/null || true)"
    [[ -z "$cmd" ]] && continue
    case "$cmd" in
      *bash*|*extglob*) continue ;;
    esac
    case "$cmd" in
      *terminal64.exe*|*MetaEditor64.exe*|*metaeditor64.exe*|*metatester64.exe*) ;;
      *) continue ;;
    esac
    if [[ -n "$want" ]]; then
      pfx="$( { tr '\0' '\n' <"/proc/$pid/environ"; } 2>/dev/null | sed -n 's/^WINEPREFIX=//p' | head -1)"
      [[ "${pfx%/}" == "${want%/}" ]] || continue
    fi
    echo "$pid"
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
#
# Main-thread utime+stime. Same field math as ops/diagnostics/mt5-freeze-watch.sh.
# Prints "utime stime" (jiffies).
_mt5_main_times() {
  awk '{ r=$0; sub(/^[^)]*\) /, "", r); split(r, f, " "); print f[12]+0, f[13]+0 }' \
    "/proc/$1/task/$1/stat" 2>/dev/null
}

# True if any listed pid's UI thread matches a freeze mode that cannot honor WM_CLOSE:
#   spin      SIGSEGV livelock in win32u — ~100% of one core, *system*-time dominant
#             (kernel handling the fault storm). A merely busy healthy UI is user-time
#             dominant; matching on CPU alone false-positived against live terminals.
#   deadlock  0 jiffies, wchan futex_do_wait
# Observed 2026-08-13: Exness spin ate the full 40s graceful wait, then SIGKILL anyway —
# chart state was already unsavable the moment the UI thread died.
_mt5_ui_frozen() {
  local pid before after bu bs au as udelta sdelta total pct wchan
  local hz sample=1
  hz="$(getconf CLK_TCK 2>/dev/null || echo 100)"
  for pid in "$@"; do
    [[ -d "/proc/$pid/task/$pid" ]] || continue
    wchan="$(cat "/proc/$pid/task/$pid/wchan" 2>/dev/null || echo '?')"
    before="$(_mt5_main_times "$pid")"
    [[ -z "$before" ]] && continue
    sleep "$sample"
    after="$(_mt5_main_times "$pid")"
    [[ -z "$after" ]] && continue
    read -r bu bs <<<"$before"
    read -r au as <<<"$after"
    udelta=$(( au - bu ))
    sdelta=$(( as - bs ))
    total=$(( udelta + sdelta ))
    pct=$(( total * 100 / (sample * hz) ))
    # Deadlock: no progress, parked on a raw pthread mutex (win32u AB-BA).
    if (( total == 0 )) && [[ "$wchan" == futex_do_wait ]]; then
      return 0
    fi
    # Spin: pinned AND system-time majority (SEGV_MAPERR storm). Busy healthy UI is
    # user-time dominant. Require sys > user (not a 2× skew): FP 2026-08-14 sat at
    # ~100% with sd=66 ud=35 and missed the old 2×(ud+1) gate while fully frozen.
    if (( pct >= 80 && sdelta > udelta )); then
      return 0
    fi
  done
  return 1
}

# Usage: stop_terminal_gracefully [timeout_seconds] [wineprefix]
# Pass a wineprefix to stop only that broker's terminal and leave the others running.
# Env: MT5_STOP_SPIN_TIMEOUT (default 8) — used when the UI thread is already frozen.
stop_terminal_gracefully() {
  local timeout="${1:-40}" want="${2:-}" pids wins w waited closed=0
  local spin_timeout="${MT5_STOP_SPIN_TIMEOUT:-8}"
  export DISPLAY="${DISPLAY:-:0}"

  mapfile -t pids < <(mt5_terminal_pids "$want")
  if [[ ${#pids[@]} -eq 0 ]]; then
    info "No MetaTrader process running${want:+ for $want}."
    return 0
  fi
  info "Stopping ${#pids[@]} MetaTrader process(es)${want:+ in $want}"

  # Ask the compositor to close the window. Measured 2026-08-11 on Hyprland 0.56 +
  # XWayland, in order of what actually reaches MT5:
  #   hyprctl dispatch closewindow  -> MT5 exits in ~3s and writes every *.chr   WORKS
  #   xdotool windowquit            -> sends WM_DELETE_WINDOW; MT5 ignores it    NO-OP
  #   xdotool windowclose           -> destroys the X window, no WM_CLOSE at all LOSES DATA
  # The window advertises WM_DELETE_WINDOW in WM_PROTOCOLS, so the xdotool path looks
  # correct and silently is not — do not "simplify" back to it.
  # Select windows by PID, not by class alone: every broker's shell has class
  # terminal64.exe, so a class-only match closes all of them regardless of the filter.
  if command -v hyprctl >/dev/null 2>&1; then
    # The env assignment must sit on python3, not on hyprctl: a prefix assignment
    # applies only to the command it precedes, so putting it before hyprctl leaves
    # python with an empty set, selects no windows, and drops through to the
    # "nothing to close" branch that SIGKILLs without saving charts.
    mapfile -t wins < <(hyprctl clients -j 2>/dev/null | MT5_PIDS="${pids[*]}" python3 -c "
import json, os, sys
wanted = {int(p) for p in os.environ.get('MT5_PIDS', '').split()}
try:
    for c in json.load(sys.stdin):
        if c.get('class') == 'terminal64.exe' and c.get('pid') in wanted:
            print(c['address'])
except Exception:
    pass
" || true)
    for w in "${wins[@]}"; do
      [[ -z "$w" ]] && continue
      hyprctl dispatch closewindow "address:$w" >/dev/null 2>&1 && closed=1
    done
  fi

  if [[ "$closed" -eq 0 ]] && [[ -z "$want" ]] && command -v xdotool >/dev/null 2>&1; then
    # Fallback only when unfiltered: xdotool matches by class and cannot honour the
    # prefix filter, so using it here would close other brokers' terminals.
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
    # If the UI is already in a win32u freeze, WM_CLOSE will never be handled — don't
    # burn the full graceful budget (Exness spin, 2026-08-13: 40s wait then SIGKILL).
    if (( timeout > spin_timeout )) && _mt5_ui_frozen "${pids[@]}"; then
      warn "UI thread frozen (spin/deadlock) — charts unsavable; shortening wait ${timeout}s → ${spin_timeout}s"
      timeout="$spin_timeout"
    fi
    info "Asked MetaTrader to close (WM_CLOSE); waiting up to ${timeout}s for it to save charts..."
  fi

  for ((waited = 0; waited < timeout; waited++)); do
    mapfile -t pids < <(mt5_terminal_pids "$want")
    if [[ ${#pids[@]} -eq 0 ]]; then
      info "MetaTrader exited cleanly (charts saved)."
      return 0
    fi
    sleep 1
  done

  warn "MetaTrader still running after ${timeout}s — escalating (chart edits may be lost)"
  mapfile -t pids < <(mt5_terminal_pids "$want")
  for w in "${pids[@]}"; do kill -TERM "$w" 2>/dev/null || true; done
  sleep 3
  mapfile -t pids < <(mt5_terminal_pids "$want")
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
