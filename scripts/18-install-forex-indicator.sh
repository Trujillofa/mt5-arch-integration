#!/usr/bin/env bash
# Install all custom MQL5 indicators + EA + includes into Wine MT5 prefixes.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "${ROOT}/scripts/lib.sh" 2>/dev/null || true

if [[ -f "${ROOT}/config/local.paths" ]]; then
  # shellcheck disable=SC1091
  source "${ROOT}/config/local.paths"
fi

WINEPREFIX="${WINEPREFIX:-${HOME}/.mt5}"
export WINEPREFIX

CANDIDATES=(
  "${WINEPREFIX}/drive_c/Program Files/MetaTrader 5/MQL5"
  "${WINEPREFIX}/drive_c/Program Files/WSFmarkets MT5 Terminal/MQL5"
  "${WINEPREFIX}/drive_c/Program Files/FP Markets MT5 Terminal/MQL5"
  "${WINEPREFIX}/drive_c/Program Files/Vantage International MT5/MQL5"
  "${WINEPREFIX}/drive_c/Program Files/MetaTrader 5 EXNESS/MQL5"
  "${HOME}/.mt5/drive_c/Program Files/MetaTrader 5/MQL5"
  "${HOME}/.mt5-wsf/drive_c/Program Files/WSFmarkets MT5 Terminal/MQL5"
  "${HOME}/.mt5-fpmarkets/drive_c/Program Files/FP Markets MT5 Terminal/MQL5"
  "${HOME}/.mt5-vantage/drive_c/Program Files/Vantage International MT5/MQL5"
  "${HOME}/.mt5-exness/drive_c/Program Files/MetaTrader 5 EXNESS/MQL5"
)

SRC_INC=(
  "${ROOT}/mql5/Include/ForexUtils.mqh"
  "${ROOT}/mql5/Include/FxSymbolRegistry.mqh"
  "${ROOT}/mql5/Include/IndexSessionUtils.mqh"
  "${ROOT}/mql5/Include/IndexM5Export.mqh"
)
SRC_IND=(
  "${ROOT}/mql5/Indicators/ForexIndicatorTemplate.mq5"
  "${ROOT}/mql5/Indicators/ForexHtfPivotsFib.mq5"
  "${ROOT}/mql5/Indicators/BtcTrendPullback.mq5"
  "${ROOT}/mql5/Indicators/UsIndexSessionScalp.mq5"
)
SRC_EA=(
  "${ROOT}/mql5/Experts/ForexSignalLogger.mq5"
  "${ROOT}/mql5/Experts/ForexHtfFibTester.mq5"
  "${ROOT}/mql5/Experts/TradeTransactionJournal.mq5"
  "${ROOT}/mql5/Mt5ArchBridge.mq5"
)
SRC_SCRIPTS=(
  "${ROOT}/mql5/Scripts/ExportHtfFibParityFixture.mq5"
  "${ROOT}/mql5/Scripts/ExportSymbolCapabilities.mq5"
  "${ROOT}/mql5/Scripts/ExportSymbolSyncAudit.mq5"
  "${ROOT}/mql5/Scripts/ExportXauHistory.mq5"
  "${ROOT}/mql5/Scripts/ExportInstrumentHistory.mq5"
  "${ROOT}/mql5/Scripts/ExportUsIndexM5.mq5"
)
# Runtime data (no recompile needed — regenerate with scripts/tpl_to_sr_levels.py)
SRC_FILES=(
  "${ROOT}/mql5/Files/forex_sr_levels.csv"
)
SRC_PRESETS=(
  "${ROOT}/mql5/Presets/ForexSignalLogger-UsIndexSessionScalp.set"
)

for inc in "${SRC_INC[@]}"; do
  if [[ ! -f "${inc}" ]]; then
    echo "ERROR: missing ${inc}" >&2
    exit 1
  fi
done

for f in "${SRC_FILES[@]}"; do
  if [[ ! -f "${f}" ]]; then
    echo "ERROR: missing ${f} (regenerate: python3 scripts/tpl_to_sr_levels.py)" >&2
    exit 1
  fi
done

