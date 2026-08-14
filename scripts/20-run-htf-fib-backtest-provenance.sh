#!/usr/bin/env bash
# Reproducibility wrapper around 19-run-htf-fib-backtest.sh.
#
# Records provenance.json next to the Strategy Tester report:
#   terminal/build, broker + registry symbol, tester model/window,
#   INI/SET/MQL5/EX5 hashes, history listing identity, costs/spread,
#   report path, optional parity/sync traces.
#
# Usage:
#   export WINEPREFIX=~/.mt5-vantage
#   export MT5_BROKER=vantage          # or InpBroker; required (no suffix walk)
#   ./scripts/20-run-htf-fib-backtest-provenance.sh [SYMBOL] [PERIOD] [FROM] [TO]
#
# Optional env (same as 19-run, plus):
#   MT5_BROKER / InpBroker / BROKER  — explicit registry broker (required)
#   SKIP_TESTER=1   — record from existing artifacts; do not call 19-run
#   PARITY_TRACE=   — optional exported parity dump path
#   SYNC_AUDIT=     — optional exported sync-audit dump path
#   PROVENANCE_OUT= — override provenance.json path
#   KILL_EXISTING   — passed through to 19-run (default 1; kills terminal64)
#
# Does not write MT5_PASSWORD into provenance. Does not place live orders.
# Do not run this against a live GUI session unless you intend KILL_EXISTING=1.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env
require_cmd python3

SYMBOL="${1:-XAUUSD}"
PERIOD="${2:-H1}"
FROM="${3:-2024.01.01}"
TO="${4:-2025.01.01}"
SKIP_TESTER="${SKIP_TESTER:-0}"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BROKER="${MT5_BROKER:-${InpBroker:-${BROKER:-}}}"
if [[ -z "${BROKER// }" ]]; then
  die "MT5_BROKER / InpBroker is required (explicit registry; no suffix walk)"
fi
export MT5_BROKER="$BROKER"
export BROKER="$BROKER"

RESOLVED="$(
  REPO_ROOT="$REPO_ROOT" BROKER="$BROKER" SYMBOL="$SYMBOL" python3 - <<'PY'
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(os.environ["REPO_ROOT"]) / "src"))
from mt5_arch.symbol_registry import load_registry, resolve
m = resolve(load_registry(), os.environ["BROKER"], os.environ["SYMBOL"])
print(m.broker_symbol)
PY
)"
info "Registry $BROKER $SYMBOL → $RESOLVED"

# --- Locate terminal (same candidates as 19-run; needed for hashes / report) ---
MT5_DIR=""
for d in \
  "$WINEPREFIX/drive_c/Program Files/Vantage International MT5" \
  "$WINEPREFIX/drive_c/Program Files/MetaTrader 5" \
  "$WINEPREFIX/drive_c/Program Files/FP Markets MT5 Terminal" \
  "$WINEPREFIX/drive_c/Program Files/WSFmarkets MT5 Terminal"
do
  if [[ -f "$d/terminal64.exe" ]]; then MT5_DIR="$d"; break; fi
done
if [[ -z "${MT5_DIR:-}" ]]; then
  t64="$(find_terminal64 2>/dev/null || true)"
  [[ -n "$t64" ]] && MT5_DIR="$(dirname "$t64")"
fi
if [[ "$SKIP_TESTER" != "1" ]]; then
  [[ -n "${MT5_DIR:-}" && -f "$MT5_DIR/terminal64.exe" ]] || die "terminal64.exe not found in WINEPREFIX=$WINEPREFIX"
fi

COMMON_INI="${MT5_DIR:+$MT5_DIR/Config/common.ini}"
LOGIN_INFO="$(
  REPO_ROOT="$REPO_ROOT" COMMON_INI="${COMMON_INI:-}" python3 - <<'PY'
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(os.environ["REPO_ROOT"]) / "src"))
from mt5_arch.tester_provenance import login_from_common_ini
ini = Path(os.environ.get("COMMON_INI") or "")
login, server = login_from_common_ini(ini)
print(f"{login}\t{server}")
PY
)"
MT5_LOGIN_RESOLVED="${LOGIN_INFO%%$'\t'*}"
MT5_SERVER_RESOLVED="${LOGIN_INFO#*$'\t'}"
if [[ -z "${MT5_LOGIN_RESOLVED:-}" || "$MT5_LOGIN_RESOLVED" == "0" ]]; then
  die "Login=0 — log into MT5 GUI once, or export MT5_LOGIN (not recorded as 0)"
fi
info "Account Login=$MT5_LOGIN_RESOLVED Server=$MT5_SERVER_RESOLVED"

run_rc=0
if [[ "$SKIP_TESTER" == "1" ]]; then
  info "SKIP_TESTER=1 — not calling 19-run (will not kill terminal64)"
else
  info "Calling scripts/19-run-htf-fib-backtest.sh $RESOLVED $PERIOD $FROM $TO"
  set +e
  "$SCRIPT_DIR/19-run-htf-fib-backtest.sh" "$RESOLVED" "$PERIOD" "$FROM" "$TO"
  run_rc=$?
  set -e
  info "19-run exit=$run_rc"
