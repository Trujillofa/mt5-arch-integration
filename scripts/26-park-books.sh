#!/usr/bin/env bash
# Keep hidden MT5 books out of X11's pointer-reachable coordinate space.
#
# Diagnostic for one hypothesised crosstalk path: Hyprland tiles every window on
# a monitor to the same rect and keeps hidden-workspace XWayland windows mapped
# there, so two books on one monitor share an X11 rectangle. If a hidden book
# were ever stacked ABOVE the visible one, X11 would route the pointer to it.
#
# Tested 2026-09-24 with the layout aligned by script 25: it does not happen.
# The real X server stacking (XQueryTree) always put the visible book on top
# after a workspace switch, a ticking hidden book never raised itself (0/448
# samples), and hidden books received no pointer events. See
# docs/TROUBLESHOOTING.md -- a "chart moves on its own" report on an aligned
# layout turned out to be a failing scroll-wheel encoder.
#
# --once / --unpark-all remain for the case where a hidden book IS observed on
# top: it is floated and moved below every monitor (y=3000), where the pointer
# cannot reach it, then restored to tiled when its workspace returns. Do not
# run --watch against live books by default: parking float/tile-toggles Wine
# windows, and that churn is a known way to wedge a terminal.
#
#   ./scripts/26-park-books.sh --status      # which books are exposed
#   ./scripts/26-park-books.sh --dry-run     # show the plan, change nothing
#   ./scripts/26-park-books.sh               # apply once
#   ./scripts/26-park-books.sh --watch       # follow Hyprland workspace events
#   ./scripts/26-park-books.sh --unpark-all  # undo: restore every book to tiled
#

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || die "not inside a Hyprland session"
require_cmd hyprctl

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

MODE="--once"
EXTRA=()
for arg in "$@"; do
  case "$arg" in
    --status|--watch|--unpark-all) MODE="$arg" ;;
    --once) MODE="--once" ;;
    --dry-run|--json) EXTRA+=("$arg") ;;
    -h|--help) sed -n '2,36p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) die "unknown argument: $arg" ;;
  esac
done

# Two watchers would both apply the same plans and double the float/tile churn
# that wedges Wine, so --watch is single-instance.
if [ "$MODE" = "--watch" ]; then
  LOCK="${XDG_RUNTIME_DIR:-/tmp}/mt5-arch-park.lock"
  exec 9>"$LOCK"
  flock -n 9 || die "a --watch instance is already running (lock: $LOCK)"
fi

exec uv run mt5-arch-park "$MODE" "${EXTRA[@]+"${EXTRA[@]}"}"
