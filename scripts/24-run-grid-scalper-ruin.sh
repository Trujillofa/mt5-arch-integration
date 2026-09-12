#!/usr/bin/env bash
# Headless ruin study for Market 133466 Grid Scalper MA MT5 EA.
# Frozen lock: results/grid_scalper_ma_ruin_lock.md
# Prefix-scoped: kills ONLY $WINEPREFIX terminal64 (default ~/.mt5-fpmarkets).
# Never use scripts/19-run-htf-fib-backtest.sh for this (KILL_EXISTING=1 is host-wide).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

export WINEPREFIX="${WINEPREFIX:-$HOME/.mt5-fpmarkets}"
export_wine_env
export_wine_webview_env
require_cmd wine
require_cmd python3
require_wineprefix

allowed="$(readlink -f -- "$HOME/.mt5-fpmarkets")"
if [[ "$(readlink -f -- "$WINEPREFIX")" != "$allowed" ]]; then
  die "refusing $WINEPREFIX — ruin study allowlist is ~/.mt5-fpmarkets only"
fi

FROM="${FROM:-2024.03.01}"
TO="${TO:-2024.03.31}"
SYMBOL="${SYMBOL:-XAUUSD.r}"
PERIOD="${PERIOD:-M15}"
DEPOSIT="${DEPOSIT:-10000}"
LEVERAGE="${LEVERAGE:-1:100}"
MODEL="${MODEL:-4}"
DUMP_ONLY="${DUMP_ONLY:-0}"
TIMEOUT_SEC="${TIMEOUT_SEC:-900}"
SRC_PREFIX="${SRC_PREFIX:-$HOME/.mt5-vantage}"
EA_NAME="Grid Scalper MA MT5 EA"
TESTER_LOG="/tmp/mt5-grid-scalper-ruin.log"

REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MT5_DIR=""
for name in "FP Markets MT5 Terminal" "Vantage International MT5" "MetaTrader 5"; do
  d="$WINEPREFIX/drive_c/Program Files/$name"
  if [[ -f "$d/terminal64.exe" ]]; then MT5_DIR="$d"; break; fi
done
[[ -n "$MT5_DIR" ]] || die "terminal64.exe not found under $WINEPREFIX"

SRC_MT5=""
for name in "Vantage International MT5" "FP Markets MT5 Terminal"; do
  d="$SRC_PREFIX/drive_c/Program Files/$name"
  if [[ -f "$d/MQL5/Experts/Market/${EA_NAME}.ex5" ]]; then SRC_MT5="$d"; break; fi
done
[[ -n "$SRC_MT5" ]] || die "Market .ex5 missing under $SRC_PREFIX — download it first"

mkdir -p "$MT5_DIR/MQL5/Experts/Market" "$MT5_DIR/MQL5/Profiles/Tester" "$MT5_DIR/reports" \
  "$REPO_ROOT/results"
cp -f "$SRC_MT5/MQL5/Experts/Market/${EA_NAME}.ex5" "$MT5_DIR/MQL5/Experts/Market/"
if [[ -f "$SRC_MT5/Config/community.ini" ]]; then
  cp -f "$SRC_MT5/Config/community.ini" "$MT5_DIR/Config/community.ini"
fi
SRC_COMM="$SRC_PREFIX/drive_c/users/$USER/AppData/Roaming/MetaQuotes/Terminal/Community/mql5.community.dat"
DST_COMM="$WINEPREFIX/drive_c/users/$USER/AppData/Roaming/MetaQuotes/Terminal/Community/mql5.community.dat"
if [[ -f "$SRC_COMM" ]]; then
  mkdir -p "$(dirname "$DST_COMM")"
  cp -f "$SRC_COMM" "$DST_COMM"
fi
if [[ -f "$SRC_MT5/Bases/mql5.market.personal.dat" ]]; then
  mkdir -p "$MT5_DIR/Bases"
  cp -f "$SRC_MT5/Bases/mql5.market.personal.dat" "$MT5_DIR/Bases/mql5.market.personal.dat"
