#!/usr/bin/env bash
# Headless MT5 Strategy Tester for the vendored Renko experts (real ticks only).
#
# Companion to the offline screen in scripts/renko_event_clock_screen.py. The
# Python screen rebuilds bricks from M15 bars; this runs the same frozen
# parameters against the terminal's real tick history, which is the only way to
# find out whether that reconstruction was faithful.
#
# Usage:
#   export WINEPREFIX=~/.mt5-vantage
#   ./scripts/25-run-renko-vendor-backtest.sh adx        [SYMBOL] [PERIOD] [FROM] [TO]
#   ./scripts/25-run-renko-vendor-backtest.sh bollinger  [SYMBOL] [PERIOD] [FROM] [TO]
#
# Optional env:
#   DEPOSIT=10000  LEVERAGE=1:100  TIMEOUT_SEC=1800  KILL_EXISTING=1  SKIP_COMPILE=0
#   MODEL=4        — every tick based on real ticks. 1/2/3 are REFUSED (see below).
#   MT5_LOGIN / MT5_SERVER / MT5_PASSWORD  — override common.ini
#
# Why MODEL is pinned to real ticks:
#   Both experts build Renko from the incoming bid tick inside OnTick. Under the
#   tester's 1-minute OHLC model (MODEL=1, the default in 19-*.sh) the "ticks" are
#   four synthetic prices per minute, so the brick series — and therefore every
#   signal — is an artefact of the tester's interpolation rather than of price.
#
# Why the window is capped:
#   results/xau_holdout_lock.json fixes holdout_start under the rule "NEVER used
#   for selection". This script refuses a TO date at or past it so a tester run
#   cannot quietly burn the holdout. Evaluating the holdout is a separate,
#   deliberate act, not a default.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env
require_cmd wine
require_cmd python3

REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CHARTER="$REPO_ROOT/results/xau_charters/2026-09-19_renko_event_clock_vendor_v1.json"
HOLDOUT_LOCK="$REPO_ROOT/results/xau_holdout_lock.json"

EA_KEY="${1:-}"
case "$EA_KEY" in
  adx)       EA_NAME="GDS_Renko_ADX_Demo" ;;
  bollinger) EA_NAME="GDS_Renko_Bollinger_4Mode_Demo" ;;
  *) die "usage: $(basename "$0") {adx|bollinger} [SYMBOL] [PERIOD] [FROM] [TO]" ;;
esac

SYMBOL="${2:-XAUUSD}"
PERIOD="${3:-M15}"
FROM="${4:-2022.05.17}"
TO="${5:-2025.12.31}"
DEPOSIT="${DEPOSIT:-10000}"
MODEL="${MODEL:-4}"
LEVERAGE="${LEVERAGE:-1:100}"
TIMEOUT_SEC="${TIMEOUT_SEC:-1800}"
KILL_EXISTING="${KILL_EXISTING:-1}"
SKIP_COMPILE="${SKIP_COMPILE:-0}"

[[ -f "$CHARTER" ]] || die "frozen charter missing: $CHARTER"

if [[ "$MODEL" != "4" && "$MODEL" != "0" ]]; then
  die "MODEL=$MODEL builds bricks from synthetic ticks. Use MODEL=4 (real ticks)."
fi

# Refuse to run into the pre-registered holdout.
TO="$TO" HOLDOUT_LOCK="$HOLDOUT_LOCK" python3 - <<'PY' || exit 1
import json, os, sys
from datetime import datetime
lock = json.load(open(os.environ["HOLDOUT_LOCK"], encoding="utf-8"))
start = datetime.fromisoformat(lock["holdout_start"]).date()
to = datetime.strptime(os.environ["TO"], "%Y.%m.%d").date()
if to >= start:
    sys.exit(
        f"ERROR: TO={to} reaches the pre-registered holdout (starts {start}).\n"
        f"       {lock['holdout_rule']}\n"
        "       Pick an earlier TO, or evaluate the holdout deliberately and record it."
    )
PY

# --- Locate the install (same source of truth as 19-*.sh / fetch_data.py) ---
BROKER_DIRS_JSON="$REPO_ROOT/config/broker_install_dirs.json"
mapfile -t _INSTALL_DIRS < <(
  python3 - "$BROKER_DIRS_JSON" <<'PY'
import json, sys
from pathlib import Path
try:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception:
    data = {"_generic": "MetaTrader 5"}
preferred = [
    "Vantage International MT5",
    "FP Markets MT5 Terminal",
    "WSFmarkets MT5 Terminal",
    "FundedNext MT5 Terminal",
    "FTMO Global Markets MT5 Terminal",
    "MetaTrader 5",
]
dirs = [v.strip() for k, v in data.items()
        if isinstance(v, str) and v.strip() and (not k.startswith("_") or k == "_generic")]
ordered = [d for d in preferred if d in dirs]
ordered.extend(d for d in dirs if d not in ordered)
print("\n".join(ordered or preferred))
PY
)
MT5_DIR=""
for name in "${_INSTALL_DIRS[@]}"; do
  d="$WINEPREFIX/drive_c/Program Files/$name"
  if [[ -f "$d/terminal64.exe" ]]; then MT5_DIR="$d"; break; fi
