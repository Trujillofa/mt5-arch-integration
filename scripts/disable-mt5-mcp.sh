#!/usr/bin/env bash
# Disable MetaQuotes MCP endpoints in every broker Wine prefix.
# All brands ship Enable=1 on 127.0.0.1:22346 — only one terminal can bind it;
# the rest log bind errors. We use the file bridge, not MCP.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

python3 - <<'PY'
from pathlib import Path
import re

roots = [
    Path.home() / ".mt5-vantage",
    Path.home() / ".mt5-fpmarkets",
    Path.home() / ".mt5-exness",
    Path.home() / ".mt5-wsf",
    Path.home() / ".mt5",
]
flipped = 0
for root in roots:
    if not root.is_dir():
        continue
    for ini in root.glob("drive_c/Program Files/*/Config/assistant.ini"):
        raw = ini.read_bytes()
        bom = raw.startswith(b"\xff\xfe")
        if bom or (len(raw) > 3 and raw[1] == 0 and raw[3] == 0):
            text = (raw[2:] if bom else raw).decode("utf-16-le")
            enc = "utf-16-le"
        else:
            text = raw.decode("utf-8", errors="replace")
            enc = "utf-8"
        text_n = text.replace("\r\n", "\n").replace("\r", "\n")
        new_n, n = re.subn(r"(?m)^(Enable=)1$", r"\g<1>0", text_n)
        if n == 0:
            continue
        out = new_n.replace("\n", "\r\n").encode(enc)
        if bom:
            out = b"\xff\xfe" + out
        ini.write_bytes(out)
        flipped += n
        print(f"{ini}: Enable=1 → 0 ({n})")
if flipped == 0:
    print("No Enable=1 left to flip (already disabled or no assistant.ini).")
else:
    print(f"Done ({flipped} flag(s)). Restart each terminal for the bind to drop.")
PY
