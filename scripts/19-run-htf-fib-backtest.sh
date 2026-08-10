#!/usr/bin/env bash
# Headless MT5 Strategy Tester (Single, non-visual) for ForexHtfFibTester.
#
# Usage:
#   export WINEPREFIX=~/.mt5-vantage
#   ./scripts/19-run-htf-fib-backtest.sh [SYMBOL] [PERIOD] [FROM] [TO]
#
# Optional env:
#   MT5_LOGIN / MT5_SERVER / MT5_PASSWORD  — override (password only if needed)
#   DEPOSIT=10000  MODEL=1  LEVERAGE=1:100  TIMEOUT_SEC=600
#   KILL_EXISTING=1   — kill terminal64 (default 1; one install = one process)
#   SKIP_COMPILE=0
#
# Example:
#   KILL_EXISTING=1 ./scripts/19-run-htf-fib-backtest.sh XAUUSD H1 2024.01.01 2025.01.01
#
# Fixes vs broken headless:
#   - Login from Config/common.ini (not Login=0 → "account not specified")
#   - Expert=ForexHtfFibTester (not Experts\Experts\...)
#   - Config ASCII+CRLF (UTF-16 rejected by /config)
#   - ExpertParameters .set for EA v1.40
#   - Report under reports/; parse agent DIAG after run
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env
require_cmd wine
require_cmd python3

SYMBOL="${1:-XAUUSD}"
PERIOD="${2:-H1}"
FROM="${3:-2024.01.01}"
TO="${4:-2025.01.01}"
DEPOSIT="${DEPOSIT:-10000}"
MODEL="${MODEL:-1}"                 # 1 = 1-minute OHLC
LEVERAGE="${LEVERAGE:-1:100}"
TIMEOUT_SEC="${TIMEOUT_SEC:-600}"
KILL_EXISTING="${KILL_EXISTING:-1}"
SKIP_COMPILE="${SKIP_COMPILE:-0}"

REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
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
[[ -n "${MT5_DIR:-}" && -f "$MT5_DIR/terminal64.exe" ]] || die "terminal64.exe not found in WINEPREFIX=$WINEPREFIX"

EXPERTS="$MT5_DIR/MQL5/Experts"
INCLUDE="$MT5_DIR/MQL5/Include"
PRESETS="$MT5_DIR/MQL5/Profiles/Tester"
REPORTS="$MT5_DIR/reports"
COMMON_INI="$MT5_DIR/Config/common.ini"
CFG_BASENAME="htf_fib_tester.ini"
CFG="$MT5_DIR/$CFG_BASENAME"

METAEDITOR=""
for cand in "$MT5_DIR/MetaEditor64.exe" "$MT5_DIR/metaeditor64.exe"; do
  [[ -f "$cand" ]] && METAEDITOR="$cand" && break
done
[[ -n "$METAEDITOR" ]] || die "MetaEditor64.exe missing"

mkdir -p "$EXPERTS" "$INCLUDE" "$PRESETS" "$REPORTS" "$MT5_DIR/MQL5/Files" "$MT5_DIR/Tester" \
  "$REPO_ROOT/results"

# --- Login / Server from common.ini or env ---
eval "$(
  COMMON_INI="$COMMON_INI" MT5_LOGIN="${MT5_LOGIN:-}" MT5_SERVER="${MT5_SERVER:-}" python3 - <<'PY'
import os
from pathlib import Path
login = os.environ.get("MT5_LOGIN", "").strip()
server = os.environ.get("MT5_SERVER", "").strip()
common = Path(os.environ["COMMON_INI"])
if common.is_file():
    raw = common.read_bytes()
    text = raw.decode("utf-16-le", "replace") if len(raw) > 2 and (raw[:2] == b"\xff\xfe" or raw[1] == 0) else raw.decode("utf-8", "replace")
    for line in text.replace("\r", "").split("\n"):
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if k == "Login" and (not login or login == "0") and v and v != "0":
            login = v
        if k == "Server" and not server and v:
            server = v
if not login or login == "0":
    raise SystemExit("ERROR: no Login — log into MT5 GUI once, or export MT5_LOGIN")
if not server:
    raise SystemExit("ERROR: no Server — export MT5_SERVER or log in once")
def sh(s):
    return "'" + s.replace("'", "'\"'\"'") + "'"
print(f"export MT5_LOGIN={sh(login)}")
print(f"export MT5_SERVER={sh(server)}")
PY
)"
info "Account Login=$MT5_LOGIN Server=$MT5_SERVER"

# --- Compile ---
if [[ "$SKIP_COMPILE" != "1" ]]; then
  cp -f "$REPO_ROOT/mql5/Include/ForexUtils.mqh" "$INCLUDE/"
  cp -f "$REPO_ROOT/mql5/Experts/ForexHtfFibTester.mq5" "$EXPERTS/"
  info "Compiling ForexHtfFibTester..."
  (
    cd "$EXPERTS"
    wine "$METAEDITOR" /compile:"ForexHtfFibTester.mq5" /log >/dev/null 2>&1 || true
  )
  sleep 2
  [[ -f "$EXPERTS/ForexHtfFibTester.ex5" ]] || die "compile failed — $EXPERTS/ForexHtfFibTester.log"
  info "Compile OK"
