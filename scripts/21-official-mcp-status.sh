#!/usr/bin/env bash
# Read-only status for official MT5 MCP (Route B) and the AI Assistant (Route A).
# Never prints ApiKey / MT5_MCP_TOKEN / MT5_PASSWORD. Does not place orders.
# Prefix-scoped: export WINEPREFIX=~/.mt5-vantage first.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_dotenv
export_wine_env

info "WINEPREFIX=$WINEPREFIX"

python3 - <<'PY'
from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path

prefix = Path(os.environ["WINEPREFIX"]).expanduser()
cfg = None
data = {}
for cand in prefix.glob("drive_c/Program Files/*/Config/assistant.ini"):
    cfg = cand
    break
if cfg is None:
    print("assistant.ini: missing")
else:
    raw = cfg.read_bytes()
    if raw.startswith(b"\xff\xfe") or (len(raw) > 2 and raw[1] == 0):
        text = raw.decode("utf-16-le").lstrip("\ufeff")
    else:
        text = raw.decode("utf-8", "replace")
    sec, data = None, {}
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            sec = s[1:-1]
            data[sec] = {}
        elif "=" in s and sec:
            k, v = s.split("=", 1)
            data[sec][k] = v
    for name in ("MCP.MetaTrader", "MCP.MetaEditor"):
        row = data.get(name) or {}
        key = row.get("ApiKey") or ""
        print(
            f"{name}: Enable={row.get('Enable', '?')} "
            f"Endpoint={row.get('Endpoint', '?')} "
            f"ApiKey=<redacted len={len(key)}>"
        )

print("listeners:")
found = False
for host, port in (("0.0.0.0", 22345), ("127.0.0.1", 22345), ("0.0.0.0", 22346), ("127.0.0.1", 22346)):
    pass
# parse ss
try:
    out = subprocess.check_output(["ss", "-ltn"], text=True)
except OSError:
    out = ""
for line in out.splitlines():
    if ":22345" in line or ":22346" in line:
        print(" ", line.strip())
        found = True
        if ":22346" in line and "127.0.0.1" not in line.split()[3] if False else True:
            pass
if not found:
    print("  (none on 22345/22346)")

# warn non-loopback 22346
for line in out.splitlines():
    if ":22346" not in line:
        continue
    addr = line.split()[3] if len(line.split()) > 3 else ""
    if addr and not addr.startswith("127.0.0.1"):
        print(f"warning: MCP is not loopback-only ({addr}); official MCP can trade")

token = os.environ.get("MT5_MCP_TOKEN") or ""
token_src = "MT5_MCP_TOKEN"
if not token:
    mt = data.get("MCP.MetaTrader") or {}
    ini_key = str(mt.get("ApiKey") or "")
    # Dialog API Key is short (~40). The 168-char assistant.ini value 401s.
    if ini_key and len(ini_key) <= 80:
        token = ini_key
        token_src = "assistant.ini ApiKey"
    elif ini_key:
        print(
            f"handshake: skipped assistant.ini ApiKey (len={len(ini_key)}; "
            "that is not the Tools → Options → MCP API Key). "
            "export MT5_MCP_TOKEN from the dialog."
        )
if not token:
    if token_src == "MT5_MCP_TOKEN":
        print("handshake: skipped (export MT5_MCP_TOKEN from the MCP dialog API Key)")
else:
    print(f"handshake: using {token_src} (len={len(token)})")
    import urllib.error
    import urllib.request

    def _parse(raw: str) -> dict:
        raw = (raw or "").strip()
        if not raw:
            return {}
        if raw[:1] in "{[":
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
        parsed = {}
        for ln in raw.splitlines():
            if ln.startswith("data:"):
                chunk = ln[5:].strip()
                if chunk and chunk != "[DONE]":
                    try:
                        parsed = json.loads(chunk)
                    except json.JSONDecodeError:
                        pass
        return parsed

    def _post(url: str, payload: dict, session: str | None = None) -> tuple[int, dict, dict, str]:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-03-26",
        }
        if session:
            headers["Mcp-Session-Id"] = session
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw = resp.read().decode("utf-8", "replace")
                hdrs = dict(resp.headers.items())
                status = resp.status
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            hdrs = dict(e.headers.items()) if e.headers else {}
            status = e.code
        return status, hdrs, _parse(raw), raw

    urls = []
    for line in out.splitlines():
        if ":22346" not in line:
            continue
        addr = line.split()[3]
        host, _, port = addr.rpartition(":")
        urls.append(f"http://{host.strip('[]')}:{port}/mcp")
    urls.append("http://127.0.0.1:22346/mcp")
    seen: set[str] = set()
    ok = False
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        try:
            status, hdrs, parsed, raw = _post(
                url,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "mt5-arch-official-mcp-status",
                            "version": "0.1.0",
                        },
                    },
                },
            )
        except Exception as e:
            print(f"handshake {url}: {type(e).__name__}")
            continue
        www = hdrs.get("WWW-Authenticate")
        print(f"handshake {url}: HTTP {status}" + (f" www-auth={www}" if www else ""))
        if status != 200:
            continue
        ok = True
        result = parsed.get("result") or {}
        print(f"  serverInfo={result.get('serverInfo')} protocol={result.get('protocolVersion')}")
        caps = result.get("capabilities") or {}
        print(f"  capabilities={list(caps) if isinstance(caps, dict) else caps}")
        session = hdrs.get("Mcp-Session-Id") or hdrs.get("mcp-session-id")
        if session:
            print(f"  session=<redacted len={len(session)}>")
        _post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
        for method, rid in (("tools/list", 2), ("resources/list", 3), ("prompts/list", 4)):
            st, _h, pr, raw2 = _post(
                url,
                {"jsonrpc": "2.0", "id": rid, "method": method, "params": {}},
                session,
            )
            key = method.split("/")[0]
            items = (pr.get("result") or {}).get(key) or []
            names = [x.get("name") or x.get("uri") for x in items if isinstance(x, dict)]
            err = pr.get("error")
            print(f"  {method}: HTTP {st} n={len(items)} names={names}" + (f" error={err}" if err else ""))
            if not items and not err:
                snippet = (raw2 or "").replace(token, "<redacted>")[:180]
                if snippet:
                    print(f"  {method} body={snippet!r}")
        break
    if not ok:
        print("handshake: failed — export MT5_MCP_TOKEN from the MCP dialog API Key")

PY

if command -v uv >/dev/null 2>&1; then
  info "file-bridge ping (route C / CLI)"
  # Always run against the repo, not the caller's cwd (uv looks for pyproject there).
  if uv run --directory "$REPO_ROOT" mt5-arch ping --json >/tmp/mt5-official-mcp-ping.json; then
    python3 - <<'PY'
import json
from pathlib import Path
d = json.loads(Path("/tmp/mt5-official-mcp-ping.json").read_text())
build = int(d.get("build") or 0)
print(f"connected={d.get('connected')} build={build} name={d.get('name')}")
if build < 6060:
    print(f"warning: official AI/MCP needs build >= 6060 (got {build})")
else:
    print("build OK for routes A/B (>= 6060)")
PY
  else
    warn "mt5-arch ping failed (bridge down or uv env). See docs/TROUBLESHOOTING.md"
  fi
  rm -f /tmp/mt5-official-mcp-ping.json
fi
