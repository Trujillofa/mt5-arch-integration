#!/usr/bin/env bash
# Catch an MT5 freeze at onset instead of hours later.
#
# Every capture taken by hand so far arrived 40+ minutes after the fact and showed
# only the steady state. What is missing is the first seconds: what the terminal was
# doing as it went into the fault, and what the MT5 log recorded immediately before.
#
# So: sample each terminal's main thread, and the moment it stops behaving like a UI
# thread, run the capture against that pid alone.
#
# Two freeze modes, both observed, with opposite CPU signatures:
#
#   spin      main thread pinned at ~100% of one core, wchan 0 (spinning in userspace).
#             The SIGSEGV livelock -- 3 of the 4 freezes on 2026-08-11/12, and
#             FP Markets again on 2026-08-13 09:56.
#
#   deadlock  main thread at *zero* CPU, wchan futex_do_wait. Wine's win32u lock
#             taken AB-BA: the chart/history thread holds the user/GDI lock and blocks
#             in a cross-thread SendMessage (NtUserMessageCall -> wine_server_call)
#             waiting for the UI thread to pump it, while the UI thread sits in its
#             paint path (NtUserDispatchMessage -> NtGdiSelectBitmap ->
#             pthread_mutex_lock) waiting for that same lock. Vantage, 2026-08-13
#             09:26. Neither thread burns CPU, nothing is logged, and the terminal
#             keeps trading -- network threads stay up, positions stay open, the
#             bridge EA keeps writing snapshots. Only the UI is dead.
#
# Measure the MAIN thread, not the process. A terminal runs ~19 threads; summing them
# both dilutes a spinning UI thread below the threshold and lets busy history/tick
# threads push a perfectly healthy terminal over it.
#
# Telling deadlock apart from an idle terminal is the whole difficulty, and CPU alone
# cannot do it. wchan can: a healthy UI thread with nothing to do waits for messages
# in ntsync_schedule (or poll), never in futex_do_wait -- that wchan means contention
# on a raw pthread mutex, which on this path only happens under the win32u lock.
# Measured baseline, 2026-08-13 10:04, over 10s:
#
#   vantage   (deadlocked)  main 0/1000 jiffies   wchan futex_do_wait
#   fpmarkets (spinning)    main 998/1000         wchan 0
#   exness    (healthy)     main 15/1000          wchan ntsync_schedule.isra.0
#
# The healthy terminal is idle by any CPU measure and still nowhere near either
# signature. Deadlock is additionally confirmed across consecutive runs before firing,
# so a merely slow mutex wait cannot trip it.
#
# Recovery is OFF by default. A frozen UI with live network/bridge is safer than a
# blind restart that can lose unsaved chart state or race a dying wineserver. Set
# MT5_WATCH_RESTART=1 only if you accept that trade-off (still captures first).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
# shellcheck source=/dev/null
source "$REPO_ROOT/scripts/lib.sh"
load_dotenv

SAMPLE="${MT5_WATCH_SAMPLE:-5}"        # seconds of CPU sampling
THRESHOLD="${MT5_WATCH_THRESHOLD:-80}" # percent of one core that counts as spinning
STRIKES="${MT5_WATCH_STRIKES:-3}"      # consecutive deadlock observations before firing
RESTART="${MT5_WATCH_RESTART:-0}"      # 1 = restart that prefix after capture (opt-in)
STATE_DIR="${XDG_RUNTIME_DIR:-/tmp}/mt5-freeze-watch"
HZ="$(getconf CLK_TCK 2>/dev/null || echo 100)"
mkdir -p "$STATE_DIR"

# utime / stime for the main thread alone. comm is parenthesised and can contain
# spaces (Wine names this thread "main", but do not rely on that), so strip through
# the closing paren first; fields 14/15 of the original numbering land at 12/13 once
# state has become field 1. Prints "utime stime".
main_times() {
  awk '{ r=$0; sub(/^[^)]*\) /, "", r); split(r, f, " "); print f[12]+0, f[13]+0 }' \
    "/proc/$1/task/$1/stat" 2>/dev/null
}

# Desktop + optional webhook. Never fatal: notification failure must not skip capture.
notify_freeze() {
  local mode="$1" pid="$2" prefix="$3" detail="$4"
  local broker msg
  broker="$(basename "${prefix:-unknown}")"
  msg="MT5 FREEZE(${mode}) ${broker} pid=${pid} — ${detail}"

  if command -v notify-send >/dev/null 2>&1; then
    DISPLAY="${DISPLAY:-:0}" notify-send -u critical -a mt5-freeze-watch \
      "MT5 freeze (${mode})" "${broker}  pid ${pid}\n${detail}" 2>/dev/null || true
  fi

  # Optional webhook. Default body is plain text (ntfy.sh, etc.). Set
  # MT5_WATCH_WEBHOOK_JSON=1 for a JSON object POST instead.
  if [[ -n "${MT5_WATCH_WEBHOOK_URL:-}" ]] && command -v curl >/dev/null 2>&1; then
    if [[ "${MT5_WATCH_WEBHOOK_JSON:-0}" == "1" ]]; then
      curl -fsS -m 8 -X POST "$MT5_WATCH_WEBHOOK_URL" \
        -H 'Content-Type: application/json' \
        --data-binary "$(MODE="$mode" PID="$pid" PREFIX="${prefix:-}" DETAIL="$detail" MSG="$msg" python3 -c '
import json, os
print(json.dumps({
  "text": os.environ["MSG"],
  "mode": os.environ["MODE"],
  "pid": int(os.environ["PID"]),
  "prefix": os.environ["PREFIX"],
  "detail": os.environ["DETAIL"],
}))
')" >/dev/null 2>&1 || true
    else
      curl -fsS -m 8 -X POST "$MT5_WATCH_WEBHOOK_URL" \
        -H 'Content-Type: text/plain' \
        --data-binary "$msg" >/dev/null 2>&1 || true
    fi
  fi
}

