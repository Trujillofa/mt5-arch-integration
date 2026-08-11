#!/usr/bin/env bash
# Export XAUUSD/EURUSD/GBPUSD H1 (+ optional M15) with per-bar spread from Wine Vantage MT5.
# Phase-0 multi-instrument data readiness — no strategy scoring.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
load_dotenv
export_wine_env
require_cmd wine
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SYMBOLS="${SYMBOLS:-XAUUSD,EURUSD,GBPUSD}"
MONTHS="${MONTHS:-60}"
TFS="${TFS:-H1}"   # research lane primary is H1; set TFS=H1,M15 if needed
TIMEOUT_S="${TIMEOUT_S:-300}"

MT5_DIR=""
for d in \
  "$WINEPREFIX/drive_c/Program Files/Vantage International MT5" \
  "$WINEPREFIX/drive_c/Program Files/MetaTrader 5"
do
  [[ -f "$d/terminal64.exe" ]] && MT5_DIR="$d" && break
done
[[ -n "$MT5_DIR" ]] || die "terminal64 not found under WINEPREFIX=$WINEPREFIX"

mkdir -p "$MT5_DIR/MQL5/Scripts" "$MT5_DIR/MQL5/Files/mt5_arch"
cp -f "$REPO_ROOT/mql5/Scripts/ExportInstrumentHistory.mq5" "$MT5_DIR/MQL5/Scripts/"
ME="$MT5_DIR/MetaEditor64.exe"
info "Compiling ExportInstrumentHistory.mq5..."
( cd "$MT5_DIR/MQL5/Scripts" && wine "$ME" /compile:"ExportInstrumentHistory.mq5" /log >/dev/null 2>&1 || true )
[[ -f "$MT5_DIR/MQL5/Scripts/ExportInstrumentHistory.ex5" ]] || die "compile failed — open MetaEditor log"

# Kill existing terminal (one process at a time under Wine)
pids=$(ps -eo pid,cmd | awk '/terminal64\.exe/ && !/awk/ {print $1}')
for p in $pids; do kill -TERM "$p" 2>/dev/null || true; done
sleep 2
for p in $pids; do ps -p "$p" >/dev/null 2>&1 && kill -KILL "$p" 2>/dev/null || true; done

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
info "Login=$LOGIN Server=$SERVER"

# Write .set inputs for the script (UTF-16LE required by tester/scripts often;
# StartUp Script= runs with defaults unless we bake defaults into mq5 inputs —
# we pass via script inputs file if present; otherwise mq5 defaults cover us.)
python3 - <<PY
from pathlib import Path
mt5 = Path(r"$MT5_DIR")
# Startup ini (ASCII CRLF)
text = f"""[Common]
Login={'$LOGIN'}
Server={'$SERVER'}
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
Script=ExportInstrumentHistory
Symbol=XAUUSD
Period=H1
ShutdownTerminal=1
""".replace("\n", "\r\n")
(mt5 / "export_instruments.ini").write_bytes(text.encode("ascii"))
print("ini ok")
# Optional .set for script inputs (UTF-16LE)
set_body = f"""InpSymbols={'$SYMBOLS'}
InpMonths={'$MONTHS'}
InpTfs={'$TFS'}
InpOutDir=mt5_arch
"""
# MT5 .set is often UTF-16LE with BOM
(mt5 / "MQL5/Scripts/ExportInstrumentHistory.set").write_bytes(
    "\ufeff".encode("utf-16-le") + set_body.encode("utf-16-le")
)
print("set ok")
PY

info "Running export (timeout ${TIMEOUT_S}s) — may download history from server..."
cd "$MT5_DIR"
export WINEDEBUG=-all WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-d3d11=b;d3d12=b;dxgi=b}"
# Note: StartUp Script does not always apply .set; defaults in mq5 cover XAU/EUR/GBP.
timeout "$TIMEOUT_S" wine ./terminal64.exe /portable /config:export_instruments.ini || true

OUT_DIR="$MT5_DIR/MQL5/Files/mt5_arch"
info "Export artifacts in $OUT_DIR:"
ls -la "$OUT_DIR"/history_*.csv "$OUT_DIR"/symbol_meta_*.csv 2>/dev/null || true
missing=0
IFS=',' read -ra SYMS <<< "$SYMBOLS"
for s in "${SYMS[@]}"; do
  s=$(echo "$s" | tr -d ' ')
  f="$OUT_DIR/history_${s}.csv"
  if [[ -f "$f" ]]; then
    info "OK $f ($(stat -c%s "$f") bytes, $(wc -l < "$f") lines)"
  else
    warn "MISSING $f"
    missing=1
  fi
done
[[ "$missing" -eq 0 ]] || die "one or more symbol exports missing"
info "Next: python3 scripts/build_multi_instrument_data_readiness.py"
