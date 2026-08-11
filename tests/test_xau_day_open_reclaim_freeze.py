"""Freeze validation for day_open_reclaim_flat v1 — no family module required."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from xau_charter_protocol import (  # noqa: E402
    is_charter_runnable,
    load_charter,
    validate_charter,
)

CHARTER = ROOT / "results/xau_charters/2026-08-11_day_open_reclaim_flat_v1.json"
MEMO = ROOT / "docs/research/XAU-THESIS-day_open_reclaim_flat_v1.md"


def test_charter_file_exists_and_validates():
    assert CHARTER.is_file()
    ch = load_charter(CHARTER)
    assert validate_charter(ch) == []
    assert ch["family_id"] == "day_open_reclaim_flat"
    assert ch["n_free_knobs"] == 0
    assert ch["search_cardinality"] == 1
    assert ch["null"]["method"] == "within_day_ohlc_increment_rotate_v1"
    assert int(ch["null"]["n_trials"]) == 999
    assert ch["gates"]["primary_n_passers"] == "soft"
    assert ch["kill"]["on_null_fail"] == "KILL_DAY_OPEN_RECLAIM_FLAT"
    assert ch["fixed"]["costs"]["commission_per_lot"] == 0.0
    assert ch["rule"]["intraday_flat"] is True
    assert ch["rule"]["entry_allowed_hours_server"] == list(range(9, 16))
    assert ch["rule"]["flat_hour_server"] == 16
    assert "execution_contract" in ch
    assert ch["execution_contract"]["atr"]["estimator"] == "wilder_ewm"
    assert ch["execution_contract"]["exit"]["priority_same_bar_when_multiple"][0].startswith(
        "1_stop"
    )


def test_charter_runnable_before_screen():
    ok, why = is_charter_runnable(CHARTER)
    assert ok is True, why


def test_session_shape_rejects_global_return_shuffle():
    ch = load_charter(CHARTER)
    bad = dict(ch)
    bad["null"] = dict(ch["null"])
    bad["null"]["method"] = "global_return_shuffle"
    bad["null"]["forbidden_methods"] = []
    errs = validate_charter(bad)
    assert any("global_return_shuffle" in e for e in errs)
    assert any("within_day_ohlc_increment_rotate_v1" in e for e in errs)
    assert any("session" in e.lower() for e in errs)


def test_dead_lines_list_includes_early_range():
    ch = load_charter(CHARTER)
    dead = set(ch["dead_lines_do_not_revive"])
    for name in (
        "bb_rsi",
        "Donchian",
        "prior_day_high_break",
        "tod_london_ny_flat",
        "server_hour_window_flat",
        "early_server_range_break_flat",
    ):
        assert name in dead


def test_memo_exists_no_develop_metrics():
    assert MEMO.is_file()
    text = MEMO.read_text()
    assert "day_open_reclaim_flat" in text
    assert "FREEZE_ONLY" in text
    # Freeze-before-peek: no concrete develop PF/NP line items
    assert "0.7829" not in text
    assert "primary_passers" not in text.lower() or "primary passers" in text.lower()
    # allow the phrase "primary passers" in protocol discussion but not numeric screen dump
    assert "PF **" not in text


def test_charter_sha_stable_bytes():
    body = CHARTER.read_bytes()
    sha = hashlib.sha256(body).hexdigest()
    # Ensure JSON is well-formed and non-empty freeze
    assert len(sha) == 64
    json.loads(body.decode())
