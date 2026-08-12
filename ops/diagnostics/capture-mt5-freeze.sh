#!/usr/bin/env bash
# Capture evidence from a frozen MetaTrader terminal, before restarting it.
#
# The 2026-08-11 freeze looked like this: the main thread pinned at ~100% of one
# core, wchan 0 (spinning in userspace, not blocked), ~65% system time, and no
# terminal log entries for hours. Two terminals on different brokers and separate
# Wine prefixes burned CPU at the same rate to within one jiffy, which points at
# the Wine/XWayland layer rather than any strategy or feed.
#
# Restarting destroys that evidence, so run this first.
#
# Usage:  ./ops/diagnostics/capture-mt5-freeze.sh [seconds]     (default 10)
#
# Needs sudo: kernel.yama.ptrace_scope is 1, so strace cannot attach to a process
# that is not its own descendant without CAP_SYS_PTRACE.
# Deliberately no `set -e`: this is a best-effort evidence collector run against a
# sick process. A grep that matches nothing or an strace that cannot attach must not
# abort the run and throw away the evidence already gathered.
set -uo pipefail

SECS="${1:-10}"
OUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/captures"
STAMP="$(date '+%Y%m%d-%H%M%S')"
mkdir -p "$OUT_DIR"

command -v strace >/dev/null 2>&1 || { echo "error: strace not installed (pacman -S strace)" >&2; exit 1; }

