#!/usr/bin/env bash
# Start one or more broker terminals detached on a silent Hyprland workspace.
#
# Usage:
#   ./scripts/21-start-broker-background.sh fundednext wsf ftmo
#
# Does not load repo .env (that pins WSF). Does not print passwords.
# Refuses vantage / fpmarkets / exness so those live books stay put.
# For wsf / ftmo / fundednext / alphacapital, writes Mt5ArchBridge onto the
# branded Default chart (portable loads MQL5/Profiles/Charts/Default). A stale
# heartbeat restarts only that prefix's branded terminal64 — never a generic
# Program Files/MetaTrader 5 tree.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

require_cmd wine
require_cmd setsid

if [[ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
  die "No graphical display. Start from a desktop session."
fi

BG_WS="${MT5_BG_WORKSPACE:-11}"
if [[ $# -lt 1 ]]; then
  die "Usage: $0 <broker> [broker...]"
fi

for broker in "$@"; do
  case "$broker" in
    vantage|fpmarkets|exness)
      die "refusing to start $broker from this helper"
      ;;
    -h|--help)
      echo "Usage: $0 <broker> [broker...]"
      echo "Parks windows on workspace ${BG_WS} (override: MT5_BG_WORKSPACE)."
      exit 0
      ;;
    -*)
      die "unknown option: $broker"
      ;;
  esac
done

if [[ -n "${DISPLAY:-}" ]]; then
  unset WAYLAND_DISPLAY || true
fi
export DISPLAY="${DISPLAY:-:0}"
export WINEDEBUG="${WINEDEBUG:--all}"
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-d3d11=b;d3d12=b;dxgi=b}"

for broker in "$@"; do
  profile="$REPO_ROOT/config/brokers/${broker}.env"
  [[ -f "$profile" ]] || die "missing profile: $profile"

  # Isolate each broker from leftover MT5_* of the previous loop.
  unset WINEPREFIX MT5_LOGIN MT5_SERVER MT5_TERMINAL_PATH MT5_PASSWORD || true
  set -a
  # shellcheck disable=SC1090
  source "$profile"
  set +a
  export_wine_env

  case "$(realpath "${WINEPREFIX}")" in
    *mt5-vantage*|*mt5-fpmarkets*|*mt5-exness*)
      die "refusing forbidden prefix $WINEPREFIX"
      ;;
  esac
  quotes_first=0

  running=0
  if python3 -c '
import os, sys
sys.path.insert(0, "'"$REPO_ROOT"'/src")
from mt5_arch.hypr_geometry import list_terminal64_pids
raise SystemExit(0 if list_terminal64_pids(wineprefix=os.environ["WINEPREFIX"]) else 1)
' >/dev/null 2>&1; then
    running=1
  fi

  term="$(find_terminal64)" || die "terminal64.exe not found under $WINEPREFIX"
  case "$broker" in
    wsf|ftmo|fundednext|alphacapital)
      if [[ "$term" == *"/Program Files/MetaTrader 5/terminal64.exe" ]]; then
        die "$broker generic MetaQuotes tree is not the live book — start the branded terminal64.exe"
      fi
      term_dir="$(cd "$(dirname "$term")" && pwd)"
      quotes_first=0
      if [[ "$broker" == "alphacapital" ]] && \
         ! python3 "$SCRIPT_DIR/inject_branded_bridge_chart.py" \
           --broker "$broker" --term-dir "$term_dir" --quotes-ready; then
        quotes_first=1
        python3 "$SCRIPT_DIR/inject_branded_bridge_chart.py" \
          --broker "$broker" --term-dir "$term_dir" --no-expert --allow-missing-ex5 \
          || die "failed to write quotes-first Default chart for $broker"
        info "$broker has no EURUSD history yet — starting without Mt5ArchBridge so the symbol can sync"
      else
        python3 "$SCRIPT_DIR/inject_branded_bridge_chart.py" \
          --broker "$broker" --term-dir "$term_dir" \
          || die "failed to inject Mt5ArchBridge on $broker Default chart"
      fi
      if [[ "$running" -eq 1 ]]; then
        if [[ "$quotes_first" -eq 0 ]] && python3 "$SCRIPT_DIR/inject_branded_bridge_chart.py" \
          --broker "$broker" --term-dir "$term_dir" --fresh; then
          info "$broker already running with a fresh bridge — parking on workspace $BG_WS"
          park_prefix_terminals_background "$WINEPREFIX" "$BG_WS"
          continue
        fi
        info "$broker branded terminal is up but Mt5ArchBridge heartbeat is stale — restarting that book only"
        python3 "$SCRIPT_DIR/inject_branded_bridge_chart.py" \
          --broker "$broker" --term-dir "$term_dir" --stop-branded \
          || die "failed to stop stale $broker branded terminal"
      fi
      ;;
    *)
      if [[ "$running" -eq 1 ]]; then
        info "$broker already running — parking on workspace $BG_WS"
        park_prefix_terminals_background "$WINEPREFIX" "$BG_WS"
        continue
      fi
      ;;
  esac
  info "Starting $broker in background: $term"
  extra=()
  if [[ -f "$(dirname "$term")/auto_login.ini" ]]; then
    extra+=(/config:auto_login.ini)
  fi
  start_terminal64_detached "$term" /portable "${extra[@]}"
  if [[ "$broker" == "alphacapital" && "${quotes_first:-0}" -eq 1 ]]; then
    term_dir="$(cd "$(dirname "$term")" && pwd)"
    info "waiting up to 90s for ACG EURUSD history before attaching Mt5ArchBridge"
    quotes_ok=0
    for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18; do
      sleep 5
      if python3 "$SCRIPT_DIR/inject_branded_bridge_chart.py" \
        --broker alphacapital --term-dir "$term_dir" --quotes-ready; then
        quotes_ok=1
        break
      fi
    done
    if [[ "$quotes_ok" -eq 1 ]]; then
      info "ACG EURUSD history is present — attaching Mt5ArchBridge and restarting that book only"
      python3 "$SCRIPT_DIR/inject_branded_bridge_chart.py" \
        --broker alphacapital --term-dir "$term_dir" \
        || die "failed to inject Mt5ArchBridge after quotes"
      python3 "$SCRIPT_DIR/inject_branded_bridge_chart.py" \
        --broker alphacapital --term-dir "$term_dir" --stop-branded \
        || die "failed to stop ACG for post-quotes attach"
      extra=()
      if [[ -f "$(dirname "$term")/auto_login.ini" ]]; then
        extra+=(/config:auto_login.ini)
      fi
      start_terminal64_detached "$term" /portable "${extra[@]}"
    else
      warn "ACG EURUSD still has no history — left running without the EA. Wait for a live bid/ask, then re-run $0 alphacapital"
    fi
  fi
done

if command -v hyprctl >/dev/null 2>&1; then
  for _ in 1 2 3 4 5 6 7 8; do
    sleep 2
    for broker in "$@"; do
      case "$broker" in
        -*) continue ;;
      esac
      unset WINEPREFIX || true
      set -a
      # shellcheck disable=SC1090
      source "$REPO_ROOT/config/brokers/${broker}.env"
      set +a
      park_prefix_terminals_background "$WINEPREFIX" "$BG_WS"
    done
  done
fi

info "Background terminals requested on workspace $BG_WS (Super+$BG_WS to view)"
