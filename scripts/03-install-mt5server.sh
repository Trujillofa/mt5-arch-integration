#!/usr/bin/env bash
# Download mt5server.exe (mt5linux RPyC bridge) into the Wine prefix.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env
require_cmd curl

# Pin a known release asset pattern; override with MT5SERVER_URL if needed.
# See: https://github.com/lucas-campagna/mt5linux/releases
MT5SERVER_URL="${MT5SERVER_URL:-https://github.com/lucas-campagna/mt5linux/releases/latest/download/mt5server.exe}"

DEST_DIR="$(mt5server_dir)"
DEST="$(mt5server_path)"

mkdir -p "$DEST_DIR"

if [[ -f "$DEST" && "${1:-}" != "--force" ]]; then
  info "mt5server.exe already present: $DEST"
  info "Use --force to re-download."
else
  info "Downloading mt5server.exe from: $MT5SERVER_URL"
  tmp="$(mktemp)"
  curl -fsSL -L -o "$tmp" "$MT5SERVER_URL" || die "download failed"
  # Basic sanity: file should be non-trivial size
  size="$(stat -c%s "$tmp" 2>/dev/null || stat -f%z "$tmp")"
  if [[ "${size:-0}" -lt 100000 ]]; then
    rm -f "$tmp"
    die "downloaded file too small ($size bytes) — check MT5SERVER_URL"
  fi
  mv "$tmp" "$DEST"
  chmod +x "$DEST" || true
  info "Installed: $DEST ($size bytes)"
fi

if term="$(find_terminal64 2>/dev/null)"; then
  write_local_paths "$term" "$DEST"
else
  write_local_paths "" "$DEST"
  warn "terminal64.exe not found yet — install MT5 first (./scripts/02-install-mt5.sh)"
fi

info "Next: start terminal, then ./scripts/05-start-mt5server.sh"
