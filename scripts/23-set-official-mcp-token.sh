#!/usr/bin/env bash
# Rotate MT5_MCP_TOKEN (official MT5 MCP, Route B) from a freshly Generate'd key.
#
# Why this exists: the dialog API key (~42 chars) is only shown inside the terminal
# that OWNS the 22346 listener; it is never written to disk, and the 168-char
# assistant.ini ApiKey 401s as a Bearer. With several terminals running, whichever
# bound 22346 first owns the endpoint — a key Generate'd in any other terminal
# will always 401. This script prints the current owner, takes the key via a
# SILENT prompt, verifies the handshake BEFORE writing anything, then updates:
#   - repo .env (gitignored)
#   - ~/.bashrc export line (created if missing)
#   - ~/.config/environment.d/mt5-mcp.conf (0600; session env for GUI-launched apps)
#   - ~/.cursor/mcp.json header, as a literal Bearer token, only with --cursor-literal
# and imports the variable into the running systemd user manager.
#
# Never prints the token. Does not place orders.
# Usage: ./scripts/23-set-official-mcp-token.sh [--cursor-literal]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
export REPO_ROOT  # the python step below needs it, regardless of caller cwd

URL="${MT5_MCP_URL:-http://127.0.0.1:22346/mcp}"
CURSOR_LITERAL=0
if [ "${1:-}" = "--cursor-literal" ]; then
  CURSOR_LITERAL=1
elif [ -n "${1:-}" ]; then
  die "usage: $0 [--cursor-literal]"
fi

# --- Who owns 22346 right now? The key MUST come from that terminal. ----------
OWNER=""
for pid in $(ss -ltnp 2>/dev/null | grep ':22346' | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u); do
  if [ -r "/proc/$pid/environ" ]; then
    pfx=$(tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null | sed -n 's/^WINEPREFIX=//p' | head -1)
    if [ -n "$pfx" ]; then
      OWNER="$(basename "$pfx")"
      break
    fi
  fi
done
if [ -z "$OWNER" ]; then
  if ! ss -ltn 2>/dev/null | grep -q ':22346'; then
    die "no listener on 22346 — start the terminal and enable Tools → Options → MCP first"
  fi
  warn "could not identify the terminal owning 22346 (owner prefix unknown)"
fi

# --- Silent prompt -------------------------------------------------------------
printf 'Port 22346 owner: %s\n' "${OWNER:-unknown — could not identify}"
printf 'Generate the API key in THAT terminal (Tools → Options → MCP → Generate).\n'
printf 'Tools → Options → MCP → Generate, then paste the API key here (input hidden): '
IFS= read -rs MT5_NEW_TOKEN
printf '\n'
[ -n "$MT5_NEW_TOKEN" ] || die "empty input — nothing changed"
export MT5_NEW_TOKEN MT5_MCP_CURSOR_LITERAL="$CURSOR_LITERAL" MT5_MCP_URL="$URL"

python3 - <<'PY'
import json
import os
import re
import stat
import urllib.error
import urllib.request
from pathlib import Path

url = os.environ["MT5_MCP_URL"]
token = os.environ["MT5_NEW_TOKEN"].strip()
if any(c.isspace() for c in token):
    raise SystemExit(
        f"error: whitespace in key (len={len(token)}) — re-copy without trailing spaces/newlines"
    )
if len(token) >= 120:
    raise SystemExit(
        f"error: key len={len(token)} — that is the assistant.ini ApiKey blob, "
        "not the dialog key (~42 chars). Copy a freshly Generate'd dialog key."
    )
if not 30 <= len(token) <= 80:
    raise SystemExit(
        f"error: unexpected key len={len(token)} (dialog keys are ~42 chars); refusing to save"
    )

# --- Verify the handshake BEFORE touching any file -----------------------------
payload = json.dumps({
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "mt5-arch-set-token", "version": "0.1.0"},
    },
}).encode()
req = urllib.request.Request(url, data=payload, method="POST", headers={
    "Authorization": f"Bearer {token}",
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "MCP-Protocol-Version": "2025-03-26",
})
try:
    with urllib.request.urlopen(req, timeout=8) as resp:
        status, body = resp.status, resp.read().decode("utf-8", "replace")