else
  [[ -f "$EXPERTS/ForexHtfFibTester.ex5" ]] || die "ForexHtfFibTester.ex5 missing"
fi

# --- .set (UTF-16LE) for v1.40 ---
SET_NAME="ForexHtfFibTester_v140.set"
SET_PATH="$PRESETS/$SET_NAME"
python3 - <<PY
from pathlib import Path
lines = """; ForexHtfFibTester v1.40 headless
InpSignalShift=1
InpAllowLiveTrading=false
InpUseEaFibEngine=true
InpTradingMode=0
InpPivotLeft=5
InpPivotRight=5
InpHtfBars=800
InpRsiPeriod=14
InpRsiLongMax=40
InpRsiShortMin=60
InpRequireGoldenZone=true
InpRequireBiasFilter=true
InpResearchFallback=false
InpLots=0.01
InpRiskPercent=0.5
InpAtrPeriod=14
InpSlAtrMult=2.0
InpTpAtrMult=3.0
InpMaxSpreadPips=0
InpMagic=26080505
InpSlippagePoints=50
InpReverseOnOpp=true
InpOneTradePerBar=true
InpDiagVerbose=true
""".strip().splitlines()
text = "\r\n".join(lines) + "\r\n"
Path("$SET_PATH").write_bytes(b"\xff\xfe" + text.encode("utf-16-le"))
print("wrote $SET_PATH")
PY

# --- tester.ini ASCII CRLF ---
STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_REL="reports/htf_fib_${SYMBOL}_${PERIOD}_${STAMP}"
SET_NAME="$SET_NAME" SYMBOL="$SYMBOL" PERIOD="$PERIOD" FROM="$FROM" TO="$TO" \
DEPOSIT="$DEPOSIT" MODEL="$MODEL" LEVERAGE="$LEVERAGE" REPORT_REL="$REPORT_REL" CFG="$CFG" \
MT5_LOGIN="$MT5_LOGIN" MT5_SERVER="$MT5_SERVER" MT5_PASSWORD="${MT5_PASSWORD:-}" \
python3 - <<'PY'
from pathlib import Path
import os
login = os.environ["MT5_LOGIN"]
server = os.environ["MT5_SERVER"]
pw = os.environ.get("MT5_PASSWORD", "").strip()
pass_line = f"Password={pw}\r\n" if pw else ""
body = f"""[Common]
Login={login}
{pass_line}Server={server}
ProxyEnable=0
ProxyType=0
KeepPrivate=1
NewsEnable=0
CertInstall=1

[Charts]
MaxBars=100000
PreloadCharts=1

[Experts]
AllowLiveTrading=0
AllowDllImport=0
Enabled=1
Account=0
Profile=0

[Tester]
Expert=ForexHtfFibTester
ExpertParameters={os.environ["SET_NAME"]}
Symbol={os.environ["SYMBOL"]}
Period={os.environ["PERIOD"]}
Optimization=0
Model={os.environ["MODEL"]}
FromDate={os.environ["FROM"]}
ToDate={os.environ["TO"]}
ForwardMode=0
Deposit={os.environ["DEPOSIT"]}
Currency=USD
ProfitInPips=0
Leverage={os.environ["LEVERAGE"]}
ExecutionMode=0
OptimizationCriterion=0
Visual=0
Report={os.environ["REPORT_REL"]}
ReplaceReport=1
ShutdownTerminal=1
UseLocal=1
UseRemote=0
UseCloud=0
"""
body = body.replace("\r\n", "\n").replace("\n", "\r\n")
Path(os.environ["CFG"]).write_bytes(body.encode("ascii"))
safe = body.replace(pw, "***") if pw else body
print(f"wrote {os.environ['CFG']} ({Path(os.environ['CFG']).stat().st_size} bytes)")
print(safe)
PY

# --- Kill existing terminal64 (required: one process per install) ---
kill_terminals() {
  local pids
  pids=$(ps -eo pid,cmd | awk '/terminal64\.exe/ && !/awk/ {print $1}')
  [[ -z "${pids// }" ]] && { info "No terminal64 running"; return 0; }
  info "Stopping terminal64: $pids"
  for p in $pids; do kill -TERM "$p" 2>/dev/null || true; done
  sleep 3
  for p in $pids; do
    ps -p "$p" >/dev/null 2>&1 && kill -KILL "$p" 2>/dev/null || true
  done
  sleep 1
}

if [[ "$KILL_EXISTING" == "1" ]]; then
  kill_terminals
else
  if ps -eo cmd | grep -q '[t]erminal64.exe'; then
    die "terminal64 running — close it or KILL_EXISTING=1"
  fi
fi

# --- Run ---
export WINEDEBUG="${WINEDEBUG:--all}"
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-d3d11=b;d3d12=b;dxgi=b}"
LOG="/tmp/mt5-tester-headless.log"
: >"$LOG"
info "Launch: wine terminal64 /portable /config:$CFG_BASENAME"
info "$SYMBOL $PERIOD $FROM → $TO model=$MODEL timeout=${TIMEOUT_SEC}s"

