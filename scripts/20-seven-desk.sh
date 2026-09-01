#!/usr/bin/env bash
# Start the Seven Desk Next.js preview (paper copy terminal + read-only WSF fetch).
set -euo pipefail
# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

load_dotenv
if [[ -f "$REPO_ROOT/config/brokers/wsf.env" ]]; then
  # Profile has login/server only (password stays in gitignored .env).
  # Source so WSF prefix/login win over a leftover vantage/FP shell env.
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/config/brokers/wsf.env"
  set +a
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

info "Seven Desk on http://127.0.0.1:3847 (paper copy default; WSF live order is opt-in)"
info "Paper desk does not need ~/.mt5-wsf. WSF live fetch/order fail closed without ~/.mt5-wsf + confirm WSF-149736."
exec npm run dev
