#!/usr/bin/env bash
# Create or refresh the Wine prefix for MetaTrader 5.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env
require_cmd wine
require_cmd winetricks

FORCE=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    -h|--help)
      echo "Usage: $0 [--force]"
      echo "  Create WINEPREFIX=$WINEPREFIX (win64) and install core winetricks deps."
      echo "  --force  remove existing prefix first (destructive)"
      exit 0
      ;;
    *) die "unknown argument: $arg" ;;
  esac
done

if [[ -d "$WINEPREFIX" && "$FORCE" -eq 1 ]]; then
  warn "Removing existing prefix: $WINEPREFIX"
  rm -rf "$WINEPREFIX"
fi

if [[ -d "$WINEPREFIX/drive_c" ]]; then
  info "Reusing existing prefix: $WINEPREFIX"
else
  info "Creating Wine prefix: $WINEPREFIX (WINEARCH=$WINEARCH)"
  mkdir -p "$WINEPREFIX"
  # Initialize prefix non-interactively where possible
  wineboot --init 2>/dev/null || wine wineboot --init || true
fi

info "Installing winetricks components (corefonts vcrun2019)..."
# Quiet install; may still need network and some time
winetricks -q corefonts vcrun2019 || {
  warn "winetricks reported errors — often safe to continue; see docs/TROUBLESHOOTING.md"
}

info "Prefix ready: $WINEPREFIX"
info "Next: ./scripts/02-install-mt5.sh"
