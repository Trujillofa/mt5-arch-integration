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
TERM="$(find_terminal64 || true)"
if [[ -n "$TERM" ]]; then
  TERM_DIR="$(cd "$(dirname "$TERM")" && pwd)"
else
  TERM_DIR="$WINEPREFIX/drive_c/Program Files/MetaTrader 5"
fi
EXPERTS="$TERM_DIR/MQL5/Experts"
# Case can vary by installer (MetaEditor64.exe vs metaeditor64.exe)
METAEDITOR=""
for cand in \
  "$TERM_DIR/MetaEditor64.exe" \
  "$TERM_DIR/metaeditor64.exe"
do
  if [[ -f "$cand" ]]; then METAEDITOR="$cand"; break; fi
done

[[ -f "$SRC" ]] || die "missing $SRC"
# Create Experts dir if prefix exists but tree incomplete
if [[ ! -d "$EXPERTS" ]]; then
  if [[ -d "$TERM_DIR" ]]; then
    mkdir -p "$EXPERTS"
  else
    die "Experts dir missing — install MT5 first (./scripts/mt5linux-arch.sh or 02-install-mt5.sh)"
  fi
fi

INCLUDE_DIR="$TERM_DIR/MQL5/Include"
mkdir -p "$EXPERTS" "$INCLUDE_DIR"
cp -f "$REPO_ROOT/mql5/Include/FxSymbolRegistry.mqh" \
  "$INCLUDE_DIR/FxSymbolRegistry.mqh"
cp -f "$REPO_ROOT/mql5/Include/FileBridgeSnapshots.mqh" \
  "$INCLUDE_DIR/FileBridgeSnapshots.mqh"
cp -f "$REPO_ROOT/mql5/Include/DeskOrderBridge.mqh" \
  "$INCLUDE_DIR/DeskOrderBridge.mqh"
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
if ! grep -q 'FileBridgeSnapshots.mqh' "$EXPERTS/Mt5ArchBridge.mq5"; then
  die "deployed EA missing FileBridgeSnapshots.mqh include"
fi
if ! grep -q 'FxResolveSymbol' "$INCLUDE_DIR/FileBridgeSnapshots.mqh"; then
  die "FileBridgeSnapshots.mqh missing FxResolveSymbol (explicit registry)"
fi
if ! grep -q 'IsEffectivelyConnected' "$INCLUDE_DIR/FileBridgeSnapshots.mqh"; then
  die "FileBridgeSnapshots.mqh missing IsEffectivelyConnected (Wine TERMINAL_CONNECTED fallback)"
fi
if ! grep -q 'terminal_connected' "$INCLUDE_DIR/FileBridgeSnapshots.mqh"; then
  die "FileBridgeSnapshots.mqh missing terminal_connected account field"
fi
if ! grep -q 'DeskOrderProcessIfRequested' "$EXPERTS/Mt5ArchBridge.mq5"; then
  die "deployed EA missing DeskOrderProcessIfRequested (in-process desk limits)"
fi
if ! grep -q 'TRADE_ACTION_SLTP' "$INCLUDE_DIR/DeskOrderBridge.mqh"; then
  die "DeskOrderBridge.mqh missing TRADE_ACTION_SLTP (position modify)"
fi
if ! grep -q 'WriteOrders' "$INCLUDE_DIR/FileBridgeSnapshots.mqh"; then
  die "FileBridgeSnapshots.mqh missing WriteOrders (OrdersTotal dump)"
fi
if ! grep -q 'orders.json' "$INCLUDE_DIR/FileBridgeSnapshots.mqh"; then
  die "FileBridgeSnapshots.mqh missing orders.json"
fi
if [[ ! -f "$INCLUDE_DIR/DeskOrderBridge.mqh" ]]; then
  die "DeskOrderBridge.mqh missing from Include/"
fi
if [[ ! -f "$INCLUDE_DIR/FileBridgeSnapshots.mqh" ]]; then
  die "FileBridgeSnapshots.mqh missing from Include/"
fi
info "Deployed EA has timer + OnTick + connection fields"

EX5="$EXPERTS/Mt5ArchBridge.ex5"
LOG="$EXPERTS/Mt5ArchBridge.log"
if [[ -z "$METAEDITOR" ]]; then
  warn "MetaEditor64.exe missing — source deployed; compile with F7 when MetaEditor is available"
else
  info "Compiling with MetaEditor..."
  # Drop stale binary so we never report an old ex5 as success
  rm -f "$EX5"
  (
    cd "$EXPERTS"
    wine "$METAEDITOR" /compile:"Mt5ArchBridge.mq5" /log 2>/dev/null || true
  ) &
  compile_pid=$!
  for _ in $(seq 1 40); do
    if [[ -f "$EX5" ]]; then
      break
    fi
    sleep 0.5
  done
  wait "$compile_pid" 2>/dev/null || true
fi

if [[ -f "$EX5" ]]; then
  # Reject binaries older than the source we just deployed
  if [[ "$EX5" -ot "$EXPERTS/Mt5ArchBridge.mq5" ]]; then
    warn "ex5 is older than mq5 — compile may have failed; open MetaEditor and F7"
    [[ -f "$LOG" ]] && { info "compile log:"; iconv -f UTF-16 -t UTF-8 "$LOG" 2>/dev/null | tail -20 || tr -d '\000' <"$LOG" | tail -20; }
  else
    info "Compiled OK: $EX5 ($(stat -c%s "$EX5") bytes)"
  fi
else
  warn "ex5 not found yet — open MetaEditor and compile manually (F7) if needed"
  [[ -f "$LOG" ]] && { info "compile log:"; iconv -f UTF-16 -t UTF-8 "$LOG" 2>/dev/null | tail -30 || tr -d '\000' <"$LOG" | tail -30; }
fi
# Ensure output dir exists for EA
mkdir -p "$TERM_DIR/MQL5/Files/mt5_arch"/{orders_in,orders_out}

cat <<'EOF'

Next (in the MetaTrader 5 GUI):

  1. Click **Algo Trading** on the toolbar until it is GREEN
  2. Tools → Options → Expert Advisors:
       ☑ Allow algorithmic trading
       ☑ Allow DLL imports  (optional)
  3. Navigator → Expert Advisors → Mt5ArchBridge
     Drag onto any chart (e.g. EURUSD H1)
     Set InpBroker=vantage|fpmarkets|exness|wsf (required).
     Empty/wrong InpBroker fails OnInit; Python then sees a stale heartbeat.
  4. Allow live trading in the EA dialog → OK
  5. Window → Tile Windows  (fixes large black empty chart area)

Then on Linux:

  export MT5_BACKEND=file
  uv run mt5-arch ping
  uv run mt5-arch account

EOF
