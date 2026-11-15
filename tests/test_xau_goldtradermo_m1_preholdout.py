"""M1 rescore of pre-holdout GOLDTRADERMO calls.

Fixtures are tiny files. Nothing here reads the Telegram export or
asserts a profit factor from the real tape.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import xau_goldtradermo_m1_preholdout as pre  # noqa: E402

HOLDOUT = datetime(2026, 1, 1)


def _row(message_id: str, bar_time: str, *, status: str, reason: str) -> dict:
    return {
        "message_id": message_id,
        "source_file": "messages.html",
        "export_time": "2025-12-05T11:45:30-05:00",
        "export_offset": "-05:00",
        "bar_time_utc": bar_time,
        "side": "buy",
        "zone_lo": 100.0,
        "zone_hi": 101.0,
        "tps": [103.0, 105.0],
        "sl": 90.0,
        "nearest_tp": 103.0,
        "status": status,
        "reason": reason,
        "pnl": None,
    }


def test_rows_before_holdout_drop_the_sealed_window():
    rows = [
        _row("message1", "2025-12-05 16:45:30", status="unresolved", reason="same_bar_entry_and_exit"),
        _row("message2", "2026-01-02 00:00:00", status="scored", reason="tp"),
    ]
    kept = pre.rows_before_holdout(rows, HOLDOUT)
    assert [row["message_id"] for row in kept] == ["message1"]


def test_clock_agreement_accepts_offset_zero_and_rejects_a_shift():
    import pandas as pd

    minutes = pd.DataFrame(
        {
            "stamp": pd.to_datetime(["2025-12-05 16:45:00", "2025-12-05 16:46:00"]),
            "open": [100.0, 100.5],
            "high": [100.4, 103.2],
            "low": [99.5, 100.4],
            "close": [100.5, 103.0],
        }
    )
    m15 = pd.DataFrame(
        {
            "stamp": pd.to_datetime(["2025-12-05 16:45:00"]),
            "open": [100.0],
            "high": [103.2],
            "low": [99.5],
            "close": [103.0],
        }
    )
    agreement = pre.clock_agreement(minutes, m15, min_minutes=1)
    assert agreement["offset_hours"] == 0
    assert agreement["exact"] == 1

    shifted = minutes.copy()
    shifted["stamp"] = shifted["stamp"] + pd.to_timedelta(1, unit="h")
    with pytest.raises(ValueError, match="no M15 bar overlapped"):
        pre.clock_agreement(shifted, m15, min_minutes=1)


def test_transition_bucket_names_a_finer_path():
    assert (
        pre.transition_bucket("unresolved", "same_bar_entry_and_exit", "scored", "tp")
        == "unresolved_to_tp"
    )
    assert pre.transition_bucket("scored", "tp", "scored", "sl") == "m15_tp_to_sl"
    assert pre.transition_bucket("scored", "tp", "scored", "tp") == "m15_tp_unchanged"


def _write_fixture(tmp_path: Path) -> dict[str, Path]:
    m1_text = "\n".join(
        [
            "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<SPREAD>",
            "2025.12.05\t16:46:00\t100.5\t100.8\t100.2\t100.6\t10\t18",
            "2025.12.05\t16:47:00\t100.6\t103.2\t100.5\t103.0\t10\t18",
            "",
        ]
    )
    m1 = tmp_path / "m1.csv"
    m1.write_text(m1_text, encoding="utf-8")
    digest = hashlib.sha256(m1.read_bytes()).hexdigest()
    meta = tmp_path / "m1.csv.meta.json"
    meta.write_text(
        json.dumps(
            {
                "sha256": digest,
                "symbol": "XAUUSD",
                "period": "M1",
                "server_utc_offset_h": 3.0,
                "fetched_at_utc": "2026-09-24T20:44:48+00:00",
                "spread_note": "minimum tick spread within the bar",
            }
        ),
        encoding="utf-8",
    )
    m15 = tmp_path / "m15.csv"
    m15.write_text(
        "time,timeframe,symbol,open,high,low,close,tick_volume,spread\n"
        "2025-12-05T16:45:00+00:00,M15,XAUUSD,100.5,103.2,100.2,103.0,20,18\n",
        encoding="utf-8",
    )
    replay = tmp_path / "replay.json"
    replay.write_text(
        json.dumps(
            {
                "calls": [
                    _row(
                        "message1",
                        "2025-12-05 16:45:30",
                        status="unresolved",
                        reason="same_bar_entry_and_exit",
                    ),
                    _row("message9", "2026-01-02 01:00:00", status="scored", reason="tp"),
                ]
            }
        ),
        encoding="utf-8",
    )
    costs = tmp_path / "costs.json"
    costs.write_text(
        json.dumps({"point_size": 0.01, "slippage_points": 0.0, "commission_per_lot": 0.0}),
        encoding="utf-8",
    )
    holdout = tmp_path / "holdout.json"
    holdout.write_text(
        json.dumps({"holdout_start": "2026-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    return {
        "m1": m1,
        "m15": m15,
        "replay": replay,
        "costs": costs,
        "holdout": holdout,
        "out": tmp_path / "out.json",
        "note": tmp_path / "out.md",
    }


def test_entry_point_scores_only_the_preholdout_call(tmp_path: Path):
    paths = _write_fixture(tmp_path)
    report = pre.run(
        replay_path=paths["replay"],
        m1_path=paths["m1"],
        m15_path=paths["m15"],
        costs_path=paths["costs"],
        holdout_path=paths["holdout"],
        out_path=paths["out"],
        note_path=paths["note"],
        min_minutes=1,
        min_clock_bars=1,
    )
    assert report["outcome"] == "NO_NEW_FAMILY"
    assert report["family_id"] is None
    assert report["knobs"] is None
    assert "profit_factor" not in json.dumps(report)
    assert report["post_holdout_calls_left_unread"] == 1
    assert [row["message_id"] for row in report["calls"]] == ["message1"]
    scored = report["calls"][0]
    assert scored["m1_reason"] == "tp"
    assert scored["m1_entry_price"] == 100.5
    assert scored["m1_exit_price"] == 103.0
    assert report["clock"]["fetch_offset_applied"] is False
    note = paths["note"].read_text(encoding="utf-8")
    assert "NO_NEW_FAMILY" in note
    assert "message9" not in note
    assert "message1" in note


def test_entry_point_refuses_a_shifted_clock(tmp_path: Path):
    paths = _write_fixture(tmp_path)
    text = paths["m1"].read_text(encoding="utf-8").replace("16:46", "17:46").replace("16:47", "17:47")
    paths["m1"].write_text(text, encoding="utf-8")
    digest = hashlib.sha256(paths["m1"].read_bytes()).hexdigest()
    meta_path = Path(str(paths["m1"]) + ".meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["sha256"] = digest
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError, match="no M15 bar overlapped"):
        pre.run(
            replay_path=paths["replay"],
            m1_path=paths["m1"],
            m15_path=paths["m15"],
            costs_path=paths["costs"],
            holdout_path=paths["holdout"],
            out_path=paths["out"],
            note_path=paths["note"],
            min_minutes=1,
            min_clock_bars=1,
        )
