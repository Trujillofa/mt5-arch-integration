"""One-shot cost/size diagnostic is locked, not a search."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from us_index_session_v4_cost_size_once import (  # noqa: E402
    LOCK_PATH,
    SEARCH_ID,
    books_from_lock,
    load_lock,
)


def test_lock_is_diagnostic_not_search():
    lock = load_lock()
    assert lock["search_id"] == SEARCH_ID
    assert lock["kind"] == "diagnostic_replay"
    assert lock["not_a_search"] is True
    assert lock["promote"] is False
    assert lock["live_go"] is False
    assert lock["skipped"]["timescaledb"]
    assert lock["skipped"]["m1"]
    assert lock["skipped"]["us500"]
    books = books_from_lock(lock)
    assert [b[0] for b in books] == [
        "locked",
        "slip0",
        "lots2",
        "lots5",
        "slip0_lots5",
    ]
    assert books[0] == ("locked", 1.0, 10.0)
    assert json.loads(LOCK_PATH.read_text())["configs"][1]["family"] == "vol_regime_orb"
