"""Offline tests for FileBridgeClient.deals() — request-gated deal dump."""

from __future__ import annotations

import csv
import threading
import time
from pathlib import Path

import pytest
from bridge_fixtures import (
    DEAL_CSV_HEADER,
    default_deals_csv,
    default_dump_deals_done,
    write_bridge_fixture,
    write_deal_dump_fixture,
)

from mt5_arch.file_bridge import FileBridgeClient, FileBridgeError


def _client(bridge: Path, *, max_age: float = 30.0) -> FileBridgeClient:
    return FileBridgeClient(bridge, max_age_seconds=max_age)


def test_deals_happy_path_typed_rows(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_deal_dump_fixture(bridge)
    deals = _client(bridge).deals()
    assert len(deals) == 2
    first = deals[0]
    assert first.time == "2026.08.20 10:00:00"
    assert first.deal_id == 1001
    assert first.order_id == 2001
    assert first.position_id == 3001
    assert first.symbol == "EURUSD"
    assert first.type == "buy"
    assert first.entry == "in"
    assert first.volume == pytest.approx(0.1)
    assert first.price == pytest.approx(1.085)
    assert first.profit == pytest.approx(0.0)
    assert first.swap == pytest.approx(0.0)
    assert first.commission == pytest.approx(-0.70)
    assert first.fee == pytest.approx(0.0)
    assert first.reason == 0
    assert first.magic == 12345
    assert first.comment == "scale;in"
    assert deals[1].deal_id == 1002
    assert deals[1].type == "sell"
    assert deals[1].entry == "out"
    assert deals[1].profit == pytest.approx(10.0)


def test_deal_time_is_trade_server_not_utc(tmp_path: Path) -> None:
    """DEAL_TIME is TimeToString(TIME_DATE|TIME_SECONDS), not UTC."""
    bridge = tmp_path / "mt5_arch"
    write_deal_dump_fixture(bridge)
    deal = _client(bridge).deals()[0]
    assert deal.time == "2026.08.20 10:00:00"
    assert "T" not in deal.time
    assert "+" not in deal.time
    assert not deal.time.endswith("Z")
    assert "UTC" not in deal.time.upper()


def test_comment_with_sanitised_comma_is_one_field(tmp_path: Path) -> None:
    """EA replaces ,→; in comment only — csv reader, not str.split(',')."""
    bridge = tmp_path / "mt5_arch"
    write_deal_dump_fixture(bridge)
    assert _client(bridge).deals()[0].comment == "scale;in"


def test_missing_csv_is_file_bridge_error(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_deal_dump_fixture(bridge, include_csv=False)
    with pytest.raises(FileBridgeError, match="deals_export.csv"):
        _client(bridge).deals()


def test_missing_done_is_file_bridge_error_even_with_fresh_heartbeat(tmp_path: Path) -> None:
    """Heartbeat is written BEFORE DumpDealsIfRequested — it cannot gate CSV completeness."""
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    write_deal_dump_fixture(bridge, include_done=False)
    client = _client(bridge, max_age=30.0)
    client.ping()  # heartbeat is fresh
    with pytest.raises(FileBridgeError, match="dump_deals.done"):
        client.deals()


def test_deals_ignores_stale_heartbeat(tmp_path: Path) -> None:
    """A completed dump is readable even when snapshot liveness would fail."""
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge, age_seconds=120.0)
    write_deal_dump_fixture(bridge)
    client = _client(bridge, max_age=10.0)
    with pytest.raises(FileBridgeError, match="stale"):
        client.ping()
    deals = client.deals()
    assert len(deals) == 2


def test_torn_truncated_csv_is_file_bridge_error(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    torn = (
        DEAL_CSV_HEADER
        + "\n2026.08.20 10:00:00,1001,2001,3001,EURUSD,buy,in,0.1000,1.085"
    )
    write_deal_dump_fixture(bridge, csv_text=torn, done_body=default_dump_deals_done(rows=1))
    with pytest.raises(FileBridgeError, match="deals_export"):
        _client(bridge).deals()


def test_wrong_header_is_file_bridge_error(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    csv_text = default_deals_csv(n_rows=1).replace("deal_id", "ticket", 1)
    write_deal_dump_fixture(bridge, csv_text=csv_text, n_rows=1)
    with pytest.raises(FileBridgeError, match="header"):
        _client(bridge).deals()


def test_bad_numeric_field_is_file_bridge_error(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    csv_text = default_deals_csv(n_rows=1).replace("0.1000", "not-a-lot", 1)
    write_deal_dump_fixture(bridge, csv_text=csv_text, n_rows=1)
    with pytest.raises(FileBridgeError, match="bad deal 0"):
        _client(bridge).deals()


def test_empty_dump_rows_zero(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_deal_dump_fixture(
        bridge,
        csv_text=DEAL_CSV_HEADER + "\n",
        n_rows=0,
    )
    assert _client(bridge).deals() == []


def test_torn_done_is_file_bridge_error(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_deal_dump_fixture(bridge, done_body="rows=")
    with pytest.raises(FileBridgeError, match="dump_deals.done"):
        _client(bridge).deals()


def test_malformed_csv_raises_file_bridge_error_not_csv_error(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    # NUL in the file makes csv.reader raise csv.Error; must be wrapped, never leak.
    csv_text = DEAL_CSV_HEADER + "\n2026.08.20 10:00:00,1001\x00,2001,3001,EURUSD,buy,in,0.1,1.0,0,0,0,0,0,1,x\n"
    write_deal_dump_fixture(bridge, csv_text=csv_text, done_body=default_dump_deals_done(rows=1))
    with pytest.raises(FileBridgeError, match="deals_export") as exc:
        _client(bridge).deals()
    assert not isinstance(exc.value, csv.Error)
    assert exc.value.__cause__ is not None


def test_request_times_out_when_done_older_than_request(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    write_deal_dump_fixture(bridge, done_age_seconds=60.0)
    client = _client(bridge)
    with pytest.raises(FileBridgeError, match="dump_deals.done"):
        client.request_deals(timeout=0.25)
    assert (bridge / "dump_deals.request").exists()


def test_request_times_out_when_done_missing(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    client = _client(bridge)
    with pytest.raises(FileBridgeError, match="dump_deals.done"):
        client.request_deals(timeout=0.25)
    assert (bridge / "dump_deals.request").exists()


def test_request_waits_for_fresh_done(tmp_path: Path) -> None:
    """Simulated EA: write CSV, delete request, then rewrite .done (same order as v1.24)."""
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    write_deal_dump_fixture(bridge, n_rows=1, done_age_seconds=60.0)
    ready = threading.Event()

    def simulate_ea() -> None:
        req = bridge / "dump_deals.request"
        for _ in range(100):
            if req.exists():
                break
            time.sleep(0.02)
        else:
            return
        ready.set()
        write_deal_dump_fixture(bridge, n_rows=2, include_done=False)
        req.unlink()
        write_deal_dump_fixture(bridge, n_rows=2)

    thread = threading.Thread(target=simulate_ea, daemon=True)
    thread.start()
    deals = _client(bridge).request_deals(timeout=3.0)
    thread.join(timeout=3.0)
    assert ready.is_set()
    assert len(deals) == 2
    assert deals[1].deal_id == 1002
    assert not (bridge / "dump_deals.request").exists()


def test_non_ascii_comment_does_not_leak_unicode_error(tmp_path: Path) -> None:
    """EA writes FILE_ANSI: a cp1252 comment byte is not valid UTF-8.

    UnicodeDecodeError is a ValueError — it must never escape as a raw error, and one
    accented byte must not cost the whole dump.
    """
    bridge = tmp_path / "mt5_arch"
    write_deal_dump_fixture(bridge, n_rows=1)
    csv_path = bridge / "deals_export.csv"
    raw = csv_path.read_text(encoding="utf-8").rstrip("\n")
    csv_path.write_bytes(raw.encode("utf-8") + "caf\xe9 fill".encode("cp1252") + b"\n")
    deals = _client(bridge).deals()
    assert len(deals) == 1
    assert "caf" in deals[0].comment


def test_non_ascii_done_body_does_not_leak_unicode_error(tmp_path: Path) -> None:
    bridge = tmp_path / "mt5_arch"
    write_deal_dump_fixture(bridge, n_rows=1)
    done = bridge / "dump_deals.done"
    done.write_bytes(done.read_bytes() + "\xe9".encode("cp1252"))
    with pytest.raises(FileBridgeError, match="Corrupt dump_deals.done"):
        _client(bridge).deals()


def test_request_fails_fast_on_dead_bridge(tmp_path: Path) -> None:
    """A detached EA must report bridge-down now, not after the whole timeout."""
    bridge = tmp_path / "mt5_arch"
    write_bridge_fixture(bridge)
    (bridge / "heartbeat.txt").unlink()
    started = time.monotonic()
    with pytest.raises(FileBridgeError, match="heartbeat"):
        _client(bridge).request_deals(timeout=30.0)
    assert time.monotonic() - started < 5.0
    assert not (bridge / "dump_deals.request").exists()


def test_request_does_not_create_a_missing_bridge_dir(tmp_path: Path) -> None:
    """A typo'd MT5_BRIDGE_DIR must error, not conjure a tree."""
    bridge = tmp_path / "typo"
    with pytest.raises(FileBridgeError):
        _client(bridge).request_deals(timeout=0.25)
    assert not bridge.exists()