cd "$MT5_DIR"
RUNNER=(wine)
if [[ -z "${DISPLAY:-}" ]] && command -v xvfb-run >/dev/null 2>&1; then
  info "No DISPLAY — xvfb-run"
  RUNNER=(xvfb-run -a wine)
elif [[ -n "${DISPLAY:-}" ]]; then
  unset WAYLAND_DISPLAY || true
fi

set +e
timeout "$TIMEOUT_SEC" "${RUNNER[@]}" ./terminal64.exe /portable /config:"$CFG_BASENAME" >>"$LOG" 2>&1
rc=$?
set -e
info "exit code=$rc (0=ok 124=timeout)"

# --- Parse results ---
DAY="$(date +%Y%m%d)"
AGENT_LOG=""
for cand in \
  "$MT5_DIR/Tester/Agent-127.0.0.1-3001/logs/${DAY}.log" \
  "$MT5_DIR/Tester/logs/${DAY}.log"
do
  [[ -f "$cand" ]] && AGENT_LOG="$cand"
done
SUMMARY="$REPO_ROOT/results/htf_fib_headless_${SYMBOL}_${PERIOD}_${STAMP}.md"

DAY="$DAY" MT5_DIR="$MT5_DIR" AGENT_LOG="$AGENT_LOG" SUMMARY="$SUMMARY" \
SYMBOL="$SYMBOL" PERIOD="$PERIOD" FROM="$FROM" TO="$TO" RC="$rc" LOG="$LOG" \
python3 - <<'PY'
from pathlib import Path
import os, re

mt5 = Path(os.environ["MT5_DIR"])
agent = Path(os.environ.get("AGENT_LOG") or "")
day = os.environ["DAY"]
summary = Path(os.environ["SUMMARY"])

def read_log(p: Path) -> str:
    if not p.is_file():
        return ""
    raw = p.read_bytes()
    if len(raw) >= 2 and (raw[:2] == b"\xff\xfe" or raw[1] == 0):
        return raw.decode("utf-16-le", "replace")
    return raw.decode("utf-8", "replace")

text = read_log(agent)
text += "\n" + read_log(mt5 / "Tester" / "logs" / f"{day}.log")
text += "\n" + read_log(mt5 / "logs" / f"{day}.log")

pats = [
    r"cannot load config[^\r\n]*",
    r"account is not specified[^\r\n]*",
    r"EX5 not found[^\r\n]*",
    r"not found[^\r\n]*ex5[^\r\n]*",
    r"tester not started[^\r\n]*",
    r"shutdown with[^\r\n]*",
    r"ForexHtfFibTester v1\.\d+ ON[^\r\n]*",
    r"EaFib rebuild[^\r\n]*",
    r"DIAG\[OnTester\][^\r\n]*",
    r"OnTester summary[^\r\n]*",
    r"final balance[^\r\n]*",
    r"OnTester result[^\r\n]*",
    r"Test passed[^\r\n]*",
]
blocks = []
for pat in pats:
    found = re.findall(pat, text, flags=re.I)
    if found:
        blocks.append((pat, found[-6:]))

reports = []
if (mt5 / "reports").is_dir():
    reports = sorted((mt5 / "reports").glob("htf_fib_*"), key=lambda p: p.stat().st_mtime, reverse=True)[:8]
reports += sorted(mt5.glob("htf_fib_*.htm*"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]

ok = any(
    re.search(r"OnTester summary|DIAG\[OnTester\].*trades=", t, re.I)
    for _, fs in blocks for t in fs
)
fail = any(
    re.search(r"account is not specified|EX5 not found|cannot load config|tester not started", t, re.I)
    for _, fs in blocks for t in fs
)

md = [
    f"# Headless Single test — {os.environ['SYMBOL']} {os.environ['PERIOD']}\n\n",
    f"- Range: **{os.environ['FROM']} → {os.environ['TO']}**\n",
    f"- Exit code: **{os.environ['RC']}**\n",
    f"- Status: **{'OK' if ok else 'FAILED/INCOMPLETE'}**\n",
    f"- Agent: `{agent}`\n",
    f"- Wine: `{os.environ['LOG']}`\n\n## Journal\n",
]
if not blocks:
    md.append("_No markers — config may not have loaded or tester did not start._\n")
for pat, found in blocks:
    md.append(f"### `{pat}`\n```\n" + "\n".join(found) + "\n```\n")
md.append("\n## Reports\n")
for r in reports:
    md.append(f"- `{r}` ({r.stat().st_size} bytes)\n")
if not reports:
    md.append("_none_\n")

summary.write_text("".join(md))
print(f"wrote {summary}")
print("STATUS:", "OK" if ok else ("FAIL" if fail else "INCOMPLETE"))
for pat, found in blocks:
    if any(k in pat for k in ("DIAG", "OnTester", "v1.", "account", "EX5", "config", "final balance", "not started")):
        print(f"[{pat.split('[')[0][:40]}]")
        for f in found[-2:]:
            print(" ", f[:220])
raise SystemExit(0 if ok else 1)
PY

info "Summary: $SUMMARY"
info "Wine log: $LOG"