fi

eval "$(
  COMMON_INI="$MT5_DIR/Config/common.ini" python3 - <<'PY'
import os
from pathlib import Path
common = Path(os.environ["COMMON_INI"])
login = server = ""
raw = common.read_bytes()
text = raw.decode("utf-16-le", "replace") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or (len(raw) > 2 and raw[1] == 0) else raw.decode("utf-8", "replace")
for line in text.replace("\r", "").split("\n"):
    if "=" not in line:
        continue
    k, v = line.split("=", 1)
    k, v = k.strip(), v.strip()
    if k == "Login" and v and v != "0":
        login = v
    if k == "Server" and v:
        server = v
if not login or not server:
    raise SystemExit("ERROR: Login/Server missing in common.ini")
print(f"export MT5_LOGIN='{login}'")
print(f"export MT5_SERVER='{server}'")
PY
)"
info "Login=$MT5_LOGIN Server=$MT5_SERVER Expert=Market\\$EA_NAME $SYMBOL $PERIOD $FROM→$TO model=$MODEL"

write_cfg() {
  local cfg="$1" set_name="$2" from="$3" to="$4" model="$5" report="$6"
  SET_NAME="$set_name" SYMBOL="$SYMBOL" PERIOD="$PERIOD" FROM="$from" TO="$to" \
  DEPOSIT="$DEPOSIT" MODEL="$model" LEVERAGE="$LEVERAGE" REPORT_REL="$report" \
  CFG="$cfg" MT5_LOGIN="$MT5_LOGIN" MT5_SERVER="$MT5_SERVER" python3 - <<'PY'
from pathlib import Path
import os
set_name = os.environ["SET_NAME"]
expert_line = "Expert=Market\\Grid Scalper MA MT5 EA\r\n"
params = f"ExpertParameters={set_name}\r\n" if set_name else ""
body = f"""[Common]
Login={os.environ["MT5_LOGIN"]}
Server={os.environ["MT5_SERVER"]}
ProxyEnable=0
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
{expert_line}{params}Symbol={os.environ["SYMBOL"]}
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
print(f"wrote {os.environ['CFG']}")
PY
}

assert_prefix_only() {
  info "FP-only pids (must not include Vantage):"
  list_terminal64_pids || true
  python3 - <<'PY'
import os, sys
from pathlib import Path
sys.path.insert(0, os.environ.get("PYTHONPATH", "").split(":")[0] if False else "")
sys.path.insert(0, str(Path(os.environ["REPO_SRC"])))
from mt5_arch.hypr_geometry import list_terminal64_pids
fp = set(list_terminal64_pids(wineprefix=os.environ["WINEPREFIX"]))
vant = set(list_terminal64_pids(wineprefix=str(Path.home() / ".mt5-vantage")))
if fp & vant:
    raise SystemExit(f"refusing kill: overlap {fp & vant}")
print(f"  vantage still {sorted(vant)}")
PY
}

run_tester() {
  local cfg_base="$1" timeout_sec="$2"
  REPO_SRC="$REPO_ROOT/src" assert_prefix_only
  info "Stopping terminal64 in $WINEPREFIX only"
  kill_terminal64_processes
  export WINEDEBUG="${WINEDEBUG:--all}"
  export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-d3d11=b;d3d12=b;dxgi=b}"
  export_wine_webview_env
  export DISPLAY="${DISPLAY:-:0}"
  unset WAYLAND_DISPLAY || true
  : >"$TESTER_LOG"
  (
    cd "$MT5_DIR"
    timeout "$timeout_sec" wine ./terminal64.exe /portable /config:"$cfg_base" >>"$TESTER_LOG" 2>&1
  ) || true
  info "tester finished (log $TESTER_LOG)"
}

scale_set() {
  python3 - "$1" "$2" <<'PY'
from pathlib import Path
import sys
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
raw = src.read_bytes()
text = raw.decode("utf-16-le") if raw[:2] == b"\xff\xfe" else raw.decode("utf-8", "replace")
# Only scale locked *point* fields. Leave percents (recovery 30, geometry 50) alone.
out = []
scaled = 0
for line in text.splitlines():
    if line.startswith(";") or "=" not in line:
        out.append(line)
        continue
    key, _, rest = line.partition("=")
    val = rest.split("||", 1)[0]
    blob = f"{key} {rest}".lower()
    new = None
    if val == "11000":
        new = "1100"
    elif val == "100" and any(s in blob for s in ("extra", "trail", "activate", "min", "profit")) and "percent" not in blob and "%" not in blob:
        new = "10"
    elif val == "50" and any(s in blob for s in ("breakeven", "break even", "be")):
        new = "5"
    elif val == "30" and any(s in blob for s in ("trail",)) and "recover" not in blob and "percent" not in blob and "%" not in blob:
        new = "3"
    if new is not None:
        rest = new + rest[len(val):]
        print(f"scale {key.strip()} {val}->{new}")
        scaled += 1
    out.append(f"{key}={rest}")
body = "\r\n".join(out) + "\r\n"
dst.write_bytes(b"\xff\xfe" + body.encode("utf-16-le"))
print(f"wrote {dst} scaled={scaled}")
if scaled == 0:
    print("warning: no point fields matched — inspect the dumped .set before a full run")
PY
}

find_dumped_set() {
  python3 - "$MT5_DIR" "$EA_NAME" <<'PY'
from pathlib import Path
import sys
mt5 = Path(sys.argv[1])
cands = []
roots = [mt5 / "MQL5/Profiles/Tester", mt5 / "Tester", mt5 / "MQL5"]
for root in roots:
    if not root.is_dir():
        continue
    for p in root.rglob("*.set"):
        name = p.name.lower()
        if "grid" in name or "scalper" in name:
            cands.append(p)
cands = sorted(set(cands), key=lambda p: p.stat().st_mtime, reverse=True)
print(cands[0] if cands else "")
PY
}

list_recent_tester_files() {
  python3 - "$MT5_DIR" <<'PY'
from pathlib import Path
import sys
mt5 = Path(sys.argv[1])
files = []
for root in (mt5 / "Tester", mt5 / "logs", mt5 / "MQL5/Profiles/Tester", mt5 / "reports"):
    if not root.exists():
        continue
    for p in root.rglob("*"):
        if p.is_file():
            files.append(p)
files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
for p in files[:25]:
    print(f"{p.stat().st_mtime:.0f} {p.stat().st_size:8d} {p}")
PY
}

CFG1="$MT5_DIR/grid_scalper_dump.ini"
write_cfg "$CFG1" "" "2024.03.01" "2024.03.04" "0" "reports/grid_scalper_dump"
run_tester "grid_scalper_dump.ini" 300

DUMPED="$(find_dumped_set)"
if [[ -z "$DUMPED" ]]; then
  warn "no dumped .set — recent tester files:"
  list_recent_tester_files || true
  die "EA did not write a .set (Community license? EX5 not loaded?)"
fi
info "dumped $DUMPED"
cp -f "$DUMPED" "$REPO_ROOT/results/grid_scalper_ma_defaults_3digit.set"
SCALED="$MT5_DIR/MQL5/Profiles/Tester/grid_scalper_ma_2digit.set"
scale_set "$DUMPED" "$SCALED"
cp -f "$SCALED" "$REPO_ROOT/results/grid_scalper_ma_2digit.set"

if [[ "$DUMP_ONLY" == "1" ]]; then
  info "DUMP_ONLY=1 — stopping after scale"
  WINEPREFIX="$WINEPREFIX" "$SCRIPT_DIR/04-start-terminal.sh" --background || true
  exit 0
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT="reports/grid_scalper_ruin_${SYMBOL}_${PERIOD}_${STAMP}"
CFG2="$MT5_DIR/grid_scalper_ruin.ini"
write_cfg "$CFG2" "grid_scalper_ma_2digit.set" "$FROM" "$TO" "$MODEL" "$REPORT"
run_tester "grid_scalper_ruin.ini" "$TIMEOUT_SEC"

if [[ ! -f "$MT5_DIR/${REPORT}.htm" && ! -f "$MT5_DIR/${REPORT}.html" ]]; then
  if [[ "$MODEL" != "0" ]]; then
    warn "no report for model=$MODEL — fallback model=0"
    MODEL=0
    write_cfg "$CFG2" "grid_scalper_ma_2digit.set" "$FROM" "$TO" "0" "$REPORT"
    run_tester "grid_scalper_ruin.ini" 600
  fi
fi

python3 - "$MT5_DIR" "$REPORT" "$REPO_ROOT/results" "$FROM" "$TO" "$SYMBOL" "$MODEL" <<'PY'
from pathlib import Path
import re, sys
from datetime import date

mt5 = Path(sys.argv[1])
rel = sys.argv[2]
outdir = Path(sys.argv[3])
fr, to, symbol, model = sys.argv[4:8]
cands = list(mt5.glob(rel + "*")) + list((mt5 / "reports").glob("grid_scalper_ruin*"))
cands = sorted({p.resolve() for p in cands if p.is_file()}, key=lambda p: p.stat().st_mtime, reverse=True)
print("reports:", [str(p) for p in cands[:8]])
html = ""
for p in cands:
    if p.suffix.lower() in {".htm", ".html"}:
        raw = p.read_bytes()
        html = raw.decode("utf-16-le", "replace") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or (len(raw) > 2 and raw[1] == 0) else raw.decode("utf-8", "replace")
        dest = outdir / p.name
        dest.write_bytes(raw)
        print("copied", dest)
        break
log = ""
day = date.today().strftime("%Y%m%d")
for cand in [
    mt5 / "Tester" / "logs" / f"{day}.log",
    mt5 / "logs" / f"{day}.log",
    *sorted((mt5 / "Tester").glob("Agent-*/logs/" + day + ".log")),
]:
    if cand.is_file():
        raw = cand.read_bytes()
        log += raw.decode("utf-16-le", "replace") if raw[:2] == b"\xff\xfe" or (len(raw) > 2 and raw[1] == 0) else raw.decode("utf-8", "replace")
md = outdir / "grid_scalper_ma_ruin_2024-03_ex5.md"
lines = [
    "# Grid Scalper MA MT5 — official .ex5 ruin run\n\n",
    "Not a `family_id`. `promote=no`. Lock: `results/grid_scalper_ma_ruin_lock.md`.\n\n",
    f"- Symbol **{symbol}** {fr} → {to} model={model}\n",
    "- Expert `Market\\\\Grid Scalper MA MT5 EA` 2-digit scaled .set\n\n",
    "## Tester HTML markers\n",
]
for pat in [
    r"Total net profit[^\n]*",
    r"Maximal drawdown[^\n]*",
    r"Profit factor[^\n]*",
    r"Total trades[^\n]*",
    r"Margin Level[^\n]*",
    r"stop out[^\n]*",
]:
    found = re.findall(pat, html, flags=re.I)
    if found:
        lines.append(f"- `{found[-1][:200]}`\n")
if not html:
    lines.append("_No HTML report. Check Community license / EX5 load._\n")
fail = re.findall(
    r"EX5 not found[^\n]*|requires active MQL5[^\n]*|cannot load[^\n]*|tester not started[^\n]*",
    log,
    flags=re.I,
)
if fail:
    lines.append("\n## Journal failures\n")
    for x in fail[-8:]:
        lines.append(f"- `{x[:200]}`\n")
md.write_text("".join(lines), encoding="utf-8")
print("wrote", md)
PY

info "bringing FP GUI back on workspace 11"
WINEPREFIX="$WINEPREFIX" "$SCRIPT_DIR/04-start-terminal.sh" --background || true
info "done — read results/grid_scalper_ma_ruin_2024-03_ex5.md"