done
if [[ -z "${MT5_DIR:-}" ]]; then
  t64="$(find_terminal64 2>/dev/null || true)"
  [[ -n "$t64" ]] && MT5_DIR="$(dirname "$t64")"
fi
[[ -n "${MT5_DIR:-}" && -f "$MT5_DIR/terminal64.exe" ]] || die "terminal64.exe not found in WINEPREFIX=$WINEPREFIX"

EXPERTS="$MT5_DIR/MQL5/Experts"
PRESETS="$MT5_DIR/MQL5/Profiles/Tester"
REPORTS="$MT5_DIR/reports"
COMMON_INI="$MT5_DIR/Config/common.ini"
CFG_BASENAME="renko_vendor_tester.ini"
CFG="$MT5_DIR/$CFG_BASENAME"

METAEDITOR=""
for cand in "$MT5_DIR/MetaEditor64.exe" "$MT5_DIR/metaeditor64.exe"; do
  [[ -f "$cand" ]] && METAEDITOR="$cand" && break
done
[[ -n "$METAEDITOR" ]] || die "MetaEditor64.exe missing"

mkdir -p "$EXPERTS" "$PRESETS" "$REPORTS" "$MT5_DIR/Tester" "$REPO_ROOT/results"

# --- Login / Server from common.ini or env (Login=0 yields "account not specified") ---
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
        k, v = (p.strip() for p in line.split("=", 1))
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

# --- Compile (vendored sources are copied verbatim; never edited in place) ---
if [[ "$SKIP_COMPILE" != "1" ]]; then
  cp -f "$REPO_ROOT/mql5/Experts/vendor/${EA_NAME}.mq5" "$EXPERTS/"
  info "Compiling ${EA_NAME}..."
  (
    cd "$EXPERTS"
    wine "$METAEDITOR" /compile:"${EA_NAME}.mq5" /log >/dev/null 2>&1 || true
  )
  sleep 2
  [[ -f "$EXPERTS/${EA_NAME}.ex5" ]] || die "compile failed — $EXPERTS/${EA_NAME}.log"
  info "Compile OK"
else
  [[ -f "$EXPERTS/${EA_NAME}.ex5" ]] || die "${EA_NAME}.ex5 missing"
fi

# --- .set (UTF-16LE) straight from the frozen charter ---
SET_NAME="${EA_NAME}_charter_v1.set"
SET_PATH="$PRESETS/$SET_NAME"
EA_KEY="$EA_KEY" CHARTER="$CHARTER" SET_PATH="$SET_PATH" python3 - <<'PY'
import json, os
from pathlib import Path

charter = json.loads(Path(os.environ["CHARTER"]).read_text(encoding="utf-8"))
rule = charter["rule"]
lots = charter["fixed"]["lots"]

if os.environ["EA_KEY"] == "adx":
    v = rule["vehicle_adx"]
    lines = [
        "; GDS Renko ADX Demo — parameters frozen by the charter, do not hand-edit",
        f"InpBrickSize={v['brick_size']}",
        f"InpADXPeriod={v['adx_period']}",
        f"InpADXThreshold={v['adx_threshold']}",
        f"InpMinDISeparation={v['min_di_separation']}",
        f"InpEntryRunBricks={v['entry_run_bricks']}",
        f"InpTakeProfitBricks={v['tp_bricks']}",
        f"InpStopLossBricks={v['sl_bricks']}",
        f"InpMaxHoldMinutes={v['max_hold_minutes']}",
        f"InpCooldownBricks={v['cooldown_bricks']}",
        f"InpMaxSpreadFraction={v['max_spread_fraction']}",
        f"InpLots={lots}",
    ]
