#!/usr/bin/env bash
# Export XAUUSD/EURUSD/GBPUSD H1 with per-bar spread from *one* Wine MT5 prefix.
# Phase-0 multi-instrument data readiness — fail-closed. No strategy scoring.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_dotenv
export_wine_env
require_cmd wine
require_cmd python3
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SYMBOLS="${SYMBOLS:-XAUUSD,EURUSD,GBPUSD}"
MONTHS="${MONTHS:-60}"
TFS="${TFS:-H1}"
TIMEOUT_S="${TIMEOUT_S:-300}"
MAXBARS="${MAXBARS:-100000}"
# Expected account identity (must match common.ini after export)
EXPECT_LOGIN="${EXPECT_LOGIN:-${MT5_LOGIN:-27496181}}"
EXPECT_SERVER="${EXPECT_SERVER:-${MT5_SERVER:-VantageMarkets-Live 5}}"

WINEPREFIX="$(readlink -f "${WINEPREFIX:-$HOME/.mt5-vantage}")"
export WINEPREFIX
BROKER="${BROKER:-}"
if [[ -z "$BROKER" ]]; then
  case "$WINEPREFIX" in
    *mt5-vantage*) BROKER=vantage ;;
    *mt5-fpmarkets*) BROKER=fpmarkets ;;
    *mt5-exness*) BROKER=exness ;;
    *mt5-wsf*) BROKER=wsf ;;
  esac
fi
[[ -n "$BROKER" ]] || die "set BROKER=vantage|fpmarkets|exness|wsf"
export BROKER
info "WINEPREFIX=$WINEPREFIX broker=$BROKER (prefix-scoped only)"

MT5_DIR=""
for d in \
  "$WINEPREFIX/drive_c/Program Files/Vantage International MT5" \
  "$WINEPREFIX/drive_c/Program Files/MetaTrader 5"
do
  [[ -f "$d/terminal64.exe" ]] && MT5_DIR="$d" && break
done
[[ -n "$MT5_DIR" ]] || die "terminal64 not found under WINEPREFIX=$WINEPREFIX"

mkdir -p "$MT5_DIR/MQL5/Scripts" "$MT5_DIR/MQL5/Include" "$MT5_DIR/MQL5/Files/mt5_arch"
cp -f "$REPO_ROOT/mql5/Include/FxSymbolRegistry.mqh" "$MT5_DIR/MQL5/Include/"
cp -f "$REPO_ROOT/mql5/Scripts/ExportInstrumentHistory.mq5" "$MT5_DIR/MQL5/Scripts/"
ME="$MT5_DIR/MetaEditor64.exe"
info "Compiling ExportInstrumentHistory.mq5..."
( cd "$MT5_DIR/MQL5/Scripts" && wine "$ME" /compile:"ExportInstrumentHistory.mq5" /log >/dev/null 2>&1 || true )
[[ -f "$MT5_DIR/MQL5/Scripts/ExportInstrumentHistory.ex5" ]] || die "compile failed — open MetaEditor log"

