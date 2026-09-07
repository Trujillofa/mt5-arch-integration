#!/usr/bin/env bash
# Compile Mt5ArchBridgeReadOnly.mq5 into a branded Wine tree.
# Default target: Alpha Capital (~/.mt5-alphacapital / ACG Markets MT5 Terminal).
# Does not load repo .env (that pins WSF). Does not copy DeskOrderBridge.mqh.
# Does not compile or attach the trading EA.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

BROKER="${1:-alphacapital}"
case "$BROKER" in
  alphacapital) ;;
  *)
    die "this installer is for alphacapital only (got $BROKER) — trading books stay on v1.25"
    ;;
esac

profile="$REPO_ROOT/config/brokers/${BROKER}.env"
[[ -f "$profile" ]] || die "missing $profile"
unset WINEPREFIX MT5_LOGIN MT5_SERVER MT5_TERMINAL_PATH MT5_PASSWORD || true
set -a
# shellcheck disable=SC1090
source "$profile"
set +a
export_wine_env

case "$(realpath "${WINEPREFIX}")" in
  *mt5-vantage*|*mt5-fpmarkets*|*mt5-exness*)
    die "refusing forbidden prefix $WINEPREFIX"
    ;;
  *mt5-alphacapital*) ;;
  *)
    die "refusing prefix $WINEPREFIX — readonly compile is Alpha-only"
    ;;
esac

require_cmd wine
term="$(find_terminal64)" || die "terminal64.exe not found under $WINEPREFIX"
case "$term" in
  *"/Program Files/MetaTrader 5/terminal64.exe")
    die "generic MetaQuotes tree is not the Alpha book"
    ;;
esac
term_dir="$(cd "$(dirname "$term")" && pwd)"
[[ "$(basename "$term_dir")" == "ACG Markets MT5 Terminal" ]] \
  || die "expected ACG Markets MT5 Terminal, got $(basename "$term_dir")"

SRC="$REPO_ROOT/mql5/Mt5ArchBridgeReadOnly.mq5"
EXPERTS="$term_dir/MQL5/Experts"
INCLUDE_DIR="$term_dir/MQL5/Include"
[[ -f "$SRC" ]] || die "missing $SRC"
mkdir -p "$EXPERTS" "$INCLUDE_DIR"

if grep -Eiq 'OrderSend|DeskOrderBridge|desk_live_order' "$SRC"; then
  die "$SRC must not mention OrderSend, DeskOrderBridge, or desk_live_order files"
fi

cp -f "$REPO_ROOT/mql5/Include/FxSymbolRegistry.mqh" "$INCLUDE_DIR/FxSymbolRegistry.mqh"
cp -f "$REPO_ROOT/mql5/Include/FileBridgeSnapshots.mqh" "$INCLUDE_DIR/FileBridgeSnapshots.mqh"
cp -f "$SRC" "$EXPERTS/Mt5ArchBridgeReadOnly.mq5"

if grep -Eiq 'OrderSend[[:space:]]*\(|DeskOrderBridge|desk_live_order' \
     "$INCLUDE_DIR/FileBridgeSnapshots.mqh"; then
  die "FileBridgeSnapshots.mqh must stay snapshot-only"
fi
if ! grep -q 'readonly=true' "$EXPERTS/Mt5ArchBridgeReadOnly.mq5"; then
  die "deployed RO EA missing readonly=true banner"
fi
if ! grep -q 'FileBridgeSnapshots.mqh' "$EXPERTS/Mt5ArchBridgeReadOnly.mq5"; then
  die "deployed RO EA missing FileBridgeSnapshots include"
fi

METAEDITOR=""
for cand in "$term_dir/MetaEditor64.exe" "$term_dir/metaeditor64.exe"; do
  if [[ -f "$cand" ]]; then METAEDITOR="$cand"; break; fi
done

EX5="$EXPERTS/Mt5ArchBridgeReadOnly.ex5"
LOG="$EXPERTS/Mt5ArchBridgeReadOnly.log"
if [[ -z "$METAEDITOR" ]]; then
  die "MetaEditor64.exe missing under $term_dir"
fi

info "Compiling Mt5ArchBridgeReadOnly into $EXPERTS"
rm -f "$EX5"
(
  cd "$EXPERTS"
  wine "$METAEDITOR" /compile:"Mt5ArchBridgeReadOnly.mq5" /log 2>/dev/null || true
) &
compile_pid=$!
for _ in $(seq 1 40); do
  if [[ -f "$EX5" ]]; then
    break
  fi
  sleep 0.5
done
wait "$compile_pid" 2>/dev/null || true

if [[ ! -f "$EX5" ]]; then
  [[ -f "$LOG" ]] && { info "compile log:"; iconv -f UTF-16 -t UTF-8 "$LOG" 2>/dev/null | tail -40 || tr -d '\000' <"$LOG" | tail -40; }
  die "ex5 not produced"
fi
if [[ "$EX5" -ot "$EXPERTS/Mt5ArchBridgeReadOnly.mq5" ]]; then
  [[ -f "$LOG" ]] && { info "compile log:"; iconv -f UTF-16 -t UTF-8 "$LOG" 2>/dev/null | tail -40 || tr -d '\000' <"$LOG" | tail -40; }
  die "ex5 is older than mq5 — compile failed"
fi

info "Compiled OK: $EX5 ($(stat -c%s "$EX5") bytes)"
echo "$EX5"
