#!/usr/bin/env bash
# Start the Seven Desk Next.js preview (paper copy terminal + read-only WSF fetch).
set -euo pipefail
# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

load_dotenv
if [[ -f "$REPO_ROOT/config/brokers/wsf.env" ]]; then
  # Profile has login/server only (password stays commented). Environment wins.
  load_dotenv "$REPO_ROOT/config/brokers/wsf.env"
fi

APP_DIR="$REPO_ROOT/apps/seven-desk"
if [[ ! -f "$APP_DIR/package.json" ]]; then
  die "Seven Desk is missing at apps/seven-desk (package.json not found)."
fi

require_cmd npm
cd "$APP_DIR"
if [[ ! -d node_modules ]]; then
  info "Installing Seven Desk npm dependencies"
  npm install
fi

info "Seven Desk on http://127.0.0.1:3847 (paper execution; no live MT5 orders)"
info "Paper desk does not need ~/.mt5-wsf. WSF live fetch is optional and fails closed without a prefix."
exec npm run dev
