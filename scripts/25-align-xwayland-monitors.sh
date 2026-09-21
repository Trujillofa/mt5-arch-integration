#!/usr/bin/env bash
# Align XWayland's output layout with Hyprland's monitor layout.
#
# Why this exists: every MT5 terminal is an XWayland client, so Wine works
# entirely in X11 coordinates. XWayland assigns each output an X11 origin in
# the order it *attaches* the outputs, not from the Wayland positions. When
# the attach order disagrees with the configured left-to-right order, the two
# coordinate spaces come out mirrored: a book tiled at Wayland x=12 reports
# X11 X=1932 and vice versa. Anything that reads geometry in one space and
# acts in the other then lands 1920px away -- on the other screen, on another
# broker's terminal. That is the "terminals move mirrored / scrolling FTMO
# moves Vantage" failure.
#
# Hyprland exposes no option for the XWayland layout, and re-applying a
# monitor rule does not relayout it. Destroying and re-creating a monitor
# does: XWayland re-attaches the surviving outputs first, so re-creating the
# monitors in ascending Wayland-x order leaves the X11 origins in that same
# order. That is all this script does, and only when the spaces disagree.
#
# Idempotent and safe to run on a live desktop: an aligned layout is a no-op,
# and windows keep their workspaces across the re-create (Hyprland restores
# them from the persistent workspace rules).
#
#   ./scripts/25-align-xwayland-monitors.sh           # fix if misaligned
#   ./scripts/25-align-xwayland-monitors.sh --check   # report only, exit 1 if off
#
# Runs from hypr/autostart.lua so a reboot does not reintroduce the mirror:
#   o.exec_on_start(".../scripts/25-align-xwayland-monitors.sh")

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

CHECK_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=1 ;;
    -h|--help) sed -n '2,28p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) die "unknown argument: $arg" ;;
  esac
done

require_cmd hyprctl
require_cmd xrandr
require_cmd python3

# Hyprland must be reachable; on a non-Hyprland session this is not a failure.
if ! hyprctl monitors -j >/dev/null 2>&1; then
  warn "hyprctl not responding (not a Hyprland session?) -- nothing to align"
  exit 0
fi

# XWayland may not be up yet at autostart time. Without it there is no X11
# layout to compare against, so wait briefly rather than reporting a bogus
# mismatch.
xwayland_display() {
  local d
  for d in "${DISPLAY:-}" :0 :1 :2; do
    [[ -z "$d" ]] && continue
    if DISPLAY="$d" xrandr >/dev/null 2>&1; then
      echo "$d"
      return 0
    fi
  done
  return 1
}

XDISPLAY=""
for _ in $(seq 1 60); do
  if XDISPLAY="$(xwayland_display)"; then break; fi
  python3 -c 'import time; time.sleep(0.5)'
done
[[ -n "$XDISPLAY" ]] || { warn "no reachable X display -- XWayland not running; nothing to align"; exit 0; }
export DISPLAY="$XDISPLAY"

# Compare the two spaces. Prints one "name wayland_x x11_x" line per monitor
# that Hyprland has enabled, then "ALIGNED" or "MISALIGNED".
layout_report() {
  python3 - <<'PY'
import json, re, subprocess, sys

mons = json.loads(subprocess.run(["hyprctl", "monitors", "-j"],
                                 capture_output=True, text=True, check=True).stdout)
wayland = {m["name"]: int(m["x"]) for m in mons}

x11 = {}
xr = subprocess.run(["xrandr"], capture_output=True, text=True)
for line in xr.stdout.splitlines():
    m = re.match(r"^(\S+) connected(?: primary)? (\d+)x(\d+)\+(-?\d+)\+(-?\d+)", line)
    if m:
        x11[m.group(1)] = int(m.group(4))

# With one output XWayland always normalizes its origin to 0, so a nonzero
# Wayland x is expected there and is not a mirror -- and there is nothing to
# reorder anyway. Only compare the spaces when there are outputs to order.
single = len(wayland) < 2

misaligned = False
for name in sorted(wayland, key=lambda n: wayland[n]):
    wx = wayland[name]
    xx = x11.get(name)
    ok = single or (xx is not None and xx == wx)
    print(f"{name} {wx} {'?' if xx is None else xx} {'ok' if ok else 'MIRRORED'}")
    if not ok:
        misaligned = True

print("MISALIGNED" if misaligned else "ALIGNED")
PY
}