# Match the command line: Wine names the main thread "main", so a comm-based scan
# finds nothing and would report every terminal as absent.
mapfile -t PIDS < <(mt5_terminal_pids || true)
[[ ${#PIDS[@]} -eq 0 ]] && exit 0

declare -A BEFORE_U=() BEFORE_S=()
for pid in "${PIDS[@]}"; do
  [[ -d "/proc/$pid" ]] || continue
  read -r bu bs < <(main_times "$pid") || continue
  BEFORE_U[$pid]="$bu"
  BEFORE_S[$pid]="$bs"
done

sleep "$SAMPLE"

for pid in "${PIDS[@]}"; do
  [[ -d "/proc/$pid" ]] || continue
  [[ -n "${BEFORE_U[$pid]:-}" ]] || continue
  read -r au as < <(main_times "$pid") || continue
  bu="${BEFORE_U[$pid]}"
  bs="${BEFORE_S[$pid]}"
  udelta=$(( au - bu ))
  sdelta=$(( as - bs ))
  delta=$(( udelta + sdelta ))
  pct=$(( delta * 100 / (SAMPLE * HZ) ))
  wchan="$(cat "/proc/$pid/task/$pid/wchan" 2>/dev/null || echo '?')"

  # Keyed by pid+starttime so a recycled pid is treated as a new process.
  starttime="$(awk '{ r=$0; sub(/^[^)]*\) /, "", r); split(r, f, " "); print f[20] }' \
    "/proc/$pid/stat" 2>/dev/null)"
  key="$STATE_DIR/${pid}.${starttime}"

  mode=""
  # Spin needs sys-time majority: busy healthy paint is user-dominant and used to
  # false-trip a bare pct>=THRESHOLD gate (and miss sys-skewed freezes that sat
  # just under an older 2× skew check — FP 2026-08-14).
  if (( pct >= THRESHOLD && sdelta > udelta )); then
    mode="spin"
    detail="cpu=${pct}% sys=${sdelta} user=${udelta} wchan=${wchan}"
  elif (( delta == 0 )) && [[ "$wchan" == futex_do_wait ]]; then
    # Count consecutive observations rather than firing on the first one. A capture
    # costs 8s of strace against a live trading terminal, so make it earn that.
    strikes=$(( $(cat "$key.strikes" 2>/dev/null || echo 0) + 1 ))
    echo "$strikes" >"$key.strikes"
    (( strikes < STRIKES )) && continue
    mode="deadlock"
    detail="main thread 0 jiffies in futex_do_wait across ${strikes} runs"
  else
    # Healthy: clear the strike count, and re-arm the capture. Dropping the capture
    # marker here is what fixes the FP Markets miss on 2026-08-13 -- that terminal
    # froze, recovered, and froze again, and the second freeze was invisible because
    # a marker from the first (2026-08-12 16:00) suppressed it for the whole 22h
    # process lifetime. One capture per *episode*, not per process.
    rm -f "$key.strikes" "$key".captured.*
    continue
  fi

  # One capture per episode. Without this the timer re-captures the same frozen
  # terminal every minute and buries the onset evidence under duplicates.
  marker="$key.captured.$mode"
  [[ -e "$marker" ]] && continue
  : >"$marker"

  prefix="$( { tr '\0' '\n' <"/proc/$pid/environ"; } 2>/dev/null | sed -n 's/^WINEPREFIX=//p' | head -1)"
  logger -t mt5-freeze-watch "FREEZE(${mode}) pid=$pid prefix=${prefix:-?} ${detail} — capturing"
  echo "$(date '+%Y-%m-%d %H:%M:%S')  FREEZE(${mode}) pid=$pid ${prefix:-?} ${detail} — capturing"
  notify_freeze "$mode" "$pid" "${prefix:-}" "$detail"
  "$HERE/capture-mt5-freeze.sh" 8 "$pid" || true

  # Opt-in only. Default stays capture+notify: UI-dead but trading-alive is safer
  # than discarding chart edits or racing wineserver mid-shutdown.
  if [[ "$RESTART" == "1" && -n "${prefix:-}" ]]; then
    logger -t mt5-freeze-watch "RESTART requested for ${prefix} after FREEZE(${mode})"
    echo "$(date '+%Y-%m-%d %H:%M:%S')  RESTART ${prefix} (MT5_WATCH_RESTART=1)"
    WINEPREFIX="$prefix" "$REPO_ROOT/scripts/07-restart-terminal.sh" || true
  fi
done

# Drop state for processes that no longer exist, so a restarted terminal is watched
# again rather than being permanently suppressed by a stale marker.
for marker in "$STATE_DIR"/*; do
  [[ -e "$marker" ]] || continue
  mpid="$(basename "$marker")"; mpid="${mpid%%.*}"
  [[ -d "/proc/$mpid" ]] || rm -f "$marker"
done
