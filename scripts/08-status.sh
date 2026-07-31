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
  if [[ -f "$BRIDGE/account.json" ]]; then
    mtime="$(stat -c %Y "$BRIDGE/account.json")"
    age=$((now - mtime))
    echo "  account.json age: ${age}s"
    python3 -c "
import json
from pathlib import Path
p = Path(r'''$BRIDGE/account.json''')
d = json.loads(p.read_text())
print(f\"  login={d.get('login')} server={d.get('server')!r} balance={d.get('balance')} equity={d.get('equity')} currency={d.get('currency')!r}\")
print(f\"  trade_allowed={d.get('trade_allowed')} algo_allowed={d.get('algo_allowed')}\")
" 2>/dev/null || cat "$BRIDGE/account.json"
    if [[ "$age" -gt 60 ]]; then
      warn "bridge looks stale (>60s). Is Mt5ArchBridge still on a chart?"
    else
      info "bridge is fresh"
    fi
  else
    warn "no account.json yet — attach Mt5ArchBridge EA to a chart"
  fi
  n_candles="$(find "$BRIDGE" -maxdepth 1 -name 'candles_*.json' 2>/dev/null | wc -l)"
  echo "  candle files: $n_candles"
else
  warn "bridge directory missing"
fi

echo
echo "==> Fullscreen plan (dry-run)"
if command -v uv >/dev/null 2>&1; then
  (cd "$REPO_ROOT" && uv run python -m mt5_arch.window_ops --dry-run 2>/dev/null) \
    || warn "window plan failed (hyprctl?)"
else
  echo "  (uv not ready)"
fi

echo
echo "==> CLI (optional)"
if [[ -x "$REPO_ROOT/.venv/bin/mt5-arch" ]] || command -v uv >/dev/null 2>&1; then
  (cd "$REPO_ROOT" && uv run mt5-arch ping --json 2>/dev/null) || warn "mt5-arch ping failed (stale bridge or EA stopped)"
else
  echo "  (uv/venv not ready)"
fi
