"""Official MCP token helper never prints the secret and does not order."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "23-set-official-mcp-token.sh"


def test_script_23_exists_and_never_echoes_token() -> None:
    assert SCRIPT.is_file()
    assert SCRIPT.stat().st_mode & 0o111
    text = SCRIPT.read_text(encoding="utf-8")
    assert "MT5_MCP_TOKEN" in text
    assert "Never prints the token" in text
    assert "OrderSend" not in text
    assert "does not place orders" in text.lower() or "Does not place orders" in text
    # Silent prompt; no echo/print of the value.
    assert "read -rs MT5_NEW_TOKEN" in text
    assert re.search(r'echo\s+["\']?\$\{?MT5_MCP_TOKEN', text) is None
    assert re.search(r'echo\s+["\']?\$\{?MT5_NEW_TOKEN', text) is None
    assert "print(token)" not in text
    assert 'print(f"{token' not in text
    assert "print(token," not in text
    assert "printf '%s' \"$MT5_MCP_TOKEN\"" not in text
    assert "printf '%s' \"$MT5_NEW_TOKEN\"" not in text