print_report() {
  local label="$1" report="$2"
  info "$label"
  while read -r name wx xx status; do
    [[ "$name" == ALIGNED || "$name" == MISALIGNED ]] && continue
    printf '    %-12s wayland x=%-6s x11 x=%-6s %s\n' "$name" "$wx" "$xx" "$status"
  done <<<"$report"
}

REPORT="$(layout_report)"
print_report "current layout" "$REPORT"

if [[ "$REPORT" == *ALIGNED* && "$REPORT" != *MISALIGNED* ]]; then
  info "X11 and Wayland layouts agree -- nothing to do"
  exit 0
fi

if (( CHECK_ONLY )); then
  warn "X11 and Wayland monitor layouts are MIRRORED (see above)"
  exit 1
fi

# Force XWayland to re-attach the outputs in left-to-right order: disable
# every monitor except the leftmost, then `hyprctl reload`.
#
# The leftmost output survives and keeps X11 origin 0; reload re-applies
# monitors.lua, so the disabled outputs are re-created *after* it and take the
# origins to its right, which is the order we want.
#
# Reload is deliberately the only re-enable path. `hl.monitor` re-enable is
# unreliable -- it reports "ok" and leaves the output dark (observed failing 5
# times in a row on both outputs). Reload re-applies the config, where every
# monitor is enabled, so the worst case here is a restored-but-still-mirrored
# layout, never a dark screen.
#
# Exact for two monitors. With three or more, the order reload re-creates the
# disabled outputs in is not guaranteed, so re-check and retry.
mapfile -t OFFENDERS < <(hyprctl monitors -j | python3 -c '
import json, sys
mons = json.load(sys.stdin)
for m in sorted(mons, key=lambda m: int(m["x"]))[1:]:
    print(m["name"])
')

(( ${#OFFENDERS[@]} )) || die "layout reads misaligned but there is only one monitor to order"

for pass in 1 2 3; do
  for name in "${OFFENDERS[@]}"; do
    info "pass $pass: detaching $name so it re-attaches to the right"
    hyprctl eval "hl.monitor({ output = \"$name\", disabled = true })" >/dev/null
  done
  python3 -c 'import time; time.sleep(1.5)'

  info "pass $pass: hyprctl reload (re-creates the detached outputs, in order)"
  hyprctl reload >/dev/null
  python3 -c 'import time; time.sleep(3)'

  # Never leave a monitor off. Reload re-applies monitors.lua, so this should
  # always hold; shout if it somehow does not.
  MISSING="$(hyprctl monitors -j | python3 -c '
import json, sys
have = {m["name"] for m in json.load(sys.stdin)}
want = set(sys.argv[1:])
print(" ".join(sorted(want - have)))
' "${OFFENDERS[@]}")"
  if [[ -n "$MISSING" ]]; then
    warn "monitor(s) still detached after reload: $MISSING -- retrying reload"
    hyprctl reload >/dev/null
    python3 -c 'import time; time.sleep(3)'
  fi

  REPORT="$(layout_report)"
  if [[ "$REPORT" != *MISALIGNED* ]]; then
    print_report "layout after pass $pass" "$REPORT"
    info "X11 and Wayland layouts now agree"
    exit 0
  fi
  warn "pass $pass did not align the layouts"
done

print_report "final layout" "$REPORT"
die "could not align X11 with Wayland after 3 passes -- monitors are restored, but the layout is still mirrored"