installed=0
declare -A SEEN=()
for mql5 in "${CANDIDATES[@]}"; do
  [[ -d "${mql5}" ]] || continue
  real="$(readlink -f "${mql5}" 2>/dev/null || echo "${mql5}")"
  [[ -n "${SEEN[$real]+x}" ]] && continue
  SEEN[$real]=1

  mkdir -p "${mql5}/Indicators" "${mql5}/Include" "${mql5}/Experts" "${mql5}/Scripts" "${mql5}/Files" "${mql5}/Presets"
  for inc in "${SRC_INC[@]}"; do
    cp -v "${inc}" "${mql5}/Include/$(basename "${inc}")"
  done
  if [[ -f "${ROOT}/config/symbols/registry.json" ]]; then
    cp -v "${ROOT}/config/symbols/registry.json" "${mql5}/Files/symbol_registry.json"
  fi
  for f in "${SRC_FILES[@]}"; do
    [[ -f "${f}" ]] && cp -v "${f}" "${mql5}/Files/"
  done
  for f in "${SRC_IND[@]}"; do
    [[ -f "${f}" ]] && cp -v "${f}" "${mql5}/Indicators/"
  done
  for f in "${SRC_EA[@]}"; do
    if [[ -f "${f}" ]]; then
      base="$(basename "${f}")"
      # Bridge lives as EA in Experts (and historically Advisors) — keep Experts
      cp -v "${f}" "${mql5}/Experts/${base}"
    fi
  done
  for f in "${SRC_PRESETS[@]}"; do
    [[ -f "${f}" ]] && cp -v "${f}" "${mql5}/Presets/"
  done
  for f in "${SRC_SCRIPTS[@]}"; do
    [[ -f "${f}" ]] && cp -v "${f}" "${mql5}/Scripts/"
  done
  echo "Installed → ${mql5}"
  installed=$((installed + 1))
done

if [[ "${installed}" -eq 0 ]]; then
  echo "ERROR: no MT5 MQL5 directory found." >&2
  exit 1
fi

# Also stage runtime data in Common\Files: the Strategy Tester agent sandbox does not
# see the terminal's MQL5\Files, and the indicator falls back to FILE_COMMON.
for prefix in "${WINEPREFIX}" "${HOME}"/.mt5 "${HOME}"/.mt5-*; do
  common="${prefix}/drive_c/users/${USER}/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
  [[ -d "${common}" ]] || continue
  for f in "${SRC_FILES[@]}"; do
    [[ -f "${f}" ]] && cp -v "${f}" "${common}/"
  done
done

cat <<'EOF'

Next steps:
  1. MetaEditor (F4) → compile (F7):
       Include/ForexUtils.mqh          (auto via includes)
       Include/FxSymbolRegistry.mqh    (auto via includes)
       Include/IndexSessionUtils.mqh   (auto via includes)
       Indicators/ForexHtfPivotsFib.mq5     ← FX/gold primary
       Indicators/BtcTrendPullback.mq5     ← BTCUSD primary
       Indicators/UsIndexSessionScalp.mq5  ← US30/US100 M5 scalp
       Indicators/ForexIndicatorTemplate.mq5
       Experts/ForexSignalLogger.mq5        ← optional log-only EA
       Experts/TradeTransactionJournal.mq5  ← optional read-only trade-id journal
       Scripts/ExportHtfFibParityFixture.mq5 ← optional MQL5↔Python dump
       Scripts/ExportSymbolCapabilities.mq5  ← optional broker-symbol dump
       Scripts/ExportSymbolSyncAudit.mq5     ← optional H1 calendar / spread audit
       Scripts/ExportUsIndexM5.mq5           ← US100/US30 M5 dump (does not kill terminal)
  2. FX/gold H1: ForexHtfPivotsFib
     BTCUSD H1:  BtcTrendPullback
     US30/US100 M5: UsIndexSessionScalp
  3. Optional: Experts → ForexSignalLogger (Algo Trading green)
       FX:  InpIndicatorName=ForexHtfPivotsFib  buffer 8
       Template: buffer 9
       BTC: InpIndicatorName=BtcTrendPullback   buffer 7  MaxSpreadPips=0
       US index: InpIndicatorName=UsIndexSessionScalp buffer 8  MaxSpreadPips=0
       preset: Presets/ForexSignalLogger-UsIndexSessionScalp.set
       — logs signals only, never orders
  4. CSV logs: MQL5/Files/forex_signals/
     Trade-id journal (optional): Experts → TradeTransactionJournal
       InpBroker required; writes MQL5/Files/mt5_arch/journal/<session_id>/ (ids only, never orders)
  5. S/R levels: MQL5/Files/forex_sr_levels.csv (yellow=HIGH white=MED blue=LOW)
       re-export .tpl zones -> python3 scripts/tpl_to_sr_levels.py -> rerun this
       script -> refresh the chart. No recompile needed.
  6. When attaching Mt5ArchBridge, set InpBroker=vantage|fpmarkets|exness|wsf.
     A failed OnInit (empty/wrong InpBroker) surfaces to Python as a stale heartbeat.
EOF
