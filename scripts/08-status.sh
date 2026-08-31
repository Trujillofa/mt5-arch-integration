#!/usr/bin/env bash
# Status: MT5 process, window, bridge freshness, quick account peek.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env

BRIDGE="${MT5_BRIDGE_DIR:-$WINEPREFIX/drive_c/Program Files/MetaTrader 5/MQL5/Files/mt5_arch}"

echo "==> Wine prefix: $WINEPREFIX"
echo "==> Bridge dir:  $BRIDGE"

echo
echo "==> Processes"
python3 <<'PY'
import os
found = False
for pid in os.listdir("/proc"):
    if not pid.isdigit():
        continue
    try:
        cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\x00", b" ").decode("utf-8", "replace")
        st = open(f"/proc/{pid}/stat").read().split()[2]
    except OSError:
        continue
    if "bash" in cmd:
        continue
    if any(x in cmd for x in ("terminal64", "MetaEditor", "mt5server")):
        print(f"  pid={pid} state={st}  {cmd[:110]}")
        found = True
if not found:
    print("  (none)")
PY

echo
echo "==> Hyprland windows"
if command -v hyprctl >/dev/null 2>&1; then
  hyprctl clients -j 2>/dev/null | python3 -c "
import sys, json
try:
    cs = json.load(sys.stdin)
except Exception:
    print('  (hyprctl unavailable)')
    raise SystemExit(0)
n = 0
for c in cs:
    if c.get('class') == 'terminal64.exe':
        n += 1
        ws = (c.get('workspace') or {}).get('id', '?')
        print(f\"  ws={ws}  {c.get('title')!r}  size={c.get('size')}\")
if not n:
    print('  (no terminal64.exe window — process may be invisible; run 07-restart-terminal.sh)')
" || echo "  (hyprctl failed)"
else
  echo "  (hyprctl not installed)"
fi

echo
echo "==> Bridge files"
if [[ -d "$BRIDGE" ]]; then
  now="$(date +%s)"
  # Liveness comes from heartbeat.txt only — same rule as FileBridgeClient.ensure_alive.
  # account.json mtime is shown for context but never decides fresh/stale: a leftover
  # snapshot from a detached EA keeps its mtime and would read as alive.
  max_age="${MT5_BRIDGE_MAX_AGE:-15}"
  if [[ ! -f "$BRIDGE/account.json" ]]; then
    warn "no account.json yet — attach Mt5ArchBridge EA to a chart"
  elif [[ ! -f "$BRIDGE/heartbeat.txt" ]]; then
    warn "no heartbeat.txt — bridge is down (EA detached or Algo Trading off); 'mt5-arch ping' fails closed"
  else
    hb_mtime="$(stat -c %Y "$BRIDGE/heartbeat.txt")"
    age=$((now - hb_mtime))
    acct_mtime="$(stat -c %Y "$BRIDGE/account.json")"
    echo "  heartbeat.txt age: ${age}s (MT5_BRIDGE_MAX_AGE=${max_age}s)"
    echo "  account.json age:  $((now - acct_mtime))s"
    python3 -c "
import json
from pathlib import Path
p = Path(r'''$BRIDGE/account.json''')
d = json.loads(p.read_text())
print(f\"  login={d.get('login')} server={d.get('server')!r} balance={d.get('balance')} equity={d.get('equity')} currency={d.get('currency')!r}\")
print(f\"  trade_allowed={d.get('trade_allowed')} algo_allowed={d.get('algo_allowed')}\")
" 2>/dev/null || cat "$BRIDGE/account.json"
    if awk -v a="$age" -v m="$max_age" 'BEGIN { exit !(a > m) }'; then
      warn "bridge is stale (>${max_age}s) — 'mt5-arch ping' fails closed. Is Mt5ArchBridge still on a chart?"
    else
      info "bridge is fresh"
    fi
  fi
  n_candles="$(find "$BRIDGE" -maxdepth 1 -name 'candles_*.json' 2>/dev/null | wc -l)"
  echo "  candle files: $n_candles"
else
  warn "bridge directory missing"
fi

echo
echo "==> Window / ghost check"
if command -v uv >/dev/null 2>&1; then
  (cd "$REPO_ROOT" && uv run python -m mt5_arch.window_ops --dry-run --json 2>/dev/null) \
    | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print('  (parse failed)'); sys.exit(0)
print(f\"  process_running={d.get('process_running')} ghost={d.get('ghost_process')} status={d.get('status')}\")
mw = d.get('main_window')
if mw:
    print(f\"  main={mw.get('title')!r} size={mw.get('size')}\")
else:
    print('  main=(none)')
pl = d.get('placement') or {}
print(f\"  plan={pl.get('width')}x{pl.get('height')} mon={ (d.get('monitor') or {}).get('name') }\")
if d.get('ghost_process'):
    print('  RECOVER: ./scripts/10-recover-terminal.sh --fullscreen')
" || warn "window plan failed (hyprctl?)"
else
  echo "  (uv not ready)"
fi

echo
echo "==> Clipboard bridge (Wayland → X11 for Wine paste)"
if [[ -x "$SCRIPT_DIR/11-clipboard-bridge.sh" ]]; then
  "$SCRIPT_DIR/11-clipboard-bridge.sh" status 2>/dev/null || warn "bridge not running — ./scripts/11-clipboard-bridge.sh start"
else
  echo "  (no 11-clipboard-bridge.sh)"
fi

echo
echo "==> CLI (optional)"
if [[ -x "$REPO_ROOT/.venv/bin/mt5-arch" ]] || command -v uv >/dev/null 2>&1; then
  (cd "$REPO_ROOT" && uv run mt5-arch ping --json 2>/dev/null) || warn "mt5-arch ping failed (stale bridge or EA stopped)"
else
  echo "  (uv/venv not ready)"
fi
