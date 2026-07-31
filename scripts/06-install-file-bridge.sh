#!/usr/bin/env bash
# Install and compile Mt5ArchBridge.mq5 into the Wine MT5 Experts folder.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env
require_cmd wine

SRC="$REPO_ROOT/mql5/Mt5ArchBridge.mq5"
EXPERTS="$WINEPREFIX/drive_c/Program Files/MetaTrader 5/MQL5/Experts"
# Case can vary by installer (MetaEditor64.exe vs metaeditor64.exe)
METAEDITOR=""
for cand in \
  "$WINEPREFIX/drive_c/Program Files/MetaTrader 5/MetaEditor64.exe" \
  "$WINEPREFIX/drive_c/Program Files/MetaTrader 5/metaeditor64.exe"
do
  if [[ -f "$cand" ]]; then METAEDITOR="$cand"; break; fi
done

[[ -f "$SRC" ]] || die "missing $SRC"
[[ -d "$EXPERTS" ]] || die "Experts dir missing — install MT5 first"
[[ -n "$METAEDITOR" ]] || die "MetaEditor64.exe missing"

mkdir -p "$EXPERTS"
cp -f "$SRC" "$EXPERTS/Mt5ArchBridge.mq5"
info "Copied EA to $EXPERTS/Mt5ArchBridge.mq5"

info "Compiling with MetaEditor..."
# MetaEditor compile switches: /compile:<file> /log
wine "$METAEDITOR" /compile:"C:\\Program Files\\MetaTrader 5\\MQL5\\Experts\\Mt5ArchBridge.mq5" /log 2>/dev/null || true
sleep 2

EX5="$EXPERTS/Mt5ArchBridge.ex5"
LOG="$EXPERTS/Mt5ArchBridge.log"
if [[ -f "$EX5" ]]; then
  info "Compiled OK: $EX5 ($(stat -c%s "$EX5") bytes)"
else
  warn "ex5 not found yet — open MetaEditor and compile manually if needed"
  [[ -f "$LOG" ]] && { info "compile log:"; cat "$LOG" | tr -d '\000' | tail -30; }
fi

# Ensure output dir exists for EA
mkdir -p "$WINEPREFIX/drive_c/Program Files/MetaTrader 5/MQL5/Files/mt5_arch"/{orders_in,orders_out}

cat <<'EOF'

Next (in the MetaTrader 5 GUI):

  1. Click **Algo Trading** on the toolbar until it is GREEN
  2. Tools → Options → Expert Advisors:
       ☑ Allow algorithmic trading
       ☑ Allow DLL imports  (optional)
  3. Navigator → Expert Advisors → Mt5ArchBridge
     Drag onto any chart (e.g. EURUSD H1)
  4. Allow live trading in the EA dialog → OK
  5. Window → Tile Windows  (fixes large black empty chart area)

Then on Linux:

  export MT5_BACKEND=file
  uv run mt5-arch ping
  uv run mt5-arch account

EOF