# Wine names the main thread "main", so /proc/<pid>/comm does NOT say terminal64.
# Match the command line instead — a comm-based scan silently finds nothing.
mapfile -t PIDS < <(pgrep -f 'terminal64\.exe' || true)
if [[ ${#PIDS[@]} -eq 0 ]]; then
  echo "No MetaTrader terminal running."
  exit 0
fi

cpu_jiffies() { awk '{u+=$14; s+=$15} END{print u+0, s+0}' /proc/"$1"/task/*/stat 2>/dev/null; }

for PID in "${PIDS[@]}"; do
  [[ -d "/proc/$PID" ]] || continue
  PREFIX="$(tr '\0' '\n' <"/proc/$PID/environ" 2>/dev/null | sed -n 's/^WINEPREFIX=//p')"
  TAG="$(basename "${PREFIX:-unknown}")"
  REPORT="$OUT_DIR/${STAMP}-${TAG}-${PID}.txt"

  {
    echo "=== MT5 freeze capture ==="
    echo "when:      $(date '+%Y-%m-%d %H:%M:%S %Z')"
    echo "pid:       $PID"
    echo "prefix:    ${PREFIX:-?}"
    echo "cmdline:   $(tr '\0' ' ' <"/proc/$PID/cmdline" 2>/dev/null)"
    echo "state:     $(sed -n 's/^State:\t//p' "/proc/$PID/status" 2>/dev/null)"
    echo "threads:   $(sed -n 's/^Threads:\t//p' "/proc/$PID/status" 2>/dev/null)"
    echo "wchan:     $(cat "/proc/$PID/wchan" 2>/dev/null)  (0 = spinning in userspace)"

    echo
    echo "=== CPU over ${SECS}s (1 core == $((SECS * 100)) jiffies) ==="
    read -r u1 s1 < <(cpu_jiffies "$PID")
    declare -A T0=()
    for t in /proc/"$PID"/task/*; do
      T0[${t##*/}]="$(awk '{print $14+$15}' "$t/stat" 2>/dev/null || echo 0)"
    done
    sleep "$SECS"
    read -r u2 s2 < <(cpu_jiffies "$PID")
    total=$(( (u2 - u1) + (s2 - s1) ))
    echo "user: $((u2 - u1))  sys: $((s2 - s1))  total: ${total} / $((SECS * 100)) jiffies per core"
    echo "  (~100% of one core with sys dominant is the frozen signature)"

    echo
    echo "=== busiest threads ==="
    for t in /proc/"$PID"/task/*; do
      tid="${t##*/}"
      now="$(awk '{print $14+$15}' "$t/stat" 2>/dev/null || echo 0)"
      d=$(( now - ${T0[$tid]:-0} ))
      # Guard with if, not (( )) && ... : a false (( )) exits 1 and set -e kills the run.
      if [[ "$d" -gt 5 ]]; then
        printf '  tid %-8s %5d jiffies  comm=%-16s wchan=%s\n' \
          "$tid" "$d" "$(cat "$t/comm" 2>/dev/null)" "$(cat "$t/wchan" 2>/dev/null)"
      fi
    done | sort -k3 -rn | head -8

    echo
    echo "=== syscall profile (${SECS}s) ==="
    echo "compare against ops/diagnostics/strace-baseline-healthy-fpmarkets.txt"
    sudo timeout "$SECS" strace -c -f -p "$PID" -o /tmp/mt5-strace-c.$$ 2>/dev/null || true
    grep -vE 'attached|detached' "/tmp/mt5-strace-c.$$" 2>/dev/null | head -20
    sudo rm -f "/tmp/mt5-strace-c.$$"

    echo
    echo "=== raw syscall sample, main thread only (2s) ==="
    sudo timeout 2 strace -p "$PID" -o /tmp/mt5-strace-raw.$$ 2>/dev/null || true
    grep -vE 'attached|detached' "/tmp/mt5-strace-raw.$$" 2>/dev/null | head -40
    sudo rm -f "/tmp/mt5-strace-raw.$$"

    echo
    echo "=== backtrace (gdb) ==="
    # Use gdb, NEVER winedbg. winedbg attaches as a *Windows* debugger, and a Windows
    # debuggee is killed when its debugger exits: attaching it to the frozen terminal on
    # 2026-08-12 terminated the process, losing both the stack and the unsaved charts.
    # gdb attaches via ptrace and detaches cleanly, leaving the terminal running.
    #
    # SIGSEGV must be passed through, not trapped: the freeze IS a SIGSEGV storm, so a
    # gdb that stops on every fault never reaches a prompt.
    GDB_OUT="/tmp/mt5-gdb.$$"
    if command -v gdb >/dev/null 2>&1; then
      sudo timeout 45 gdb -p "$PID" -batch \
        -ex "set confirm off" \
        -ex "set pagination off" \
        -ex "handle SIGSEGV nostop noprint pass" \
        -ex "info registers rip" \
        -ex "bt 25" \
        -ex "thread apply all bt 6" \
        -ex "detach" >"$GDB_OUT" 2>&1
      grep -vE '^\[|^warning:|Reading symbols' "$GDB_OUT" | head -70
    else
      echo "gdb not installed (pacman -S gdb)"
    fi

    echo
    echo "=== faulting module ==="
    # Resolve every address in the backtrace against the process map. Wine PE code has
    # no symbols, so gdb prints "?? ()" — the module name is the whole answer, and
    # matching it by eye across 40 map lines is where this gets abandoned.
    if [[ -s "$GDB_OUT" ]]; then
      grep -oE '0x[0-9a-f]{6,16}' "$GDB_OUT" | sort -u | while read -r addr; do
        awk -v a="$addr" '
          {
            split($1, r, "-")
            lo = strtonum("0x" r[1]); hi = strtonum("0x" r[2]); t = strtonum(a)
            if (t >= lo && t < hi) {
              path = ""
              for (i = 6; i <= NF; i++) path = path (i > 6 ? " " : "") $i
              if (path != "") { print "  " a "  ->  " path; exit }
            }
          }' "/proc/$PID/maps" 2>/dev/null
      done | sort -u -k3 | head -25
    fi
    sudo rm -f "$GDB_OUT"

    echo
    echo "=== terminal log tail (gap here == when it stopped making progress) ==="
    if [[ -n "$PREFIX" ]]; then
      LOG="$(find "$PREFIX/drive_c/Program Files" -maxdepth 3 -path '*/logs/*.log' -printf '%T@ %p\n' \
              2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)"
      if [[ -n "$LOG" ]]; then
        echo "log:  $LOG"
        echo "last written: $(stat -c '%y' "$LOG" | cut -c1-19)   (now $(date '+%Y-%m-%d %H:%M:%S'))"
        tail -12 "$LOG" | tr -d '\0' | cut -c1-160
      fi
    fi
  } >"$REPORT" 2>&1

  echo "captured: $REPORT"
done

echo
echo "Review the captures, then restart with:"
echo "  ./scripts/07-restart-terminal.sh --fullscreen"
echo "Note: a spinning main thread may ignore the graceful close, in which case"
echo "stop_terminal_gracefully escalates to SIGKILL and unsaved chart edits are lost."
