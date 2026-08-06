#!/usr/bin/env bash
# Export XAUUSD M15+H1 from Wine MT5 via ExportXauHistory.mq5 StartUp.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
load_dotenv
export_wine_env
require_cmd wine
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MT5_DIR=""
for d in \
  "$WINEPREFIX/drive_c/Program Files/Vantage International MT5" \
  "$WINEPREFIX/drive_c/Program Files/MetaTrader 5"
do [[ -f "$d/terminal64.exe" ]] && MT5_DIR="$d" && break; done
[[ -n "$MT5_DIR" ]] || die "terminal64 not found"
mkdir -p "$MT5_DIR/MQL5/Scripts"
cp -f "$REPO_ROOT/mql5/Scripts/ExportXauHistory.mq5" "$MT5_DIR/MQL5/Scripts/"
ME="$MT5_DIR/MetaEditor64.exe"
( cd "$MT5_DIR/MQL5/Scripts" && wine "$ME" /compile:"ExportXauHistory.mq5" /log >/dev/null 2>&1 || true )
[[ -f "$MT5_DIR/MQL5/Scripts/ExportXauHistory.ex5" ]] || die "compile failed"
pids=$(ps -eo pid,cmd | awk '/terminal64\.exe/ && !/awk/ {print $1}')
for p in $pids; do kill -TERM "$p" 2>/dev/null || true; done
sleep 2
for p in $pids; do ps -p "$p" >/dev/null 2>&1 && kill -KILL "$p" 2>/dev/null || true; done
eval "$(python3 - <<PY
from pathlib import Path
raw = Path("$MT5_DIR/Config/common.ini").read_bytes()
text = raw.decode("utf-16-le", "replace")
login=server=""
for line in text.replace("\\r","").split("\\n"):
    if line.startswith("Login="): login=line.split("=",1)[1].strip()
    if line.startswith("Server="): server=line.split("=",1)[1].strip()
print(f"LOGIN={login!r}")
print(f"SERVER={server!r}")
PY
)"
# fix eval - use export properly
LOGIN=$(python3 -c "
from pathlib import Path
raw=Path('$MT5_DIR/Config/common.ini').read_bytes()
text=raw.decode('utf-16-le','replace')
for line in text.replace(chr(13),'').split(chr(10)):
  if line.startswith('Login='): print(line.split('=',1)[1].strip())
")
SERVER=$(python3 -c "
from pathlib import Path
raw=Path('$MT5_DIR/Config/common.ini').read_bytes()
text=raw.decode('utf-16-le','replace')
for line in text.replace(chr(13),'').split(chr(10)):
  if line.startswith('Server='): print(line.split('=',1)[1].strip())
")
python3 -c "
from pathlib import Path
text='''[Common]
Login=$LOGIN
Server=$SERVER
ProxyEnable=0
KeepPrivate=1
NewsEnable=0
CertInstall=1
[Charts]
MaxBars=100000
PreloadCharts=1
[Experts]
AllowLiveTrading=0
Enabled=1
[StartUp]
Script=ExportXauHistory
Symbol=XAUUSD
Period=H1
ShutdownTerminal=1
'''.replace(chr(10), chr(13)+chr(10))
Path('$MT5_DIR/export_xau.ini').write_bytes(text.encode('ascii'))
print('ini ok')
"
info "Running export (timeout 120s)..."
cd "$MT5_DIR"
export WINEDEBUG=-all WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-d3d11=b;d3d12=b;dxgi=b}"
timeout 120 wine ./terminal64.exe /portable /config:export_xau.ini || true
OUT="$MT5_DIR/MQL5/Files/xauusd_mt5_export.csv"
[[ -f "$OUT" ]] || die "export missing"
info "OK $OUT ($(stat -c%s "$OUT") bytes)"
wc -l "$OUT"
info "Next: python fetch_data.py"
