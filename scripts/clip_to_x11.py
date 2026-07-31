#!/usr/bin/env python3
"""Write text to X11 CLIPBOARD + PRIMARY as UTF8_STRING (what Wine expects)."""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    data = sys.stdin.buffer.read()
    if not data:
        return 0
    data = data.replace(b"\x00", b"")
    if not data:
        return 0
    # Skip image payloads that sometimes arrive as "text"
    if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff" or data[:4] == b"RIFF":
        return 0

    for sel in ("clipboard", "primary"):
        subprocess.run(
            ["xclip", "-selection", sel, "-t", "UTF8_STRING", "-i"],
            input=data,
            check=False,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