# ---------------------------------------------------------------------------
# Kill only terminal64 processes whose WINEPREFIX matches this prefix.
# ---------------------------------------------------------------------------
kill_prefix_terminals() {
  python3 - <<'PY'
import os, signal, time
from pathlib import Path

want = Path(os.environ["WINEPREFIX"]).resolve()
pids = []
for p in Path("/proc").iterdir():
    if not p.name.isdigit():
        continue
    try:
        cmd = (p / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
        if "terminal64" not in cmd:
            continue
        env = (p / "environ").read_bytes().split(b"\x00")
        wp = ""
        for e in env:
            if e.startswith(b"WINEPREFIX="):
                wp = e.decode("utf-8", "replace").split("=", 1)[1]
                break
        if not wp:
            continue
        if Path(wp).expanduser().resolve() != want:
            continue
        pids.append(int(p.name))
    except (OSError, PermissionError, ValueError):
        continue
for sig in (signal.SIGTERM, signal.SIGKILL):
    for pid in pids:
        try:
            os.kill(pid, sig)
            print(f"sent {sig.name} to prefix terminal pid={pid}")
        except ProcessLookupError:
            pass
    if sig == signal.SIGTERM and pids:
        time.sleep(2)
print(f"prefix_terminal_pids={pids}")
PY
}
info "Stopping terminal64 only in this WINEPREFIX..."
kill_prefix_terminals

LOGIN=$(python3 -c "
from pathlib import Path
raw=Path(r'$MT5_DIR/Config/common.ini').read_bytes()
text=raw.decode('utf-16-le','replace')
for line in text.replace(chr(13),'').split(chr(10)):
  if line.startswith('Login='): print(line.split('=',1)[1].strip())
")
SERVER=$(python3 -c "
from pathlib import Path
raw=Path(r'$MT5_DIR/Config/common.ini').read_bytes()
text=raw.decode('utf-16-le','replace')
for line in text.replace(chr(13),'').split(chr(10)):
  if line.startswith('Server='): print(line.split('=',1)[1].strip())
")
info "common.ini Login=$LOGIN Server=$SERVER"
[[ "$LOGIN" == "$EXPECT_LOGIN" ]] || die "login mismatch: common.ini=$LOGIN expected=$EXPECT_LOGIN"
[[ "$SERVER" == "$EXPECT_SERVER" ]] || die "server mismatch: common.ini=$SERVER expected=$EXPECT_SERVER"

OUT_DIR="$MT5_DIR/MQL5/Files/mt5_arch"
RUN_ID="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
EXPORT_MARK_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
# Epoch second just before run — require output mtimes strictly after this.
PRE_EXPORT_EPOCH=$(date +%s)
# Subtract 1s slack for FS second resolution
PRE_EXPORT_EPOCH=$((PRE_EXPORT_EPOCH - 1))

# Move prior history_* / completion aside so we never accept stale CSVs as success.
ARCHIVE="$OUT_DIR/_stale_$(date -u +%Y%m%dT%H%M%SZ)_$RUN_ID"
mkdir -p "$ARCHIVE"
for s in ${SYMBOLS//,/ }; do
  s=$(echo "$s" | tr -d ' ')
  for f in "$OUT_DIR/history_${s}.csv" "$OUT_DIR/symbol_meta_${s}.csv"; do
    [[ -f "$f" ]] && mv -f "$f" "$ARCHIVE/"
  done
done
for f in "$OUT_DIR/export_complete.json" "$OUT_DIR/export_run.json"; do
  [[ -f "$f" ]] && mv -f "$f" "$ARCHIVE/"
done
info "Stale CSVs moved to $ARCHIVE (if any)"

# Pre-launch challenge: MQL must echo run_id/symbols/tfs unchanged.
python3 - <<PY
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

out = Path(r"$OUT_DIR")
run_id = "$RUN_ID"
symbols = [s.strip() for s in "$SYMBOLS".split(",") if s.strip()]
# Fixed server-time window: last MONTHS months ending "now" (server clock at export)
months = int("$MONTHS")
# Bound labels for attestation (MQL still uses TimeCurrent()-months internally;
# challenge documents the intended window policy).
challenge = {
    "run_id": run_id,
    "symbols": symbols,
    "timeframes": "$TFS",
    "months": months,
    "holdout_start_server": "2026-01-01 00:00:00",
    "expect_login": int("$EXPECT_LOGIN") if "$EXPECT_LOGIN".isdigit() else "$EXPECT_LOGIN",
    "expect_server": "$EXPECT_SERVER",
    "issued_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
(out / "export_challenge.json").write_text(json.dumps(challenge, separators=(",", ":")) + "\n")
repo = Path(r"$REPO_ROOT/results/instrument_data_manifests")
repo.mkdir(parents=True, exist_ok=True)
(repo / "export_challenge.json").write_text(json.dumps(challenge, indent=2) + "\n")
print("challenge", run_id, symbols)
PY

python3 - <<PY
from pathlib import Path
mt5 = Path(r"$MT5_DIR")
text = f"""[Common]
Login={'$LOGIN'}
Server={'$SERVER'}
ProxyEnable=0
KeepPrivate=1
NewsEnable=0
CertInstall=1
[Charts]
MaxBars=${MAXBARS}
PreloadCharts=1
[Experts]
AllowLiveTrading=0
Enabled=1
[StartUp]
Script=ExportInstrumentHistory
Symbol=XAUUSD
Period=H1
ScriptParameters=ExportInstrumentHistory.set
ShutdownTerminal=1
""".replace("\n", "\r\n")
(mt5 / "export_instruments.ini").write_bytes(text.encode("ascii"))
set_body = f"""InpBroker={'$BROKER'}
InpSymbols={'$SYMBOLS'}
InpMonths={'$MONTHS'}
InpTfs={'$TFS'}
InpOutDir=mt5_arch
InpChallengeFile=mt5_arch\\\\export_challenge.json
"""
# MT5 loads start-config script inputs from MQL5\\Presets\\<script>.set — NOT
# from the script's own folder. Verified 2026-08-20: with the .set beside the
# .ex5 the StartUp script ran on defaults (FATAL: InpBroker empty, 12ms exit).
# Atomic write per the v4 "set-atomic" freeze.
preset_dir = mt5 / "MQL5/Presets"
preset_dir.mkdir(parents=True, exist_ok=True)
tmp_set = preset_dir / ".ExportInstrumentHistory.set.tmp"
(tmp_set).write_bytes(
    "\ufeff".encode("utf-16-le") + set_body.encode("utf-16-le")
)
tmp_set.replace(preset_dir / "ExportInstrumentHistory.set")
(preset_dir / "ExportInstrumentHistory.set").chmod(0o644)
print("ini/set ok")
PY

info "Running export (timeout ${TIMEOUT_S}s) run_id=$RUN_ID ..."
cd "$MT5_DIR"
export WINEDEBUG=-all WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-d3d11=b;d3d12=b;dxgi=b}"
set +e
timeout "$TIMEOUT_S" wine ./terminal64.exe /portable /config:export_instruments.ini
rc=$?
set -e
# Wine exit codes are unreliable under portable ShutdownTerminal; attestation is
# mtime-fresh files + export_complete.json + export_run.json. Accepted set is
# enforced in the Python builder (0, 3, 124).
info "wine exit_code=$rc"

EXPORT_MARK_END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Fail-closed: every symbol history + meta must exist AND be mtime-fresh for this run.
python3 - <<PY
import hashlib, json, os, sys
from pathlib import Path

out = Path(r"$OUT_DIR")
symbols = [s.strip() for s in "$SYMBOLS".split(",") if s.strip()]
pre = int("$PRE_EXPORT_EPOCH")
run_id = "$RUN_ID"
login = "$LOGIN"
server = "$SERVER"
wp = r"$WINEPREFIX"
rc = int("$rc")
files = {}
errs = []
for s in symbols:
    hist = out / f"history_{s}.csv"
    meta = out / f"symbol_meta_{s}.csv"
    for p, kind in ((hist, "history"), (meta, "meta")):
        if not p.is_file():
            errs.append(f"missing_{kind}:{s}")
            continue
        mtime = int(p.stat().st_mtime)
        if mtime < pre:
            errs.append(f"stale_{kind}:{s}:mtime={mtime}<pre={pre}")
            continue
        if p.stat().st_size < 100:
            errs.append(f"tiny_{kind}:{s}:size={p.stat().st_size}")
            continue
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        files[f"{kind}_{s}"] = {
            "path": str(p),
            "sha256": h,
            "bytes": p.stat().st_size,
            "mtime_unix": mtime,
        }

complete_path = out / "export_complete.json"
if not complete_path.is_file():
    errs.append("missing_export_complete.json")
elif int(complete_path.stat().st_mtime) < pre:
    errs.append("stale_export_complete.json")
else:
    try:
        complete = json.loads(complete_path.read_text())
    except json.JSONDecodeError as e:
        errs.append(f"export_complete_json_error:{e}")
        complete = {}
    if not complete.get("ok"):
        errs.append("export_complete_ok_false")
    if not complete.get("terminal_connected"):
        errs.append("export_complete_not_connected")
    if complete.get("run_id") != run_id:
        errs.append(
            f"run_id_mismatch:complete={complete.get('run_id')!r} challenge={run_id!r}"
        )
    if complete.get("account_login") is None:
        errs.append("complete_missing_account_login")
    if not complete.get("account_server"):
        errs.append("complete_missing_account_server")
    if "challenge_echo" not in complete:
        errs.append("complete_missing_challenge_echo")
    else:
        # Exact challenge/echo compare (not presence-only)
        ch_path = out / "export_challenge.json"
        if not ch_path.is_file():
            errs.append("missing_export_challenge_for_echo_compare")
        else:
            try:
                challenge = json.loads(ch_path.read_text())
            except json.JSONDecodeError as e:
                errs.append(f"export_challenge_json_error:{e}")
                challenge = None
            echo_raw = complete.get("challenge_echo")
            try:
                if isinstance(echo_raw, dict):
                    echo = echo_raw
                else:
                    echo = json.loads(echo_raw) if echo_raw else None
            except (TypeError, json.JSONDecodeError):
                errs.append("challenge_echo_unparseable")
                echo = None
            if challenge is not None and isinstance(echo, dict):
                for key in (
                    "run_id",
                    "symbols",
                    "timeframes",
                    "holdout_start_server",
                    "expect_login",
                    "expect_server",
                ):
                    if challenge.get(key) != echo.get(key):
                        errs.append(
                            f"challenge_echo_mismatch:{key}:"
                            f"challenge={challenge.get(key)!r}:echo={echo.get(key)!r}"
                        )
            elif challenge is not None:
                errs.append("challenge_echo_not_object")
    # Do NOT overwrite MQL run_id. Record shell identity separately.
    complete["shell_login"] = int(login) if str(login).isdigit() else login
    complete["shell_server"] = server
    complete_path.write_text(json.dumps(complete, indent=2) + "\n")
    repo_meta = Path(r"$REPO_ROOT/results/instrument_data_manifests")
    repo_meta.mkdir(parents=True, exist_ok=True)
    (repo_meta / "export_complete.json").write_text(json.dumps(complete, indent=2) + "\n")

if errs:
    print("EXPORT_FAIL:", "; ".join(errs), file=sys.stderr)
    sys.exit(2)

meta = {
    "run_id": run_id,
    "export_started_utc": "$EXPORT_MARK_START",
    "export_finished_utc": "$EXPORT_MARK_END",
    "wine_exit_code": rc,
    "wineprefix": wp,
    "mt5_dir": r"$MT5_DIR",
    "login": int(login) if str(login).isdigit() else login,
    "server": server,
    "expect_login": int("$EXPECT_LOGIN") if "$EXPECT_LOGIN".isdigit() else "$EXPECT_LOGIN",
    "expect_server": "$EXPECT_SERVER",
    "symbols": symbols,
    "months": int("$MONTHS"),
    "timeframes": "$TFS",
    "clock_note": "Bar timestamps in history_*.csv are MT5 server clock strings (offset-free). Not labeled UTC.",
    "account_source": "common.ini pre-check + MQL export_complete.json runtime AccountInfo/TERMINAL_CONNECTED",
    "files": files,
}
repo_meta = Path(r"$REPO_ROOT/results/instrument_data_manifests")
repo_meta.mkdir(parents=True, exist_ok=True)
path = out / "export_run.json"
path.write_text(json.dumps(meta, indent=2) + "\n")
(repo_meta / "export_run.json").write_text(json.dumps(meta, indent=2) + "\n")
print(json.dumps({"ok": True, "run_id": run_id, "n_files": len(files), "wine_exit_code": rc}, indent=2))
PY

info "Export verified fresh for all symbols. export_run.json written."
info "Next: python3 scripts/build_multi_instrument_data_readiness.py"
