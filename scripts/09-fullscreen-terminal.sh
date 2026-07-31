#!/usr/bin/env bash
# Maximize or fullscreen the main MetaTrader terminal on the active Hyprland monitor.
# Does NOT use Wine virtual desktop. Charts stay as tabs in the main window.
#
# Usage:
#   ./scripts/09-fullscreen-terminal.sh
#   ./scripts/09-fullscreen-terminal.sh --dry-run
#   ./scripts/09-fullscreen-terminal.sh --mode fullscreen
#   ./scripts/09-fullscreen-terminal.sh --monitor HDMI-A-1
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv

MODE="maximize"
DRY_RUN=0
MONITOR=""
JSON=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --json) JSON=1; shift ;;
    --mode) MODE="${2:-}"; shift 2 ;;
    --mode=*) MODE="${1#--mode=}"; shift ;;
    --monitor) MONITOR="${2:-}"; shift 2 ;;
    --monitor=*) MONITOR="${1#--monitor=}"; shift ;;
    maximize|fullscreen) MODE="$1"; shift ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *) die "unknown arg: $1" ;;
  esac
done

if [[ "$MODE" != "maximize" && "$MODE" != "fullscreen" ]]; then
  die "mode must be maximize or fullscreen (got $MODE)"
fi

# Policy: never launch Wine virtual desktop (comments/deletes are fine)
if grep -RInE 'wine[[:space:]]+explorer[[:space:]]+/desktop=|explorer\.exe[[:space:]]+/desktop=' \
  "$SCRIPT_DIR" --include='*.sh' 2>/dev/null \
  | grep -vE 'Never|never|No virtual|reg delete|#' ; then
  die "virtual desktop launch found in scripts — refuse"
fi

cd "$REPO_ROOT"
ARGS=(--mode "$MODE")
[[ -n "$MONITOR" ]] && ARGS+=(--monitor "$MONITOR")
[[ "$DRY_RUN" -eq 1 ]] && ARGS+=(--dry-run)
[[ "$JSON" -eq 1 ]] && ARGS+=(--json)

info "MT5 window $MODE (no Wine virtual desktop)..."
set +e
uv run python -m mt5_arch.window_ops "${ARGS[@]}"
rc=$?
set -e
if [[ "$rc" -eq 3 && "$DRY_RUN" -eq 0 && "${MT5_NO_AUTO_RECOVER:-0}" != "1" ]]; then
  warn "Ghost/unmapped MT5 detected — recovering..."
  "$SCRIPT_DIR/10-recover-terminal.sh" --fullscreen
  exit $?
fi
if [[ "$rc" -eq 3 && "${MT5_NO_AUTO_RECOVER:-0}" == "1" ]]; then
  warn "ghost still present during nested recover — not re-entering recover"
fi
exit "$rc"
