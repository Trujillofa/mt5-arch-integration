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
# Create Experts dir if prefix exists but tree incomplete
if [[ ! -d "$EXPERTS" ]]; then
  if [[ -d "$WINEPREFIX/drive_c/Program Files/MetaTrader 5" ]]; then
    mkdir -p "$EXPERTS"
  else
    die "Experts dir missing — install MT5 first (./scripts/mt5linux-arch.sh or 02-install-mt5.sh)"
  fi
fi

mkdir -p "$EXPERTS"
cp -f "$SRC" "$EXPERTS/Mt5ArchBridge.mq5"
info "Copied EA source to $EXPERTS/Mt5ArchBridge.mq5"
# Verify deploy (gating for install path)
[[ -f "$EXPERTS/Mt5ArchBridge.mq5" ]] || die "copy failed"
if ! grep -q 'EventSetTimer' "$EXPERTS/Mt5ArchBridge.mq5"; then
  die "deployed EA missing EventSetTimer (second-based refresh)"
fi
if ! grep -q 'OnTick' "$EXPERTS/Mt5ArchBridge.mq5"; then
  die "deployed EA missing OnTick backup path"
fi
if ! grep -q 'terminal_connected' "$EXPERTS/Mt5ArchBridge.mq5"; then
  die "deployed EA missing terminal_connected account field"
fi
info "Deployed EA has timer + OnTick + connection fields"

if [[ -z "$METAEDITOR" ]]; then
  warn "MetaEditor64.exe missing — source deployed; compile with F7 when MetaEditor is available"
else
  info "Compiling with MetaEditor..."
  wine "$METAEDITOR" /compile:"C:\\Program Files\\MetaTrader 5\\MQL5\\Experts\\Mt5ArchBridge.mq5" /log 2>/dev/null || true
  sleep 2
fi

EX5="$EXPERTS/Mt5ArchBridge.ex5"
LOG="$EXPERTS/Mt5ArchBridge.log"
if [[ -f "$EX5" ]]; then
  info "Compiled OK: $EX5 ($(stat -c%s "$EX5") bytes)"
else
  warn "ex5 not found yet — open MetaEditor and compile manually (F7) if needed"
  [[ -f "$LOG" ]] && { info "compile log:"; tr -d '\000' <"$LOG" | tail -30; }
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
