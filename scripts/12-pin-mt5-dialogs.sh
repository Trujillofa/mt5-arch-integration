#!/usr/bin/env bash
# Pin MT5 Order / Login dialogs — XWayland-safe poller.
#
# Why not Hyprland socket2 openwindow?
#   Wine/XWayland Order dialogs emit no openwindow event (measured 2026-08-14:
#   socket2 only saw activewindow while Order: mapped). Polling clients works.
#
# Why pin at all?
#   Wine restores a stale position then animates toward another saved coordinate
#   for 1–2s (14+ movewindow updates; sometimes crosses monitors). Hyprland
#   `center` fights that and makes the glitch worse; `no_anim` does not stop
#   Wine's SetWindowPos stream. We force an exact centered pixel position on
#   the dialog's monitor for ~2s so the tween loses.
#
# Autostart (Hyprland):
#   exec-once = ~/Projects/trading/mt5-arch-integration/scripts/12-pin-mt5-dialogs.sh
set -uo pipefail

STATE_DIR="${XDG_RUNTIME_DIR:-/tmp}/mt5-dialog-pin"
mkdir -p "$STATE_DIR"
POLL_MS="${MT5_DIALOG_PIN_MS:-200}"
PIN_ROUNDS="${MT5_DIALOG_PIN_ROUNDS:-40}"   # 40 * 50ms ≈ 2s

pin_one() {
  local addr="$1"
  local marker="$STATE_DIR/${addr//\//_}"
  [[ -e "$marker" ]] && return 0
  : >"$marker"
  (
    local i mon_id w h mx my mw mh cx cy
    for i in $(seq 1 "$PIN_ROUNDS"); do
      read -r mon_id w h < <(ADDR="$addr" hyprctl clients -j 2>/dev/null | python3 -c '
import json, os, sys
addr = os.environ["ADDR"]
try:
    clients = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for c in clients:
    if c.get("address") == addr:
        title = c.get("title") or ""
        if not (title.startswith("Order:") or title == "Login"):
            sys.exit(0)
        print(c.get("monitor", 0), c["size"][0], c["size"][1])
        break
' 2>/dev/null) || true
      if [[ -z "${mon_id:-}" || -z "${w:-}" ]]; then
        rm -f "$marker"
        exit 0
      fi
      read -r mx my mw mh < <(hyprctl monitors -j 2>/dev/null | MON="$mon_id" python3 -c '
import json, os, sys
want = int(os.environ["MON"])
for m in json.load(sys.stdin):
    if m["id"] == want:
        print(m["x"], m["y"], m["width"], m["height"])
        break
' 2>/dev/null) || true
      [[ -n "${mx:-}" ]] || { sleep 0.05; continue; }
      cx=$(( mx + (mw - w) / 2 ))
      cy=$(( my + (mh - h) / 2 ))
      (( cy < my + 40 )) && cy=$(( my + 40 ))
      hyprctl dispatch movewindowpixel "exact $cx $cy,address:$addr" >/dev/null 2>&1 || true
      sleep 0.05
    done
    rm -f "$marker"
  ) &
}

# Drop markers for addresses that no longer exist
cleanup_markers() {
  local f addr
  for f in "$STATE_DIR"/*; do
    [[ -e "$f" ]] || continue
    addr="$(basename "$f")"
    addr="${addr//_//}"  # not needed; we store address with 0x
    hyprctl clients -j 2>/dev/null | ADDR="$addr" python3 -c '
import json, os, sys
addr = os.environ["ADDR"]
try:
    clients = json.load(sys.stdin)
except Exception:
    sys.exit(0)
sys.exit(0 if any(c.get("address")==addr for c in clients) else 1)
' 2>/dev/null || rm -f "$f"
  done
}

echo "12-pin-mt5-dialogs: polling every ${POLL_MS}ms" >&2
while true; do
  hyprctl clients -j 2>/dev/null | python3 -c '
import json, sys
try:
    clients = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for c in clients:
    if c.get("class") != "terminal64.exe":
        continue
    title = c.get("title") or ""
    if title.startswith("Order:") or title == "Login":
        print(c["address"])
' 2>/dev/null | while read -r addr; do
    [[ -n "$addr" ]] && pin_one "$addr"
  done
  cleanup_markers 2>/dev/null || true
  sleep "$(awk -v ms="$POLL_MS" 'BEGIN{printf "%.3f", ms/1000}')"
done
