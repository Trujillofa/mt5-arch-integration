#!/usr/bin/env bash
# Multi-broker health: report / fix frozen or missing MetaTrader terminals.
#
# Default (report only):
#   ./scripts/14-fix-terminals.sh
#   ./scripts/14-fix-terminals.sh --json
#
# Restart only brokers that are DOWN or UI-frozen (scoped per WINEPREFIX):
#   ./scripts/14-fix-terminals.sh --fix
#
# Force restart every configured broker:
#   ./scripts/14-fix-terminals.sh --fix-all
#
# Brokers default to vantage / fpmarkets / exness / wsf when their ~/.mt5-* exists.
# Override: MT5_BROKERS="vantage exness" ./scripts/14-fix-terminals.sh --fix
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export DISPLAY="${DISPLAY:-:0}"

MODE=report
JSON=0
for arg in "$@"; do
  case "$arg" in
    --fix) MODE=fix ;;
    --fix-all) MODE=fix-all ;;
    --json) JSON=1 ;;
    -h|--help)
      sed -n '2,18p' "$0"
      exit 0
      ;;
    *) die "unknown arg: $arg (use --fix | --fix-all | --json)" ;;
  esac
done

default_brokers() {
  local b
  for b in vantage fpmarkets exness wsf; do
    [[ -d "$HOME/.mt5-$b" ]] && echo "$b"
  done
}

mapfile -t BROKERS < <(
  if [[ -n "${MT5_BROKERS:-}" ]]; then
    # shellcheck disable=SC2086
    printf '%s\n' $MT5_BROKERS
  else
    default_brokers
  fi
)
[[ ${#BROKERS[@]} -gt 0 ]] || die "no broker prefixes found under ~/.mt5-*"

hz="$(getconf CLK_TCK 2>/dev/null || echo 100)"
rows=()

classify() {
  local pfx="$1" pid="${2:-}" status="DOWN" pct=0 ud=0 sd=0 wchan="-"
  if [[ -n "$pid" && -d "/proc/$pid" ]]; then
    local before after bu bs au as
    before="$(_mt5_main_times "$pid")"
    sleep 1
    after="$(_mt5_main_times "$pid")"
    read -r bu bs <<<"$before"
    read -r au as <<<"$after"
    ud=$(( au - bu ))
    sd=$(( as - bs ))
    pct=$(( (ud + sd) * 100 / hz ))
    wchan="$(cat "/proc/$pid/task/$pid/wchan" 2>/dev/null || echo '?')"
    if _mt5_ui_frozen "$pid"; then
      status="FROZEN"
    else
      status="OK"
    fi
  fi
  printf '%s|%s|%s|%s|%s|%s|%s\n' "$pfx" "${pid:--}" "$status" "$pct" "$ud" "$sd" "$wchan"
}

echo "==> Broker terminal health" >&2
for b in "${BROKERS[@]}"; do
  pfx="$HOME/.mt5-$b"
  mapfile -t pids < <(mt5_terminal_pids "$pfx" || true)
  row="$(classify "$b" "${pids[0]:-}")"
  rows+=("$row")
  IFS='|' read -r name pid status pct ud sd wchan <<<"$row"
  [[ "$pid" == "-" ]] && pid="—"
  printf '  %-10s %-8s pid=%-8s cpu=%3s%% ud=%s sd=%s wchan=%s\n' \
    "$name" "$status" "$pid" "$pct" "$ud" "$sd" "$wchan" >&2
done

if [[ "$JSON" -eq 1 ]]; then
  printf '%s\n' "${rows[@]}" | python3 -c '
import json,sys
out=[]
for line in sys.stdin:
    name,pid,status,pct,ud,sd,wchan=line.rstrip("\n").split("|")
    out.append({"broker":name,"pid":int(pid) if pid not in ("","-") else None,"status":status,
                "cpu_pct":int(pct),"udelta":int(ud),"sdelta":int(sd),"wchan":wchan})
print(json.dumps(out, indent=2))
'
fi

if [[ "$MODE" == "report" ]]; then
  bad=0
  for row in "${rows[@]}"; do
    IFS='|' read -r name _ status _ <<<"$row"
    # Missing optional prefixes (e.g. wsf) are not a failure — only live brokers
    # that are FROZEN, or configured brokers that are DOWN when the prefix has a
    # recent terminal expectation. Treat DOWN as bad only for vantage/fp/exness.
    case "$status" in
      FROZEN) bad=1 ;;
      DOWN)
        case "$name" in
          vantage|fpmarkets|exness) bad=1 ;;
        esac
        ;;
    esac
  done
  exit "$bad"
fi

fixed=0
for row in "${rows[@]}"; do
  IFS='|' read -r name pid status _ <<<"$row"
  need=0
  if [[ "$MODE" == "fix-all" ]]; then
    # Never auto-start optional prefixes that have no install expectation.
    [[ "$status" != "DOWN" || "$name" =~ ^(vantage|fpmarkets|exness)$ ]] || continue
    need=1
  elif [[ "$status" == "FROZEN" ]]; then
    need=1
  elif [[ "$status" == "DOWN" && "$name" =~ ^(vantage|fpmarkets|exness)$ ]]; then
    need=1
  fi
  [[ "$need" -eq 1 ]] || continue
  info "Fixing $name ($status)…"
  WINEPREFIX="$HOME/.mt5-$name" "$SCRIPT_DIR/07-restart-terminal.sh" || warn "restart failed for $name"
  fixed=$((fixed + 1))
done

if [[ "$fixed" -eq 0 ]]; then
  info "Nothing to fix."
else
  info "Fixed $fixed broker(s). Re-check with: ./scripts/14-fix-terminals.sh"
fi