fi

WINE_VER="$(wine --version 2>/dev/null || true)"
PARITY_TRACE="${PARITY_TRACE:-}"
SYNC_AUDIT="${SYNC_AUDIT:-}"
PROVENANCE_OUT="${PROVENANCE_OUT:-}"
DEPOSIT="${DEPOSIT:-10000}"
MODEL="${MODEL:-1}"
LEVERAGE="${LEVERAGE:-1:100}"

OUT="$(
  REPO_ROOT="$REPO_ROOT" MT5_DIR="${MT5_DIR:-}" BROKER="$BROKER" REQUESTED="$SYMBOL" \
  RESOLVED="$RESOLVED" PERIOD="$PERIOD" FROM="$FROM" TO="$TO" \
  LOGIN="$MT5_LOGIN_RESOLVED" SERVER="$MT5_SERVER_RESOLVED" \
  MODEL="$MODEL" DEPOSIT="$DEPOSIT" LEVERAGE="$LEVERAGE" \
  WINE_VER="$WINE_VER" PARITY_TRACE="$PARITY_TRACE" SYNC_AUDIT="$SYNC_AUDIT" \
  PROVENANCE_OUT="$PROVENANCE_OUT" python3 - <<'PY'
import os, sys
from pathlib import Path

sys.path.insert(0, str(Path(os.environ["REPO_ROOT"]) / "src"))
from mt5_arch.tester_provenance import (
    find_latest_report,
    find_symbol_history_dir,
    history_listing_identity,
    parse_ini_map,
    parse_mt5_build,
    pe_file_version,
    provenance_path_for_report,
    record_tester_run,
)

root = Path(os.environ["REPO_ROOT"])
mt5 = Path(os.environ.get("MT5_DIR") or "")
requested = os.environ["REQUESTED"]
resolved = os.environ["RESOLVED"]
period = os.environ["PERIOD"]
server = os.environ["SERVER"]
report = find_latest_report(mt5 / "reports", resolved, period) if mt5.is_dir() else None
override = os.environ.get("PROVENANCE_OUT") or ""
if override:
    out = Path(override)
elif report is not None:
    out = provenance_path_for_report(report)
else:
    out = root / "results" / f"htf_fib_{resolved}_{period}.provenance.json"

ini_path = mt5 / "htf_fib_tester.ini" if mt5.is_dir() else None
set_path = mt5 / "MQL5" / "Profiles" / "Tester" / "ForexHtfFibTester_v140.set" if mt5.is_dir() else None
ex5_path = mt5 / "MQL5" / "Experts" / "ForexHtfFibTester.ex5" if mt5.is_dir() else None
expert_src = root / "mql5" / "Experts" / "ForexHtfFibTester.mq5"
include_src = root / "mql5" / "Include" / "ForexUtils.mqh"
terminal = mt5 / "terminal64.exe" if mt5.is_dir() else Path()
ver = pe_file_version(terminal) if terminal.is_file() else ""
fields = parse_ini_map(set_path) if set_path and set_path.is_file() else {}
max_spread = fields.get("InpMaxSpreadPips", "0")
slip = fields.get("InpSlippagePoints", "50")
hist_dir = find_symbol_history_dir(mt5, server, resolved) if mt5.is_dir() else Path("")
hist = history_listing_identity(hist_dir) if mt5.is_dir() else {
    "found": False,
    "path": "",
    "n_files": 0,
    "listing_sha256": "",
    "note": "Multi-currency Strategy Tester results depend on available synchronized foreign-symbol history; this record is identity, not a quality score.",
}
report_path = str(report) if report is not None else ""
parity = os.environ.get("PARITY_TRACE") or None
sync = os.environ.get("SYNC_AUDIT") or None
record_tester_run(
    out,
    source="mql5_export",
    broker=os.environ["BROKER"],
    requested=requested,
    login=os.environ["LOGIN"],
    server=server,
    period=period,
    model=os.environ["MODEL"],
    from_date=os.environ["FROM"],
    to_date=os.environ["TO"],
    report_path=report_path,
    ini_path=ini_path,
    set_path=set_path,
    mql5_expert_path=expert_src,
    mql5_include_path=include_src,
    ex5_path=ex5_path,
    terminal_name=mt5.name if mt5.is_dir() else "",
    terminal_path=str(terminal) if terminal.is_file() else "",
    terminal_build=parse_mt5_build(ver),
    wine_version=os.environ.get("WINE_VER") or "",
    deposit=os.environ.get("DEPOSIT") or 10000,
    leverage=os.environ.get("LEVERAGE") or "1:100",
    max_spread_pips=max_spread,
    slippage_points=slip,
    history=hist,
    parity_trace_path=parity,
    sync_audit_path=sync,
)
print(out)
PY
)"

info "Provenance: $OUT"
if [[ "$run_rc" -ne 0 ]]; then
  die "19-run failed (exit $run_rc); provenance write attempted at $OUT"
fi
info "OK"