except urllib.error.HTTPError as e:
    status, body = e.code, e.read().decode("utf-8", "replace")
except OSError as e:
    raise SystemExit(f"error: cannot reach {url}: {e}")

if status == 401:
    raise SystemExit(
        "error: HTTP 401 — token rejected. Re-check:\n"
        "  1) the key was Generate'd in the terminal that OWNS 22346 (printed above);\n"
        "  2) it is a FRESH Generate (older dialog keys are invalidated);\n"
        "  3) nothing extra got copied with it. Nothing was written."
    )
if status != 200:
    raise SystemExit(f"error: HTTP {status} from {url}; nothing was written")

info = {}
for ln in body.splitlines():
    chunk = ln[5:].strip() if ln.startswith("data:") else ln.strip()
    if chunk.startswith("{"):
        try:
            info = json.loads(chunk).get("result") or {}
            break
        except json.JSONDecodeError:
            pass
srv = info.get("serverInfo") or {}
print(f"handshake OK: HTTP 200 server={srv.get('name')} version={srv.get('version')}")

# --- Rotate everywhere ----------------------------------------------------------
repo = Path(os.environ.get("REPO_ROOT") or Path.cwd())
envf = repo / ".env"
if envf.exists():
    s = envf.read_text()
    s2, n = re.subn(r"(?m)^MT5_MCP_TOKEN=.*$", f"MT5_MCP_TOKEN={token}", s)
    if n == 0:
        s2 = (s.rstrip("\n") + f"\nMT5_MCP_TOKEN={token}\n") if s.strip() else f"MT5_MCP_TOKEN={token}\n"
    envf.write_text(s2)
    print(".env updated")

bashrc = Path.home() / ".bashrc"
line = f"export MT5_MCP_TOKEN={token}"
if bashrc.exists():
    s = bashrc.read_text()
    s2, n = re.subn(r"(?m)^export MT5_MCP_TOKEN=.*$", line, s)
    if n == 0:
        s2 = (s.rstrip("\n") + f"\n# MT5 MCP: referenced as ${{MT5_MCP_TOKEN}} by mt5-official in ~/.cursor/mcp.json\n{line}\n")
    bashrc.write_text(s2)
    print("~/.bashrc export updated")

envd = Path.home() / ".config" / "environment.d" / "mt5-mcp.conf"
envd.parent.mkdir(parents=True, exist_ok=True)
envd.write_text(f"MT5_MCP_TOKEN={token}\n")
envd.chmod(stat.S_IRUSR | stat.S_IWUSR)
print(f"{envd} written (0600) — picked up by GUI apps after next login")

if os.environ.get("MT5_MCP_CURSOR_LITERAL") == "1":
    mcp = Path.home() / ".cursor" / "mcp.json"
    cfg = json.loads(mcp.read_text()) if mcp.exists() else {"mcpServers": {}}
    srvs = cfg.setdefault("mcpServers", {})
    if "mt5-official" not in srvs:
        raise SystemExit(f"error: no 'mt5-official' server in {mcp}; configure it first")
    srvs["mt5-official"].setdefault("headers", {})["Authorization"] = f"Bearer {token}"
    mcp.write_text(json.dumps(cfg, indent=2) + "\n")
    print("~/.cursor/mcp.json Authorization header set (literal token)")

print("done — restart Cursor (fully quit first) so it inherits the new value")
PY

# Push the new value into the running user manager (apps started by the session
# after this inherit it; environment.d covers future logins).
export MT5_MCP_TOKEN="$MT5_NEW_TOKEN"
systemctl --user import-environment MT5_MCP_TOKEN 2>/dev/null \
  && info "imported MT5_MCP_TOKEN into systemd user environment" \
  || warn "systemctl --user import-environment failed (non-systemd session?)"
unset MT5_NEW_TOKEN
