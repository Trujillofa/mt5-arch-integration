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

SRC_INC="${ROOT}/mql5/Include/ForexUtils.mqh"
SRC_IND=(
  "${ROOT}/mql5/Indicators/ForexIndicatorTemplate.mq5"
  "${ROOT}/mql5/Indicators/ForexHtfPivotsFib.mq5"
  "${ROOT}/mql5/Indicators/BtcTrendPullback.mq5"
)
SRC_EA=(
  "${ROOT}/mql5/Experts/ForexSignalLogger.mq5"
  "${ROOT}/mql5/Experts/ForexHtfFibTester.mq5"
  "${ROOT}/mql5/Mt5ArchBridge.mq5"
)
# Runtime data (no recompile needed — regenerate with scripts/tpl_to_sr_levels.py)
SRC_FILES=(
  "${ROOT}/mql5/Files/forex_sr_levels.csv"
)

if [[ ! -f "${SRC_INC}" ]]; then
  echo "ERROR: missing ${SRC_INC}" >&2
  exit 1
fi

installed=0
declare -A SEEN=()
for mql5 in "${CANDIDATES[@]}"; do
  [[ -d "${mql5}" ]] || continue
  real="$(readlink -f "${mql5}" 2>/dev/null || echo "${mql5}")"
  [[ -n "${SEEN[$real]+x}" ]] && continue
  SEEN[$real]=1

  mkdir -p "${mql5}/Indicators" "${mql5}/Include" "${mql5}/Experts" "${mql5}/Files"
  cp -v "${SRC_INC}" "${mql5}/Include/ForexUtils.mqh"
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
       Indicators/ForexHtfPivotsFib.mq5     ← FX/gold primary
       Indicators/BtcTrendPullback.mq5     ← BTCUSD primary
       Indicators/ForexIndicatorTemplate.mq5
       Experts/ForexSignalLogger.mq5        ← optional log-only EA
  2. FX/gold H1: ForexHtfPivotsFib
     BTCUSD H1:  BtcTrendPullback
  3. Optional: Experts → ForexSignalLogger (Algo Trading green)
       FX:  InpIndicatorName=ForexHtfPivotsFib  buffer 8
       Template: buffer 9
       BTC: InpIndicatorName=BtcTrendPullback   buffer 7  MaxSpreadPips=0
       — logs signals only, never orders
  4. CSV logs: MQL5/Files/forex_signals/
  5. S/R levels: MQL5/Files/forex_sr_levels.csv (yellow=HIGH white=MED blue=LOW)
       re-export .tpl zones -> python3 scripts/tpl_to_sr_levels.py -> rerun this
       script -> refresh the chart. No recompile needed.
EOF