else:
    b, r, m, s = (
        rule["vehicle_bb_breakout"],
        rule["vehicle_bb_reentry"],
        rule["vehicle_bb_midline"],
        rule["vehicle_bb_squeeze"],
    )
    lines = [
        "; GDS Renko Bollinger 4-Mode Demo — frozen by the charter, do not hand-edit",
        f"InpLots={lots}",
        "InpMaxPositions=4",
        "InpSkipOppositeSignals=true",
        "InpBreakoutEnabled=true",
        f"InpBreakoutBrickSize={b['brick_size']}",
        f"InpBreakoutBBPeriod={b['bb_period']}",
        f"InpBreakoutDeviation={b['deviation']}",
        f"InpBreakoutEntryRun={b['entry_run_bricks']}",
        f"InpBreakoutTP={b['tp_bricks']}",
        f"InpBreakoutSL={b['sl_bricks']}",
        f"InpBreakoutMaxHold={b['max_hold_minutes']}",
        f"InpBreakoutCooldown={b['cooldown_bricks']}",
        "InpReentryEnabled=true",
        f"InpReentryBrickSize={r['brick_size']}",
        f"InpReentryBBPeriod={r['bb_period']}",
        f"InpReentryDeviation={r['deviation']}",
        f"InpReentryEntryRun={r['entry_run_bricks']}",
        f"InpReentryTP={r['tp_bricks']}",
        f"InpReentrySL={r['sl_bricks']}",
        f"InpReentryMaxHold={r['max_hold_minutes']}",
        f"InpReentryCooldown={r['cooldown_bricks']}",
        "InpMidlineEnabled=true",
        f"InpMidlineBrickSize={m['brick_size']}",
        f"InpMidlineBBPeriod={m['bb_period']}",
        f"InpMidlineDeviation={m['deviation']}",
        f"InpMidlineEntryRun={m['entry_run_bricks']}",
        f"InpMidlineTP={m['tp_bricks']}",
        f"InpMidlineSL={m['sl_bricks']}",
        f"InpMidlineMaxHold={m['max_hold_minutes']}",
        f"InpMidlineCooldown={m['cooldown_bricks']}",
        "InpSqueezeEnabled=true",
        f"InpSqueezeBrickSize={s['brick_size']}",
        f"InpSqueezeBBPeriod={s['bb_period']}",
        f"InpSqueezeDeviation={s['deviation']}",
        f"InpSqueezeMaxWidth={s['squeeze_max_width_bricks']}",
        f"InpSqueezeEntryRun={s['entry_run_bricks']}",
        f"InpSqueezeTP={s['tp_bricks']}",
        f"InpSqueezeSL={s['sl_bricks']}",
        f"InpSqueezeMaxHold={s['max_hold_minutes']}",
        f"InpSqueezeCooldown={s['cooldown_bricks']}",
    ]

text = "\r\n".join(lines) + "\r\n"
Path(os.environ["SET_PATH"]).write_bytes(b"\xff\xfe" + text.encode("utf-16-le"))
print(f"wrote {os.environ['SET_PATH']} ({len(lines) - 1} inputs)")
PY

# --- tester.ini: ASCII + CRLF, bare Expert name, AllowLiveTrading=0 ---
STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_REL="reports/renko_${EA_KEY}_${SYMBOL}_${PERIOD}_${STAMP}"
EA_NAME="$EA_NAME" SET_NAME="$SET_NAME" SYMBOL="$SYMBOL" PERIOD="$PERIOD" FROM="$FROM" TO="$TO" \
DEPOSIT="$DEPOSIT" MODEL="$MODEL" LEVERAGE="$LEVERAGE" REPORT_REL="$REPORT_REL" CFG="$CFG" \
MT5_LOGIN="$MT5_LOGIN" MT5_SERVER="$MT5_SERVER" MT5_PASSWORD="${MT5_PASSWORD:-}" \
python3 - <<'PY'
import os
from pathlib import Path

