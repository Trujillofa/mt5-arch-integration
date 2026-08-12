#!/usr/bin/env bash
# Catch an MT5 freeze at onset instead of hours later.
#
# Every capture taken by hand so far arrived 40+ minutes after the fact and showed
# only the steady state. What is missing is the first seconds: what the terminal was
# doing as it went into the fault, and what the MT5 log recorded immediately before.
#
# So: sample each terminal's CPU, and the moment one is pinned at ~a full core, run
# the capture against that pid alone.
#
# Detects the SIGSEGV livelock (3 of the 4 freezes seen on 2026-08-11/12): main thread
# spinning, wchan 0, ~100% of one core. It does NOT detect the X11 deadlock mode
# (0% CPU, wchan futex_do_wait), which is indistinguishable from an idle terminal by
# CPU alone -- naming that one needs a liveness probe, not a threshold.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAMPLE="${MT5_WATCH_SAMPLE:-5}"        # seconds of CPU sampling
THRESHOLD="${MT5_WATCH_THRESHOLD:-80}" # percent of one core that counts as spinning
STATE_DIR="${XDG_RUNTIME_DIR:-/tmp}/mt5-freeze-watch"
mkdir -p "$STATE_DIR"

cpu_jiffies() { awk '{u+=$14; s+=$15} END{print u+s+0}' /proc/"$1"/task/*/stat 2>/dev/null; }

# Match the command line: Wine names the main thread "main", so a comm-based scan
# finds nothing and would report every terminal as absent.
mapfile -t PIDS < <(pgrep -f 'terminal64\.exe' || true)
[[ ${#PIDS[@]} -eq 0 ]] && exit 0

declare -A BEFORE=()
for pid in "${PIDS[@]}"; do
  [[ -d "/proc/$pid" ]] && BEFORE[$pid]="$(cpu_jiffies "$pid")"
done

sleep "$SAMPLE"

for pid in "${PIDS[@]}"; do
  [[ -d "/proc/$pid" ]] || continue
  before="${BEFORE[$pid]:-}"
  [[ -z "$before" ]] && continue
  after="$(cpu_jiffies "$pid")"
  pct=$(( (after - before) * 100 / (SAMPLE * 100) ))
  (( pct < THRESHOLD )) && continue

  # One capture per process lifetime. Without this the timer re-captures the same
  # frozen terminal every minute and buries the onset evidence under duplicates.
  # Keyed by pid+starttime so a recycled pid is still treated as a new process.
  starttime="$(awk '{print $22}' "/proc/$pid/stat" 2>/dev/null)"
  marker="$STATE_DIR/${pid}.${starttime}"
  [[ -e "$marker" ]] && continue
  : >"$marker"

  prefix="$( { tr '\0' '\n' <"/proc/$pid/environ"; } 2>/dev/null | sed -n 's/^WINEPREFIX=//p' | head -1)"
  logger -t mt5-freeze-watch "FREEZE pid=$pid prefix=${prefix:-?} cpu=${pct}% of one core — capturing"
  echo "$(date '+%Y-%m-%d %H:%M:%S')  FREEZE pid=$pid ${prefix:-?} cpu=${pct}% — capturing"
  "$HERE/capture-mt5-freeze.sh" 8 "$pid" || true
done

# Drop markers for processes that no longer exist, so a restarted terminal is watched
# again rather than being permanently suppressed by a stale marker.
for marker in "$STATE_DIR"/*; do
  [[ -e "$marker" ]] || continue
  mpid="$(basename "$marker")"; mpid="${mpid%%.*}"
  [[ -d "/proc/$mpid" ]] || rm -f "$marker"
done
