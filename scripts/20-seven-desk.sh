#!/usr/bin/env bash
# Keep Seven Desk on :3847 via systemd --user (host next, not Podman).
#
# Host unit because the desk orchestrates Wine / scripts/21 / file-bridge.
#
# Usage:
#   ./scripts/20-seven-desk.sh              # install + enable --now user unit
#   ./scripts/20-seven-desk.sh --foreground # exec npm run dev (for the unit)
#   ./scripts/20-seven-desk.sh --stop
#   ./scripts/20-seven-desk.sh --restart
#   ./scripts/20-seven-desk.sh --status
#
# After reboot: user linger + WantedBy=default.target starts seven-desk.service.
set -euo pipefail
# shellcheck source=lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

PORT=3847
UNIT="seven-desk.service"
UNIT_SRC="$REPO_ROOT/ops/systemd/seven-desk.service"
UNIT_DST="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/seven-desk.service"
APP_DIR="$REPO_ROOT/apps/seven-desk"
URL="http://127.0.0.1:${PORT}/"

http_code() {
  curl -sS -o /dev/null -w '%{http_code}' --max-time 3 "$URL" 2>/dev/null || echo 000
}

http_200() {
  [[ "$(http_code)" == 200 ]]
}

port_listening() {
  ss -ltn 2>/dev/null | grep -Eq ":${PORT}[[:space:]]"
}

unit_active() {
  systemctl --user is-active --quiet "$UNIT"
}

install_unit() {
  [[ -f "$UNIT_SRC" ]] || die "missing $UNIT_SRC"
  mkdir -p "$(dirname "$UNIT_DST")"
  ln -sfn "$UNIT_SRC" "$UNIT_DST"
}

prepare_app() {
  load_dotenv
  if [[ -f "$REPO_ROOT/config/brokers/wsf.env" ]]; then
    # Profile has login/server only (password stays in gitignored .env).
    # Source so WSF prefix/login win over a leftover vantage/FP shell env.
    set -a
    # shellcheck disable=SC1091
    source "$REPO_ROOT/config/brokers/wsf.env"
    set +a
  fi
  [[ -f "$APP_DIR/package.json" ]] || die "Seven Desk is missing at apps/seven-desk"
  require_cmd npm
  cd "$APP_DIR"
  if [[ ! -d node_modules ]]; then
    info "Installing Seven Desk npm dependencies"
    npm install
  fi
}

run_foreground() {
  prepare_app
  info "Seven Desk on $URL (paper copy default; WSF live order is opt-in)"
  exec npm run dev
}

print_status() {
  local code pid
  code="$(http_code)"
  info "Seven Desk $URL  HTTP ${code}"
  if unit_active; then
    pid="$(systemctl --user show -p MainPID --value "$UNIT" 2>/dev/null || echo '?')"
    info "unit $UNIT is active (pid ${pid})"
  else
    info "unit $UNIT is not active"
  fi
}

wait_http_200() {
  local i
  for i in $(seq 1 60); do
    if http_200; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start_desk() {
  require_cmd systemctl || die "systemctl is required"
  require_cmd curl || die "curl is required"
  [[ -f "$APP_DIR/package.json" ]] || die "Seven Desk is missing at apps/seven-desk"

  if http_200; then
    info "Seven Desk already healthy on $URL — leaving it"
    print_status
    return 0
  fi
  if port_listening; then
    die "port ${PORT} is taken but not HTTP 200; stop that process, then rerun $0"
  fi

  install_unit
  systemctl --user daemon-reload
  systemctl --user enable --now "$UNIT"

  if ! wait_http_200; then
    systemctl --user status "$UNIT" --no-pager -l || true
    die "Seven Desk did not reach HTTP 200 on $URL"
  fi
  info "Seven Desk on $URL (paper copy default; live OrderSend stays fail-closed)"
  print_status
}

stop_desk() {
  require_cmd systemctl || die "systemctl is required"
  systemctl --user disable --now "$UNIT" >/dev/null 2>&1 || true
  info "Seven Desk stopped"
}

cmd="${1:---start}"
case "$cmd" in
  --start | "")
    start_desk
    ;;
  --foreground)
    run_foreground
    ;;
  --stop)
    stop_desk
    ;;
  --restart)
    stop_desk
    start_desk
    ;;
  --status)
    require_cmd curl || die "curl is required"
    print_status
    ;;
  -h | --help)
    sed -n '2,14p' "$0"
    ;;
  *)
    die "Usage: $0 [--start|--foreground|--stop|--restart|--status]"
    ;;
esac