pw = os.environ.get("MT5_PASSWORD", "").strip()
pass_line = f"Password={pw}\n" if pw else ""
body = f"""[Common]
Login={os.environ["MT5_LOGIN"]}
{pass_line}Server={os.environ["MT5_SERVER"]}
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
Expert={os.environ["EA_NAME"]}
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
print(f"wrote {os.environ['CFG']} ({Path(os.environ['CFG']).stat().st_size} bytes)")
PY

# --- One terminal64 per install ---
kill_terminals() {
  local pids
  pids=$(ps -eo pid,cmd | awk '/terminal64\.exe/ && !/awk/ {print $1}')
  [[ -z "${pids// }" ]] && { info "No terminal64 running"; return 0; }
  info "Stopping terminal64: $pids"
  for p in $pids; do kill -TERM "$p" 2>/dev/null || true; done
  sleep 3
  for p in $pids; do ps -p "$p" >/dev/null 2>&1 && kill -KILL "$p" 2>/dev/null || true; done
  sleep 1
}
if [[ "$KILL_EXISTING" == "1" ]]; then
  kill_terminals
elif ps -eo cmd | grep -q '[t]erminal64.exe'; then
  die "terminal64 running — close it or KILL_EXISTING=1"
fi

# --- Run ---
export WINEDEBUG="${WINEDEBUG:--all}"
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-d3d11=b;d3d12=b;dxgi=b}"
LOG="/tmp/mt5-renko-tester.log"
: >"$LOG"
info "Launch: wine terminal64 /portable /config:$CFG_BASENAME"
info "$EA_NAME $SYMBOL $PERIOD $FROM → $TO model=$MODEL (real ticks) timeout=${TIMEOUT_SEC}s"

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

# --- Parse ---
DAY="$(date +%Y%m%d)"
AGENT_LOG=""
for cand in "$MT5_DIR/Tester/Agent-127.0.0.1-3001/logs/${DAY}.log" "$MT5_DIR/Tester/logs/${DAY}.log"; do
  [[ -f "$cand" ]] && AGENT_LOG="$cand"
done
SUMMARY="$REPO_ROOT/results/renko_vendor_headless_${EA_KEY}_${SYMBOL}_${PERIOD}_${STAMP}.md"

DAY="$DAY" MT5_DIR="$MT5_DIR" AGENT_LOG="$AGENT_LOG" SUMMARY="$SUMMARY" EA_NAME="$EA_NAME" \
SYMBOL="$SYMBOL" PERIOD="$PERIOD" FROM="$FROM" TO="$TO" RC="$rc" LOG="$LOG" MODEL="$MODEL" \
python3 - <<'PY'
import os, re
from pathlib import Path

mt5 = Path(os.environ["MT5_DIR"])
day = os.environ["DAY"]
agent = Path(os.environ.get("AGENT_LOG") or "")
summary = Path(os.environ["SUMMARY"])

def read_log(p: Path) -> str:
    if not p.is_file():
        return ""
    raw = p.read_bytes()
    if len(raw) >= 2 and (raw[:2] == b"\xff\xfe" or raw[1] == 0):
        return raw.decode("utf-16-le", "replace")
    return raw.decode("utf-8", "replace")

text = "\n".join(
    read_log(p)
    for p in (agent, mt5 / "Tester" / "logs" / f"{day}.log", mt5 / "logs" / f"{day}.log")
)

pats = [
    r"cannot load config[^\r\n]*",
    r"account is not specified[^\r\n]*",
    r"EX5 not found[^\r\n]*",
    r"tester not started[^\r\n]*",
    r"GDS Renko[^\r\n]*",
    r"final balance[^\r\n]*",
    r"total net profit[^\r\n]*",
    r"profit factor[^\r\n]*",
    r"total trades[^\r\n]*",
    r"shutdown with[^\r\n]*",
]
blocks = [(p, f[-6:]) for p in pats if (f := re.findall(p, text, flags=re.I))]

ok = bool(re.search(r"final balance|total net profit", text, re.I))
reports = sorted((mt5 / "reports").glob("renko_*"), key=lambda p: p.stat().st_mtime, reverse=True)[:8] \
    if (mt5 / "reports").is_dir() else []

md = [
    f"# Renko vendor headless test — {os.environ['EA_NAME']}\n\n",
    f"- Symbol/period: **{os.environ['SYMBOL']} {os.environ['PERIOD']}**\n",
    f"- Range: **{os.environ['FROM']} → {os.environ['TO']}** (holdout not reached)\n",
    f"- Tick model: **{os.environ['MODEL']}** (4 = every tick based on real ticks)\n",
    f"- Exit code: **{os.environ['RC']}**\n",
    f"- Status: **{'OK' if ok else 'FAILED/INCOMPLETE'}**\n",
    f"- Agent log: `{agent}`\n- Wine log: `{os.environ['LOG']}`\n\n",
    "> Offline research artifact. AllowLiveTrading=0. No orders were placed.\n\n## Journal\n",
]
if not blocks:
    md.append("_No markers — config may not have loaded or the tester did not start._\n")
for pat, found in blocks:
    md.append(f"### `{pat}`\n```\n" + "\n".join(found) + "\n```\n")
md.append("\n## Reports\n")
md.extend(f"- `{r}` ({r.stat().st_size} bytes)\n" for r in reports)
if not reports:
    md.append("_none_\n")

summary.write_text("".join(md))
print(f"wrote {summary}")
print("STATUS:", "OK" if ok else "INCOMPLETE")
raise SystemExit(0 if ok else 1)
PY

info "Summary: $SUMMARY"
info "Wine log: $LOG"
