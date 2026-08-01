#!/usr/bin/env bash
# Escalation: stop Docker containers + Tailscale, bring down docker0/br-* (needs sudo),
# force MT5 login on WINEPREFIX, measure Network, then restore interfaces + services.
#
# Usage:
#   WINEPREFIX=~/.mt5-staging ./scripts/15-bridge-down-and-login.sh
#   ./scripts/15-bridge-down-and-login.sh --wait-sec 90
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env

WAIT_SEC=90
for arg in "$@"; do
  case "$arg" in
    --wait-sec=*) WAIT_SEC="${arg#*=}" ;;
    -h|--help)
      echo "Usage: $0 [--wait-sec=N]"
      exit 0
      ;;
  esac
done

require_cmd wine
require_cmd sudo
require_cmd docker

EVID="${REPO_ROOT}/.net-fix-evidence"
mkdir -p "$EVID"
STATE_DIR="${XDG_RUNTIME_DIR:-/tmp}/mt5-bridge-down-$$"
mkdir -p "$STATE_DIR"
REPORT="$EVID/phase4-bridge-down-$(date +%Y%m%dT%H%M%S).log"

BRIDGE_NAMES=()
restore_all() {
  set +e
  info "Restoring bridge interfaces..."
  if [[ -f "$STATE_DIR/bridges.txt" ]]; then
    while IFS= read -r br; do
      [[ -z "$br" ]] && continue
      sudo -n ip link set "$br" up 2>/dev/null || true
    done <"$STATE_DIR/bridges.txt"
  fi
  info "Restoring Tailscale..."
  tailscale up >/dev/null 2>&1 || true
  if [[ -f "$STATE_DIR/docker.ids" ]]; then
    info "Restoring Docker containers..."
    # shellcheck disable=SC2046
    docker start $(cat "$STATE_DIR/docker.ids") >/dev/null 2>&1 || true
  fi
  rm -rf "$STATE_DIR"
  set -e
}
trap restore_all EXIT

{
  echo "=== phase4 bridge-down $(date -Is) ==="
  echo "WINEPREFIX=$WINEPREFIX"
  wine --version || true
} | tee "$REPORT"

info "Recording docker container ids"
docker ps -q >"$STATE_DIR/docker.ids" || true
if [[ -s "$STATE_DIR/docker.ids" ]]; then
  info "Stopping containers"
  # shellcheck disable=SC2046
  docker stop $(cat "$STATE_DIR/docker.ids") >/dev/null
fi

info "tailscale down"
tailscale down || true

info "Listing docker bridges to down"
: >"$STATE_DIR/bridges.txt"
while IFS= read -r line; do
  name="${line%% *}"
  case "$name" in
    docker0|br-*)
      echo "$name" >>"$STATE_DIR/bridges.txt"
      BRIDGE_NAMES+=("$name")
      ;;
  esac
done < <(ip -br link show 2>/dev/null || true)

if [[ ! -s "$STATE_DIR/bridges.txt" ]]; then
  warn "No docker0/br-* interfaces found"
else
  info "Bringing down: $(tr '\n' ' ' <"$STATE_DIR/bridges.txt")"
  while IFS= read -r br; do
    sudo -n ip link set "$br" down
  done <"$STATE_DIR/bridges.txt"
fi

info "Force login + EA on WINEPREFIX=$WINEPREFIX"
# force-login exits 2 when Network auth fails — still continue measurement/restore
set +e
"$SCRIPT_DIR/13-force-login-bridge.sh" 2>&1 | tee -a "$REPORT"
FORCE_RC=${PIPESTATUS[0]}
set -e
echo "force_login_exit=$FORCE_RC" | tee -a "$REPORT"

MT5_DIR="$WINEPREFIX/drive_c/Program Files/MetaTrader 5"
LOG="$MT5_DIR/logs/$(date +%Y%m%d).log"
ACCT="$MT5_DIR/MQL5/Files/mt5_arch/account.json"

info "Extra wait ${WAIT_SEC}s for Network (post force-login)"
END=$((SECONDS + WAIT_SEC))
while (( SECONDS < END )); do
  sleep 5
  nets=0
  if [[ -f "$LOG" ]]; then
    nets="$(iconv -f UTF-16 -t UTF-8 "$LOG" 2>/dev/null | rg -c 'Network' || echo 0)"
  fi
  # shellcheck disable=SC2034
  read -r cur lev conn <<<"$(
    ACCT_PATH="$ACCT" python3 - <<'PY'
import json, os
from pathlib import Path
p = Path(os.environ["ACCT_PATH"])
if not p.exists():
    print(" 0 False")
else:
    d = json.loads(p.read_text())
    print(d.get("currency") or "", int(d.get("leverage") or 0), d.get("terminal_connected_raw"))
PY
  )"
  echo "t_left=$((END-SECONDS))s Network=$nets currency='$cur' lev=$lev conn=$conn" | tee -a "$REPORT"
  if [[ -n "${cur:-}" && "${lev:-0}" != "0" ]]; then
    info "PASS A candidate: currency=$cur leverage=$lev"
    break
  fi
done

{
  echo "=== final measure $(date -Is) ==="
  ip -br addr | head -20
  ss -tnp 2>/dev/null | rg 'wine|main|terminal' || true
  if [[ -f "$LOG" ]]; then
    echo "Network=$(iconv -f UTF-16 -t UTF-8 "$LOG" 2>/dev/null | rg -c Network || echo 0)"
    iconv -f UTF-16 -t UTF-8 "$LOG" 2>/dev/null | tail -25
  fi
  if [[ -f "$ACCT" ]]; then
    python3 -c "import json;from pathlib import Path;print(json.dumps(json.loads(Path(r'''$ACCT''').read_text()),indent=2))"
  fi
  WINEPREFIX="$WINEPREFIX" MT5_BACKEND=file uv run mt5-arch account 2>&1 || true
  echo ACCT_EXIT:$?
} | tee -a "$REPORT"

info "Report: $REPORT"
# trap restores bridges/docker/ts
