"""Offline tests for the read-only Prometheus textfile exporter."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from bridge_fixtures import write_bridge_fixture

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mt5_metrics_exporter import (  # noqa: E402
    collect,
    compute_exposure,
    main,
    parse_control,
    render,
)


def test_fixture_renders_bridge_metrics(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    text = render(collect(bridge, now=time.time()))

    assert "mt5_bridge_dir_present 1" in text
    assert "mt5_feed_stale 0" in text
    assert "mt5_account_equity 4980.5" in text
    assert "mt5_account_margin 120" in text
    assert "mt5_positions_open 1" in text
    assert 'mt5_position_volume{symbol="EURUSD",side="buy"} 0.1' in text
    # 0.10 lots x 100000 contract x 1.09 current price
    assert 'mt5_exposure_quote{symbol="EURUSD"} 10900' in text
    assert "mt5_exposure_quote_total 10900" in text
    assert "mt5_positions_unpriced 0" in text
    assert "mt5_control_present 0" in text
    assert 'mt5_snapshot_ok{file="account.json"} 1' in text


def test_help_and_type_lines_are_unique_per_family(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    text = render(collect(bridge))
    helps = [ln.split()[2] for ln in text.splitlines() if ln.startswith("# HELP ")]
    types = [ln.split()[2] for ln in text.splitlines() if ln.startswith("# TYPE ")]
    assert len(helps) == len(set(helps))
    assert len(types) == len(set(types))


def test_stale_heartbeat_is_a_metric_not_an_error(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge, age_seconds=120.0)
    state = collect(bridge, max_age=15.0)
    text = render(state)
    assert "mt5_feed_stale 1" in text
    assert state["heartbeat_age"] is not None
    assert state["heartbeat_age"] >= 120.0


def test_missing_bridge_still_renders_stale(tmp_path: Path) -> None:
    text = render(collect(tmp_path / "nope"))
    assert "mt5_bridge_dir_present 0" in text
    assert "mt5_feed_stale 1" in text
    assert "mt5_positions_open" not in text  # absence is not a flat book


def test_control_inhibited_and_age(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    (bridge / "control.json").write_text(
        json.dumps(
            {
                "version": 1,
                "account_id": "demo",
                "inhibited": True,
                "operator": "coordinator",
                "reason": "daily loss",
                "updated_at": "2026-11-15T10:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    text = render(collect(bridge))
    assert "mt5_control_present 1" in text
    assert "mt5_control_parse_ok 1" in text
    assert "mt5_control_inhibited 1" in text
    assert "mt5_control_age_seconds" in text


def test_malformed_control_fails_closed(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    (bridge / "control.json").write_text("{oops", encoding="utf-8")
    state = collect(bridge)
    assert state["control_present"] is True
    assert state["control_parse_ok"] is False
    assert state["control"] == {
        "valid": False,
        "inhibited": True,
        "reason": "control.json malformed",
    }
    text = render(state)
    assert "mt5_control_parse_ok 0" in text
    assert "mt5_control_inhibited 1" in text


def test_parse_control_boolean_semantics() -> None:
    assert parse_control({"inhibited": False})["inhibited"] is False
    assert parse_control({"inhibited": "false"})["inhibited"] is True
    assert parse_control(None)["valid"] is False


def test_unpriced_position_is_counted_not_guessed() -> None:
    exposure, unpriced = compute_exposure(
        [{"symbol": "XAUUSD", "volume": 0.1, "price_current": 4000.0}],
        [{"symbol": "EURUSD", "contract_size": 100000}],
    )
    assert exposure == {}
    assert unpriced == 1


def test_cli_writes_atomically(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    out = tmp_path / "mt5.prom"
    assert main(["--bridge-dir", str(bridge), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "mt5_feed_stale 0" in text
    assert not (tmp_path / "mt5.prom.tmp").exists()
