#!/usr/bin/env bash
# Temporarily stop Docker containers + Tailscale, force MT5 login, then restore.
# Usage: ./scripts/14-isolate-net-and-login.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env

STATE_DIR="${XDG_RUNTIME_DIR:-/tmp}/mt5-net-isolate-$$"
mkdir -p "$STATE_DIR"

cleanup() {
  info "Restoring Tailscale + Docker containers..."
  tailscale up >/dev/null 2>&1 || true
  if [[ -f "$STATE_DIR/docker.ids" ]]; then
    # shellcheck disable=SC2046
    docker start $(cat "$STATE_DIR/docker.ids") >/dev/null 2>&1 || true
  fi
  rm -rf "$STATE_DIR"
}
trap cleanup EXIT

info "Recording docker container ids"
docker ps -q >"$STATE_DIR/docker.ids" || true
if [[ -s "$STATE_DIR/docker.ids" ]]; then
  info "Stopping containers: $(tr '\n' ' ' <"$STATE_DIR/docker.ids")"
  # shellcheck disable=SC2046
  docker stop $(cat "$STATE_DIR/docker.ids") >/dev/null
fi
info "tailscale down"
tailscale down || true
sleep 1
info "Force login + EA"
"$SCRIPT_DIR/13-force-login-bridge.sh"
info "Done (trap will restore docker/tailscale)"
