#!/usr/bin/env bash
# Force-paste current Wayland text into the MetaTrader (Wine/XWayland) window.
#
# Use when Ctrl+V / right-click Paste still fails after the clipboard bridge.
# Strategy:
#   1. Pull *text* from Wayland (ignore images)
#   2. Mirror into X11 UTF8_STRING (Wine-friendly)
#   3. Focus main terminal64 window
#   4. Send Shift+Insert (most reliable under Wine), fallback Ctrl+V
#   5. If still needed: type characters with xdotool (login fields)
#
# Usage:
#   ./scripts/12-paste-into-mt5.sh           # paste via keys
#   ./scripts/12-paste-into-mt5.sh --type    # type text (best for password/login)
#   ./scripts/12-paste-into-mt5.sh --sync-only
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

MODE="keys" # keys | type | sync-only
for arg in "$@"; do
  case "$arg" in
    --type) MODE="type" ;;
    --sync-only) MODE="sync-only" ;;
    -h|--help)
      sed -n '2,16p' "$0"
      exit 0
      ;;
  esac
done

require_cmd wl-paste
require_cmd xclip
export DISPLAY="${DISPLAY:-:0}"
# Bridge must keep Wayland
if [[ -z "${WAYLAND_DISPLAY:-}" ]]; then
  for sock in wayland-1 wayland-0; do
    if [[ -S "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/$sock" ]]; then
      export WAYLAND_DISPLAY="$sock"
      break
    fi
  done
fi

# Prefer plain text only — images on clipboard break paste into login fields
TEXT="$(wl-paste --type text --no-newline 2>/dev/null || true)"
if [[ -z "$TEXT" ]]; then
  # Fallback: default type if it is not binary
  RAW="$(wl-paste --no-newline 2>/dev/null || true)"
  if [[ -n "$RAW" && "$RAW" != $'\x89PNG'* ]]; then
    TEXT="$RAW"
  fi
fi

if [[ -z "$TEXT" ]]; then
  die "no text on Wayland clipboard (copy text, not a screenshot). wl-paste --type text is empty."
fi

# Mirror to X11 with UTF8_STRING (Wine)
printf '%s' "$TEXT" | python3 "$SCRIPT_DIR/clip_to_x11.py"
# Also plain xclip as belt-and-suspenders
printf '%s' "$TEXT" | xclip -selection clipboard -t UTF8_STRING -i
printf '%s' "$TEXT" | xclip -selection primary -t UTF8_STRING -i

info "clipboard text ready (${#TEXT} chars) → X11 UTF8_STRING"
if [[ "$MODE" == "sync-only" ]]; then
  exit 0
fi

# Focus MT5 main window
ADDR=""
if command -v hyprctl >/dev/null 2>&1; then
  ADDR="$(hyprctl clients -j 2>/dev/null | python3 -c '
import json,sys,re
cs=json.load(sys.stdin)
mains=[]
for c in cs:
    if c.get("class")!="terminal64.exe":
        continue
    t=(c.get("title") or "")
    if t.strip().lower()=="login":
        # Login dialog — preferred paste target when open
        print(c.get("address",""))
        raise SystemExit(0)
    if re.search(r"(?i)(wsfmarkets|netting|metaquotes)", t) or re.match(r"^\d+\s*-\s*", t):
        mains.append(c)
if mains:
    m=max(mains, key=lambda c: (c.get("size") or [0,0])[0]*(c.get("size") or [0,0])[1])
    print(m.get("address",""))
' 2>/dev/null || true)"
  if [[ -n "$ADDR" ]]; then
    hyprctl dispatch focuswindow "address:$ADDR" >/dev/null 2>&1 || true
    sleep 0.15
  else
    warn "no terminal64.exe window found — sending keys to whatever is focused"
  fi
fi

require_cmd xdotool
# Clear stuck modifiers (Hyprland Super, etc.)
xdotool keyup Shift_L Shift_R Control_L Control_R Alt_L Alt_R Super_L Super_R 2>/dev/null || true
sleep 0.05

if [[ "$MODE" == "type" ]]; then
  info "typing ${#TEXT} chars into focused window (delay 8ms)…"
  # --clearmodifiers avoids Super still held from keybind
  xdotool type --clearmodifiers --delay 8 -- "$TEXT"
  info "done (typed)"
  exit 0
fi

# Prefer Shift+Insert (Omarchy Super+V maps to this; Wine usually honors it)
info "sending Shift+Insert (paste)…"
xdotool key --clearmodifiers shift+Insert
sleep 0.2
# Also try Ctrl+V once (some MT5 fields only honor this)
xdotool key --clearmodifiers ctrl+v
info "done (keys). If still empty, run: $0 --type"
