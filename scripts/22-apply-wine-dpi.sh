#!/usr/bin/env bash
# Write Wine LogPixels (default 120, ~70% of the old 192) to every ~/.mt5* prefix.
#
# Usage:
#   ./scripts/22-apply-wine-dpi.sh
#   ./scripts/22-apply-wine-dpi.sh --restart-running
#
# --restart-running: prefix-scoped wineserver -k + relaunch each live terminal64
# with the same /portable (+ auto_login.ini if it was on the cmdline). Does not
# start prefixes that are down. Does not print passwords. No live orders.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

RESTART=0
for arg in "$@"; do
  case "$arg" in
    --restart-running) RESTART=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *) die "unknown arg: $arg" ;;
  esac
done

require_cmd wine
DPI="${MT5_LOG_PIXELS:-120}"
info "LogPixels=$DPI (MT5_LOG_PIXELS override allowed, 96–192)"

shopt -s nullglob
prefixes=()
for p in "$HOME"/.mt5 "$HOME"/.mt5-*; do
  [[ -d "$p" ]] || continue
  prefixes+=("$(readlink -f -- "$p")")
done
shopt -u nullglob

if [[ ${#prefixes[@]} -eq 0 ]]; then
  die "no ~/.mt5* prefixes"
fi

for prefix in "${prefixes[@]}"; do
  export WINEPREFIX="$prefix"
  export WINEARCH=win64
  apply_wine_logpixels
  info "wrote LogPixels=$DPI in $prefix"
done

if [[ "$RESTART" -ne 1 ]]; then
  info "Registry only. Re-run with --restart-running to apply to live terminals."
  exit 0
fi

if [[ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
  die "No graphical display. --restart-running needs a desktop session."
fi
if ! command -v hyprctl >/dev/null 2>&1; then
  die "hyprctl not found; --restart-running needs Hyprland to list live terminals"
fi
export DISPLAY="${DISPLAY:-:0}"
export WINEDEBUG="${WINEDEBUG:--all}"
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-d3d11=b;d3d12=b;dxgi=b}"
export_wine_webview_env

mapfile -t jobs < <(python3 - <<'PY'
import json, os, subprocess
from pathlib import Path

cs = json.loads(subprocess.check_output(["hyprctl", "-j", "clients"]))
seen = set()
for c in cs:
    if c.get("class") != "terminal64.exe":
        continue
    pid = c.get("pid")
    if not pid:
        continue
    try:
        env = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
        argv = [p.decode() for p in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0") if p]
        cwd = str(Path(f"/proc/{pid}/cwd").resolve())
    except OSError:
        continue
    wp = ""
    for part in env:
        if part.startswith(b"WINEPREFIX="):
            wp = os.path.realpath(part.split(b"=", 1)[1].decode())
            break
    if not wp or wp in seen:
        continue
    seen.add(wp)
    exe = next((a for a in argv if a.endswith("terminal64.exe")), "")
    if exe.startswith("./") or not exe.startswith("/"):
        candidate = str(Path(cwd) / "terminal64.exe")
        if Path(candidate).is_file():
            exe = candidate
    if not Path(exe).is_file():
        continue
    extra = []
    joined = " ".join(argv)
    if "/portable" in argv or "/portable" in joined:
        extra.append("/portable")
    if any("auto_login.ini" in a for a in argv):
        extra.append("/config:auto_login.ini")
    ws = (c.get("workspace") or {}).get("id") or ""
    print(f"{wp}\t{exe}\t{ws}\t{' '.join(extra)}")
PY
)

if [[ ${#jobs[@]} -eq 0 ]]; then
  info "No live terminal64 windows; prefixes already have LogPixels=$DPI"
  exit 0
fi

for line in "${jobs[@]}"; do
  [[ -n "$line" ]] || continue
  prefix="${line%%$'\t'*}"
  rest="${line#*$'\t'}"
  term="${rest%%$'\t'*}"
  rest="${rest#*$'\t'}"
  ws="${rest%%$'\t'*}"
  extra="${rest#*$'\t'}"
  export WINEPREFIX="$prefix"
  export WINEARCH=win64
  info "Restarting $prefix (workspace ${ws:-?}) at LogPixels=$DPI"
  apply_wine_logpixels
  kill_prefix_wineserver
  # shellcheck disable=SC2086
  start_terminal64_detached "$term" $extra
  if [[ -n "$ws" ]] && command -v hyprctl >/dev/null 2>&1; then
    for _ in $(seq 1 20); do
      sleep 1
      if park_prefix_terminals_background "$prefix" "$ws"; then
        :
      fi
      if PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" python3 -c '
import os, sys
from mt5_arch.hypr_geometry import list_terminal64_pids
sys.exit(0 if list_terminal64_pids(wineprefix=os.environ["WINEPREFIX"]) else 1)
' ; then
        break
      fi
    done
  fi
done

info "Restarted ${#jobs[@]} live prefix(es) at LogPixels=$DPI"
