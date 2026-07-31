"""Pytest configuration — sys.path for local test helpers."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `from bridge_fixtures import ...` when tests/ is not a package
_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))
